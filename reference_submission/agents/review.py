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


_EARN_CUE = re.compile(
    r"\b(actual|consensus|estimate|surprise|beat|miss|eps|"
    r"earnings per share)\b", re.I)


def _claim_metric(text: str) -> str | None:
    for name, rx in _METRIC:
        if rx.search(text):
            return name
    # earnings claim without the literal word "EPS": a $-figure with
    # actual/consensus/beat/miss + a fiscal period (report_03 pattern)
    if _EARN_CUE.search(text) and re.search(r"\d", text) \
            and _parse_period(text) != (None, None):
        return "eps"
    return None


# ---- filing-date verification helpers ------------------------------

_FORM_RE = re.compile(
    r"\b(10-?K|10-?Q|8-?K|DEF\s?14A|S-1|20-?F)\b|"
    r"(annual report|quarterly report|proxy statement)", re.I)
_FORM_WORD = {"annual report": "10-K", "quarterly report": "10-Q",
              "proxy statement": "DEF 14A"}
_ACC_RE = re.compile(r"\b(\d{10}-\d{2}-\d{6})\b")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
_DATE_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_DATE_MDY = re.compile(
    r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d{2})\b")


def _claim_form(text: str) -> str | None:
    m = _FORM_RE.search(text)
    if not m:
        return None
    if m.group(1):
        return m.group(1).upper().replace(" ", "")
    return _FORM_WORD.get(m.group(2).lower())


def _parse_dates(text: str) -> list[str]:
    out: list[str] = []
    for y, mo, d in _DATE_ISO.findall(text):
        out.append(f"{y}-{mo}-{d}")
    for mon, d, y in _DATE_MDY.findall(text):
        mi = _MONTHS.get(mon.lower())
        if mi:
            out.append(f"{y}-{mi:02d}-{int(d):02d}")
    return out


# ---- per-field EPS verification ------------------------------------

_NUMTOK = r"\$?\s*(-?\d[\d,]*\.?\d*)"
_RX_ACTUAL = re.compile(
    r"(?:actual|reported|posted|delivered|came in at|print of|eps of)"
    r"\D{0,18}?" + _NUMTOK, re.I)
_RX_EST = re.compile(
    r"(?:consensus|estimate[sd]?|expected|street|forecast)"
    r"\D{0,18}?" + _NUMTOK, re.I)
_RX_MISS = re.compile(r"\b(miss|missed|shortfall|fell short|below)\b", re.I)
_RX_BEAT = re.compile(r"\b(beat|beats|topped|surpass|above)\b", re.I)


def _f(s: str) -> float | None:
    try:
        return float(s.replace(",", "").replace("$", "").strip())
    except (ValueError, AttributeError):
        return None


def _eps_problems(quote: str, row: dict) -> list[str]:
    """Per-field check: actual / estimate / surprise sign vs the
    authoritative earnings row. Returns human-readable problems."""
    probs: list[str] = []
    act = row.get("actual")
    est = row.get("estimate")
    sp = row.get("surprisePercent")
    surp = row.get("surprise")

    m = _RX_ACTUAL.search(quote)
    if m and isinstance(act, (int, float)):
        v = _f(m.group(1))
        if v is not None and abs(v) <= 1000 and not approx_equal(v, act):
            probs.append(f"claimed actual EPS {v:g} but verified "
                         f"actual is {act:g}")
    m = _RX_EST.search(quote)
    if m and isinstance(est, (int, float)):
        v = _f(m.group(1))
        if v is not None and abs(v) <= 1000 and not approx_equal(v, est):
            probs.append(f"claimed consensus/estimate {v:g} but verified "
                         f"estimate is {est:g}")
    # beat/miss direction vs real surprise sign
    if isinstance(surp, (int, float)) and surp != 0:
        claims_miss = bool(_RX_MISS.search(quote))
        claims_beat = bool(_RX_BEAT.search(quote))
        if claims_miss and surp > 0:
            probs.append(f"claims a MISS but it was a BEAT "
                         f"(surprise +{surp:g}"
                         + (f", +{sp:g}%" if isinstance(sp, (int, float))
                            else "") + ")")
        elif claims_beat and surp < 0:
            probs.append(f"claims a BEAT but it was a MISS "
                         f"(surprise {surp:g}"
                         + (f", {sp:g}%" if isinstance(sp, (int, float))
                            else "") + ")")
    return probs


