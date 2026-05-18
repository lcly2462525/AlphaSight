"""Company-name / alias -> ticker resolution.

Topics say "Apple" or "the iPhone maker", not always `AAPL`. Missing the
ticker poisons the time-window + kind filters, so we resolve aggressively
from a static alias map plus exact ticker regex over catalog symbols.
"""

from __future__ import annotations

import re

# Curated aliases for the large-cap names in this universe. Lowercased
# substring match; keep terms distinctive to avoid false hits.
_ALIASES: dict[str, list[str]] = {
    "AAPL": ["apple", "iphone maker", "cupertino"],
    "MSFT": ["microsoft", "azure", "redmond"],
    "NVDA": ["nvidia", "jensen huang"],
    "AMZN": ["amazon", "aws"],
    "GOOGL": ["google", "alphabet", "waymo"],
    "GOOG": ["alphabet class c"],
    "META": ["meta platforms", "facebook", "instagram", "zuckerberg"],
    "TSLA": ["tesla", "elon musk"],
    "AMD": ["advanced micro devices", "lisa su"],
    "AVGO": ["broadcom"],
    "BRK.B": ["berkshire", "buffett"],
    "JPM": ["jpmorgan", "jp morgan"],
    "BAC": ["bank of america"],
    "WMT": ["walmart"],
    "COST": ["costco"],
    "HD": ["home depot"],
    "ABBV": ["abbvie"],
    "CAT": ["caterpillar"],
    "BA": ["boeing"],
    "AMT": ["american tower"],
    "AAL": ["american airlines"],
    "DAL": ["delta air"],
}


class EntityResolver:
    def __init__(self, symbols: list[str]) -> None:
        self._known = {s.upper() for s in symbols}
        if self._known:
            syms = sorted(self._known, key=len, reverse=True)
            self._sym_re = re.compile(
                r"\b(" + "|".join(re.escape(s) for s in syms) + r")\b"
            )
        else:
            self._sym_re = re.compile(r"(?!)")
        # only keep aliases whose ticker is actually in this universe
        self._alias = {
            tk: terms for tk, terms in _ALIASES.items()
            if tk in self._known
        }

    def resolve(self, text: str) -> list[str]:
        hits: set[str] = set()
        for m in self._sym_re.finditer(text):
            hits.add(m.group(1).upper())
        low = text.lower()
        for tk, terms in self._alias.items():
            if any(term in low for term in terms):
                hits.add(tk)
        return sorted(hits)
