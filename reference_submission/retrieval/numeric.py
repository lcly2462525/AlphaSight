"""Financial number normalization + tolerant comparison.

`$6.5B`, `5.5 billion`, `1,200 million`, `(1.2)`, `12%` must all reduce
to a comparable scalar so the deterministic fact-check (used by both
generate self-audit and review verifier) does not mis-fire.
"""

from __future__ import annotations

import re

_MULT = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}

# $6.5B / 5.5 billion / 1,200 million / (1.2) / 12%
_NUM_RE = re.compile(
    r"(?P<paren>\()?\s*\$?\s*"
    r"(?P<num>-?\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<mult>k|mm?|mn|bn?|tn?|thousand|million|billion|trillion)?\s*"
    r"(?P<pct>%)?\s*\)?",
    re.IGNORECASE,
)


class Num:
    __slots__ = ("value", "is_pct", "raw")

    def __init__(self, value: float, is_pct: bool, raw: str) -> None:
        self.value = value
        self.is_pct = is_pct
        self.raw = raw

    def __repr__(self) -> str:  # pragma: no cover
        return f"Num({self.value!r}, pct={self.is_pct}, raw={self.raw!r})"


def parse_numbers(text: str) -> list[Num]:
    """Extract every money/percent magnitude from a string."""
    out: list[Num] = []
    for m in _NUM_RE.finditer(text):
        raw_num = m.group("num")
        if raw_num in (None, "", "-"):
            continue
        try:
            val = float(raw_num.replace(",", ""))
        except ValueError:
            continue
        mult = (m.group("mult") or "").lower()
        if mult:
            val *= _MULT.get(mult, 1.0)
        if m.group("paren"):  # accounting negative: (1.2)
            val = -abs(val)
        out.append(Num(val, bool(m.group("pct")), m.group(0).strip()))
    return out


def approx_equal(a: float, b: float, *, rel: float = 0.02,
                  abs_: float = 1e-6) -> bool:
    if a == b:
        return True
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def contradicts(claimed: float, truth: float, *, rel: float = 0.05) -> bool:
    """True when `claimed` is far enough from `truth` to flag as wrong.

    Looser than ``approx_equal`` on purpose: the verifier should only
    raise issues it can defend, not nitpick rounding.
    """
    if truth == 0:
        return abs(claimed) > max(1.0, abs(claimed) * rel)
    return abs(claimed - truth) > abs(truth) * max(rel, 0.05)
