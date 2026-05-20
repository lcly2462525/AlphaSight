#!/usr/bin/env python3
"""Build dataset/time_index.json from the structured corpus.

See docs/timestamp/BUILD_AND_IMPLEMENTATION.md §4. v2 schema produces:

  per-ticker:
    * filings_by_accession  — canonical filing date with cross-source
                              attest (filename+catalog+sec_subm+fil_json)
                              + accepted_utc / accepted_et / rolls_over_day
                              for the after-close-rolls-over-a-day case
    * filings_by_form       — sorted unique date list per form
    * fiscal_periods        — (fy, fq) -> (start, end) from
                              financials_reported.json (sole truth source;
                              earnings.period explicitly excluded)
    * earnings_periods      — (fy, fq) -> actual/estimate/calendar_label
                              from earnings.json. `calendar_label` is
                              EXPLICITLY marked: it is the Finnhub
                              calendar-quarter-end label, NOT the fiscal
                              period end. Stored so Review can detect
                              claims that confuse the two.
  top-level:
    * trading_days          — global sorted list of trading dates (union
                              across all prices/*.csv)
    * _meta                 — build_at, version, source stats

Pure stdlib, no LLM. Idempotent (output overwrites). Runs in seconds.

Usage:
    python reference_submission/build_time_index.py
    python reference_submission/build_time_index.py --dataset DIR --out PATH
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# allow running as script from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from retrieval.timeparse import (
    parse_filing_filename, parse_iso_z, parse_space_naive_et)


def _norm_form(s: str) -> str:
    return (s or "").upper().replace(" ", "").strip()


def _day(s: str | None) -> str | None:
    """First 10 chars if YYYY-MM-DD prefix, else None."""
    if not s or not isinstance(s, str):
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def _vote(dates: dict[str, str]) -> tuple[str | None, str]:
    """Pick the canonical date and a consistency tag from sources.

    dates: {source_name: YYYY-MM-DD} — caller filters out None values.
    Returns (canonical_date, consistency) where consistency is:
      'ok'       — all sources agree (>=2 sources, fully unanimous)
      'partial'  — only one source had a value, others were absent
      'conflict' — multiple sources, not unanimous (canonical = mode)
      and (None, 'missing') if dates is empty.
    """
    if not dates:
        return None, "missing"
    vals = list(dates.values())
    if len(vals) == 1:
        return vals[0], "partial"
    counts = Counter(vals)
    canon, _ = counts.most_common(1)[0]
    if len(counts) == 1:
        return canon, "ok"
    return canon, "conflict"


# ----------------------------------------------------------- per-ticker

def collect_ticker(ticker: str, ds: Path,
                   catalog_by_acc: dict[str, dict]) -> dict:
    out_fba: dict[str, dict] = {}            # filings_by_accession
    out_fbf: dict[str, set[str]] = {}        # filings_by_form -> set of dates
    out_fp:  dict[str, dict] = {}            # fiscal_periods

    # --- src1: filename ----------------------------------------------
    filings_dir = ds / "corpus/filings" / ticker
    src_filename: dict[str, tuple[str, str]] = {}   # acc -> (form, date)
    if filings_dir.is_dir():
        for fp in filings_dir.iterdir():
            if fp.suffix.lower() != ".htm":
                continue
            parsed = parse_filing_filename(fp.name)
            if parsed:
                form, date, acc = parsed
                src_filename[acc] = (_norm_form(form), date)

    # --- src2: catalog.jsonl (already grouped by symbol) -------------
    src_catalog: dict[str, tuple[str, str]] = {}   # acc -> (form, date)
    for acc, row in catalog_by_acc.items():
        if ticker not in (row.get("symbols") or []):
            continue
        d = _day(row.get("timestamp"))
        if d:
            src_catalog[acc] = (_norm_form(row.get("form", "")), d)

    # --- src3: sec_submissions.json (columnar) ------------------------
    # Also captures acceptanceDateTime (UTC ISO-Z) per accession.
    src_secsubm: dict[str, tuple[str, str]] = {}        # acc -> (form, day)
    accept_utc: dict[str, str] = {}                     # acc -> UTC Z ISO
    p_ss = ds / "corpus/research" / ticker / "sec_submissions.json"
    if p_ss.exists():
        try:
            ss = json.loads(p_ss.read_text("utf-8"))
            recent = (ss.get("data") or {}).get("filings", {}).get("recent", {})
            accs = recent.get("accessionNumber") or []
            forms = recent.get("form") or []
            fdates = recent.get("filingDate") or []
            adts = recent.get("acceptanceDateTime") or []
            for i, acc in enumerate(accs):
                if not acc:
                    continue
                d = _day(fdates[i] if i < len(fdates) else None)
                if d:
                    src_secsubm[acc] = (
                        _norm_form(forms[i] if i < len(forms) else ""), d)
                adt = adts[i] if i < len(adts) else None
                if adt:
                    a = parse_iso_z(adt)
                    if a and a.instant_utc:
                        accept_utc[acc] = a.instant_utc
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    # --- src4: filings.json (list of dicts) --------------------------
    # Also captures acceptedDate (ET naive) per accession — secondary
    # source for instant, used when sec_submissions lacks one.
    src_filjson: dict[str, tuple[str, str]] = {}        # acc -> (form, day)
    accept_et_naive: dict[str, str] = {}                # acc -> raw ET str
    p_fj = ds / "corpus/research" / ticker / "filings.json"
    if p_fj.exists():
        try:
            fj = json.loads(p_fj.read_text("utf-8"))
            for r in (fj.get("data") or []):
                acc = r.get("accessNumber") or r.get("accessionNumber")
                d = _day(r.get("filedDate"))
                if acc and d:
                    src_filjson[acc] = (_norm_form(r.get("form", "")), d)
                ad = r.get("acceptedDate")
                if acc and isinstance(ad, str) and ad.strip():
                    accept_et_naive[acc] = ad.strip()
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    # --- merge --------------------------------------------------------
    all_accs = (set(src_filename) | set(src_catalog) |
                set(src_secsubm) | set(src_filjson))
    for acc in all_accs:
        sources: dict[str, str] = {}
        forms_seen: list[str] = []
        for key, src_map in (("filename", src_filename),
                             ("catalog",  src_catalog),
                             ("sec_subm", src_secsubm),
                             ("fil_json", src_filjson)):
            if acc in src_map:
                form, date = src_map[acc]
                sources[key] = date
                if form:
                    forms_seen.append(form)
        canon_date, consistency = _vote(sources)
        if canon_date is None:
            continue
        # form: filename > sec_submissions > filings.json > catalog
        form_canon = ""
        for prefer in ("filename", "sec_subm", "fil_json", "catalog"):
            if prefer in src_filename and prefer == "filename":
                form_canon = src_filename[acc][0]; break
            if prefer == "sec_subm" and acc in src_secsubm:
                form_canon = src_secsubm[acc][0]; break
            if prefer == "fil_json" and acc in src_filjson:
                form_canon = src_filjson[acc][0]; break
            if prefer == "catalog" and acc in src_catalog:
                form_canon = src_catalog[acc][0]; break
        # accept instants: prefer sec_submissions (tz-explicit UTC),
        # fall back to filings.json (ET naive) → derive UTC + ET views.
        utc_iso = accept_utc.get(acc)
        et_iso: str | None = None
        if utc_iso:
            from datetime import datetime, timezone
            try:
                from zoneinfo import ZoneInfo
                _ET = ZoneInfo("America/New_York")
                dt_u = datetime.strptime(
                    utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                et_iso = dt_u.astimezone(_ET).strftime("%Y-%m-%dT%H:%M:%S%z")
            except (ImportError, ValueError):
                et_iso = None
        elif acc in accept_et_naive:
            anc = parse_space_naive_et(accept_et_naive[acc])
            if anc:
                utc_iso = anc.instant_utc
                et_iso = anc.instant_et

        rolls_over = False
        if utc_iso and et_iso:
            rolls_over = (utc_iso[:10] != et_iso[:10])

        rec = {
            "form": form_canon,
            "date": canon_date,
            "sources": sources,
            "consistency": consistency,
        }
        if utc_iso:
            rec["accepted_utc"] = utc_iso
        if et_iso:
            rec["accepted_et"] = et_iso
        if rolls_over:
            rec["rolls_over_day"] = True
        out_fba[acc] = rec
        if form_canon:
            out_fbf.setdefault(form_canon, set()).add(canon_date)

    # --- fiscal periods (financials_reported only) -------------------
    p_fr = ds / "corpus/research" / ticker / "financials_reported.json"
    if p_fr.exists():
        try:
            fr = json.loads(p_fr.read_text("utf-8"))
            rows = ((fr.get("data") or {}).get("data") or [])
            for r in rows:
                try:
                    fy = int(r.get("year"))
                    fq = int(r.get("quarter"))
                except (TypeError, ValueError):
                    continue
                start = _day(r.get("startDate"))
                end = _day(r.get("endDate"))
                if not (start and end) or not (1 <= fq <= 4):
                    continue
                key = f"{fy}|{fq}"
                # keep the latest-filed entry per (fy,fq) — restatements
                filed_d = _day(r.get("filedDate")) or ""
                prev = out_fp.get(key)
                if prev and prev.get("_filed", "") >= filed_d:
                    continue
                out_fp[key] = {
                    "fy": fy, "fq": fq,
                    "start": start, "end": end,
                    "form": _norm_form(r.get("form", "")),
                    "source": f"research/{ticker}/financials_reported.json",
                    "_filed": filed_d,
                }
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        for v in out_fp.values():
            v.pop("_filed", None)

    # --- earnings periods (from earnings.json) -----------------------
    # Stored SEPARATELY from fiscal_periods. `calendar_label` is the
    # Finnhub `period` value — a calendar-quarter-end LABEL, never a
    # fiscal period end. The explicit field name + `_warning` keep
    # downstream from confusing the two (the FP that got
    # `_period_end_candidates` dropped earlier was exactly this trap).
    out_ep: dict[str, dict] = {}
    p_er = ds / "corpus/research" / ticker / "earnings.json"
    if p_er.exists():
        try:
            er = json.loads(p_er.read_text("utf-8"))
            rows = er.get("data") or []
            for r in rows:
                try:
                    fy = int(r.get("year"))
                    fq = int(r.get("quarter"))
                except (TypeError, ValueError):
                    continue
                if not (1 <= fq <= 4):
                    continue
                lbl = _day(r.get("period"))
                key = f"{fy}|{fq}"
                rec_e: dict = {
                    "fy": fy, "fq": fq,
                    "calendar_label": lbl,           # Finnhub label (chimera)
                    "actual": r.get("actual"),
                    "estimate": r.get("estimate"),
                    "surprise": r.get("surprise"),
                    "surprise_percent": r.get("surprisePercent"),
                    "source": f"research/{ticker}/earnings.json",
                    "_warning": ("calendar_label is the Finnhub period field "
                                 "(calendar-quarter-end label); it is NOT "
                                 "the fiscal-period end — use fiscal_periods "
                                 "for that."),
                }
                out_ep[key] = rec_e
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    return {
        "filings_by_accession": out_fba,
        "filings_by_form": {f: sorted(ds) for f, ds in out_fbf.items()},
        "fiscal_periods": out_fp,
        "earnings_periods": out_ep,
    }


# --------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    ap.add_argument("--dataset", type=Path, default=here.parent / "dataset",
                    help="dataset root (default: <repo>/dataset)")
    ap.add_argument("--out", type=Path,
                    default=here.parent / "dataset/time_index.json",
                    help="output time_index.json")
    args = ap.parse_args()

    ds: Path = args.dataset
    out_p: Path = args.out

    # discover tickers from filings dir (full set should also be in research)
    filings_root = ds / "corpus/filings"
    research_root = ds / "corpus/research"
    if not research_root.is_dir():
        raise SystemExit(f"no research dir: {research_root}")
    tickers = sorted(
        {p.name for p in research_root.iterdir() if p.is_dir()
         and not p.name.startswith(".")}
        | ({p.name for p in filings_root.iterdir() if p.is_dir()
            and not p.name.startswith(".")} if filings_root.is_dir() else set())
    )

    # preload catalog rows indexed by accession (one read, used per ticker)
    catalog_by_acc: dict[str, dict] = {}
    cat = ds / "catalog.jsonl"
    if cat.exists():
        with cat.open(encoding="utf-8") as fh:
            for ln in fh:
                try:
                    o = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if o.get("kind") != "filing":
                    continue
                acc = ""
                pth = o.get("path") or ""
                # catalog path: filings/TICKER/FORM__YYYY-MM-DD__ACC.htm
                if pth:
                    name = pth.rsplit("/", 1)[-1]
                    parsed = parse_filing_filename(name)
                    if parsed:
                        acc = parsed[2]
                if acc:
                    catalog_by_acc[acc] = o

    index: dict[str, dict] = {}
    totals = {"accessions": 0, "fiscal_periods": 0, "earnings_periods": 0,
              "conflicts": 0, "partials": 0, "rolls_over": 0}
    for tk in tickers:
        d = collect_ticker(tk, ds, catalog_by_acc)
        if (d["filings_by_accession"] or d["filings_by_form"]
                or d["fiscal_periods"] or d["earnings_periods"]):
            index[tk] = d
            totals["accessions"] += len(d["filings_by_accession"])
            totals["fiscal_periods"] += len(d["fiscal_periods"])
            totals["earnings_periods"] += len(d["earnings_periods"])
            for v in d["filings_by_accession"].values():
                if v["consistency"] == "conflict":
                    totals["conflicts"] += 1
                elif v["consistency"] == "partial":
                    totals["partials"] += 1
                if v.get("rolls_over_day"):
                    totals["rolls_over"] += 1

    # ----- trading_days (global, union over all prices/*.csv) ---------
    trading: set[str] = set()
    prices_root = ds / "prices"
    if prices_root.is_dir():
        for pf in prices_root.iterdir():
            if pf.suffix.lower() != ".csv":
                continue
            try:
                with pf.open(encoding="utf-8") as fh:
                    next(fh, "")           # header
                    for ln in fh:
                        d = ln.split(",", 1)[0].strip()
                        if _day(d):
                            trading.add(d)
            except OSError:
                continue
    trading_sorted = sorted(trading)

    # ----- _meta ------------------------------------------------------
    from datetime import datetime, timezone as _tz
    meta = {
        "built_at": datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "v2",
        "tickers": len(index),
        "accessions": totals["accessions"],
        "consistency": {
            "ok": totals["accessions"] - totals["partials"]
                   - totals["conflicts"],
            "partial": totals["partials"],
            "conflict": totals["conflicts"],
        },
        "accessions_with_day_rollover": totals["rolls_over"],
        "fiscal_periods": totals["fiscal_periods"],
        "earnings_periods": totals["earnings_periods"],
        "trading_days": len(trading_sorted),
    }
    payload = {"_meta": meta, "trading_days": trading_sorted, **index}

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(
        json.dumps(payload, ensure_ascii=False,
                   sort_keys=True, indent=1),
        encoding="utf-8")

    print(f"time_index v2: {len(index)} tickers, "
          f"{totals['accessions']} accessions "
          f"(ok={meta['consistency']['ok']} partial={totals['partials']} "
          f"conflict={totals['conflicts']} day_rollover={totals['rolls_over']}), "
          f"{totals['fiscal_periods']} fiscal + "
          f"{totals['earnings_periods']} earnings periods, "
          f"{len(trading_sorted)} trading days "
          f"-> {out_p}", file=sys.stderr)


if __name__ == "__main__":
    main()
