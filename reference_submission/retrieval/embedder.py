"""Embedding backend for Qwen3-VL-Embedding-8B, with hard degradation.

Qwen3-VL-Embedding-8B is a multimodal model: in-process loading via
sentence-transformers is NOT guaranteed, and an 8B model also competes
with the inference LLM for GPU. So we try, in order:

  1. OpenAI-compatible /v1/embeddings endpoint  (preferred — the eval
     box can serve the embedding model with vLLM; no in-process GPU,
     no VL-loading pitfalls)
  2. sentence-transformers (trust_remote_code)
  3. transformers AutoModel + last-token pooling (Qwen embedding style)
  4. None  -> HybridRetriever silently runs BM25-only

Qwen3 embeddings are instruction-aware: queries get an instruction
prefix, documents do not. Mismatching that costs recall, so the query
path applies it explicitly.
"""

from __future__ import annotations

import os
from functools import lru_cache

_DEFAULT_PATH = "/root/.cache/modelscope/hub/models/Qwen/Qwen3-VL-Embedding-8B"
_QUERY_INSTRUCT = (
    "Instruct: Given a financial research query, retrieve passages "
    "from filings and news that support or contradict it.\nQuery: "
)


def _as_query(text: str) -> str:
    return f"{_QUERY_INSTRUCT}{text}"


class Embedder:
    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path or os.environ.get(
            "ALPHASIGHT_EMBED_MODEL", _DEFAULT_PATH)
        # endpoint config (preferred backend)
        self._ep_url = (os.environ.get("ALPHASIGHT_EMBED_BASE_URL")
                        or os.environ.get("OPENAI_API_BASE"))
        self._ep_model = os.environ.get("ALPHASIGHT_EMBED_MODEL_NAME")
        self._backend: str | None = None
        self._model = None
        self._tok = None
        self._ok: bool | None = None

    # ---- backend resolution ----------------------------------------

    @property
    def available(self) -> bool:
        if self._ok is None:
            self._ok = self._resolve()
        return self._ok

    def _resolve(self) -> bool:
        if self._ep_url and self._ep_model:
            try:
                from openai import OpenAI  # noqa: F401
                self._backend = "endpoint"
                return True
            except Exception:
                pass
        if os.path.isdir(self.model_path):
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    self.model_path, trust_remote_code=True)
                self._backend = "st"
                return True
            except Exception:
                self._model = None
            try:
                import torch  # noqa: F401
                from transformers import AutoModel, AutoTokenizer
                self._tok = AutoTokenizer.from_pretrained(
                    self.model_path, trust_remote_code=True)
                self._model = AutoModel.from_pretrained(
                    self.model_path, trust_remote_code=True,
                    torch_dtype="auto").eval()
                self._backend = "hf"
                return True
            except Exception:
                self._model = self._tok = None
        return False

    # ---- encoding ---------------------------------------------------

    def _encode_endpoint(self, texts: list[str]):
        from openai import OpenAI
        client = OpenAI(base_url=self._ep_url,
                        api_key=os.environ.get("OPENAI_API_KEY", "sk-none"))
        resp = client.embeddings.create(model=self._ep_model, input=texts)
        return [d.embedding for d in resp.data]

    def _encode_st(self, texts: list[str], batch_size: int):
        return self._model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True,
            show_progress_bar=False)

    def _encode_hf(self, texts: list[str], batch_size: int):
        import torch
        import torch.nn.functional as F
        out = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            enc = self._tok(batch, padding=True, truncation=True,
                            max_length=1024, return_tensors="pt")
            with torch.no_grad():
                hs = self._model(**enc).last_hidden_state
            mask = enc["attention_mask"]
            idx = mask.sum(dim=1) - 1            # last non-pad token
            pooled = hs[torch.arange(hs.size(0)), idx]
            pooled = F.normalize(pooled, p=2, dim=1)
            out.extend(pooled.cpu().tolist())
        return out

    def encode(self, texts: list[str], *, batch_size: int = 32,
               is_query: bool = False):
        """Embed documents (default) or queries (instruction-prefixed)."""
        if not self.available:
            return None
        payload = [_as_query(t) for t in texts] if is_query else list(texts)
        try:
            if self._backend == "endpoint":
                return self._encode_endpoint(payload)
            if self._backend == "st":
                return self._encode_st(payload, batch_size)
            if self._backend == "hf":
                return self._encode_hf(payload, batch_size)
        except Exception:
            return None
        return None

    @lru_cache(maxsize=512)
    def encode_one(self, text: str):
        v = self.encode([text], is_query=True)
        return None if v is None else v[0]
