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
# per-kind candidate caps keep per-request BM25 build bounded.
# research is JSON (already structured into FactStore); a small cap
# lets its raw dump back stop gaps without flooding BM25 with JSON noise.
# news_event = the news_merged atomic-event stream: each is a single
# short, high-signal chunk (no body windows), so a larger cap is cheap
# vs raw `news` and preserves recall for date-localized review claims.
_CAND_CAP = {"filing": 60, "news": 400, "social": 200, "research": 40,
             "news_event": 300}
_CHUNK_BUDGET = 1200
_TOTAL_BUDGET = 12000
# the event lane only carries the one-sentence event; for the top few
# events also pull their SOURCE article and chunk it exactly like raw
# news, so the highest-signal events come with their original passage
# (numbers/context the sentence drops), not just the gist.
_EVENT_ORIG_EXPAND = 3


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
        self.fact_store = FactStore(self.corpus, Path(prices_dir),
                                    catalog=catalog)
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
        # filings/research are single-issuer: their path is
        # `<kind>/<TICKER>/...`. Multi-symbol news can tag peers, so a
        # WMT 10-Q tagged with HD would otherwise leak into an HD
        # report. For filing/research require the PATH company to be the
        # subject; news/social stay symbol-scoped (legitimately cross).
        if tickers:
            tset = set(tickers)
            kept = []
            for m in metas:
                if m.kind in ("filing", "research"):
                    parts = m.path.split("/")
                    if len(parts) > 1 and parts[1] not in tset:
                        continue
                kept.append(m)
            metas = kept
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
                if m.kind == "news_event":
                    # event text is materialized in the catalog row (built
                    # offline) — one chunk, zero file I/O. m.path is a real
                    # source news file so [SOURCE: ...] stays citable.
                    ev = (m.extra or {}).get("event_text", "")
                    if ev:
                        chunks.append(Chunk(m.path, ev, "news_event",
                                            "event"))
                    continue
                txt = doc_text(str(self.corpus / m.path), m.kind)
                chunks.extend(chunk_doc(m.path, txt, m.kind))
        return chunks

    def subject_universe(self) -> list[str]:
        """Tickers that actually have filings — the only valid report
        subjects. Used by the agent to lock a subject for open-ended
        topics instead of falling back to whole-corpus retrieval."""
        return sorted(self.fact_store._filings)

    def search(self, query: str, *, route: RouteDecision | None = None,
               top_k: int = 12, tickers: list[str] | None = None,
               require_subject: bool = False) -> RetrievalResult:
        route = route or self.router.decide(query)
        # explicit subject lock wins; else resolve from the query text.
        tickers = tickers or self.entity.resolve(query)
        # generate sets require_subject: with no subject we must NOT
        # widen to the whole corpus (that grounded an HD report on
        # Costco's 10-Q) — return empty so the agent falls back.
        if require_subject and not tickers:
            return RetrievalResult(facts="", evidence=[], route=route)
        window = self._window(query)
        if route.tighten_window and window is None:
            window = None

        facts = (self.fact_store.facts_block(tickers, window)
                 if route.use_fact_store else "")

        # The corpus is entirely 2025; topics routinely say "FY2026" /
        # "2026 outlook". A hard year filter then removes every doc and
        # the model hallucinates. Relax the window (keep the ticker
        # scope) rather than return nothing.
        chunks = self._narrow_chunks(tickers, window, route)
        if not chunks and window is not None:
            chunks = self._narrow_chunks(tickers, None, route)
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

        # news_event is a curated, attributed, dated high-signal lane.
        # One-sentence events score far below long filing/social chunks
        # in the shared BM25 pool and get cut by the top_k*4 sparse
        # truncation before fusion ever sees them — so kind_bias (a
        # rank-based RRF re-weight) cannot lift them. Score events on
        # their OWN BM25 so length never crowds them out, then guarantee
        # the best ones a reserved, leading slice of the evidence (this
        # is what places events ABOVE raw news, deterministically).
        ev_pairs = [(c, t) for c, t in tok_chunks if c.kind == "news_event"]
        event_lead: list[Chunk] = []
        if ev_pairs:
            ebm = BM25Okapi([t for _, t in ev_pairs])
            esc = ebm.get_scores(q_tok)
            eranked = sorted(zip((c for c, _ in ev_pairs), esc),
                             key=lambda kv: -kv[1])
            event_lead = [c for c, s in eranked
                          if s > 0][:max(1, top_k // 2)]

        dense: list[Chunk] = []
        if self._dense is not None:
            allowed = {c.path for c in sparse} or None
            dense = self._dense.search(query, top_k * 4, allowed)

        fused = weighted_rrf(sparse, dense, route.w_sparse, route.w_dense,
                             kind_bias=route.kind_bias,
                             item_filter=route.item_filter)
        # Original-text expansion (independent of the generic `news`
        # channel, which still runs in `fused`): for the top few events,
        # read their source article and chunk it through the SAME
        # chunk_doc(...,"news") window pipeline, then keep the single
        # window that best matches the query. Missing raw files (ticker
        # not extracted) degrade silently — doc_text returns "" so the
        # event sentence still stands alone.
        orig_lead: list[Chunk] = []
        if event_lead:
            seen_src: set[str] = set()
            for ev in event_lead[:_EVENT_ORIG_EXPAND]:
                src = ev.path  # = source_paths[0], a real news/<T>/<h>.json
                if not src or "/" not in src or src in seen_src:
                    continue
                seen_src.add(src)
                o_chunks = chunk_doc(
                    src, doc_text(str(self.corpus / src), "news"), "news")
                o_tok = [(c, tokenize(c.text)) for c in o_chunks]
                o_tok = [(c, t) for c, t in o_tok if t]
                if not o_tok:
                    continue
                o_bm = BM25Okapi([t for _, t in o_tok])
                o_sc = o_bm.get_scores(q_tok)
                best_c, best_s = max(zip((c for c, _ in o_tok), o_sc),
                                     key=lambda kv: kv[1])
                if best_s > 0:
                    orig_lead.append(best_c)

        lead = event_lead + orig_lead
        if lead:
            seen = {(c.path, c.text[:64]) for c in lead}
            fused = lead + [c for c in fused
                            if (c.path, c.text[:64]) not in seen]

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
