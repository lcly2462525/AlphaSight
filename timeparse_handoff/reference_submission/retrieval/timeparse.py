"""Time-anchor parsing + canonical time index for Review/Generate.

See docs/timestamp/BUILD_AND_IMPLEMENTATION.md for the full design. This module is
pure stdlib, no LLM calls. Two parts:

  * parsers   — convert each known dataset timestamp format to a canonical
                ET calendar day (and optionally a UTC instant). Used at
                build time and by ad-hoc callers.
  * TimeIndex — runtime API loaded from dataset/time_index.json (built by
                build_time_index.py). Gives Review the cross-source
                authoritative date for any (ticker, accession) or
                (ticker, fy, fq) and the set of filing dates per form.

Design constraints (from docs/timestamp/archive/timestamp_analysis.md §3-§4):
  - T1-only: only filings + fiscal periods + price sessions enter the
    index. news/social publication times and `_meta.fetched_at` are out.
  - Canonical date is the ET calendar day (申报语义); for UTC-Z inputs
    the ET day is computed by tz-aware conversion (this is what catches
    after-close filings that roll over a calendar day in UTC).
  - `earnings.json.period` is the Finnhub calendar-quarter-end label,
    NEVER stored as fiscal_period.end. Only `financials_reported`
    populates the fiscal bridge.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except ImportError:  # very old python — fall back to fixed -05:00
    _ET = timezone.utc  # caller should not hit this on Python 3.9+


_DEFAULT_INDEX_PATH = Path(__file__).resolve().parents[2] / "dataset/time_index.json"


# ----------------------------------------------------------------- model

@dataclass
class TimeAnchor:
    entity: str
    concept: str                # filed | period_end | period_start | ...
    date: str                   # YYYY-MM-DD, ET calendar day
    instant_utc: str | None
    instant_et:  str | None
    precision:   str            # day | second
    fiscal:      tuple[int, int] | None
    source:      str
    raw:         str


# --------------------------------------------------------------- parsers

_ISO_Z_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?Z$")
_SPACE_NAIVE_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$")
_DATE_ONLY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
# corpus/filings filename:  FORM__YYYY-MM-DD__ACCESSION.htm
# FORM may contain hyphens (10-K, 10-Q, 8-K, DEF 14A→DEF14A); accession
# is 10-2-6 digits with hyphens.
_FNAME_RE = re.compile(
    r"^([A-Z0-9\-]+(?:\s*\d+[A-Z]?)?)__"
    r"(\d{4}-\d{2}-\d{2})__"
    r"(\d{10}-\d{2}-\d{6})\.htm$",
    re.I)
# Twitter created_at: "Wed Jan 01 15:00:02 +0000 2025"
_TWITTER_FMT = "%a %b %d %H:%M:%S %z %Y"


def parse_iso_z(s: str, *, entity: str = "", concept: str = "",
                source: str = "") -> TimeAnchor | None:
    """`...T..:..:..(.fff)Z` (news.published_at, sec acceptanceDateTime).
    UTC instant; canonical date is the ET calendar day (after-close
    filings roll forward in UTC but stay on ET filing day — we want ET)."""
    m = _ISO_Z_RE.match(s)
    if not m:
        return None
    y, mo, d, h, mi, se = (int(g) for g in m.groups())
    dt_utc = datetime(y, mo, d, h, mi, se, tzinfo=timezone.utc)
    dt_et = dt_utc.astimezone(_ET)
    return TimeAnchor(
        entity=entity, concept=concept,
        date=dt_et.strftime("%Y-%m-%d"),
        instant_utc=dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        instant_et=dt_et.strftime("%Y-%m-%dT%H:%M:%S%z"),
        precision="second",
        fiscal=None, source=source, raw=s,
    )


def parse_space_naive_et(s: str, *, entity: str = "", concept: str = "",
                          source: str = "") -> TimeAnchor | None:
    """`YYYY-MM-DD HH:MM:SS` (filings.json acceptedDate / financials).
    Treat as **ET naive** and attach America/New_York. filedDate where
    the time is 00:00:00 is recognized as day-precision masquerade and
    downgraded to precision=day (no instant)."""
    m = _SPACE_NAIVE_RE.match(s)
    if not m:
        return None
    y, mo, d, h, mi, se = (int(g) for g in m.groups())
    is_midnight = h == 0 and mi == 0 and se == 0
    date_str = f"{y:04d}-{mo:02d}-{d:02d}"
    if is_midnight:
        return TimeAnchor(
            entity=entity, concept=concept,
            date=date_str, instant_utc=None, instant_et=None,
            precision="day", fiscal=None, source=source, raw=s,
        )
    dt_et = datetime(y, mo, d, h, mi, se, tzinfo=_ET)
    dt_utc = dt_et.astimezone(timezone.utc)
    return TimeAnchor(
        entity=entity, concept=concept, date=date_str,
        instant_utc=dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        instant_et=dt_et.strftime("%Y-%m-%dT%H:%M:%S%z"),
        precision="second", fiscal=None, source=source, raw=s,
    )


def parse_date_only(s: str, *, entity: str = "", concept: str = "",
                    source: str = "") -> TimeAnchor | None:
    """`YYYY-MM-DD` (filenames / catalog / sec_submissions.filingDate /
    prices.date). Day precision."""
    if not _DATE_ONLY_RE.match(s):
        return None
    return TimeAnchor(
        entity=entity, concept=concept, date=s,
        instant_utc=None, instant_et=None,
        precision="day", fiscal=None, source=source, raw=s,
    )


def parse_twitter_created_at(s: str, *, entity: str = "",
                              source: str = "") -> TimeAnchor | None:
    """`Wed Jan 01 15:00:02 +0000 2025` — kept for completeness; social
    is T2 by §3.1 and does NOT enter time_index."""
    try:
        dt = datetime.strptime(s, _TWITTER_FMT)
    except ValueError:
        return None
    dt_utc = dt.astimezone(timezone.utc)
    dt_et = dt_utc.astimezone(_ET)
    return TimeAnchor(
        entity=entity, concept="published",
        date=dt_et.strftime("%Y-%m-%d"),
        instant_utc=dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        instant_et=dt_et.strftime("%Y-%m-%dT%H:%M:%S%z"),
        precision="second", fiscal=None, source=source, raw=s,
    )


def parse_filing_filename(name: str) -> tuple[str, str, str] | None:
    """`FORM__YYYY-MM-DD__ACCESSION.htm` → (form, date, accession), or
    None if not a recognized filing filename."""
    m = _FNAME_RE.match(name)
    if not m:
        return None
    form = m.group(1).upper().replace(" ", "")
    return form, m.group(2), m.group(3)


def parse_temporal(raw: str, *, entity: str = "", concept: str = "",
                   source: str = "") -> TimeAnchor | None:
    """Smart dispatcher. Tries formats in order of specificity."""
    if not isinstance(raw, str) or not raw:
        return None
    s = raw.strip()
    for fn in (parse_iso_z, parse_space_naive_et, parse_date_only):
        a = fn(s, entity=entity, concept=concept, source=source)
        if a is not None:
            return a
    return parse_twitter_created_at(s, entity=entity, source=source)


# ------------------------------------------------------------ TimeIndex

_TOP_RESERVED = {"_meta", "trading_days"}


class TimeIndex:
    """Read-only query API over the prebuilt time_index.json (schema v2).

    Top-level:
      _meta              build metadata (built_at, schema_version, stats)
      trading_days       global sorted ["YYYY-MM-DD", ...]
      <TICKER>           per-ticker subtables (see below)

    Per-ticker:
      filings_by_accession[acc] = {
          "form": str, "date": YYYY-MM-DD,
          "sources": {filename, catalog, sec_subm, fil_json},
          "consistency": "ok" | "partial" | "conflict",
          "accepted_utc": "YYYY-MM-DDTHH:MM:SSZ"   (optional),
          "accepted_et":  "YYYY-MM-DDTHH:MM:SS-04/-05" (optional),
          "rolls_over_day": True   (optional, ET day ≠ UTC day)}
      filings_by_form[form] = sorted unique [YYYY-MM-DD, ...]
      fiscal_periods["fy|fq"] = {
          "fy": int, "fq": int, "start": YYYY-MM-DD, "end": YYYY-MM-DD,
          "form": str, "source": str}
      earnings_periods["fy|fq"] = {
          "fy", "fq", "calendar_label" (Finnhub period, NOT fiscal end),
          "actual", "estimate", "surprise", "surprise_percent",
          "source", "_warning"}
    """

    def __init__(self, data: dict) -> None:
        self._d = data or {}
        td = self._d.get("trading_days") or []
        self._td_set: set[str] = set(td) if isinstance(td, list) else set()

    @classmethod
    def empty(cls) -> "TimeIndex":
        return cls({})

    @classmethod
    def load(cls, path: Path | str = _DEFAULT_INDEX_PATH) -> "TimeIndex":
        p = Path(path)
        with p.open(encoding="utf-8") as fh:
            return cls(json.load(fh))

    # ---- filing queries -----------------------------------------------

    def filing_by_accession(self, ticker: str, acc: str) -> dict | None:
        return (self._d.get(ticker, {})
                .get("filings_by_accession", {})
                .get(acc))

    def filing_dates_of_form(self, ticker: str, form: str) -> list[str]:
        form_norm = (form or "").upper().replace(" ", "")
        return list((self._d.get(ticker, {})
                     .get("filings_by_form", {})
                     .get(form_norm, [])))

    def has_filing_conflict(self, ticker: str, acc: str) -> bool:
        rec = self.filing_by_accession(ticker, acc)
        return bool(rec and rec.get("consistency") not in (None, "ok"))

    # ---- fiscal-period queries ----------------------------------------

    def fiscal_period(self, ticker: str, fy: int, fq: int) -> dict | None:
        return (self._d.get(ticker, {})
                .get("fiscal_periods", {})
                .get(f"{fy}|{fq}"))

    def earnings_period(self, ticker: str, fy: int, fq: int) -> dict | None:
        return (self._d.get(ticker, {})
                .get("earnings_periods", {})
                .get(f"{fy}|{fq}"))

    # ---- trading-day queries ------------------------------------------

    def is_trading_day(self, date: str) -> bool:
        return date in self._td_set

    def trading_days(self) -> list[str]:
        return list(self._d.get("trading_days") or [])

    # ---- meta ----------------------------------------------------------

    def meta(self) -> dict:
        return dict(self._d.get("_meta") or {})

    def tickers(self) -> list[str]:
        return sorted(k for k in self._d.keys() if k not in _TOP_RESERVED)

    def __bool__(self) -> bool:
        return any(k for k in self._d.keys() if k not in _TOP_RESERVED)
