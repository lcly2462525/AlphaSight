"""Offline dense-index builder (optional augmentation).

Run once on the cloud box where Qwen3-VL-Embedding-8B exists:

    python build_index.py --corpus ../dataset/corpus \
        --catalog ../dataset/catalog.jsonl --out index

Embeds kind-aware chunks of filing+news (research -> FactStore, social
-> noise) and writes:
    index/dense.faiss
    index/chunk_meta.jsonl

If the model is absent the script exits cleanly; the online system runs
BM25-only without this index.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

from catalog import filter_docs, load_catalog            # noqa: E402
from retrieval.chunking import chunk_doc                  # noqa: E402
from retrieval.embedder import Embedder                   # noqa: E402
from retrieval.textutil import doc_text                   # noqa: E402

try:
    from tqdm import tqdm                                 # noqa: E402
except ImportError:                                       # pragma: no cover
    def tqdm(it, **_):                                    # type: ignore
        return it

_NEWS_CAP = 40000  # cap embedded news chunks to keep index bounded


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=_SELF.parent / "dataset/corpus")
    ap.add_argument("--catalog", type=Path,
                    default=_SELF.parent / "dataset/catalog.jsonl")
    ap.add_argument("--out", type=Path, default=_SELF / "index")
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    emb = Embedder()
    if not emb.available:
        print("embedding model unavailable — skipping dense index "
              "(system will run BM25-only).")
        return 0

    catalog = load_catalog(args.catalog)
    metas = filter_docs(catalog, kinds=["filing", "news"])
    args.out.mkdir(parents=True, exist_ok=True)

    texts: list[str] = []
    meta: list[dict] = []
    news_seen = 0
    for m in tqdm(metas, desc="chunking", unit="doc"):
        if m.kind == "news":
            if news_seen >= _NEWS_CAP:
                continue
            news_seen += 1
        txt = doc_text(str(args.corpus / m.path), m.kind)
        for ch in chunk_doc(m.path, txt, m.kind):
            if m.kind == "news" and ch.section == "body":
                continue  # title chunk is enough for index size
            texts.append(ch.text)
            meta.append({"path": ch.path, "text": ch.text[:1200],
                         "kind": ch.kind, "section": ch.section})

    if not texts:
        print("no chunks to embed.")
        return 0

    print(f"embedding {len(texts)} chunks ...")
    import faiss
    import numpy as np

    vecs: list = []
    bs = max(1, args.batch_size)
    for i in tqdm(range(0, len(texts), bs), desc="embedding",
                  unit="batch"):
        part = emb.encode(texts[i:i + bs], batch_size=bs)
        if part is None:
            print("encode failed — skipping dense index.")
            return 0
        vecs.extend(part)
    arr = np.asarray(vecs, dtype="float32")
    index = faiss.IndexFlatIP(arr.shape[1])
    index.add(arr)
    faiss.write_index(index, str(args.out / "dense.faiss"))
    with (args.out / "chunk_meta.jsonl").open("w", encoding="utf-8") as f:
        for row in meta:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"done: {len(texts)} vectors -> {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
