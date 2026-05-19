"""Kind-aware chunking. Preserve information instead of truncating.

filing  -> SEC Item-aware sliding windows (Item 1A/7/8 carry the alpha)
news    -> title is its own high-signal chunk + body windows
social  -> already short; one chunk
research -> handled by FactStore, raw only as fallback
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")
_ITEM_RE = re.compile(
    r"(item\s+\d+[a-z]?\.?\s+[A-Z][^.\n]{0,80})", re.IGNORECASE)


@dataclass
class Chunk:
    path: str
    text: str
    kind: str
    section: str = ""


def _windows(text: str, size: int, overlap: int) -> list[str]:
    text = _WS.sub(" ", text).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    out, i, n = [], 0, len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            sp = text.rfind(" ", i + size - overlap, end)
            if sp > i:
                end = sp
        seg = text[i:end].strip()
        if seg:
            out.append(seg)
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return out


def _split_items(text: str) -> list[tuple[str, str]]:
    """Split a filing into (section_label, body) on SEC Item anchors."""
    marks = list(_ITEM_RE.finditer(text))
    if len(marks) < 2:
        return [("", text)]
    segs: list[tuple[str, str]] = []
    for i, m in enumerate(marks):
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        label = _WS.sub(" ", m.group(1)).strip()[:60]
        segs.append((label, text[start:end]))
    return segs


def _is_natural(text: str) -> bool:
    """Reject residual binary/garbage chunks (defense in depth).

    Natural prose has mostly letters+spaces and regular word spacing;
    decoded binary has few spaces, many symbols, huge "words".
    """
    n = len(text)
    if n < 1:
        return False
    letters = sum(c.isalpha() for c in text)
    spaces = sum(c == " " for c in text)
    # loose: financial tables are number-dense but still real prose;
    # the space + word-length checks are the real binary discriminators
    if letters / n < 0.45:
        return False
    if spaces / n < 0.08:               # binary blobs lack word spacing
        return False
    longest = max((len(w) for w in text.split()), default=0)
    return longest <= 40               # no 200-char "tokens"


def _mk(path, text, kind, section, out):
    if _is_natural(text):
        out.append(Chunk(path, text, kind, section))


def chunk_doc(path: str, text: str, kind: str) -> list[Chunk]:
    if not text:
        return []
    out: list[Chunk] = []
    if kind == "filing":
        for label, body in _split_items(text):
            for w in _windows(body, 1100, 150):
                _mk(path, w, kind, label, out)
        return out
    if kind == "news":
        head, _, rest = text.partition("\n")
        if head.strip():
            _mk(path, head.strip(), kind, "title", out)
        for w in _windows(rest or text, 800, 120):
            _mk(path, w, kind, "body", out)
        return out
    if kind == "social":
        for t in _windows(text, 1000, 0):
            _mk(path, t, kind, "social", out)
        return out
    for w in _windows(text, 1200, 100):
        _mk(path, w, kind, "", out)
    return out
