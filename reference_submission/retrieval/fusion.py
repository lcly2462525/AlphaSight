"""Weighted Reciprocal Rank Fusion of the sparse and dense rankings.

RRF needs no score normalization across the two heterogeneous channels;
the router supplies per-query weights and a per-kind multiplier.
"""

from __future__ import annotations

from retrieval.chunking import Chunk

_K = 60


def weighted_rrf(
    sparse: list[Chunk],
    dense: list[Chunk],
    w_sparse: float,
    w_dense: float,
    *,
    kind_bias: dict[str, float] | None = None,
    item_filter: list[str] | None = None,
) -> list[Chunk]:
    kind_bias = kind_bias or {}
    scores: dict[tuple, float] = {}
    keep: dict[tuple, Chunk] = {}

    def key(c: Chunk) -> tuple:
        return (c.path, c.text[:64])

    for rank, c in enumerate(sparse):
        k = key(c)
        scores[k] = scores.get(k, 0.0) + w_sparse / (_K + rank)
        keep.setdefault(k, c)
    for rank, c in enumerate(dense):
        k = key(c)
        scores[k] = scores.get(k, 0.0) + w_dense / (_K + rank)
        keep.setdefault(k, c)

    for k, c in keep.items():
        mult = kind_bias.get(c.kind, 1.0)
        if item_filter and c.kind == "filing":
            sect = (c.section or "").lower()
            mult *= 1.5 if any(it in sect for it in item_filter) else 0.85
        scores[k] *= mult

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return [keep[k] for k, _ in ranked]
