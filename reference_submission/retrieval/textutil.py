"""Tokenization, document text extraction, sentence splitting.

Single source of truth for turning raw corpus files into clean text so
chunking / BM25 / compression all agree on the same representation.
"""

from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path

_EN_WORD = re.compile(r"[A-Za-z0-9]{2,}")
_CN_CHAR = re.compile(r"[一-鿿]")
_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "has", "have", "had", "its", "our", "their", "they", "will",
    "would", "could", "should", "been", "being", "than", "then", "into",
    "such", "also", "any", "all", "may", "can", "but", "not", "which",
}


def tokenize(text: str) -> list[str]:
    en = [w for w in (m.lower() for m in _EN_WORD.findall(text))
          if w not in _STOP]
    cn = _CN_CHAR.findall(text)
    return en + cn


# Some "filings" (all form=ARS) are raw PDFs / images renamed to .htm.
# Reading them as text yields binary garbage that pollutes BM25 and the
# LLM prompt, so they must be rejected at ingestion.
_BIN_MAGIC = (b"%PDF", b"\x7fELF", b"PK\x03\x04", b"\xff\xd8\xff",
              b"\x89PNG", b"GIF8", b"\x1f\x8b")
_SCRIPT_STYLE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_DATA_URI = re.compile(r"data:[^\s\"')]+", re.IGNORECASE)
_B64_RUN = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")


def _looks_binary(data: bytes) -> bool:
    if data[:4] in _BIN_MAGIC or data[:5] == b"%PDF-" or \
            any(data.startswith(m) for m in _BIN_MAGIC):
        return True
    sample = data[:65536]
    if not sample:
        return True
    nul_ctrl = sum(1 for b in sample
                   if b == 0 or (b < 9) or (13 < b < 32))
    nonascii = sum(1 for b in sample if b > 126)
    n = len(sample)
    return (nul_ctrl / n > 0.02) or (nonascii / n > 0.30)


def strip_html(raw: str) -> str:
    raw = _SCRIPT_STYLE.sub(" ", raw)
    raw = _DATA_URI.sub(" ", raw)
    raw = _HTML_TAG.sub(" ", raw)
    raw = _B64_RUN.sub(" ", raw)
    # SEC filings keep entities (&#8212; em-dash, &#160; nbsp, &#8217;
    # apostrophe). Decode so headers/numbers/quotes are real text.
    raw = html.unescape(raw)
    raw = raw.replace("\xa0", " ")
    return _WS.sub(" ", raw).strip()


def split_sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split(text)
    return [s.strip() for s in parts if s.strip()]


def _read_filing(p: Path) -> str:
    data = p.read_bytes()
    if _looks_binary(data):
        return ""
    return strip_html(data.decode("utf-8", errors="ignore"))


def _read_news(p: Path) -> str:
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(d, dict):
        return ""
    parts = [str(d.get(k, "")) for k in ("title", "text", "summary",
                                         "description")]
    return "\n".join(x for x in parts if x).strip()


def _read_social(p: Path) -> str:
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, ValueError):
        return ""
    rows = d.get("data") if isinstance(d, dict) else d
    if not isinstance(rows, list):
        return ""
    out = []
    for t in rows[:40]:
        if isinstance(t, dict) and isinstance(t.get("text"), str):
            out.append(t["text"])
    return "\n".join(out).strip()


def _read_research(p: Path) -> str:
    # research goes through FactStore; raw text only as last-resort context.
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, ValueError):
        return ""
    return json.dumps(d, ensure_ascii=False)[:20000]


@lru_cache(maxsize=8192)
def doc_text(path_str: str, kind: str) -> str:
    p = Path(path_str)
    if not p.exists():
        return ""
    try:  # cheap magic sniff: reject any binary masquerading as text
        with p.open("rb") as fh:
            if any(fh.read(8).startswith(m) for m in _BIN_MAGIC):
                return ""
    except OSError:
        return ""
    if kind == "filing":
        return _read_filing(p)
    if kind == "news":
        return _read_news(p)
    if kind == "social":
        return _read_social(p)
    if kind == "research":
        return _read_research(p)
    return p.read_text(encoding="utf-8", errors="ignore")


def news_title(path_str: str) -> str:
    p = Path(path_str)
    if not p.exists():
        return ""
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        return str(d.get("title", "")) if isinstance(d, dict) else ""
    except (json.JSONDecodeError, ValueError):
        return ""
