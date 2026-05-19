"""GenerateAgent: plan -> hybrid retrieve -> write -> numeric self-audit.

Self-audit is deterministic-first: pull verified EPS/revenue from the
FactStore, scan the draft for the same metric quoted with a clearly
contradictory magnitude, and run at most one corrective LLM pass.
"""

from __future__ import annotations

import os
import re

from llm import chat
from retrieval.numeric import contradicts, parse_numbers
from agents._util import load_prompt

_EPS_NEAR = re.compile(r"\beps\b", re.IGNORECASE)
_REV_NEAR = re.compile(r"\b(revenue|sales)\b", re.IGNORECASE)


class GenerateAgent:
    def __init__(self, retriever, llm_cfg, gen_params: dict) -> None:
        self.retriever = retriever
        self.llm = llm_cfg
        self.params = gen_params
        self._prompt = load_prompt("grounded_generate.md")

    def run(self, topic: str) -> str:
        import sys
        import time

        def _log(m: str) -> None:
            print(f"[gen] {m}", file=sys.stderr, flush=True)

        t0 = time.time()
        subject = self._subject(topic)
        if not subject:
            # No lockable subject -> do NOT fabricate on whole-corpus
            # evidence. Bail so Submission falls back to the baseline.
            _log("no subject resolved; deferring to baseline")
            raise RuntimeError("no subject company resolved")
        _log(f"subject={subject}; retrieving ...")
        res = self.retriever.search(topic, top_k=12, tickers=subject,
                                    require_subject=True)
        _log(f"retrieved {len(res.evidence)} passages "
             f"({time.time() - t0:.1f}s); calling LLM ...")
        subject_block = (
            f"This report's subject company is **{', '.join(subject)}**. "
            f"Make every claim about it using ONLY that company's own "
            f"FACTS/EVIDENCE; cite a peer's path ONLY inside an explicit, "
            f"labeled comparison and name the peer."
        )
        prompt = self._prompt.format(
            topic=topic,
            subject_block=subject_block,
            facts_block=res.facts or "(none)",
            evidence_block=res.evidence_block(),
        )
        draft = chat([{"role": "user", "content": prompt}],
                     config=self.llm, **self.params)
        if not isinstance(draft, str) or not draft.strip():
            raise RuntimeError("empty generation")
        if os.environ.get("ALPHASIGHT_GEN_NO_AUDIT") == "1":
            _log(f"done ({time.time() - t0:.1f}s, no audit)")
            return draft
        _log("self-audit ...")
        out = self._self_audit(subject, draft)
        _log(f"done ({time.time() - t0:.1f}s)")
        return out

    def _subject(self, topic: str) -> list[str]:
        """Lock the report's subject company.

        Open-ended topics ("which 2025 laggard wins in 2026") name no
        ticker, so entity.resolve returns []. Without a subject the
        retriever widened to the whole corpus and pulled peers' filings
        (an HD report grounded on Costco's 10-Q). So: resolve from text;
        if empty, have the LLM pick ONE ticker from the filing universe;
        validate it; only then scope retrieval to it.
        """
        named = self.retriever.entity.resolve(topic)
        if named:
            return named[:3]
        universe = self.retriever.subject_universe()
        if not universe:
            return []
        pick = (
            "Pick the SINGLE most relevant company for this research "
            "topic. Reply with ONLY its ticker, exactly as listed.\n\n"
            f"TICKERS: {', '.join(universe)}\n\nTOPIC: {topic}"
        )
        try:
            raw = chat([{"role": "user", "content": pick}],
                       config=self.llm,
                       **{**self.params, "max_tokens": 8,
                          "temperature": 0.0})
            tok = re.findall(r"[A-Z][A-Z.\-]{0,6}", (raw or "").upper())
            for t in tok:
                if t in universe:
                    return [t]
        except Exception:
            pass
        return []

    def _self_audit(self, subject: list[str], draft: str) -> str:
        # Reuse the review agent's tested per-field / period-aligned
        # numeric verification instead of the old "any number near
        # 'eps' contradicts all" heuristic. Audit the LOCKED subject
        # (not a re-resolve of the topic, which is empty for open-ended
        # topics and silently skipped the whole audit).
        from agents.review import _parse_period, _eps_problems

        fs = self.retriever.fact_store
        problems: list[str] = []
        for tk in subject[:3]:
            for line in draft.splitlines():
                ln = line.strip()
                if len(ln) < 8:
                    continue
                yr, q = _parse_period(ln)
                if _EPS_NEAR.search(ln):
                    row = fs.earnings_row(tk, yr, q)
                    if row:
                        for p in _eps_problems(ln, row):
                            problems.append(
                                f'- "{ln[:140]}" -> {tk} '
                                f'FY{row.get("year")}Q{row.get("quarter")}'
                                f': {p}')
                if _REV_NEAR.search(ln):
                    rows = fs.metric(tk, "revenue", year=yr, quarter=q)
                    truths = [r["value"] for r in rows]
                    nums = [n.value for n in parse_numbers(ln)
                            if not n.is_pct and abs(n.value) >= 1e6]
                    if truths and nums and not any(
                            not contradicts(n, t)
                            for n in nums for t in truths):
                        problems.append(
                            f'- "{ln[:140]}" -> {tk} revenue verified '
                            f'{[f"{t:.0f}" for t in truths[:3]]}')
        problems = problems[:6]
        if not problems:
            return draft
        fix = (
            "A deterministic check found numbers in the draft that "
            "contradict verified earnings facts. Rewrite the report "
            "correcting ONLY these figures to the stated facts; keep the "
            "stance, structure, length and all [SOURCE: ...] citations.\n\n"
            f"PROBLEMS:\n{chr(10).join(problems[:6])}\n\n"
            f'DRAFT:\n"""{draft}"""'
        )
        try:
            fixed = chat([{"role": "user", "content": fix}],
                         config=self.llm, **self.params)
            return fixed if isinstance(fixed, str) and fixed.strip() else draft
        except Exception:
            return draft
