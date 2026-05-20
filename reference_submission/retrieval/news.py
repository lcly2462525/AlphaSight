"""News-only retrieval pipeline — parallel to HybridRetriever.

The news / news_merged data has distinct structure (atomic events with
polarity / attributed_to / timestamp / multi-symbol scope) that does
not fit the generic filing/research/social BM25 pool well — short
event sentences get crowded out by long filing windows, and the
discriminative fields (polarity, attributed_to, event_id) are lost
when chunks are kept generic.

This module owns its own index, structured query type, and evidence
format. It runs alongside HybridRetriever; the two feed two separate
sections of the review prompt.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rank_bm25 import BM25Okapi

from retrieval.textutil import tokenize


# ---- data classes ---------------------------------------------------


@dataclass
class EventChunk:
    """One atomic news event from news_merged."""
    event_id: str
    text: str
    polarity: str | None
    attributed_to: str | None
    provider: str | None
    timestamp: str            # ISO YYYY-MM-DDTHH:MM:SSZ
    scope: str | None
    symbols: tuple[str, ...]  # union of source_paths tickers + file ticker
    source_path: str          # representative news/<T>/<hash>.json
    confidence: float | None = None


@dataclass
class NewsQuery:
    """Structured per-claim news query — every field is optional.
    NewsRetriever applies the non-empty fields as filters or boosts."""
    tickers: list[str] = field(default_factory=list)
    date_range: tuple[str, str] | None = None     # ISO YYYY-MM-DD pair
    polarity_hint: str | None = None              # bullish|bearish|neutral
    outlet_hint: str | None = None                # Bloomberg|CNBC|JPM|...
    text: str = ""                                # free-text BM25 query
    numeric_hints: list[str] = field(default_factory=list)


@dataclass
class NewsEvidence:
    """Result row — event + paired body excerpt + citation."""
    event: str
    polarity: str | None
    attributed_to: str | None
    provider: str | None
    timestamp: str
    source_path: str
    body_excerpt: str
    score: float


# ---- helpers --------------------------------------------------------


def _subject_iter(rec: dict) -> Iterable[dict]:
    """Yield subject entries that carry a usable ticker mention.
    Drops role=='tagged_only' — those are end-of-article 'related
    stocks' tags, not what the event is actually about."""
    for s in rec.get("subject") or []:
        if not isinstance(s, dict):
            continue
        if s.get("type") != "ticker":
            continue
        if s.get("role") == "tagged_only":
            continue
        if s.get("mention"):
            yield s


def _build_alias_map(events: Iterable[dict],
                     valid_tickers: set[str]) -> dict[str, str]:
    """Mine subject.mention -> ticker aliases from event records.

    Pick top_T by lift relative to the background frequency of T,
    not raw co-occurrence count — otherwise heavily-discussed tickers
    (e.g. 'T' for AT&T) outrank the right answer for mentions that
    co-occur with them by accident (Verizon shows up in many AT&T
    articles; counts say T, lift says VZ). Accept M -> top_T when:
      * support n1     >= 5     (enough events to trust the signal)
      * precision      >= 0.3   (M is at least somewhat concentrated)
      * lift           >= 3.0   (well above chance)
    """
    co: dict[str, Counter] = {}
    subject_count: Counter = Counter()
    background: Counter = Counter()
    total_events = 0
    for rec in events:
        sp_tickers: set[str] = set()
        for p in rec.get("source_paths") or []:
            parts = str(p).split("/")
            if (len(parts) >= 2 and parts[0] == "news"
                    and parts[1] in valid_tickers):
                sp_tickers.add(parts[1])
        if not sp_tickers:
            continue
        total_events += 1
        for t in sp_tickers:
            background[t] += 1
        for s in _subject_iter(rec):
            m = s["mention"]
            if m.upper() in valid_tickers:
                continue
            subject_count[m] += 1
            for t in sp_tickers:
                co.setdefault(m, Counter())[t] += 1
    if total_events == 0:
        return {}
    alias: dict[str, str] = {}
    for m, c in co.items():
        total_m = subject_count[m] or 1
        best_t, best_lift, best_n = None, 0.0, 0
        for t, n in c.items():
            bg = background[t] / total_events
            if bg <= 0:
                continue
            lift = (n / total_m) / bg
            if lift > best_lift:
                best_t, best_lift, best_n = t, lift, n
        if best_t is None or best_n < 5:
            continue
        if best_lift < 3.0:
            continue
        if best_n / total_m < 0.3:
            continue
        alias[m] = best_t
    return alias


