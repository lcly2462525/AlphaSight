"""Whitespace-tolerant claim anchoring.

The single biggest review bug: claims are matched/emitted as *verbatim*
substrings, but reports wrap sentences and bullets across newlines, so a
normalized claim ("PFE's peer basket is LLY, JNJ, ...") is never an exact
substring and is silently dropped before any verifier sees it.

`Anchored` builds a whitespace-collapsed view of the report plus an
index map back to the raw text. Verifiers run on the normalized view
(format-agnostic); whatever they flag is re-anchored to the *original*
raw span so the emitted quote stays a true verbatim substring.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


class Anchored:
    def __init__(self, report: str) -> None:
        self.raw = report
        chars: list[str] = []
        idx: list[int] = []          # normalized pos -> raw pos
        prev_space = False
        for i, c in enumerate(report):
            if c.isspace():
                if not prev_space and chars:
                    chars.append(" ")
                    idx.append(i)
                prev_space = True
            else:
                chars.append(c)
                idx.append(i)
                prev_space = False
        # drop a trailing collapsed space
        if chars and chars[-1] == " ":
            chars.pop()
            idx.pop()
        self.norm = "".join(chars)
        self._idx = idx
        self._lower = self.norm.lower()

    @staticmethod
    def normalize(text: str) -> str:
        return _WS.sub(" ", text or "").strip()

    def find_raw(self, quote: str) -> str | None:
        """Return the original raw span whose normalized form == quote,
        or None if the (normalized) quote does not occur in the report."""
        q = self.normalize(quote)
        if not q:
            return None
        p = self.norm.find(q)
        if p < 0:
            p = self._lower.find(q.lower())
            if p < 0:
                return None
        raw_start = self._idx[p]
        raw_end = self._idx[p + len(q) - 1]
        return self.raw[raw_start:raw_end + 1]

    def contains(self, quote: str) -> bool:
        return self.find_raw(quote) is not None