class ReviewAgent:
    def __init__(self, retriever, llm_cfg, rev_params: dict) -> None:
        self.retriever = retriever
        self.llm = llm_cfg
        self.params = rev_params
        self._extract_p = load_prompt("extract_claims.md")
        self._adj_p = load_prompt("adjudicate.md")

    def _primary_ticker(self, report: str) -> list[str]:
        """The company the report is about. Single/two-letter tickers
        false-match common words, so rank by (frequency, length) over
        the whole report and prefer a `(TICKER)` / `$TICKER` mention —
        not the alphabetically-first resolved symbol."""
        allt = self.retriever.entity.resolve(report)
        if not allt:
            return []

        def score(t: str) -> tuple:
            explicit = (f"({t})" in report) or (f"${t}" in report)
            return (explicit, report.count(t), len(t))

        return [max(allt, key=score)]

    def _scope(self, quote: str, primary: list[str]) -> list[str]:
        """Tickers a deterministic check may run against. Prefer tickers
        named in the claim itself; fall back to the report's primary
        ONLY if it is unambiguous (>=3 chars, or explicitly written as
        `(T)`/`$T`/repeated) — a shaky 1-2 letter primary would risk
        verifying the claim against the wrong company's facts."""
        inq = self.retriever.entity.resolve(quote)
        if inq:
            return inq[:3]
        if primary and len(primary[0]) >= 3:
            return primary
        return []

    def run(self, report: str) -> list[ReviewIssue]:
        import sys
        import time

        def _log(m: str) -> None:
            print(f"[rev] {m}", file=sys.stderr, flush=True)

        t0 = time.time()
        _log("extracting claims (LLM) ...")
        claims = self._extract(report)
        primary = self._primary_ticker(report)

        candidates: list[dict] = []
        used: set[str] = set()
        for c in (self._numeric_candidates(claims, primary)
                  + self._date_candidates(claims, primary)):
            if c["quote"] in used:
                continue
            candidates.append(c)
            used.add(c["quote"])
        _log(f"{len(claims)} claims, {len(candidates)} deterministic "
             f"candidates; retrieving for the rest ...")
        for c in self._retrieval_candidates(claims, used):
            candidates.append(c)

        _log(f"adjudicating {len(candidates)} candidates (LLM) ...")
        issues: list[ReviewIssue] = []
        seen: set[str] = set()
        for q, r in self._adjudicate(candidates):
            if q in report and q not in seen:
                issues.append(ReviewIssue(quote=q, reason=r))
                seen.add(q)
        _log(f"done ({time.time() - t0:.1f}s, {len(issues)} issues)")
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
                            primary: list[str]) -> list[dict]:
        out: list[dict] = []
        for c in claims:
            q = c["quote"]
            metric = _claim_metric(q)
            if not metric:
                continue
            tickers = self._scope(q, primary)
            if not tickers:
                continue
            year, quarter = _parse_period(q)
            for tk in tickers:
                if metric == "eps":
                    row = self.retriever.fact_store.earnings_row(
                        tk, year, quarter)
                    if not row:
                        continue
                    probs = _eps_problems(q, row)
                    if not probs:
                        break
                    src = f"research/{tk}/earnings.json"
                    period = (f"FY{row.get('year')} Q{row.get('quarter')}")
                    out.append({"quote": q, "kind": "numeric",
                                "evidence": (
                                    f"DETERMINISTIC FACT [SOURCE: {src}] "
                                    f"{tk} {period} earnings — "
                                    + "; ".join(probs))})
                    break
                # revenue / net_income: period-aligned single value
                rows = self.retriever.fact_store.metric(
                    tk, metric, year=year, quarter=quarter)
                if not rows:
                    continue
                truths = [r["value"] for r in rows]
                nums = [n for n in parse_numbers(q) if not n.is_pct
                        and abs(n.value) >= 1e6]
                if not nums or any(approx_equal(n.value, t)
                                   for n in nums for t in truths):
                    break
                period = (f"FY{year}" if year else "") + \
                         (f" Q{quarter}" if quarter else "")
                fact = "; ".join(
                    f"FY{r['year']} Q{r['quarter']} {metric}={r['value']:g}"
                    for r in rows[:6])
                out.append({
                    "quote": q,
                    "evidence": (
                        f"DETERMINISTIC FACT [SOURCE: {rows[0]['source']}] "
                        f"{tk} {metric}{(' for ' + period) if period else ''}"
                        f": {fact}. The claim's figure does not match."),
                    "kind": "numeric"})
                break
        return out

    # ---- step 2b: filing-date candidates ---------------------------

    def _date_candidates(self, claims: list[dict],
                         primary: list[str]) -> list[dict]:
        out: list[dict] = []
        for c in claims:
            q = c["quote"]
            form = _claim_form(q)
            dates = _parse_dates(q)
            if not form or not dates:
                continue
            tickers = self._scope(q, primary)
            if not tickers:
                continue
            accs = _ACC_RE.findall(q)
            for tk in tickers:
                recs = self.retriever.fact_store.filings_of(
                    tk, form=form, accession=accs[0] if accs else None)
                if not recs:
                    continue
                real = sorted({r["date"] for r in recs if r["date"]})
                if not real or any(d in real for d in dates):
                    break
                out.append({
                    "quote": q, "kind": "date",
                    "evidence": (
                        f"DETERMINISTIC FACT [SOURCE: catalog] {tk} "
                        f"{form} filings were filed on {', '.join(real)} "
                        f"(accession-encoded). The claim's date "
                        f"{', '.join(dates)} does not match any actual "
                        f"filing date for this form.")})
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