def _make_chunk(rec: dict, file_tickers: set[str],
                alias_map: dict[str, str],
                valid_tickers: set[str]) -> EventChunk | None:
    ev_text = (rec.get("event") or "").strip()
    ts = rec.get("timestamp")
    if not ev_text or not ts:
        return None
    sp = rec.get("source_paths") or []
    if sp:
        primary = sp[0]
    elif file_tickers:
        primary = f"news_merged/{next(iter(sorted(file_tickers)))}.jsonl"
    else:
        primary = ""
    syms: set[str] = set(file_tickers)
    for p in sp:
        parts = str(p).split("/")
        if len(parts) >= 2 and parts[0] == "news" and parts[1]:
            syms.add(parts[1])
    # Merge subject tickers — the fix for events whose 'subject' is a
    # company that doesn't appear in source_paths (e.g. an article
    # filed under news/AAPL/ commenting on Meta).
    for s in _subject_iter(rec):
        m = s["mention"]
        m_up = m.upper()
        if m_up in valid_tickers:
            syms.add(m_up)
        else:
            t = alias_map.get(m)
            if t and t in valid_tickers:
                syms.add(t)
    return EventChunk(
        event_id=rec.get("event_id", ""),
        text=ev_text,
        polarity=rec.get("polarity"),
        attributed_to=rec.get("attributed_to"),
        provider=rec.get("provider"),
        timestamp=str(ts),
        scope=rec.get("scope"),
        symbols=tuple(sorted(syms)),
        source_path=primary,
        confidence=rec.get("confidence"),
    )


# ---- index ----------------------------------------------------------


class NewsIndex:
    """In-memory index over news_merged events.

    Build cost: ~10-30s on the full 50-ticker corpus (~149K events
    before dedup, ~100K after merging cross-symbol duplicates by
    event_id). Body excerpts are loaded lazily per source_path on
    demand — only the events that score in the top-K of a search pay
    the per-file read cost.
    """

    def __init__(self, news_merged_dir: Path) -> None:
        self.events: list[EventChunk] = []
        self.event_bm25: BM25Okapi | None = None
        # subset map: position in BM25 corpus -> index into self.events
        self._bm25_idx: list[int] = []
        # inverted lookups
        self.by_ticker: dict[str, list[int]] = {}
        self.by_outlet: dict[str, list[int]] = {}
        self._load_events(news_merged_dir)
        self._build()

    def _load_events(self, dir_path: Path) -> None:
        if not dir_path.exists():
            return
        files = sorted(dir_path.glob("*.jsonl"))
        if not files:
            return
        # Universe of valid tickers = the 50 file stems (news_merged is
        # partitioned per catalog ticker).
        valid_tickers: set[str] = {fp.stem for fp in files}

        # First pass: parse + dedup by event_id, accumulate which files
        # each event_id appeared in (for symbol merge).
        raw_by_id: dict[str, dict] = {}
        file_tickers_by_id: dict[str, set[str]] = {}
        raw_no_id: list[tuple[dict, str]] = []
        for fp in files:
            file_ticker = fp.stem
            with fp.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    eid = rec.get("event_id", "")
                    if eid:
                        if eid not in raw_by_id:
                            raw_by_id[eid] = rec
                            file_tickers_by_id[eid] = {file_ticker}
                        else:
                            file_tickers_by_id[eid].add(file_ticker)
                    else:
                        raw_no_id.append((rec, file_ticker))

        # Mine mention -> ticker alias map from the deduped records.
        alias_map = _build_alias_map(raw_by_id.values(), valid_tickers)

        # Second pass: build EventChunks with subject tickers merged
        # into symbols using valid_tickers + alias_map.
        by_id: dict[str, EventChunk] = {}
        for eid, rec in raw_by_id.items():
            chunk = _make_chunk(rec, file_tickers_by_id[eid],
                                alias_map, valid_tickers)
            if chunk is not None:
                by_id[eid] = chunk
        for rec, ft in raw_no_id:
            chunk = _make_chunk(rec, {ft}, alias_map, valid_tickers)
            if chunk is not None:
                self.events.append(chunk)
        if by_id:
            self.events = list(by_id.values()) + self.events

    def _build(self) -> None:
        if not self.events:
            return
        toks: list[list[str]] = []
        for i, e in enumerate(self.events):
            t = tokenize(e.text)
            if not t:
                continue
            self._bm25_idx.append(i)
            toks.append(t)
            for sym in e.symbols:
                self.by_ticker.setdefault(sym, []).append(i)
            if e.attributed_to:
                self.by_outlet.setdefault(
                    e.attributed_to.lower(), []).append(i)
        if toks:
            self.event_bm25 = BM25Okapi(toks)

    def candidate_indices(self, q: NewsQuery) -> set[int]:
        """Hard filters: ticker + date_range. Empty fields = no filter
        on that axis."""
        if q.tickers:
            kept: set[int] = set()
            for t in q.tickers:
                kept.update(self.by_ticker.get(t, []))
        else:
            kept = set(range(len(self.events)))
        if q.date_range:
            lo, hi = q.date_range
            kept = {i for i in kept
                    if lo <= (self.events[i].timestamp or "")[:10] <= hi}
        return kept


# ---- retriever ------------------------------------------------------


