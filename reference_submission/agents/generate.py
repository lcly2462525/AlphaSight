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
        _log(f"subject={subject or '(unresolved)'}; retrieving ...")
        res = self.retriever.search(topic, top_k=12,
                                    tickers=subject or None)
        _log(f"retrieved {len(res.evidence)} passages "
             f"({time.time() - t0:.1f}s); calling LLM ...")
        focus = (f"\n\n# SUBJECT COMPANY\nThis report is about: "
                 f"{', '.join(subject)}. Use ONLY evidence about "
                 f"{', '.join(subject)} for claims about it; cite a "
                 f"peer's filing ONLY when explicitly comparing and "
                 f"name the peer.") if subject else ""
        prompt = self._prompt.format(
            topic=topic,
            facts_block=res.facts or "(none)",
            evidence_block=res.evidence_block(),
        ) + focus
        draft = chat([{"role": "user", "content": prompt}],
                     config=self.llm, **self.params)
        if not isinstance(draft, str) or not draft.strip():
            raise RuntimeError("empty generation")
        if os.environ.get("ALPHASIGHT_GEN_NO_AUDIT") == "1":
            _log(f"done ({time.time() - t0:.1f}s, no audit)")
            return draft
        _log("self-audit ...")
        out = self._self_audit(topic, draft)
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

    def _self_audit(self, topic: str, draft: str) -> str:
        tickers = self.retriever.entity.resolve(topic)
        problems: list[str] = []
        for tk in tickers[:3]:
            tf = self.retriever.fact_store.lookup(tk)
            eps_truth = [e["actual"] for e in tf.earnings
                         if isinstance(e.get("actual"), (int, float))]
            for line in draft.splitlines():
                if not eps_truth or not _EPS_NEAR.search(line):
                    continue
                for n in parse_numbers(line):
                    if n.is_pct or abs(n.value) > 100:
                        continue
                    if all(contradicts(n.value, t) for t in eps_truth):
                        problems.append(
                            f'- QUOTE: "{n.raw}"  CONTEXT: {line.strip()[:120]}'
                            f'  FACT: {tk} reported EPS in '
                            f'{sorted(set(eps_truth))}')
                        break
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
