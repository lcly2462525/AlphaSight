"""ReviewAgent: extract -> tiered verify -> emit.

Claims are extracted whitespace-tolerantly (see anchor.py) so wrapped
sentences/bullets/table rows survive. Each claim is routed to a
type-specific verifier and the result is split into two tiers:

  * exact  — structured comparison against an authoritative source with
             no parse ambiguity (filing-date catalog, peers.json, prices
             CSV, EPS table cells vs earnings.json, report-internal
             return arithmetic). These are EMITTED DIRECTLY — the old
             LLM re-adjudication flipped confirmed-correct facts into
             false issues.
  * weak   — fragile parses (free-text QoQ pairs, generic revenue
             numeric) that still go through a contradiction-only LLM
             pass together with the narrative/source/causal claims.

Every emitted quote is re-anchored to the original raw span so it
stays a verbatim substring of the report.
"""

from __future__ import annotations

import re

from llm import chat
from schemas import ReviewIssue
from retrieval.numeric import approx_equal, contradicts, parse_numbers
from agents._util import load_prompt, parse_json_obj
from agents.anchor import Anchored
from agents.tables import col, parse_tables

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

# An EPS figure: optional $, 1-3 integer digits, a MANDATORY decimal
# (excludes bare quarter digits "Q2", 4-digit years "2025"), and not a
# percentage. EPS magnitudes are small; this also rejects prices/volumes.
_NUMTOK = r"\$?\s*(-?\d{1,3}\.\d{1,4})(?!\s*%)(?!\d)"
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
    + r"\D{0,12}?(?:consensus|estimate[sd]?|expected)", re.I)
# Chinese consensus must use the consensus NOUN ("一致预期" / "市场预期"),
# never bare "预期" — "超预期"/"不及预期" are beat/miss verbs, and a
# loose "<num> ... 预期" grabbed unrelated %/actual values (a major
# false-positive source on the Chinese reports).
_CN_EST = r"(?:市场)?一致预期|市场预期|彭博一致预期|分析师预期"
_RX_EST_CN = re.compile(
    r"(?:" + _CN_EST + r")\D{0,8}?" + _NUMTOK)
_RX_EST_CN_BEFORE = re.compile(
    _NUMTOK + r"\s*美元?\s*的?\s*(?:" + _CN_EST + r")")
# Chinese "actual" must be tied to the EPS noun (bare "实际" appears in
# price/volume/revenue prose and grabbed unrelated numbers).
_RX_ACTUAL_CN = re.compile(
    r"实际\s*(?:EPS|每股收益|每股盈利)\s*(?:为|约|是)?\s*" + _NUMTOK)
_RX_MISS = re.compile(r"\b(miss|missed|shortfall|fell short|below)\b", re.I)
_RX_BEAT = re.compile(r"\b(beat|beats|topped|surpass|above)\b", re.I)


def _f(s: str) -> float | None:
    try:
        return float(s.replace(",", "").replace("$", "").strip())
    except (ValueError, AttributeError):
        return None


