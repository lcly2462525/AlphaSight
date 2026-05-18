"""Tokenization, document text extraction, sentence splitting.

Single source of truth for turning raw corpus files into clean text so
chunking / BM25 / compression all agree on the same representation.
"""

from __future__ import annotations

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


def strip_html(raw: str) -> str:
    raw = _HTML_TAG.sub(" ", raw)
    return _WS.sub(" ", raw).strip()


def split_sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split(text)
    return [s.strip() for s in parts if s.strip()]


def _read_filing(p: Path) -> str:
    return strip_html(p.read_text(encoding="utf-8", errors="ignore"))


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
