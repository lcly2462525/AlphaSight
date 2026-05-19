"""Offline builder: news_merged/*.jsonl  ->  catalog supplement.

The processed `dataset/corpus/news_merged/<T>.jsonl` files hold 149K
LLM-extracted atomic events (one sentence each, with polarity /
attributed_to / timestamp / scope). The online retriever is entirely
catalog-driven, so these events are invisible until they appear in the
catalog. This script materializes one `DocMeta`-shaped row per *unique*
event into a SEPARATE supplement file — the organizer-provided
`catalog.jsonl` is never touched. `load_catalog` concatenates the
supplement when ALPHASIGHT_CATALOG_SUPPLEMENT points at it.

Design notes (see plan):
  * kind = "news_event": its own kind so `_CAND_CAP` / `kind_bias`
    target it directly and it stays symbol-scoped (not path-scoped).
  * symbols come from `source_paths` ticker segments + the file's own
    ticker — `subject[].mention` is free-text company names and is NOT
    a reliable ticker key.
  * The same event_id appears in multiple <T>.jsonl files (multi-symbol
    articles); dedupe by event_id, union the symbols.
  * `event_text` is rendered here once and stored in `extra` so the
    online path does zero file I/O and the chunk survives compression
    (always < _CHUNK_BUDGET).
  * `path` = a representative real source news file so the evidence
    `[SOURCE: ...]` citation stays verifiable.

Run once after extracting raw news:

    python reference_submission/tools/build_news_event_catalog.py \
        --news-merged dataset/corpus/news_merged \
        --out dataset/news_event_catalog.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SELF = Path(__file__).resolve()
sys.path.insert(0, str(_SELF.parent.parent))  # reference_submission/

from schemas import DocMeta  # noqa: E402

_TEXT_CAP = 1000  # keep event_text well under retrieval _CHUNK_BUDGET=1200


def _tickers_from_sources(source_paths: list[str]) -> set[str]:
    """`news/<TICKER>/<hash>.json` -> {TICKER}. The reliable anchor."""
    out: set[str] = set()
    for sp in source_paths or []:
        parts = str(sp).split("/")
        if len(parts) >= 3 and parts[0] == "news" and parts[1]:
            out.add(parts[1])
    return out


def _render_event_text(rec: dict) -> str:
    """Compact, single-line, high-signal string.

    `[EVENT <date> | <polarity> | src: <attributed_to> | via <provider>
      | <scope>] <event sentence> [horizon: <h>]`

    Conditional segments are omitted when absent (polarity/attributed_to
    are frequently missing). No event_id / sha256 in the text (would be
    a 64-char token and add no retrieval signal); provenance lives in
    the [SOURCE: ...] line and in `extra`.
    """
    date = str(rec.get("timestamp", ""))[:10]
    seg = [f"EVENT {date}"] if date else ["EVENT"]
    if rec.get("polarity"):
        seg.append(str(rec["polarity"]))
    if rec.get("attributed_to"):
        seg.append(f"src: {rec['attributed_to']}")
    if rec.get("provider"):
        seg.append(f"via {rec['provider']}")
    if rec.get("scope"):
        seg.append(str(rec["scope"]))
    head = "[" + " | ".join(seg) + "] "
    body = str(rec.get("event", "")).strip()
    txt = head + body
    if rec.get("horizon"):
        txt += f" [horizon: {rec['horizon']}]"
    return txt[:_TEXT_CAP]


def build(news_merged: Path, out: Path) -> int:
    files = sorted(news_merged.glob("*.jsonl"))
    if not files:
        print(f"error: no *.jsonl under {news_merged}", file=sys.stderr)
        return 2

    # event_id -> aggregated row state
    events: dict[str, dict] = {}
    n_lines = n_bad = n_skip = 0

    for fp in files:
        file_ticker = fp.stem  # e.g. "BRK.B"
        with fp.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                n_lines += 1
                try:
                    rec = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    n_bad += 1
                    continue
                eid = rec.get("event_id")
                ts = rec.get("timestamp")
                ev = (rec.get("event") or "").strip()
                if not eid or not ts or not ev:
                    n_skip += 1  # DocMeta needs a timestamp; no text => no signal
                    continue
                syms = _tickers_from_sources(rec.get("source_paths"))
                syms.add(file_ticker)
                cur = events.get(eid)
                if cur is None:
                    sp = rec.get("source_paths") or []
                    events[eid] = {
                        "rec": rec,
                        "symbols": syms,
                        "path": sp[0] if sp else f"news_merged/{file_ticker}.jsonl",
                    }
                else:
                    cur["symbols"] |= syms  # multi-symbol article seen again

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    n_written = 0
    pol = Counter()
    # deterministic order -> reproducible, diff-friendly supplement
    for eid in sorted(events):
        st = events[eid]
        rec = st["rec"]
        text = _render_event_text(rec)
        if not text or len(text) < 12:
            n_skip += 1
            continue
        row = DocMeta(
            path=st["path"],
            kind="news_event",
            symbols=sorted(st["symbols"]),
            timestamp=rec["timestamp"],
            form=None,
            source_url=rec.get("provider"),
            extra={
                "event_id": eid,
                "event_text": text,
                "polarity": rec.get("polarity"),
                "attributed_to": rec.get("attributed_to"),
                "provider": rec.get("provider"),
                "scope": rec.get("scope"),
                "source_paths": rec.get("source_paths") or [],
            },
        )
        if n_written == 0:
            tmp_fh = tmp.open("w", encoding="utf-8")
        tmp_fh.write(row.model_dump_json() + "\n")
        pol[rec.get("polarity") or "(none)"] += 1
        n_written += 1

    if n_written == 0:
        print("error: produced 0 rows", file=sys.stderr)
        return 2
    tmp_fh.close()
    tmp.replace(out)

    print(f"news_merged files     : {len(files)}")
    print(f"lines read            : {n_lines}")
    print(f"unique events written : {n_written}  -> {out}")
    print(f"skipped (no ts/text)  : {n_skip}   bad json: {n_bad}")
    print(f"polarity distribution : {dict(pol)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--news-merged", type=Path,
                    default=Path("dataset/corpus/news_merged"),
                    help="dir of <TICKER>.jsonl event files")
    ap.add_argument("--out", type=Path,
                    default=Path("dataset/news_event_catalog.jsonl"),
                    help="supplement output (never the organizer catalog)")
    args = ap.parse_args(argv)
    return build(args.news_merged, args.out)


if __name__ == "__main__":
    sys.exit(main())
