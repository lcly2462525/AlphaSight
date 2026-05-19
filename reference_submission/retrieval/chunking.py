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
_MIN_SECTION = 300          # shorter => TOC remnant / empty, drop
_MAX_SECTION = 90_000       # bound the trailing exhibits/financials dump
_SEP = r"[.\s\-—:]{0,4}"

# Identify the RELEVANT sections by canonical Item + its standardized
# title. An in-body cross-reference ("see Item 7 below") lacks the full
# title, so it cannot false-match a section header. Order matters:
# longer/more-specific titles (7A, 1A) are tried before 7/1.
_SECTION_PATTERNS: list[tuple[str, "re.Pattern"]] = [
    ("item 1a", re.compile(r"item\s+1a\b" + _SEP + r"risk\s+factors",
                            re.I)),
    ("item 7a", re.compile(r"item\s+7a\b" + _SEP +
                           r"quantitative\s+and\s+qualitative", re.I)),
    ("item 7",  re.compile(r"item\s+7\b" + _SEP +
                           r"management.{0,3}s?\s+discussion", re.I)),
    ("item 2",  re.compile(r"item\s+2\b" + _SEP +
                           r"management.{0,3}s?\s+discussion", re.I)),
    ("item 8",  re.compile(r"item\s+8\b" + _SEP +
                           r"financial\s+statements", re.I)),
    ("item 1",  re.compile(r"item\s+1\b" + _SEP + r"business\b", re.I)),
    ("item 2.02", re.compile(r"item\s+2\.02\b" + _SEP +
                             r"results\s+of\s+operations", re.I)),
    ("item 8.01", re.compile(r"item\s+8\.01\b" + _SEP +
                             r"other\s+events", re.I)),
    ("item 7.01", re.compile(r"item\s+7\.01\b" + _SEP +
                             r"regulation\s+fd", re.I)),
]


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


# A real header is `Item N <sep> <CanonicalTitle> <prose>`. Reject:
#  - TOC entries: title is followed by `<pagenum> Item|Part`
#  - the rest is handled implicitly: cross-refs ("Item 1A of this Form
#    10-K under the heading ...") put non-sep words between the number
#    and the title, so the adjacency-constrained pattern never matches.
_TOC_TAIL = re.compile(r"\s*\d{1,4}\s+(item|part)\b", re.I)


def _split_items(text: str) -> list[tuple[str, str]]:
    """Identify the *real* SEC sections, then return (label, body).

    Derived from real filings (Workiva uses an em-dash header, Apple's
    own filer uses a period; both also carry a TOC and many in-body
    cross-references). Robust rule, generator-agnostic:

      1. A candidate header requires the canonical TITLE to sit
         immediately after the Item number (only `.`/`-`/`—`/`:` between)
         — this alone discards cross-refs like "Item 1A of this Form
         10-K under the heading 'Risk Factors'".
      2. Drop candidates whose title is followed by `<pagenum> Item`
         (table-of-contents lines).
      3. Among the survivors of each section key, the real body header
         is the one that begins the LONGEST run before the next
         survivor — TOC/xref copies sit in tight clusters, the body
         spans thousands of chars.
    """
    cands: list[tuple[int, str, str]] = []  # (pos, key, title)
    for key, rx in _SECTION_PATTERNS:
        for m in rx.finditer(text):
            tail = text[m.end():m.end() + 14]
            if _TOC_TAIL.match(tail):
                continue
            cands.append((m.start(), key, m.group(0)))
    if not cands:
        return [("", text)]
    cands.sort()
    positions = [p for p, _, _ in cands]
    # per key, keep the occurrence that starts the longest run
    best: dict[str, tuple[int, int, str]] = {}  # key -> (pos, span, ttl)
    for idx, (pos, key, ttl) in enumerate(cands):
        nxt = positions[idx + 1] if idx + 1 < len(positions) else len(text)
        span = nxt - pos
        if key not in best or span > best[key][1]:
            best[key] = (pos, span, ttl)
    heads = sorted((pos, key) for key, (pos, _, _) in best.items())
    segs: list[tuple[str, str]] = []
    for i, (pos, key) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        body = text[pos:min(end, pos + _MAX_SECTION)]
        if len(body) >= _MIN_SECTION:
            segs.append((key, body))
    return segs or [("", text)]


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
        # _split_items only matches the high-value sections (1A/7/7A/8
        # /MD&A/8-K events), so every returned section is chunked fully;
        # the "" fallback (no headers, e.g. 8-K/non-standard) windows
        # the whole doc.
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
