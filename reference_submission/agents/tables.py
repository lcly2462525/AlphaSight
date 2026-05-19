"""Markdown table parsing for the review verifier.

Reports inject errors inside table cells (`| Q4 2025 | $14.01 |
$13.5000 | +3.8% |`, `| 4 | MS | $13.46B | $9.68B | +39.1% |`). The
prose-oriented claim regex never parses these, so a whole class of
numeric mutations went uncaught. We parse each pipe table into
(headers, rows) and keep, per row, the verbatim raw line so the emitted
quote is still a substring of the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


@dataclass
class Table:
    headers: list[str]
    rows: list[dict] = field(default_factory=list)   # {by:{hdr:cell}, raw}
    caption: str = ""                                  # nearest line above


def parse_tables(report: str) -> list[Table]:
    lines = report.splitlines()
    out: list[Table] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.count("|") >= 2 and i + 1 < n and _SEP_RE.match(lines[i + 1]):
            headers = [h.lower() for h in _cells(line)]
            caption = ""
            k = i - 1
            while k >= 0:
                t = lines[k].strip().lstrip("#").strip()
                if t:
                    caption = t
                    break
                k -= 1
            tbl = Table(headers=headers, caption=caption)
            j = i + 2
            while j < n and lines[j].count("|") >= 2 \
                    and not _SEP_RE.match(lines[j]):
                cells = _cells(lines[j])
                if any(c for c in cells):
                    by = {headers[c]: cells[c]
                          for c in range(min(len(headers), len(cells)))}
                    tbl.rows.append({"by": by, "raw": lines[j]})
                j += 1
            if tbl.rows:
                out.append(tbl)
            i = j
            continue
        i += 1
    return out


def col(by: dict, *keywords: str) -> str | None:
    """First cell whose header contains any keyword (substring, lower)."""
    for h, v in by.items():
        if any(kw in h for kw in keywords):
            return v
    return None
