"""Structured Fact Store: research/*.json + prices/*.csv -> exact facts.

`research` is structured numbers; running BM25 over it is wasteful and
imprecise. We extract it (plus OHLCV) into a per-ticker fact table that
is (a) injected into the generate prompt as verified anchors and (b)
queried by the review verifier for deterministic number checks.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Revenue / net-income concept aliases seen in financials_reported.json
_REV = ("RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet")
_NI = ("NetIncomeLoss", "ProfitLoss",
       "NetIncomeLossAvailableToCommonStockholdersBasic")


@dataclass
class TickerFacts:
    ticker: str
    earnings: list[dict] = field(default_factory=list)   # eps actual/est/surprise
    financials: list[dict] = field(default_factory=list)  # rev / ni per quarter
    prices: dict[str, dict] = field(default_factory=dict)  # date -> ohlcv
    peers: list[str] = field(default_factory=list)


class FactStore:
    def __init__(self, corpus_dir: Path, prices_dir: Path,
                 catalog: list | None = None) -> None:
        self._research = corpus_dir / "research"
        self._prices = prices_dir
        # per-ticker filing metadata from the catalog (authoritative
        # filed dates; the path encodes form__YYYY-MM-DD__accession)
        self._filings: dict[str, list[dict]] = {}
        for d in catalog or []:
            if getattr(d, "kind", None) != "filing":
                continue
            stem = Path(d.path).stem
            parts = stem.split("__")
            acc = parts[2] if len(parts) > 2 else ""
            date = (d.timestamp or "")[:10]
            for s in d.symbols or []:
                self._filings.setdefault(s, []).append({
                    "form": (d.form or (parts[0] if parts else "")),
                    "date": date, "accession": acc, "path": d.path})

    @lru_cache(maxsize=64)
    def _load(self, ticker: str) -> TickerFacts:
        tf = TickerFacts(ticker=ticker)
        self._load_earnings(ticker, tf)
        self._load_financials(ticker, tf)
        self._load_peers(ticker, tf)
        self._load_prices(ticker, tf)
        return tf

    def earnings_row(self, ticker: str, year: int | None,
                     quarter: int | None) -> dict | None:
        """Full earnings row (actual/estimate/surprise/surprisePercent)
        for a fiscal period — enables per-field verification."""
        for e in self._load(ticker).earnings:
            if year is not None and e.get("year") != year:
                continue
            if quarter is not None and e.get("quarter") != quarter:
                continue
            return e
        return None

    def filings_of(self, ticker: str, form: str | None = None,
                   accession: str | None = None) -> list[dict]:
        """Filing-date records for a ticker, optionally filtered by form
        prefix (10-K matches 10-K/A too) or exact accession."""
        rows = self._filings.get(ticker, [])
        out = []
        for r in rows:
            if accession and accession not in r["accession"]:
                continue
            if form and not r["form"].upper().startswith(form.upper()):
                continue
            out.append(r)
        return out

    def _load_earnings(self, ticker: str, tf: TickerFacts) -> None:
        p = self._research / ticker / "earnings.json"
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8")).get("data", [])
        except (json.JSONDecodeError, ValueError, OSError):
            return
        for r in data if isinstance(data, list) else []:
            if isinstance(r, dict) and r.get("actual") is not None:
                tf.earnings.append(r)

    def _load_financials(self, ticker: str, tf: TickerFacts) -> None:
        p = self._research / ticker / "financials_reported.json"
        if not p.exists():
            return
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            return
        rows = (((blob.get("data") or {}).get("data")) or [])
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            concepts: dict[str, float] = {}
            for sec in ("ic", "bs", "cf"):
                for item in (r.get("report", {}) or {}).get(sec, []) or []:
                    c = item.get("concept", "")
                    v = item.get("value")
                    if isinstance(v, (int, float)):
                        concepts[c] = v
            rev = next((concepts[k] for k in concepts
                        if any(x in k for x in _REV)), None)
            ni = next((concepts[k] for k in concepts
                       if any(x in k for x in _NI)), None)
            tf.financials.append({
                "year": r.get("year"), "quarter": r.get("quarter"),
                "form": r.get("form"), "revenue": rev, "net_income": ni,
                "startDate": (r.get("startDate") or "")[:10],
                "endDate": (r.get("endDate") or "")[:10],
                "filedDate": (r.get("filedDate") or "")[:10],
            })

    def _load_peers(self, ticker: str, tf: TickerFacts) -> None:
        p = self._research / ticker / "peers.json"
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8")).get("data", [])
        except (json.JSONDecodeError, ValueError, OSError):
            return
        if isinstance(data, list):
            tf.peers = [str(x).upper() for x in data if isinstance(x, str)]

    def _load_prices(self, ticker: str, tf: TickerFacts) -> None:
        p = self._prices / f"{ticker}.csv"
        if not p.exists():
            return
        try:
            with p.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    d = row.get("date")
                    if not d:
                        continue
                    try:
                        tf.prices[d] = {
                            "open": float(row["open"]),
                            "close": float(row["close"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "volume": float(row["volume"]),
                        }
                    except (KeyError, ValueError):
                        continue
        except OSError:
            return

    # ---- public API -------------------------------------------------

    def facts_block(self, tickers: list[str],
                     window: tuple[str, str] | None) -> str:
        """Human-readable verified-anchor block for the generate prompt."""
        lines: list[str] = []
        for tk in tickers[:4]:
            tf = self._load(tk)
            for e in tf.earnings[:5]:
                lines.append(
                    f"[SOURCE: research/{tk}/earnings.json] {tk} "
                    f"FY{e.get('year')}Q{e.get('quarter')} EPS "
                    f"actual={e.get('actual')} est={e.get('estimate')} "
                    f"surprise={e.get('surprise')} "
                    f"({e.get('surprisePercent')}%)")
            for f in tf.financials[:3]:
                if f["revenue"] is not None or f["net_income"] is not None:
                    lines.append(
                        f"[SOURCE: research/{tk}/financials_reported.json] "
                        f"{tk} FY{f['year']}Q{f['quarter']} "
                        f"revenue={f['revenue']} net_income={f['net_income']}")
            days = sorted(tf.prices)
            if window:
                win = [d for d in days if window[0] <= d <= window[1]]
                days = win or days
            if days:
                a, b = days[0], days[-1]
                c0 = tf.prices[a]["close"]
                c1 = tf.prices[b]["close"]
                ret = f"{(c1 / c0 - 1) * 100:+.1f}%" if c0 else "NA"
                lines.append(
                    f"[SOURCE: prices/{tk}.csv] {tk} {a} close={c0} -> "
                    f"{b} close={c1} ({ret} over window)")
        return "\n".join(lines) if lines else "(no structured facts resolved)"

    def lookup(self, ticker: str) -> TickerFacts:
        return self._load(ticker)

    def peers(self, ticker: str) -> list[str]:
        return list(self._load(ticker).peers)

    def period_rows(self, ticker: str, *,
                    year: int | None = None,
                    quarter: int | None = None) -> list[dict]:
        out = []
        for f in self._load(ticker).financials:
            if year is not None and f.get("year") != year:
                continue
            if quarter is not None and f.get("quarter") != quarter:
                continue
            out.append(f)
        return out

    def price_on(self, ticker: str, date: str) -> dict | None:
        return self._load(ticker).prices.get(date)

    def price_window(self, ticker: str, year: int) -> dict | None:
        prices = self._load(ticker).prices
        days = sorted(d for d in prices if d.startswith(f"{year}-"))
        if not days:
            return None
        first, last = days[0], days[-1]
        first_row = prices[first]
        last_row = prices[last]
        c0 = first_row.get("close")
        c1 = last_row.get("close")
        ret = (c1 / c0 - 1) * 100 if c0 else None
        return {
            "first_date": first,
            "last_date": last,
            "first": first_row,
            "last": last_row,
            "return_pct": ret,
        }

    def metric(self, ticker: str, metric: str, *,
               year: int | None = None,
               quarter: int | None = None) -> list[dict]:
        """Period-aligned metric rows for one ticker.

        metric in {"eps", "revenue", "net_income"}. When year/quarter are
        given, returns only the matching fiscal period(s); otherwise all
        known rows. Each row: {year, quarter, value, source}.
        """
        tf = self._load(ticker)
        out: list[dict] = []
        if metric == "eps":
            for e in tf.earnings:
                v = e.get("actual")
                if not isinstance(v, (int, float)):
                    continue
                if year is not None and e.get("year") != year:
                    continue
                if quarter is not None and e.get("quarter") != quarter:
                    continue
                out.append({"year": e.get("year"),
                            "quarter": e.get("quarter"), "value": v,
                            "source": f"research/{ticker}/earnings.json"})
        elif metric in ("revenue", "net_income"):
            for f in tf.financials:
                v = f.get(metric)
                if not isinstance(v, (int, float)):
                    continue
                if year is not None and f.get("year") != year:
                    continue
                if quarter is not None and f.get("quarter") != quarter:
                    continue
                out.append({"year": f.get("year"),
                            "quarter": f.get("quarter"), "value": v,
                            "source": f"research/{ticker}/"
                                      f"financials_reported.json"})
        return out
