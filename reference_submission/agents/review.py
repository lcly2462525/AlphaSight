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
    r"(first|second|third|fourth)\s+quarter|"
    r"(第一|第二|第三|第四|一|二|三|四)\s*季度",
    re.I)
_FY_RE = re.compile(
    r"FY\s?(\d{2,4})|fiscal(?:\s+year)?\s+(\d{4})|\b(20\d{2})\b", re.I)
_QWORD = {"first": 1, "second": 2, "third": 3, "fourth": 4,
          "第一": 1, "一": 1, "第二": 2, "二": 2,
          "第三": 3, "三": 3, "第四": 4, "四": 4}


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
        elif qm.group(4):
            q = _QWORD.get(qm.group(4))
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
    r"earnings per share)\b|每股收益|预期|一致预期|高于|低于", re.I)


_CLAIM_CUE = re.compile(
    r"(\$|\d+(?:\.\d+)?\s*%|\b20\d{2}\b|Q[1-4]|FY\s?\d{2,4}|"
    r"million|billion|trillion|EPS|consensus|estimate|surprise|"
    r"beat|miss|above|below|growth|decline|increase|decrease|"
    r"upgrade|downgrade|peer|basket|Bloomberg|CNBC|Reuters|Benzinga|"
    r"Wall Street Journal|WSJ|Fierce Pharma|8-K|10-K|10-Q|"
    r"亿|万亿|百万|季度|财年|每股收益|一致预期|高于|低于|增长|下降|"
    r"上调|下调|评级|召回|披露|报道|股东会|市值|客户资产|同业|可比公司)",
    re.I)
_WEAK_FRAGMENT = re.compile(
    r"^\s*(?:Q[1-4]\s*(?:FY)?\s*\d{2,4}|FY\s?\d{2,4}|"
    r"\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{1,2}|December\s+quarter|"
    r"April low close|January\s+\d{1,2}|December\s+\d{1,2})\s*$",
    re.I)
_SOURCE_CUE = re.compile(
    r"Bloomberg|CNBC|Reuters|Benzinga|Wall Street Journal|WSJ|"
    r"Fierce Pharma|SEC|Form\s+[0-9A-Z-]+|8-K|10-K|10-Q|披露|报道",
    re.I)
_PEER_CUE = re.compile(r"peer|peers\.json|basket|同业|可比公司", re.I)
_PRICE_CUE = re.compile(
    r"opened|closed|close-to-close|52-week|price gain|price decline|"
    r"calendar-year|YTD|year-to-date|开盘|收盘|年初至今|过去一年|涨幅|跌幅",
    re.I)
_DIR_DOWN = re.compile(
    r"miss|below|decline|decrease|down|lower|downgrade|下降|下滑|低于|下调|"
    r"减少|回落", re.I)
_DIR_UP = re.compile(
    r"beat|above|increase|growth|up|higher|upgrade|增长|上升|高于|上调|提升",
    re.I)


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
_DATE_CN = re.compile(r"\b(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\b")


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
    for y, mo, d in _DATE_CN.findall(text):
        out.append(f"{y}-{int(mo):02d}-{int(d):02d}")
    return out


# ---- per-field EPS verification ------------------------------------

_NUMTOK = r"\$?\s*(-?\d[\d,]*\.?\d*)"
_RX_ACTUAL = re.compile(
    r"(?:actual|reported|posted|delivered|came in at|print of|eps of)"
    r"\D{0,18}?" + _NUMTOK, re.I)
_RX_ACTUAL_BEFORE = re.compile(
    r"(?<![A-Za-z])" + _NUMTOK
    + r"\D{0,12}?(?:actual|reported|posted|delivered|实际)", re.I)
_RX_EST = re.compile(
    r"(?:consensus|estimate[sd]?|expected|street|forecast)"
    r"\D{0,18}?" + _NUMTOK, re.I)