def _eps_problems(quote: str, row: dict) -> list[str]:
    """Per-field check: actual / estimate / surprise sign vs the
    authoritative earnings row. Returns human-readable problems.

    Gate: only an actual earnings-result claim (an explicit EPS figure
    or a stated consensus/estimate) is checkable. Prose that merely
    contains the word "miss"/"beat" is not — that was a false-positive
    source (e.g. '...the December-quarter EPS miss was...')."""
    am = (_RX_ACTUAL_BEFORE.search(quote) or _RX_ACTUAL.search(quote)
          or _RX_ACTUAL_CN.search(quote))
    em = (_RX_EST.search(quote) or _RX_EST_BEFORE.search(quote)
          or _RX_EST_CN.search(quote) or _RX_EST_CN_BEFORE.search(quote))
    if not (am or em):
        return []
    probs: list[str] = []
    act = row.get("actual")
    est = row.get("estimate")
    sp = row.get("surprisePercent")
    surp = row.get("surprise")

    av = _f(am.group(1)) if am else None
    ev = _f(em.group(1)) if em else None
    if (av is not None and isinstance(act, (int, float))
            and abs(av) <= 1000 and not approx_equal(av, act)):
        probs.append(f"claimed actual EPS {av:g} but verified "
                     f"actual is {act:g}")
    # If the "estimate" we parsed equals the parsed actual, we almost
    # certainly grabbed the actual figure, not a stated consensus —
    # don't raise a bogus estimate mismatch.
    if (ev is not None and isinstance(est, (int, float))
            and abs(ev) <= 1000 and not approx_equal(ev, est)
            and not (av is not None and approx_equal(ev, av))):
        probs.append(f"claimed consensus/estimate {ev:g} but verified "
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
        self._veto_p = load_prompt("verify_exact.md")
        self._grounded_p = load_prompt("grounded_review.md")
        self._verify_p = load_prompt("verify_issue.md")

    def _primary_ticker(self, report: str) -> list[str]:
        """The ONE company the report is about. These reports open with
        `# Company Name (TICKER) — ...`; peers appear later only as
        comparisons. Returning the peer list as 'subject' (the old bug)
        made the deterministic checks compare a report against a peer's
        facts — a huge false-positive source (AMD report vs NVDA.csv).
        So: lock the title ticker as a SINGLE subject; multi only for an
        explicit sector basket `(A, B, C)`."""
        universe = set(self.retriever.subject_universe())
        # Normalize fullwidth parens/colon/comma so Chinese titles like
        # `（NYSE：BA）` / `（NFLX）` parse the same as ASCII.
        _fw = str.maketrans("（）：，", "():,")
        head = report[:1500].translate(_fw)

        # 1. Exchange-qualified ticker anywhere near the top.
        m = re.search(
            r"\(\s*(?:NYSE|NASDAQ|Nasdaq|纳斯达克|纽交所)\s*[:：]?\s*"
            r"([A-Z.]{1,6})\s*\)", head)
        if m and m.group(1) in universe:
            return [m.group(1)]

        # 2. The (TICKER) in the title / first heading line.
        for line in head.splitlines()[:6]:
            if "(" not in line:
                continue
            for t in re.findall(r"\(\s*([A-Z]{1,6}(?:\.[A-Z])?)\s*\)", line):
                if t in universe:
                    return [t]
            if line.strip().startswith("#"):
                break

        # 2b. Title names the company, not the ticker (Chinese reports:
        #     `# 微软公司（Microsoft Corporation）...`). Resolve the
        #     heading line ONLY (peers appear in the body, never here).
        for line in head.splitlines()[:4]:
            s = line.strip().lstrip("#").strip()
            if not s:
                continue
            try:
                res = [t for t in self.retriever.entity.resolve(s)
                       if t in universe]
            except Exception:
                res = []
            if res:
                res.sort(key=lambda t: (s.count(t), len(t)), reverse=True)
                return [res[0]]
            break

        # 3. Explicit sector-comparison basket: "(AAA, BBB, CCC)".
        mb = re.search(r"\((?:[A-Z]{2,5},\s*)+[A-Z]{2,5}\)", head)
        if mb:
            bk = [t for t in re.findall(r"\b[A-Z.]{2,5}\b", mb.group(0))
                  if t in universe]
            if bk:
                return bk[:6]

        # 4. Fallback: most-frequent resolved symbol that is explicitly
        #    written as (T)/$T — never just the first peer mentioned.
        allt = self.retriever.entity.resolve(report)
        if not allt:
            return []

        def score(t: str) -> tuple:
            expl = (f"({t})" in report) or (f"${t}" in report)
            return (expl, report.count(t), len(t))

        best = max(allt, key=score)
        if len(best) <= 2 and not ((f"({best})" in report)
                                   or (f"${best}" in report)):
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

    # Stage-2 is a VETO (drop-only), not a precision gate, so the cap
    # must not be the limiter — restore the pre-c284915 budget (8). The
    # blunt cap=4 cut true positives faster than false ones. The veto
    # is the filter; _MAX_CANDIDATES only bounds verify LLM calls.
    _MAX_ISSUES = 8
    _MAX_CANDIDATES = 16
    _MAX_NARRATIVE = 4       # (legacy, unused by the propose-verify path)

    def run(self, report: str) -> list[ReviewIssue]:
        import sys
        import time

        def _log(m: str) -> None:
            print(f"[rev] {m}", file=sys.stderr, flush=True)

        t0 = time.time()
        anc = Anchored(report)
        _log("extracting claims (regex + LLM) ...")
        claims = self._extract(anc)
        primary = self._primary_ticker(report)

        det: list[dict] = []
        used: set[str] = set()
        # _period_end_candidates dropped: reports label quarters by
        # calendar end (2025-09-30) while non-calendar fiscal filers
        # (AVGO/NVDA/...) end elsewhere — a labeling convention, not an
        # injected error. It was a pure exact-tier FP generator.
        for c in (self._numeric_candidates(claims, primary)
                  + self._date_candidates(claims, primary)
                  + self._price_candidates(claims, primary)
                  + self._peer_candidates(claims, primary)
                  + self._arithmetic_candidates(claims)
                  + self._table_candidates(anc, primary)):
            if c["quote"] in used:
                continue
            det.append(c)
            used.add(c["quote"])

        # 1. Deterministic exact-tier pre-pass = precision anchors.
        #    Unambiguous, source-backed, language-agnostic — emit
        #    directly (through the drop-only veto). These hold precision.
        exact = self._veto_exact(
            [c for c in det if c.get("tier") == "exact"])

        issues: list[ReviewIssue] = []
        seen_raw: set[str] = set()
        for c in exact:
            raw = anc.find_raw(c["quote"])
            if not raw or raw in seen_raw:
                continue
            issues.append(ReviewIssue(
                quote=raw, reason=c.get("reason") or self._reason_from(c)))
            seen_raw.add(raw)

        # 2. Generate-style grounded check (recall, the main path):
        #    lock the subject, build the SAME authoritative context
        #    generate uses (exact FactStore block + retrieved passages),
        #    then walk the report section by section and let the LLM
        #    compare — language-agnostic, contradiction-only, grounded
        #    on exact facts so it cannot hallucinate truth.
        facts = self._facts_block(primary, anc.raw)
        try:
            _dense = self.retriever.dense_active()
        except Exception:
            _dense = False
        _log(f"retrieval: {'BM25+DENSE embeddings' if _dense else 'BM25-only'}")
        evidence = self._evidence_pool(primary, claims)
        sections = self._split_sections(anc.raw)
        _log(f"{len(claims)} claims, {len(exact)} det-exact emitted; "
             f"grounded check over {len(sections)} sections "
             f"(shared evidence pool) ...")
        # Propose-then-verify. Stage 1 (recall): the grounded check
        # surfaces many CANDIDATES — no hard cap kills true positives
        # here. Stage 2 (precision): each candidate gets its own focused
        # fact-check (targeted retrieval + strict confirm/reject). The
        # per-candidate loop is the precision gate, replacing the blunt
        # cap that was dropping real issues.
        cand: list[tuple[int, str, str]] = []
        for q, r in self._grounded_check(evidence, facts, sections):
            raw = anc.find_raw(q)
            if not raw or raw in seen_raw:
                continue
            seen_raw.add(raw)
            cand.append((self._ground_score(r), raw, r))
        cand.sort(key=lambda x: -x[0])
        cand = cand[:self._MAX_CANDIDATES]          # bound LLM calls only
        # The extract LLM already parsed each claim into structured
        # fields (sx). Index them so a candidate can carry its own
        # structured reading into verify — the verifier then compares
        # explicit ticker/period/metric/value instead of guessing which
        # fact the sentence refers to.
        sx_index = [(self._toks(Anchored.normalize(c["quote"])),
                     self._fmt_sx(c["sx"]))
                    for c in claims
                    if c.get("sx") and self._fmt_sx(c["sx"])]
        _log(f"{len(claims)} claims, {len(exact)} det-exact, "
             f"{len(cand)} candidates; verifying each ...")
        for _, raw, hint in cand:
            if len(issues) >= self._MAX_ISSUES:
                break
            ok = self._verify_issue(raw, hint, primary, facts,
                                    self._match_sx(raw, sx_index))
            if ok:
                issues.append(ReviewIssue(quote=raw, reason=ok))

        _log(f"done ({time.time() - t0:.1f}s, {len(issues)} issues)")
        return issues[:self._MAX_ISSUES]

    @staticmethod
    def _fmt_sx(sx: dict | None) -> str:
        """Compact one-line render of the first-stage structured parse
        of a claim (only the non-null fields). Empty if nothing useful."""
        if not isinstance(sx, dict):
            return ""
        parts: list[str] = []
        for k in ("ticker", "fy", "fq", "metric", "value", "direction",
                  "date", "form"):
            v = sx.get(k)
            if v not in (None, "", "null", "none", [], {}):
                parts.append(f"{k}={v}")
        pe = sx.get("peers")
        if isinstance(pe, list) and pe:
            parts.append(f"peers={','.join(map(str, pe[:12]))}")
        return "; ".join(parts)

    @staticmethod
    def _toks(s: str) -> set[str]:
        return set(re.findall(r"[A-Za-z0-9.]+|[一-鿿]", s or ""))

    @staticmethod
    def _match_sx(raw: str, sx_index: list[tuple[set, str]]) -> str:
        """Attach the structured parse of the extracted claim that best
        overlaps this candidate quote. Substring OR high token overlap
        (claim spans and grounded-candidate spans align loosely, not by
        containment). Best-effort — empty when nothing lines up."""
        nt = ReviewAgent._toks(Anchored.normalize(raw))
        if not nt:
            return ""
        best, bscore = "", 0.0
        for ctoks, sxs in sx_index:
            if not ctoks:
                continue
            inter = len(ctoks & nt)
            cov = inter / len(ctoks)            # how much of the claim
            if cov >= 0.6 and inter >= 4 and cov > bscore:
                best, bscore = sxs, cov
        return best

    def _verify_issue(self, quote: str, hint: str, primary: list[str],
                      facts: str, parse: str = "") -> str | None:
        """Stage-2 VETO (not a strict gate). Default KEEP — only drop a
        candidate the focused check says is clearly NOT an error. This
        preserves the pre-c284915 recall (a strict default-reject gate
        was cutting true positives faster than it cut false ones).
        Returns the (possibly refined) reason to keep, or None to drop.
        Any LLM/parse failure => KEEP with the first-stage reason."""
        try:
            res = self.retriever.search(
                quote[:600], top_k=5, tickers=primary or None)
            evidence = res.evidence_block()[:3000]
        except Exception:
            evidence = "(no passages)"
        try:
            raw = chat(
                [{"role": "user",
                  "content": self._verify_p.format(
                      quote=quote[:1200], hint=(hint or "")[:600],
                      parse=(parse or "(none)")[:500],
                      facts=facts[:6000], evidence=evidence)}],
                config=self.llm,
                **{**self.params,
                   "response_format": {"type": "json_object"}})
            data = parse_json_obj(raw)
        except Exception:
            return (hint or "").strip() or None       # fail-open: keep
        if not isinstance(data, dict):
            return (hint or "").strip() or None
        if str(data.get("verdict", "")).strip().lower() == "drop":
            return None
        # keep: prefer the verifier's refined reason, else the
        # first-stage hint.
        reason = str(data.get("reason", "")).strip()
        return reason or (hint or "").strip() or None

    @staticmethod
    def _ground_score(reason: str) -> int:
        """Higher = more defensible. Prefer contradictions backed by a
        structured corpus point or a hard number/date, then internal
        self-contradictions, over vague narrative ones."""
        r = reason or ""
        s = 1
        if re.search(r"earnings\.json|financials_reported|peers\.json|"
                     r"prices/|catalog|\.csv|8-?K|10-?[KQ]|accession|"
                     r"filed|披露|备案", r, re.I):
            s += 3
        if re.search(r"\d", r) and re.search(
                r"vs\.?|不是|并非|应为|实为|矛盾|contradict|not\b|"
                r"instead|而非", r, re.I):
            s += 2
        if re.search(r"自相矛盾|报告自身|上下文相反|前后|inconsistent", r):
            s += 2
        return s

    # ---- generate-style grounded sectioned review ------------------

    @staticmethod
    def _money(v) -> str:
        if not isinstance(v, (int, float)):
            return "?"
        a = abs(v)
        if a >= 1e9:
            return f"{v / 1e9:.3g}B"
        if a >= 1e6:
            return f"{v / 1e6:.3g}M"
        return f"{v:g}"

    def _subject_tickers(self, report: str,
                         primary: list[str]) -> list[str]:
        """Lock the subject(s). Chinese reports often miss the
        `(NYSE: X)` patterns, so fall back to whole-report entity
        resolution, keeping only tickers we actually have data for."""
        fs = self.retriever.fact_store
        have = set(fs._filings)
        try:
            have |= {t for t in self.retriever.subject_universe()}
        except Exception:
            pass
        out = [t for t in (primary or []) if t]
        if not out:
            try:
                out = self.retriever.entity.resolve(report)
            except Exception:
                out = []
        seen, keep = set(), []
        for t in out:
            if t in seen:
                continue
            seen.add(t)
            tf = None
            try:
                tf = fs.lookup(t)
            except Exception:
                pass
            if t in have or (tf and (tf.earnings or tf.financials
                                     or tf.peers or tf.prices)):
                keep.append(t)
        return keep[:4]

    def _facts_block(self, primary: list[str], report: str = "") -> str:
        """Review-specific RICH point list: every authoritative data
        point the LLM may need to align a claim to — all earnings rows,
        single+cumulative financials, filing dates, period ends, peer
        list, price anchors. Replaces generate's thin 9-line anchor
        block (the grounded path is only as good as this list)."""
        fs = self.retriever.fact_store
        tickers = self._subject_tickers(report, primary)
        if not tickers:
            return "(no subject resolved — no structured facts)"
        blocks: list[str] = []
        for tk in tickers:
            try:
                tf = fs.lookup(tk)
            except Exception:
                continue
            L = [f"=== {tk} ==="]
            # recent years only (reports reference 2024-2026); drop the
            # stale 2020-2022 noise and de-dupe (year,quarter).
            def _recent(rows):
                seen, keep = {}, []
                for r in sorted(rows, key=lambda r: (r.get("year") or 0,
                                                     r.get("quarter") or 0)):
                    if (r.get("year") or 0) < 2024:
                        continue
                    seen[(r.get("year"), r.get("quarter"))] = r
                for k in sorted(seen,
                                key=lambda k: (k[0] or 0, k[1] or 0)):
                    keep.append(seen[k])
                return keep

            ern = _recent(tf.earnings)
            if ern:
                L.append(f"EPS [research/{tk}/earnings.json] "
                         f"(actual/consensus/surprise):")
                for e in ern[-12:]:
                    sp = e.get("surprisePercent")
                    L.append(
                        f"  FY{e.get('year')} Q{e.get('quarter')} "
                        f"actual={e.get('actual')} est={e.get('estimate')} "
                        f"surprise={e.get('surprise')}"
                        + (f" ({sp:+.2f}%)"
                           if isinstance(sp, (int, float)) else ""))
            fin = _recent(tf.financials)
            if fin:
                L.append(f"Financials [research/{tk}/"
                         f"financials_reported.json] (single-quarter; "
                         f"cum=fiscal-YTD):")
                for f in fin[-8:]:
                    cum = ""
                    if f.get("cumulative"):
                        cum = (f" [9M/YTD cum rev="
                               f"{self._money(f.get('revenue_cum'))} "
                               f"ni={self._money(f.get('net_income_cum'))}]")
                    L.append(
                        f"  FY{f.get('year')} Q{f.get('quarter')} "
                        f"rev={self._money(f.get('revenue'))} "
                        f"ni={self._money(f.get('net_income'))} "
                        f"end={f.get('endDate')}{cum}")
            recs = fs._filings.get(tk, [])
            if recs:
                L.append("Filing dates [catalog]:")
                for r in sorted(recs, key=lambda x: x.get("date") or "")[:14]:
                    L.append(f"  {r.get('form')} filed {r.get('date')} "
                             f"(acc {r.get('accession')})")
            peers = list(tf.peers)
            if peers:
                L.append(f"Peers [research/{tk}/peers.json]: "
                         f"{', '.join(peers)}")
            yrs = sorted({d[:4] for d in tf.prices})
            for y in yrs[-2:]:
                try:
                    w = fs.price_window(tk, int(y))
                except Exception:
                    w = None
                if w:
                    ret = w.get("return_pct")
                    L.append(
                        f"Prices [prices/{tk}.csv] {y}: "
                        f"{w['first_date']} close={w['first']['close']} -> "
                        f"{w['last_date']} close={w['last']['close']}"
                        + (f" (calendar-year return {ret:+.1f}%)"
                           if isinstance(ret, (int, float)) else ""))
            blocks.append("\n".join(L))
        return "\n\n".join(blocks) if blocks else \
            "(no structured facts resolved)"

    @staticmethod
    def _split_sections(report: str) -> list[str]:
        """Split on markdown headers; merge tiny pieces; window very
        long ones. Falls back to the whole report when header-less."""
        lines = report.splitlines()
        secs: list[list[str]] = []
        cur: list[str] = []
        for ln in lines:
            if re.match(r"^\s{0,3}#{1,6}\s", ln) and cur:
                secs.append(cur)
                cur = [ln]
            else:
                cur.append(ln)
        if cur:
            secs.append(cur)
        out: list[str] = []
        buf = ""
        for s in secs:
            txt = "\n".join(s).strip()
            if not txt:
                continue
            if len(buf) + len(txt) < 1800:
                buf = (buf + "\n\n" + txt).strip()
            else:
                if buf:
                    out.append(buf)
                buf = txt
        if buf:
            out.append(buf)
        # window any oversized section
        final: list[str] = []
        for s in out or [report]:
            if len(s) <= 4000:
                final.append(s)
            else:
                for i in range(0, len(s), 3500):
                    final.append(s[i:i + 4000])
        return final[:12]

    def _evidence_pool(self, primary: list[str],
                       claims: list[dict]) -> str:
        """ONE strong generate-style retrieval, reused across every
        section. Per-section `sec[:1200]` queries were Chinese prose vs
        English filings (weak BM25, fragmented). The query here is the
        subject + the extracted claims — claims carry the specific
        numbers/dates/English entities that actually hit source text."""
        try:
            q = " ".join((primary or [])
                         + [c["quote"] for c in claims[:24]])
            res = self.retriever.search(
                q[:4000], top_k=14, tickers=primary or None)
            ev = res.evidence_block()
            return ev[:7000] if ev else "(no passages retrieved)"
        except Exception:
            return "(no passages retrieved)"

    def _grounded_check(self, evidence: str, facts: str,
                        sections: list[str]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for sec in sections:
            try:
                raw = chat(
                    [{"role": "user",
                      "content": self._grounded_p.format(
                          facts=facts[:9000], evidence=evidence,
                          section=sec[:4000])}],
                    config=self.llm,
                    **{**self.params,
                       "response_format": {"type": "json_object"}})
                data = parse_json_obj(raw)
            except Exception:
                continue
            for it in (data.get("issues", [])
                       if isinstance(data, dict) else []):
                if not isinstance(it, dict):
                    continue
                q = str(it.get("quote", "")).strip()
                r = str(it.get("reason", "")).strip()
                if q and r and q not in seen:
                    out.append((q, r))
                    seen.add(q)
        return out

    @staticmethod
    def _reason_from(c: dict) -> str:
        """Turn a verifier's evidence line into an emittable reason that
        cites the corpus source (matches the answer-key reason style)."""
        ev = (c.get("evidence") or "").strip()
        ev = re.sub(r"^DETERMINISTIC FACT\s*", "", ev)
        ev = re.sub(r"\[SOURCE:\s*([^\]]+)\]", r"Per corpus/\1,", ev, count=1)
        ev = re.sub(r"^arithmetic:\s*", "Arithmetic check: ", ev)
        return ev or "Contradicted by the structured corpus."

    # ---- step 1: extract -------------------------------------------

    def _extract(self, anc: Anchored) -> list[dict]:
        report = anc.raw
        out: list[dict] = []
        seen: set[str] = set()

        def add(q: str, kind: str = "other", sx: dict | None = None) -> None:
            q = Anchored.normalize(q)
            if not self._good_quote(q, anc):
                return
            # Keep the more complete quote when one contains another.
            for old in list(seen):
                if q != old and old in q and len(q) > len(old) + 12:
                    seen.remove(old)
                    out[:] = [x for x in out if x["quote"] != old]
                elif q != old and q in old:
                    # subsumed; still attach structured fields if the
                    # longer kept quote lacks them.
                    if sx:
                        for x in out:
                            if x["quote"] == old and not x.get("sx"):
                                x["sx"] = sx
                    return
            if q not in seen:
                out.append({"quote": q, "kind": kind,
                            "claim_type": self._claim_type(q),
                            "sx": sx})
                seen.add(q)
            elif sx:
                for x in out:
                    if x["quote"] == q and not x.get("sx"):
                        x["sx"] = sx

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
                add(c["quote"], c.get("kind", "other"), sx=c)

        out.sort(key=lambda x: self._claim_priority(x["quote"]), reverse=True)
        return out[:40]

    def _good_quote(self, q: str, anc: Anchored) -> bool:
        if not q or not anc.contains(q):
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
                    # Exact only when the period is fully pinned AND the
                    # matched row is that exact period. A claim with no
                    # year matches the first same-quarter row of ANY
                    # fiscal year, so the comparison is unreliable —
                    # demote to weak (LLM adjudicates) instead of
                    # direct-emitting a likely false positive.
                    pinned = (year is not None and quarter is not None
                              and row.get("year") == year
                              and row.get("quarter") == quarter)
                    out.append({"quote": q, "kind": "numeric",
                                "tier": "exact" if pinned else "weak",
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
                    "kind": "numeric", "tier": "weak"})
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
                    "quote": q, "kind": "date", "tier": "exact",
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
                    "kind": "date_timeline", "tier": "exact",
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
                        "kind": "derived_calculation", "tier": "exact",
                        "evidence": (
                            "DETERMINISTIC FACT [SOURCE: prices/"
                            f"{tk}.csv] " + "; ".join(facts)
                            + ". The claim's stated return/price calculation "
                              "does not match the price file.")})
                    break
        return out

    _NOT_TICKER = {"EPS", "FY", "QOQ", "YOY", "SEC", "NYSE", "NASDAQ",
                   "CIK", "GAAP", "USD", "CEO", "CFO", "AND", "THE", "US"}

    def _peer_candidates(self, claims: list[dict],
                         primary: list[str]) -> list[dict]:
        """The peer SUBJECT is the possessive company ("PFE's peer
        basket ...") or the report's primary — NOT the tickers listed
        inside the claim. Querying peers() with a listed peer (the old
        bug) made every peer-membership error invisible."""
        out: list[dict] = []
        universe = set(self.retriever.subject_universe())
        for c in claims:
            q = c["quote"]
            if not re.search(r"\bpeer", q, re.I) and not re.search(
                    r"同业|可比公司", q):
                continue
            subj = None
            m = re.search(r"\b([A-Z]{1,6})(?:'s|’s)\s+peer", q)
            if m and m.group(1) in universe:
                subj = m.group(1)
            if subj is None and len(primary) == 1 \
                    and primary[0] in universe:
                subj = primary[0]
            if subj is None:
                continue
            peers = self.retriever.fact_store.peers(subj)
            if not peers:
                continue
            peer_set = set(peers) - {subj}
            # Only the explicitly ENUMERATED list members are checkable.
            # Parse the region after "basket is / peers are / : / 为"
            # up to the first sentence/clause break — comparing the
            # whole sentence flagged correct lists (tickers from
            # surrounding prose) and tanked precision.
            em = re.search(
                r"(?:peers?(?:\s+(?:basket|list|group|set))?\s*"
                r"(?:is|are|:|=|包括|为)|peers\.json[^A-Za-z]{0,24})"
                r"(.+)", q, re.I | re.S)
            region = em.group(1) if em else ""
            region = re.split(r"[—–]|\s-\s|(?<=[A-Za-z])\.\s|;|\n|\(|（"
                              r"|\bwhich\b|\bincluding\b|\bversus\b",
                              region)[0]
            toks = [t for t in re.findall(r"\b[A-Z][A-Z.]{0,5}\b", region)
                    if t not in self._NOT_TICKER and t != subj]
            if len(toks) < 4:           # not a real enumerated list
                continue
            extras = sorted(set(toks) - peer_set)
            if not extras:
                continue
            out.append({
                "quote": q,
                "kind": "peer_membership", "tier": "exact",
                "evidence": (
                    f"DETERMINISTIC FACT [SOURCE: research/{subj}/"
                    f"peers.json] {subj}'s authoritative peer list is "
                    f"{sorted(peer_set)}. Claimed peers not in it: "
                    f"{', '.join(extras)}.")})
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
                    "kind": "derived_calculation", "tier": "weak",
                    "evidence": (
                        f"DETERMINISTIC FACT arithmetic: using {a:g} vs {b:g}, "
                        f"the derived change is {calc:+.1f}%, not {claimed:g}%. "
                        "The claim's stated magnitude or direction does not match.")})

        # Calendar-year / close-to-close return stated alongside the very
        # closes it is derived from — recompute from the report's own
        # numbers (source-free, near-zero false positives).
        _PX = r"\$?\s*\**\s*\$?\s*([\d,]+\.\d{2})"
        for c in claims:
            q = c["quote"]
            if q in {x["quote"] for x in out}:
                continue
            if not re.search(r"calendar-year|close-to-close|price\s+"
                             r"(?:gain|decline|return)|annual\s+return|"
                             r"年初至今|全年.{0,4}(?:涨幅|跌幅|回报|收益)",
                             q, re.I):
                continue
            sm = (re.search(r"close-to-close against" + _PX, q, re.I)
                  or re.search(r"opened[^$%]{0,40}?\$\s*([\d,]+\.\d{2})",
                               q, re.I)
                  or re.search(_PX + r"\s*(?:on\s+)?"
                               r"(?:January\s*2|Jan\.?\s*2|2025-01-02)",
                               q, re.I))
            em = (re.search(r"closed[^$%]{0,45}?\$\s*\**\s*([\d,]+\.\d{2})",
                            q, re.I)
                  or re.search(_PX + r"\s*(?:on\s+)?"
                               r"(?:December\s*31|Dec\.?\s*31|2025-12-31)",
                               q, re.I))
            pm = re.search(r"(-?\d+(?:\.\d+)?)\s*%", q)
            if not (sm and em and pm):
                continue
            start = float(sm.group(1).replace(",", ""))
            end = float(em.group(1).replace(",", ""))
            if start == 0:
                continue
            claimed = float(pm.group(1))
            calc = (end / start - 1) * 100
            if abs(claimed - calc) <= max(2.0, abs(calc) * 0.10):
                continue
            out.append({
                "quote": q,
                "kind": "derived_calculation", "tier": "exact",
                "evidence": (
                    f"DETERMINISTIC FACT arithmetic: close-to-close "
                    f"{start:g} -> {end:g} is {calc:+.1f}%, not the stated "
                    f"{claimed:g}%. The report's own prices contradict its "
                    f"computed return.")})
        return out

    # ---- step 2c: table-cell verifiers (EPS / nine-month) ----------

    @staticmethod
    def _first_num(s: str | None) -> float | None:
        ns = parse_numbers(s or "")
        return ns[0].value if ns else None

    def _eps_table_row(self, tk: str, y: int | None, q: int,
                       by: dict, qn: str) -> dict | None:
        row = self.retriever.fact_store.earnings_row(tk, y, q)
        if not row:
            return None
        av = self._first_num(col(by, "actual", "reported"))
        ev = self._first_num(col(by, "estimate", "consensus", "expected"))
        sp_cell = col(by, "surprise")
        ra, re_, rsp = (row.get("actual"), row.get("estimate"),
                        row.get("surprisePercent"))
        probs: list[str] = []
        if (av is not None and isinstance(ra, (int, float))
                and abs(av) <= 1000 and not approx_equal(av, ra)):
            probs.append(f"actual EPS stated {av:g}, verified {ra:g}")
        if (ev is not None and isinstance(re_, (int, float))
                and abs(ev) <= 1000 and not approx_equal(ev, re_)):
            probs.append(f"consensus/estimate stated {ev:g}, verified {re_:g}")
        if sp_cell and isinstance(rsp, (int, float)):
            spv = [n.value for n in parse_numbers(sp_cell) if n.is_pct]
            if spv and not approx_equal(spv[0], rsp, rel=0.15, abs_=0.6):
                probs.append(f"surprise stated {spv[0]:g}%, verified {rsp:g}%")
        if not probs:
            return None
        return {
            "quote": qn, "kind": "numeric", "tier": "exact",
            "evidence": (
                f"DETERMINISTIC FACT [SOURCE: research/{tk}/earnings.json] "
                f"{tk} FY{row.get('year')} Q{row.get('quarter')} earnings — "
                + "; ".join(probs) + ".")}

    def _ninemonth_table_row(self, tk: str, by: dict, tbl, qn: str,
                             is_ni: bool) -> dict | None:
        yrs = [int(x) for x in re.findall(
            r"20\d{2}", " ".join(tbl.headers) + " " + tbl.caption)]
        target = max(yrs) if yrs else 2025
        key = "net_income" if is_ni else "revenue"
        label = "nine-month net income" if is_ni else "nine-month revenue"
        cell = None
        for h, v in by.items():
            if str(target) in h and (is_ni and ("ni" in h or "net" in h)
                                     or (not is_ni and ("rev" in h
                                                        or "sales" in h))):
                cell = v
                break
        claimed = self._first_num(cell)
        if claimed is None or abs(claimed) < 1e6:
            return None
        rows = self.retriever.fact_store.period_rows(
            tk, year=target, quarter=3)
        if not rows:
            return None
        r = rows[0]
        if not r.get("cumulative"):
            return None
        truth = r.get(f"{key}_cum")
        if not isinstance(truth, (int, float)) or truth == 0:
            return None
        # FactStore concept selection is fuzzy for financial-sector
        # filers (it can latch onto a tiny line item). If the
        # authoritative figure is orders of magnitude off the claimed
        # one, it is a concept mis-pick, not a report error — skip
        # rather than emit a garbage deterministic issue.
        ratio = abs(claimed) / abs(truth)
        if ratio < 0.25 or ratio > 4.0:
            return None
        # high precision: only flag a clear, large mismatch
        if (not contradicts(claimed, truth, rel=0.12)
                or abs(claimed - truth) <= abs(truth) * 0.12):
            return None
        return {
            "quote": qn, "kind": "numeric", "tier": "exact",
            "evidence": (
                f"DETERMINISTIC FACT [SOURCE: research/{tk}/"
                f"financials_reported.json] {tk} FY{target} {label} "
                f"(through Q3) is {truth:,.0f}; the table states "
                f"{claimed:,.0f}, which does not match.")}

    def _table_candidates(self, anc: Anchored,
                          primary: list[str]) -> list[dict]:
        out: list[dict] = []
        universe = set(self.retriever.subject_universe())
        subj0 = (primary[0] if len(primary) == 1
                 and primary[0] in universe else None)
        for tbl in parse_tables(anc.raw):
            ctx = (" ".join(tbl.headers) + " " + tbl.caption).lower()
            hdr = " ".join(tbl.headers)
            is_eps = ("eps" in ctx or "earnings per share" in ctx
                      or (("actual" in hdr or "estimate" in hdr
                           or "consensus" in hdr) and "surprise" in hdr))
            nine = bool(re.search(
                r"9m\b|nine[- ]?months?|9-?month|九个月|前三季度|前三个季度",
                ctx))
            is_ni = ("net income" in ctx or "net inc" in ctx
                     or re.search(r"\bni\b", ctx) or "净利" in ctx)
            is_rev = ("revenue" in ctx or "sales" in ctx or "营收" in ctx)
            for row in tbl.rows:
                by = row["by"]
                qn = anc.normalize(row["raw"])
                if len(qn) < 8:
                    continue
                tk = None
                for v in by.values():
                    vv = (v or "").strip().upper()
                    if vv in universe:
                        tk = vv
                        break
                tk = tk or subj0
                if not tk:
                    continue
                rowtext = " ".join(str(v) for v in by.values())
                y, qq = _parse_period(rowtext + " " + tbl.caption)
                cand = None
                if is_eps and qq and y is not None:
                    cand = self._eps_table_row(tk, y, qq, by, qn)
                if cand is None and nine and (is_ni or is_rev):
                    cand = self._ninemonth_table_row(tk, by, tbl, qn, is_ni)
                if cand:
                    out.append(cand)
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

    # ---- exact-tier LLM veto gate (drop-only) ----------------------

    def _veto_exact(self, candidates: list[dict]) -> list[dict]:
        """One-directional precision gate: the LLM may only DROP a
        candidate whose claim was mis-parsed (a price/volume/year taken
        as EPS, a forecast taken as a reported figure, a period
        mismatch). It cannot re-derive, re-judge, or add. Any failure
        keeps everything — the deterministic verdict stays authoritative
        and the offline (no-LLM) path is unaffected."""
        if not candidates:
            return []
        items = "\n\n".join(
            f'[{i}] CLAIM: "{c["quote"][:600]}"\n'
            f'DETERMINISTIC FINDING: '
            f'{(c.get("reason") or self._reason_from(c))[:400]}'
            for i, c in enumerate(candidates))
        try:
            raw = chat(
                [{"role": "user",
                  "content": self._veto_p.format(items=items)}],
                config=self.llm,
                **{**self.params,
                   "response_format": {"type": "json_object"}})
            data = parse_json_obj(raw)
        except Exception:
            return candidates
        drop = data.get("drop", []) if isinstance(data, dict) else []
        if not isinstance(drop, list):
            return candidates
        drop_idx = {int(x) for x in drop
                    if isinstance(x, (int, str)) and str(x).strip().isdigit()}
        kept = [c for i, c in enumerate(candidates) if i not in drop_idx]
        # Guard against a degenerate "drop everything" reply: if the LLM
        # asks to drop all, distrust it and keep all (precision win must
        # not be wiped by one bad generation).
        return kept if kept else candidates

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
