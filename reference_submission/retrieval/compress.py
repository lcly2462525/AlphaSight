"""In-chunk compression: keep query-relevant sentences within a budget.

Truncation throws away mid/late content; sentence scoring keeps the
signal-dense parts (numbers, dates) and discards filler.
"""

from __future__ import annotations

import re

from retrieval.textutil import split_sentences, tokenize

_NUMERIC = re.compile(r"\d|%|\$")


def compress_chunk(text: str, query_tokens: set[str], budget: int) -> str:
    if len(text) <= budget:
        return text
    sents = split_sentences(text)
    if len(sents) <= 1:
        return text[:budget]
    scored = []
    for idx, s in enumerate(sents):
        toks = set(tokenize(s))
        score = len(toks & query_tokens)
        if _NUMERIC.search(s):  # financial anchors are high value
            score += 1
        scored.append((score, idx, s))
    scored.sort(key=lambda x: (-x[0], x[1]))
    kept: list[tuple[int, str]] = []
    used = 0
    for score, idx, s in scored:
        if score <= 0 and kept:
            break
        if used + len(s) > budget:
            continue
        kept.append((idx, s))
        used += len(s) + 1
    if not kept:
        return text[:budget]
    kept.sort(key=lambda x: x[0])
    return " ... ".join(s for _, s in kept)
