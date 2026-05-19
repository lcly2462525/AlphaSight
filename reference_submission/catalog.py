"""Load and filter catalog.jsonl → list[DocMeta]."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable

from schemas import DocMeta


def _read_jsonl_docs(path: Path, docs: list[DocMeta]) -> None:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(DocMeta.model_validate_json(line))


def load_catalog(path: str | Path) -> list[DocMeta]:
    docs: list[DocMeta] = []
    _read_jsonl_docs(Path(path), docs)
    # Optional, strictly-additive supplement (e.g. the news_merged event
    # stream). The organizer-provided catalog file is only ever read; the
    # supplement is concatenated when ALPHASIGHT_CATALOG_SUPPLEMENT points
    # at an existing file, else behaviour is byte-identical to before.
    sup = os.environ.get("ALPHASIGHT_CATALOG_SUPPLEMENT")
    if sup and Path(sup).exists():
        _read_jsonl_docs(Path(sup), docs)
    return docs


def collect_symbols(docs: Iterable[DocMeta]) -> list[str]:
    """Distinct symbols seen across the catalog."""
    out: set[str] = set()
    for d in docs:
        for s in d.symbols:
            if s:
                out.add(s)
    return sorted(out)


_NEVER = re.compile(r"(?!)")


def build_symbol_re(symbols: Iterable[str]) -> re.Pattern[str]:
    """Word-bounded regex matching any of the given symbols.

    Sorted longest-first so multi-part tickers like `BRK.B` match in
    full instead of being shadowed by the shorter `BRK` alternative.
    Each symbol is `re.escape`d, so dotted tickers behave correctly.
    """
    syms = sorted({s for s in symbols if s}, key=len, reverse=True)
    if not syms:
        return _NEVER
    return re.compile(r"\b(" + "|".join(re.escape(s) for s in syms) + r")\b")


def filter_docs(
    docs: list[DocMeta],
    *,
    kinds: list[str] | None = None,
    symbols: list[str] | None = None,
    time_range: tuple[str, str] | None = None,
    forms: list[str] | None = None,
) -> list[DocMeta]:
    out = []
    for d in docs:
        if kinds and d.kind not in kinds:
            continue
        if symbols and not set(d.symbols) & set(symbols):
            continue
        if forms and d.form not in forms:
            continue
        if time_range:
            lo, hi = time_range
            ts = (d.timestamp or "")[:10]
            if not (lo <= ts <= hi):
                continue
        out.append(d)
    return out
