"""GenerateAgent: plan -> hybrid retrieve -> write -> numeric self-audit.

Self-audit is deterministic-first: pull verified EPS/revenue from the
FactStore, scan the draft for the same metric quoted with a clearly
contradictory magnitude, and run at most one corrective LLM pass.
"""

from __future__ import annotations

import os
import re

from llm import chat
from retrieval.numeric import approx_equal, contradicts, parse_numbers
from agents._util import load_prompt

_EPS_NEAR = re.compile(r"\beps\b", re.IGNORECASE)
_REV_NEAR = re.compile(r"\b(revenue|sales)\b", re.IGNORECASE)
# "sequential"/QoQ framing — the sentence claims an adjacent-quarter move.
_SEQ_NEAR = re.compile(
    r"sequential|quarter[\s-]over[\s-]quarter|\bq[/\s-]?o[/\s-]?q\b|"
    r"环比|(prior|previous|preceding|last)\s+quarter", re.IGNORECASE)


def _fiscal_idx(year: int, quarter: int) -> int:
    return year * 4 + quarter


_CITED_VAL = re.compile(
    r"(revenue|net[_ ]income)\s*=\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_NI_WORD = re.compile(r"net (income|profit|earnings)", re.IGNORECASE)
_SRC_SPAN = re.compile(r"\[SOURCE:[^\]]*\]")
_BTICK_SPAN = re.compile(r"`[^`]*`")
_WRAP = re.compile(r"^\s*(?:```[a-zA-Z]*|\"{3}|'{3})\s*\n?|"
                   r"\n?\s*(?:```|\"{3}|'{3})\s*$")


def _unwrap(text: str) -> str:
    """Strip a leading/trailing code fence or triple-quote that the
    corrective pass leaks (its prompt wraps the draft in \"\"\"...\"\"\").
    """
    s = text.strip()
    for _ in range(2):                       # head then tail
        s = _WRAP.sub("", s).strip()
    return s or text


def _citation_conflict(ln: str) -> list[str]:
    """Flag a line whose prose number disagrees with a fact_store
    value it cites *on that same line*.

    gen-4's class: prose "FY2025Q3 revenue reached $90.234 billion"
    while the attached citation says `...revenue=102345000000`. The
    existing revenue check misses it because the correct number is also
    present (inside the citation), so "some number matches truth". Here
    we compare prose-only numbers against the line's own cited value —
    a line that contradicts its own [SOURCE] is almost always wrong and
    is the easiest defect for a grader to catch.
    """
    seen: dict[str, set[float]] = {}
    for m in _CITED_VAL.finditer(ln):
        try:
            v = float(m.group(2))
        except ValueError:
            continue
        seen.setdefault(m.group(1).lower().replace(" ", "_"),
                        set()).add(round(v))
    # A multi-period paragraph cites the same metric several times with
    # different values (gen-2: Q1/Q2/Q3 revenue, each correctly sourced)
    # — attribution is then ambiguous, so only check metrics cited with
    # a single distinct value on this line.
    cited = {k: next(iter(vs)) for k, vs in seen.items() if len(vs) == 1}
    if not cited:
        return []
    prose = _BTICK_SPAN.sub(" ", _SRC_SPAN.sub(" ", ln))
    # (position, value) for each billions-scale prose number, so each
    # metric is compared only against the number the prose attributes
    # to IT (nearest the metric word) — not a blind cross-product.
    nums: list[tuple[int, float]] = []
    for n in parse_numbers(prose):
        if n.is_pct or n.value < 1e9:
            continue
        nums.append((max(prose.find(n.raw), 0), n.value))
    out: list[str] = []
    for metric, cv in cited.items():
        if cv <= 0 or not nums:
            continue
        word = _REV_NEAR if metric == "revenue" else _NI_WORD
        kw = [m.start() for m in word.finditer(prose)]
        if not kw:
            continue
        # nearest in-band prose number to any occurrence of the word
        band = [(min(abs(p - k) for k in kw), v)
                for p, v in nums if cv / 3 <= v <= cv * 3]
        if not band:
            continue
        _, pv = min(band, key=lambda x: x[0])
        if contradicts(pv, cv):
            out.append(
                f'a prose {metric.replace("_", " ")} figure (~{pv:.0f}) '
                f'contradicts {metric}={cv:.0f} cited by the [SOURCE] on '
                f'this same line — restate the prose as the cited value')
    return out


def _qoq_problems(ln: str, series: list[dict]) -> list[str]:
    """Catch QoQ-framed revenue sentences that span non-adjacent
    quarters.

    The de-cumulation fix feeds the model correct single-quarter
    anchors, but it can still pair the right growth % with the wrong
    base quarter — e.g. "21.9% sequential revenue jump from $44.062B
    (Q1) to $57.006B (Q3)": each figure is individually a real single
    quarter, so a presence check passes, yet Q1->Q3 is two quarters,
    not sequential (and is +29% not +22%). We only flag when BOTH cited
    figures match verified single-quarter revenues and they are >=2
    fiscal quarters apart — deterministic and defensible; rounding on
    an otherwise-adjacent pair is intentionally not nitpicked.

    Caller must gate on `_REV_NEAR` and `_SEQ_NEAR`.
    """
    monies = [n.value for n in parse_numbers(ln)
              if not n.is_pct and n.value >= 1e9]
    matched: list[tuple] = []
    for v in monies:
        for s in series:
            sv = s.get("value")
            if (isinstance(sv, (int, float))
                    and isinstance(s.get("year"), int)
                    and isinstance(s.get("quarter"), int)
                    and approx_equal(v, sv, rel=0.01)):
                matched.append(
                    (_fiscal_idx(s["year"], s["quarter"]),
                     s["year"], s["quarter"], float(sv)))
                break
    if len(matched) < 2:
        return []
    matched.sort()
    iA, yA, qA, vA = matched[0]
    iB, yB, qB, vB = matched[-1]
    gap = iB - iA
    # gap 0-1: adjacent / same quarter -> fine. gap >5: the two figures
    # are too far apart to be a "this vs prior quarter" claim — almost
    # certainly a coincidental match on an unrelated $ figure, so stay
    # silent (precision over recall).
    if gap < 2 or gap > 5 or vA == 0:
        return []
    prev = next((s for s in series
                 if _fiscal_idx(s.get("year", 0),
                                s.get("quarter", 0)) == iB - 1
                 and isinstance(s.get("value"), (int, float))), None)
    if prev:
        detail = (f'FY{prev["year"]}Q{prev["quarter"]} revenue '
                  f'{prev["value"]:.0f} (true QoQ '
                  f'{(vB / prev["value"] - 1) * 100:+.1f}%)')
    else:
        detail = f'the immediately-prior quarter, not FY{yA}Q{qA}'
    return [f'a "sequential/QoQ" revenue change is stated between '
            f'FY{yA}Q{qA} ({vA:.0f}) and FY{yB}Q{qB} ({vB:.0f}) — '
            f'{gap} quarters apart, NOT consecutive '
            f'({(vB / vA - 1) * 100:+.1f}% over {gap} quarters, not a '
            f'single-quarter move). The quarter before FY{yB}Q{qB} is '
            f'{detail}.']


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
        from tools.financial_analysis import FinancialToolAgent

        tool_block, tool_trace = FinancialToolAgent(
            self.retriever.fact_store).plan_and_run(
                subject, topic, self.llm, self.params)
        for tr in tool_trace:
            _log(f"tool-agent: {tr}")
        facts_block = res.facts or "(none)"
        if tool_block and tool_block != "(no tool output)":
            facts_block = (
                f"{facts_block}\n\n# DETERMINISTIC FINANCIAL TOOL OUTPUT\n"
                f"{tool_block}")
        _log(f"retrieved {len(res.evidence)} passages "
             f"and built finance tool pack "
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
            facts_block=facts_block,
            evidence_block=res.evidence_block(),
        )
        draft = chat([{"role": "user", "content": prompt}],
                     config=self.llm, **self.params)
        if not isinstance(draft, str) or not draft.strip():
            raise RuntimeError("empty generation")
        draft = _unwrap(draft)
        if os.environ.get("ALPHASIGHT_GEN_NO_AUDIT") == "1":
            _log(f"done ({time.time() - t0:.1f}s, no audit)")
            return draft
        _log("self-audit ...")
        out = _unwrap(self._self_audit(subject, draft))
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
        # subject-independent: a line that contradicts its own [SOURCE].
        for line in draft.splitlines():
            ln = line.strip()
            if len(ln) < 8:
                continue
            for p in _citation_conflict(ln):
                problems.append(f'- "{ln[:140]}" -> {p}')
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
                    if _SEQ_NEAR.search(ln):
                        for p in _qoq_problems(ln, fs.metric(tk, "revenue")):
                            problems.append(f'- "{ln[:140]}" -> {tk} {p}')
        problems = problems[:6]
        if not problems:
            return draft
        fix = (
            "A deterministic check found numbers in the draft that "
            "contradict verified facts or are internally inconsistent "
            "(e.g. a QoQ/sequential change stated across non-adjacent "
            "quarters). Rewrite the report correcting ONLY the flagged "
            "figures and their period framing to match the stated "
            "facts; keep the stance, structure, length and all "
            "[SOURCE: ...] citations.\n\n"
            "Output ONLY the corrected report as raw markdown — no "
            "surrounding quotes, code fences, or delimiters, no "
            "preamble.\n\n"
            f"PROBLEMS:\n{chr(10).join(problems[:6])}\n\n"
            f"PROBLEM DRAFT BELOW (everything after this line):\n{draft}"
        )
        try:
            fixed = chat([{"role": "user", "content": fix}],
                         config=self.llm, **self.params)
            if isinstance(fixed, str) and fixed.strip():
                return _unwrap(fixed)
            return draft
        except Exception:
            return draft
