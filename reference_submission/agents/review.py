"""ReviewAgent: extract -> per-claim verify -> LLM adjudicate.

Two candidate sources feed ONE adjudication pass:

  * numeric  — period-aligned per-claim match against the FactStore
               (parse ticker+fiscal period+metric, look up that exact
               row, attach the authoritative value as evidence)
  * narrative — retrieval-grounded evidence for the remaining claims

Every candidate — including the deterministic numeric ones — is judged
by the LLM before becoming an issue. The deterministic step never emits
directly: it only produces high-precision, fact-backed candidates so the
LLM can drop mis-parses (false positives are penalised). Every emitted
quote is forced to be a verbatim substring of the report.
"""

from __future__ import annotations

import re

from llm import chat
from schemas import ReviewIssue
from retrieval.numeric import approx_equal, parse_numbers
from agents._util import load_prompt, parse_json_obj

_METRIC = [
    ("eps", re.compile(r"\beps\b|earnings per share", re.I)),
    ("net_income", re.compile(r"net (income|profit|earnings)", re.I)),
    ("revenue", re.compile(r"\b(revenue|sales|top.?line)\b", re.I)),
]
_Q_RE = re.compile(
    r"Q\s?([1-4])(?![0-9])|(?<![A-Za-z])([1-4])\s?Q(?![A-Za-z])|"
    r"(first|second|third|fourth)\s+quarter",
    re.I)
_FY_RE = re.compile(
    r"FY\s?(\d{2,4})|fiscal(?:\s+year)?\s+(\d{4})|\b(20\d{2})\b", re.I)
_QWORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}


def _parse_period(text: str) -> tuple[int | None, int | None]:
    qm = _Q_RE.search(text)
    q = None
    if qm:
        if qm.group(1):
            q = int(qm.group(1))
        elif qm.group(2):
            q = int(qm.group(2))
        elif qm.group(3):
            q = _QWORD.get(qm.group(3).lower())
    ym = _FY_RE.search(text)
    y = None
    if ym:
        raw = ym.group(1) or ym.group(2) or ym.group(3)
        if raw:
            y = int(raw)
            if y < 100:
                y += 2000
    return y, q


def _claim_metric(text: str) -> str | None:
    for name, rx in _METRIC:
        if rx.search(text):
            return name
    return None


class ReviewAgent:
    def __init__(self, retriever, llm_cfg, rev_params: dict) -> None:
        self.retriever = retriever
        self.llm = llm_cfg
        self.params = rev_params
        self._extract_p = load_prompt("extract_claims.md")
        self._adj_p = load_prompt("adjudicate.md")

    def run(self, report: str) -> list[ReviewIssue]:
        claims = self._extract(report)
        tickers = self.retriever.entity.resolve(report)

        candidates: list[dict] = []
        used: set[str] = set()
        for c in self._numeric_candidates(claims, tickers):
            candidates.append(c)
            used.add(c["quote"])
        for c in self._retrieval_candidates(claims, used):
            candidates.append(c)

        issues: list[ReviewIssue] = []
        seen: set[str] = set()
        for q, r in self._adjudicate(candidates):
            if q in report and q not in seen:
                issues.append(ReviewIssue(quote=q, reason=r))
                seen.add(q)
        return issues

    # ---- step 1: extract -------------------------------------------

    def _extract(self, report: str) -> list[dict]:
        try:
            raw = chat(
                [{"role": "user",
                  "content": self._extract_p.format(report=report[:12000])}],
                config=self.llm,
                **{**self.params, "response_format": {"type": "json_object"}})
            cl = parse_json_obj(raw).get("claims", [])
        except Exception:
            cl = []
        out = []
        for c in cl if isinstance(cl, list) else []:
            if isinstance(c, dict) and isinstance(c.get("quote"), str):
                q = c["quote"].strip()
                if q and q in report:
                    out.append({"quote": q, "kind": c.get("kind", "other")})
        return out[:15]

    # ---- step 2a: period-aligned numeric candidates ----------------

    def _numeric_candidates(self, claims: list[dict],
                            tickers: list[str]) -> list[dict]:
        if not tickers:
            return []
        out: list[dict] = []
        for c in claims:
            q = c["quote"]
            metric = _claim_metric(q)
            if not metric:
                continue
            nums = [n for n in parse_numbers(q) if not n.is_pct]
            if not nums:
                continue
            year, quarter = _parse_period(q)
            for tk in tickers[:4]:
                rows = self.retriever.fact_store.metric(
                    tk, metric, year=year, quarter=quarter)
                if not rows:
                    continue
                truths = [r["value"] for r in rows]
                # claim consistent if any quoted number ~= any truth
                if any(approx_equal(n.value, t)
                       for n in nums for t in truths):
                    break
                period = (f"FY{year}" if year else "") + \
                         (f" Q{quarter}" if quarter else "")
                fact = "; ".join(
                    f"FY{r['year']} Q{r['quarter']} {metric}={r['value']:g}"
                    for r in rows[:6])
                src = rows[0]["source"]
                out.append({
                    "quote": q,
                    "evidence": (
                        f"DETERMINISTIC FACT [SOURCE: {src}] {tk} "
                        f"{metric}{(' for ' + period) if period else ''}: "
                        f"{fact}. The claim's figure for this metric does "
                        f"not match the verified value above."),
                    "kind": "numeric",
                })
                break
        return out

    # ---- step 2b: retrieval candidates for the rest ----------------

    def _retrieval_candidates(self, claims: list[dict],
                              used: set[str]) -> list[dict]:
        out = []
        for c in claims[:10]:
            q = c["quote"]
            if q in used:
                continue
            res = self.retriever.search(q, top_k=4)
            out.append({"quote": q,
                        "evidence": res.evidence_block()[:2500],
                        "kind": "narrative"})
        return out

    # ---- step 3: single LLM adjudication over ALL candidates -------

    def _adjudicate(self, candidates: list[dict]) -> list[tuple[str, str]]:
        if not candidates:
            return []
        blocks = "\n\n".join(
            f'CLAIM: "{c["quote"]}"\nEVIDENCE:\n{c["evidence"]}'
            for c in candidates)
        try:
            raw = chat(
                [{"role": "user",
                  "content": self._adj_p.format(candidates=blocks)}],
                config=self.llm,
                **{**self.params, "response_format": {"type": "json_object"}})
            data = parse_json_obj(raw)
        except Exception:
            return []
        out = []
        for it in data.get("issues", []) if isinstance(data, dict) else []:
            if not isinstance(it, dict):
                continue
            q = str(it.get("quote", "")).strip()
            r = str(it.get("reason", "")).strip()
            if q and r:
                out.append((q, r))
        return out
