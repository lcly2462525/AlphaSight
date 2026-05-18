"""HybridRetriever — the single online entry point.

Per-request narrowed BM25 over kind-aware chunks (proven to scale on
this 117K corpus without a prebuilt sparse index), optionally fused
with a prebuilt dense index, plus the structured Fact Store. Works
end-to-end with BM25 alone when the embedding model is absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rank_bm25 import BM25Okapi

from catalog import filter_docs
from retrieval.chunking import Chunk, chunk_doc
from retrieval.compress import compress_chunk
from retrieval.fact_store import FactStore
from retrieval.fusion import weighted_rrf
from retrieval.router import QueryRouter, RouteDecision
from retrieval.textutil import doc_text, tokenize

_YEAR_RE = re.compile(r"\b(20\d{2})\b")
# per-kind candidate caps keep per-request BM25 build bounded
_CAND_CAP = {"filing": 60, "news": 400, "social": 200, "research": 0}
_CHUNK_BUDGET = 700
_TOTAL_BUDGET = 9000


@dataclass
class RetrievalResult:
    facts: str = ""
    evidence: list[tuple[str, str]] = field(default_factory=list)
    route: RouteDecision | None = None

    def evidence_block(self) -> str:
        if not self.evidence:
            return "(no evidence selected)"
        return "\n".join(f"---\n[SOURCE: {p}]\n{t}" for p, t in self.evidence)


class HybridRetriever:
    def __init__(self, catalog, corpus_dir: Path, prices_dir: Path,
                 entity_resolver, index_dir: Path | None = None) -> None:
        self.catalog = catalog
        self.corpus = Path(corpus_dir)
        self.entity = entity_resolver
        self.fact_store = FactStore(self.corpus, Path(prices_dir))
        self.router = QueryRouter()
        self._dense = None
        if index_dir is not None:
            from retrieval.dense import DenseIndex
            from retrieval.embedder import Embedder
            self._dense = DenseIndex(Path(index_dir), Embedder())

    def _window(self, query: str) -> tuple[str, str] | None:
        ys = sorted(set(_YEAR_RE.findall(query)))
        if not ys:
            return None
        return (f"{ys[0]}-01-01", f"{ys[-1]}-12-31")

    def _narrow_chunks(self, tickers, window, route) -> list[Chunk]:
        metas = filter_docs(self.catalog, symbols=tickers or None,
                            time_range=window)
        by_kind: dict[str, list] = {}
        for m in metas:
            by_kind.setdefault(m.kind, []).append(m)
        chunks: list[Chunk] = []
        for kind, docs in by_kind.items():
            cap = _CAND_CAP.get(kind, 100)
            if cap <= 0:
                continue
            docs.sort(key=lambda x: x.timestamp or "", reverse=True)
            for m in docs[:cap]:
                txt = doc_text(str(self.corpus / m.path), m.kind)
                chunks.extend(chunk_doc(m.path, txt, m.kind))
        return chunks

    def search(self, query: str, *, route: RouteDecision | None = None,
               top_k: int = 12) -> RetrievalResult:
        route = route or self.router.decide(query)
        tickers = self.entity.resolve(query)
        window = self._window(query)
        if route.tighten_window and window is None:
            window = None

        facts = (self.fact_store.facts_block(tickers, window)
                 if route.use_fact_store else "")

        chunks = self._narrow_chunks(tickers, window, route)
        if not chunks:
            return RetrievalResult(facts=facts, evidence=[], route=route)

        q_tok = tokenize(query)
        tok_chunks = [(c, tokenize(c.text)) for c in chunks]
        tok_chunks = [(c, t) for c, t in tok_chunks if t]
        if not tok_chunks or not q_tok:
            return RetrievalResult(facts=facts, evidence=[], route=route)
        bm = BM25Okapi([t for _, t in tok_chunks])
        scores = bm.get_scores(q_tok)
        ranked = sorted(zip((c for c, _ in tok_chunks), scores),
                        key=lambda kv: -kv[1])
        sparse = [c for c, s in ranked if s > 0][:top_k * 4]

        dense: list[Chunk] = []
        if self._dense is not None:
            allowed = {c.path for c in sparse} or None
            dense = self._dense.search(query, top_k * 4, allowed)

        fused = weighted_rrf(sparse, dense, route.w_sparse, route.w_dense,
                             kind_bias=route.kind_bias,
                             item_filter=route.item_filter)

        q_set = set(q_tok)
        evidence: list[tuple[str, str]] = []
        used = 0
        for c in fused:
            if len(evidence) >= top_k or used >= _TOTAL_BUDGET:
                break
            snip = compress_chunk(c.text, q_set, _CHUNK_BUDGET)
            if not snip:
                continue
            evidence.append((c.path, snip))
            used += len(snip)
        return RetrievalResult(facts=facts, evidence=evidence, route=route)