class NewsRetriever:
    """Public search interface — atomic events paired with the most
    query-relevant body window from the same source article.

    Body excerpts are loaded and BM25-indexed lazily per source_path
    and cached for the lifetime of the process."""

    def __init__(self, news_merged_dir: str | Path,
                 corpus_dir: str | Path) -> None:
        self._news_merged_dir = Path(news_merged_dir)
        self._corpus = Path(corpus_dir)
        self.index = NewsIndex(self._news_merged_dir)
        # source_path -> (windows, BM25 over windows)
        self._body_cache: dict[
            str, tuple[list[str], BM25Okapi | None]] = {}

    # ------------------------------------------------------------------

    def search(self, q: NewsQuery, top_k: int = 10) -> list[NewsEvidence]:
        if not self.index.events or self.index.event_bm25 is None:
            return []
        # Build effective BM25 query text — text + outlet + numerics.
        query_text = q.text or ""
        if q.outlet_hint:
            query_text = f"{query_text} {q.outlet_hint}"
        if q.numeric_hints:
            query_text = f"{query_text} {' '.join(q.numeric_hints)}"
        q_tok = tokenize(query_text)
        if not q_tok:
            return []
        candidates = self.index.candidate_indices(q)
        if not candidates:
            return []
        # Score the full BM25 corpus once; pick by candidate filter.
        bm_scores = self.index.event_bm25.get_scores(q_tok)
        # Map BM25 position -> event idx -> score
        score_by_event: dict[int, float] = {}
        for pos, ev_idx in enumerate(self.index._bm25_idx):
            score_by_event[ev_idx] = bm_scores[pos]
        ranked: list[tuple[float, int]] = []
        for i in candidates:
            sc = score_by_event.get(i, 0.0)
            if sc <= 0:
                continue
            # Polarity match boost (1.3x) when both sides specify it.
            if (q.polarity_hint
                    and self.index.events[i].polarity
                    and self.index.events[i].polarity == q.polarity_hint):
                sc *= 1.3
            # Outlet match boost when attributed_to aligns with hint.
            if q.outlet_hint:
                attr = (self.index.events[i].attributed_to or "").lower()
                if attr and q.outlet_hint.lower() in attr:
                    sc *= 1.25
            ranked.append((sc, i))
        ranked.sort(reverse=True)
        out: list[NewsEvidence] = []
        for sc, i in ranked[:top_k]:
            e = self.index.events[i]
            body = self._best_body_excerpt(e.source_path, q_tok)
            out.append(NewsEvidence(
                event=e.text,
                polarity=e.polarity,
                attributed_to=e.attributed_to,
                provider=e.provider,
                timestamp=e.timestamp,
                source_path=e.source_path,
                body_excerpt=body,
                score=sc,
            ))
        return out

    # ------------------------------------------------------------------

    def _best_body_excerpt(self, source_path: str,
                           q_tok: list[str]) -> str:
        """Return the source article's best-matching 600-char window
        for the query tokens. Empty string when the source file is
        missing or has no body."""
        if not source_path or source_path.startswith("news_merged/"):
            return ""
        cached = self._body_cache.get(source_path)
        if cached is None:
            cached = self._load_body(source_path)
            self._body_cache[source_path] = cached
        windows, bm = cached
        if not windows:
            return ""
        if bm is None:
            return windows[0][:400]
        scores = bm.get_scores(q_tok)
        best_idx = max(range(len(windows)), key=lambda i: scores[i])
        return windows[best_idx][:400]

    def _load_body(self, source_path: str
                    ) -> tuple[list[str], BM25Okapi | None]:
        full = self._corpus / source_path
        try:
            d = json.loads(full.read_text(encoding="utf-8",
                                          errors="ignore"))
        except (FileNotFoundError, json.JSONDecodeError, ValueError,
                OSError):
            return [], None
        if not isinstance(d, dict):
            return [], None
        body = str(d.get("text", "")).strip()
        if not body:
            return [], None
        # Sliding 600-char windows with 100 char overlap. For short
        # articles a single window covers the whole body.
        windows: list[str] = []
        step = 500
        for s in range(0, len(body), step):
            w = body[s:s + 600].strip()
            if w:
                windows.append(w)
            if s + 600 >= len(body):
                break
        if not windows:
            return [], None
        toks = [tokenize(w) for w in windows]
        if not any(toks):
            return windows, None
        return windows, BM25Okapi(toks)


# ---- prompt rendering ----------------------------------------------


def format_news_evidence_block(evs: list[NewsEvidence],
                                max_chars: int = 5000) -> str:
    """Render NewsEvidence list as a prompt block — one record per
    event with its source article excerpt directly beneath."""
    if not evs:
        return "(no news evidence)"
    parts: list[str] = []
    used = 0
    for ev in evs:
        date = (ev.timestamp or "")[:10]
        head_bits = [f"EVENT {date}" if date else "EVENT"]
        if ev.polarity:
            head_bits.append(ev.polarity)
        if ev.attributed_to:
            head_bits.append(f"src: {ev.attributed_to}")
        if ev.provider:
            head_bits.append(f"via {ev.provider}")
        head = "[" + " | ".join(head_bits) + "]"
        block = f"---\n{head} {ev.event}\n[SOURCE: {ev.source_path}]"
        if ev.body_excerpt:
            block += f"\n(excerpt) {ev.body_excerpt}"
        if used + len(block) > max_chars and parts:
            break
        parts.append(block)
        used += len(block) + 1
    return "\n".join(parts) if parts else "(no news evidence)"
