"""FAISS dense index: optional augmentation, never required.

If the prebuilt index or faiss or the embedder is missing, `search`
returns [] and HybridRetriever silently runs sparse-only.
"""

from __future__ import annotations

import json
from pathlib import Path

from retrieval.chunking import Chunk


class DenseIndex:
    def __init__(self, index_dir: Path, embedder) -> None:
        self.dir = Path(index_dir)
        self.embedder = embedder
        self._index = None
        self._meta: list[dict] = []
        self._loaded = False

    def _load(self) -> None:
        self._loaded = True
        faiss_path = self.dir / "dense.faiss"
        meta_path = self.dir / "chunk_meta.jsonl"
        if not (faiss_path.exists() and meta_path.exists()):
            return
        try:
            import faiss
            self._index = faiss.read_index(str(faiss_path))
            with meta_path.open(encoding="utf-8") as f:
                self._meta = [json.loads(ln) for ln in f if ln.strip()]
        except Exception:
            self._index = None
            self._meta = []

    @property
    def ready(self) -> bool:
        if not self._loaded:
            self._load()
        return self._index is not None and bool(self._meta)

    def search(self, query: str, top_n: int,
               allowed_paths: set[str] | None = None) -> list[Chunk]:
        if not self.ready or not self.embedder.available:
            return []
        qv = self.embedder.encode_one(query)
        if qv is None:
            return []
        try:
            import numpy as np
            D, I = self._index.search(
                np.asarray([qv], dtype="float32"), top_n * 3)
        except Exception:
            return []
        out: list[Chunk] = []
        for idx in I[0]:
            if idx < 0 or idx >= len(self._meta):
                continue
            m = self._meta[idx]
            if allowed_paths is not None and m.get("path") not in allowed_paths:
                continue
            out.append(Chunk(m.get("path", ""), m.get("text", ""),
                             m.get("kind", ""), m.get("section", "")))
            if len(out) >= top_n:
                break
        return out