_RX_EST_BEFORE = re.compile(
    r"(?<![A-Za-z])" + _NUMTOK
    + r"\D{0,12}?(?:consensus|estimate[sd]?|expected|预期|一致预期)",
    re.I)
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

    m = _RX_ACTUAL_BEFORE.search(quote) or _RX_ACTUAL.search(quote)
    if m and isinstance(act, (int, float)):
        v = _f(m.group(1))
        if v is not None and abs(v) <= 1000 and not approx_equal(v, act):
            probs.append(f"claimed actual EPS {v:g} but verified "
                         f"actual is {act:g}")
    m = _RX_EST.search(quote) or _RX_EST_BEFORE.search(quote)
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
        universe = set(self.retriever.subject_universe())
        explicit: list[str] = []
        patterns = [
            r"\((?:NYSE|NASDAQ|Nasdaq|纳斯达克|纽交所)\s*[:：]\s*([A-Z.]{1,6})\)",
            r"(?:NYSE|NASDAQ|Nasdaq|纳斯达克|纽约证券交易所|股票代码|交易代码|代码)\s*[:：]?\s*([A-Z.]{1,6})",
            r"\((?:[A-Z]{2,5},\s*)+[A-Z]{2,5}\)",
            r"Coverage:\s*([A-Z.,\s]+)\s*[—-]",
        ]
        for pat in patterns:
            for m in re.finditer(pat, report):
                toks = re.findall(r"\b[A-Z.]{1,6}\b", m.group(0))
                for t in toks:
                    if len(t) >= 2 and t in universe and t not in explicit:
                        explicit.append(t)
        if not explicit:
            head = report[:1500]
            for t in re.findall(r"\b[A-Z.]{2,6}\b", head):
                if t in universe and t not in {"NYSE", "NASDAQ", "SEC", "CIK"} \
                        and t not in explicit:
                    explicit.append(t)
        if explicit:
            # Return several only for deliberate sector-comparison notes.
            return explicit[:6] if len(explicit) > 1 else explicit

        allt = self.retriever.entity.resolve(report)
        if not allt:
            return []

        def score(t: str) -> tuple:
            explicit = (f"({t})" in report) or (f"${t}" in report)
            return (explicit, report.count(t), len(t))

        best = max(allt, key=score)
        if len(best) <= 2 and not ((f"({best})" in report) or (f"${best}" in report)):
            return []
        return [best]

    def _scope(self, quote: str, primary: list[str]) -> list[str]:
        """Tickers a deterministic check may run against. Prefer tickers
        named in the claim itself; fall back to the report's primary
        ONLY if it is unambiguous (>=3 chars, or explicitly written as
        `(T)`/`$T`/repeated) — a shaky 1-2 letter primary would risk
        verifying the claim against the wrong company's facts."""
        inq = self.retriever.entity.resolve(quote)
        universe = set(self.retriever.subject_universe())
        for tok in re.findall(r"\b[A-Z.]{2,6}\b", quote):
            if tok in universe and tok not in inq:
                inq.append(tok)
        if inq:
            return inq[:3]
        if len(primary) == 1 and len(primary[0]) >= 3:
            return primary
        return []

    def run(self, report: str) -> list[ReviewIssue]:
        import sys
        import time

        def _log(m: str) -> None:
            print(f"[rev] {m}", file=sys.stderr, flush=True)

        t0 = time.time()
        _log("extracting claims (regex + LLM) ...")
        claims = self._extract(report)
        primary = self._primary_ticker(report)

        candidates: list[dict] = []
        used: set[str] = set()
        for c in (self._numeric_candidates(claims, primary)
                  + self._date_candidates(claims, primary)
                  + self._period_end_candidates(claims, primary)
                  + self._price_candidates(claims, primary)
                  + self._peer_candidates(claims, primary)
                  + self._arithmetic_candidates(claims)):
            if c["quote"] in used:
                continue
            candidates.append(c)
            used.add(c["quote"])
        _log(f"{len(claims)} claims, {len(candidates)} deterministic "
             f"candidates; retrieving for the rest ...")
        for c in self._retrieval_candidates(claims, used, primary):
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
        out: list[dict] = []
        seen: set[str] = set()

        def add(q: str, kind: str = "other") -> None:
            q = q.strip()
            if not self._good_quote(q, report):
                return
            # Keep the more complete quote when one contains another.
            for old in list(seen):
                if q != old and old in q and len(q) > len(old) + 12:
                    seen.remove(old)
                    out[:] = [x for x in out if x["quote"] != old]
                elif q != old and q in old:
                    return
            if q not in seen:
                out.append({"quote": q, "kind": kind,
                            "claim_type": self._claim_type(q)})
                seen.add(q)

        for q in self._regex_claims(report):
            add(q, self._claim_type(q))

        try:
            raw = chat(
                [{"role": "user",
                  "content": self._extract_p.format(report=report[:16000])}],
                config=self.llm,
                **{**self.params, "response_format": {"type": "json_object"}})
            cl = parse_json_obj(raw).get("claims", [])
        except Exception:
            cl = []
        for c in cl if isinstance(cl, list) else []:
            if isinstance(c, dict) and isinstance(c.get("quote"), str):
                add(c["quote"], c.get("kind", "other"))

        out.sort(key=lambda x: self._claim_priority(x["quote"]), reverse=True)
        return out[:40]

    def _good_quote(self, q: str, report: str) -> bool:
        if not q or q not in report:
            return False
        if len(q) < 18 or _WEAK_FRAGMENT.match(q):
            return False
        return bool(_CLAIM_CUE.search(q))

    def _regex_claims(self, report: str) -> list[str]:
        claims: list[str] = []
        lines = report.splitlines()
        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.strip()
            if re.match(r"^[-*]\s+", line):
                block = [raw]
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    s = nxt.strip()
                    if not s:
                        break
                    if re.match(r"^(#|[-*]\s+|\|)", s):
                        break
                    block.append(nxt)
                    j += 1
                q = "\n".join(block).strip()
                if _CLAIM_CUE.search(q):
                    claims.append(q)
                i = j
                continue
            if line.startswith("|") and _CLAIM_CUE.search(line):
                claims.append(line)
            i += 1

        # Single lines catch compact prose and table rows exactly.
        for raw in lines:
            line = raw.strip()
            if not line or len(line) < 18:
                continue
            if line.startswith("#"):
                continue
            if _CLAIM_CUE.search(line):
                claims.append(line)
        # Paragraph pass keeps original newlines so quotes remain substrings.
        for para in re.split(r"\n\s*\n", report):
            para = para.strip()
            if len(para) < 30 or para.startswith("#"):
                continue
            one_line = " ".join(x.strip() for x in para.splitlines()
                                if x.strip())
            for sent in re.split(r"(?<=[。！？.!?])\s+", one_line):
                sent = sent.strip()
                if 25 <= len(sent) <= 420 and _CLAIM_CUE.search(sent) \
                        and sent in report:
                    claims.append(sent)
            if 30 <= len(para) <= 420 and _CLAIM_CUE.search(para):
                claims.append(para)
        return claims

    def _claim_type(self, q: str) -> str:
        if _PEER_CUE.search(q):
            return "peer_membership"
        if _SOURCE_CUE.search(q) and _parse_dates(q):
            return "source_attribution"
        if _PRICE_CUE.search(q):
            return "derived_calculation"
        if _DIR_UP.search(q) or _DIR_DOWN.search(q):
            return "direction_reversal"
        if _parse_dates(q) or _claim_form(q):
            return "date_timeline"
        if parse_numbers(q):
            return "numeric_mutation"
        return "other"

    def _claim_priority(self, q: str) -> tuple[int, int]:
        typ = self._claim_type(q)
        rank = {
            "direction_reversal": 7,
            "derived_calculation": 6,
            "numeric_mutation": 5,
            "date_timeline": 5,
            "peer_membership": 5,
            "source_attribution": 4,
        }.get(typ, 1)
        return rank, min(len(q), 500)

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
                if quarter is None or re.search(
                    r"nine[- ]month|nine months|9M|上半年|九个月", q, re.I):
                    continue
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
            if not re.search(r"filed|submitted|filing date|filed with|"
                             r"提交|备案|披露日期|提交日", q, re.I):
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

    def _period_end_candidates(self, claims: list[dict],
                               primary: list[str]) -> list[dict]:
        out: list[dict] = []
        for c in claims:
            q = c["quote"]
            if not re.search(r"ended|ending|截至|结束", q, re.I):
                continue
            dates = _parse_dates(q)
            if not dates:
                continue
            year, quarter = _parse_period(q)
            if year is None or quarter is None:
                continue
            for tk in self._scope(q, primary):
                rows = self.retriever.fact_store.period_rows(
                    tk, year=year, quarter=quarter)
                ends = sorted({r.get("endDate") for r in rows
                               if r.get("endDate")})
                if not ends or any(d in ends for d in dates):
                    continue
                out.append({
                    "quote": q,
                    "kind": "date_timeline",
                    "evidence": (
                        f"DETERMINISTIC FACT [SOURCE: research/{tk}/"
                        f"financials_reported.json] {tk} FY{year} Q{quarter} "
                        f"period endDate is {', '.join(ends)}. The claim's "
                        f"date {', '.join(dates)} does not match.")})
                break
        return out

    def _price_candidates(self, claims: list[dict],
                          primary: list[str]) -> list[dict]:
        out: list[dict] = []
        for c in claims:
            q = c["quote"]
            if not _PRICE_CUE.search(q):
                continue
            years = [int(y) for y in re.findall(r"\b(20\d{2})\b", q)]
            year = min(years) if years else 2025
            pcts = [n.value for n in parse_numbers(q) if n.is_pct]
            dates = _parse_dates(q)
            for tk in self._scope(q, primary):
                facts: list[str] = []
                mismatch = False
                win = self.retriever.fact_store.price_window(tk, year)
                if win and win.get("return_pct") is not None:
                    ret = float(win["return_pct"])
                    facts.append(
                        f"{tk} {win['first_date']} close={win['first']['close']} "
                        f"-> {win['last_date']} close={win['last']['close']} "
                        f"return={ret:+.1f}%")
                    if pcts and re.search(
                        r"calendar-year|close-to-close|price gain|price decline|"
                        r"\breturn\b|年初至今.*(?:涨幅|跌幅)|"
                        r"过去一年.*(?:涨幅|跌幅)|全年.*(?:涨幅|跌幅)|"
                        r"年度.*(?:涨幅|跌幅)|年内.*(?:涨幅|跌幅)", q, re.I):
                        if not any(abs(p - ret) <= max(1.0, abs(ret) * 0.08)
                                   for p in pcts):
                            mismatch = True
                for d in dates:
                    row = self.retriever.fact_store.price_on(tk, d)
                    if row:
                        facts.append(
                            f"{tk} {d} open={row['open']} close={row['close']} "
                            f"high={row['high']} low={row['low']}")
                if mismatch:
                    out.append({
                        "quote": q,
                        "kind": "derived_calculation",
                        "evidence": (
                            "DETERMINISTIC FACT [SOURCE: prices/"
                            f"{tk}.csv] " + "; ".join(facts)
                            + ". The claim's stated return/price calculation "
                              "does not match the price file.")})
                    break
        return out

    def _peer_candidates(self, claims: list[dict],
                         primary: list[str]) -> list[dict]:
        out: list[dict] = []
        for c in claims:
            q = c["quote"]
            if not re.search(r"peer(?:s)?(?:\.json| list| basket)|peer basket|"
                             r"peer list|可比公司列表|同业列表", q, re.I):
                continue
            for tk in self._scope(q, primary):
                peers = self.retriever.fact_store.peers(tk)
                if not peers:
                    continue
                claimed = [x for x in re.findall(r"\b[A-Z][A-Z.]{1,5}\b", q)
                           if x not in {"EPS", "FY", "QOQ", "YOY", "SEC"}]
                # The subject itself may appear in prose; compare only
                # explicit list members after the possessive subject.
                extras = sorted({x for x in claimed if x != tk and x not in peers})
                if extras:
                    out.append({
                        "quote": q,
                        "kind": "peer_membership",
                        "evidence": (
                            f"DETERMINISTIC FACT [SOURCE: research/{tk}/"
                            f"peers.json] {tk} peer list is {peers}. "
                            f"Extra claimed tickers not in peers: {extras}.")})
                    break
        return out

    def _arithmetic_candidates(self, claims: list[dict]) -> list[dict]:
        out: list[dict] = []
        for c in claims:
            q = c["quote"]
            if not re.search(r"环比|QoQ|较", q, re.I):
                continue
            vals = []
            for m in re.finditer(r"\$\s*(-?\d+(?:\.\d+)?)|"
                                 r"(-?\d+(?:\.\d+)?)\s*美元", q):
                vals.append(float(m.group(1) or m.group(2)))
            pcts = [n.value for n in parse_numbers(q) if n.is_pct]
            if len(vals) < 2 or not pcts:
                continue
            a, b, claimed = vals[0], vals[1], pcts[-1]
            if b == 0:
                continue
            calc = (a / b - 1) * 100
            mismatch = abs(claimed - calc) > max(1.0, abs(calc) * 0.08)
            polarity_bad = ((calc > 0 and _DIR_DOWN.search(q)) or
                            (calc < 0 and _DIR_UP.search(q)))
            if mismatch or polarity_bad:
                out.append({
                    "quote": q,
                    "kind": "derived_calculation",
                    "evidence": (
                        f"DETERMINISTIC FACT arithmetic: using {a:g} vs {b:g}, "
                        f"the derived change is {calc:+.1f}%, not {claimed:g}%. "
                        "The claim's stated magnitude or direction does not match.")})
        return out

    # ---- step 2b: retrieval candidates for the rest ----------------

    def _retrieval_candidates(self, claims: list[dict],
                              used: set[str],
                              primary: list[str]) -> list[dict]:
        out = []
        for c in claims[:25]:
            q = c["quote"]
            if q in used:
                continue
            tickers = self._scope(q, primary)
            res = self.retriever.search(q, top_k=4, tickers=tickers or None)
            out.append({"quote": q,
                        "evidence": res.evidence_block()[:2500],
                        "kind": c.get("claim_type") or "narrative"})
        return out

    # ---- step 3: single LLM adjudication over ALL candidates -------

    def _adjudicate(self, candidates: list[dict]) -> list[tuple[str, str]]:
        if not candidates:
            return []
        blocks = "\n\n".join(
            f'CLAIM_TYPE: {c.get("kind", "unknown")}\n'
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
