"""Embedding backend for Qwen3-VL-Embedding-8B, with hard degradation.

Resolution order:
  1. OpenAI-compatible /v1/embeddings endpoint  (preferred — the eval
     box can serve the embedding model with vLLM; no in-process GPU,
     no VL-loading pitfalls)
  2. sentence-transformers (HuggingFace, trust_remote_code)
  3. transformers AutoModel + last-token pooling (Qwen embedding style)
  4. None  -> HybridRetriever runs BM25-only

The model is referenced by a **HuggingFace id** (`Qwen/Qwen3-VL-Embedding-8B`
by default), NOT a hardcoded absolute path. HuggingFace resolves it from
the standard HF cache (HF_HOME / ~/.cache/huggingface) or downloads it;
override with ALPHASIGHT_EMBED_MODEL (HF id *or* a local dir).

Failures are LOGGED to stderr (visible in the run console) instead of
being silently swallowed, so a misconfigured embedding path is obvious.

Qwen3 embeddings are instruction-aware: queries get an instruction
prefix, documents do not. Mismatching that costs recall, so the query
path applies it explicitly.
"""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache

# Default is a HuggingFace repo id, resolved via the HF cache/hub — not
# a machine-specific filesystem path.
_DEFAULT_HF_ID = "Qwen/Qwen3-VL-Embedding-8B"
_QUERY_INSTRUCT = (
    "Instruct: Given a financial research query, retrieve passages "
    "from filings and news that support or contradict it.\nQuery: "
)

_log = logging.getLogger("alphasight.embedder")
if not _log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter(
        "[embedder] %(levelname)s %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)


def _as_query(text: str) -> str:
    return f"{_QUERY_INSTRUCT}{text}"


class Embedder:
    def __init__(self, model_id: str | None = None) -> None:
        # HF id or local dir; default is a HF repo id (no hardcoded path)
        self.model_id = model_id or os.environ.get(
            "ALPHASIGHT_EMBED_MODEL", _DEFAULT_HF_ID)
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
                _log.info("using OpenAI-compatible embeddings endpoint "
                          "%s (model=%s)", self._ep_url, self._ep_model)
                return True
            except Exception as e:
                _log.warning("endpoint backend unavailable: %r", e)

        # HuggingFace resolution — let HF locate the model in its cache
        # or download it; do NOT pre-gate on a filesystem path.
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_id, trust_remote_code=True)
            self._backend = "st"
            _log.info("loaded via sentence-transformers (HF id/path: %s)",
                      self.model_id)
            return True
        except Exception as e:
            _log.warning("sentence-transformers load failed for '%s': %r",
                         self.model_id, e)

        try:
            import torch  # noqa: F401
            from transformers import AutoModel, AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(
                self.model_id, trust_remote_code=True)
            self._model = AutoModel.from_pretrained(
                self.model_id, trust_remote_code=True,
                torch_dtype="auto").eval()
            self._backend = "hf"
            _log.info("loaded via transformers AutoModel (HF id/path: %s)",
                      self.model_id)
            return True
        except Exception as e:
            _log.error("transformers load failed for '%s': %r — dense "
                       "retrieval DISABLED, running BM25-only.",
                       self.model_id, e)

        return False

    # ---- encoding ---------------------------------------------------

    def _encode_endpoint(self, texts: list[str]):
        from openai import OpenAI
        # Bounded timeout + no retries: a slow/contended embeddings
        # server must DEGRADE to BM25, never hang the whole review.
        # (The SDK default is ~10min; with one embed call per evidence
        # pool + one per verify candidate, that reads as "stuck".)
        try:
            to = float(os.environ.get("ALPHASIGHT_EMBED_TIMEOUT", "20"))
        except ValueError:
            to = 20.0
        client = OpenAI(
            base_url=self._ep_url,
            api_key=os.environ.get("OPENAI_API_KEY", "sk-none"),
            timeout=to, max_retries=0)
        # Cap input size — a 4000-char query wastes the small 0.6B
        # embedder and can stall it; instruction embedders truncate
        # anyway. 2000 chars ≈ plenty for retrieval.
        capped = [t[:2000] for t in texts]
        resp = client.embeddings.create(model=self._ep_model, input=capped)
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
        except Exception as e:
            _log.error("encode failed on backend '%s': %r",
                       self._backend, e)
            return None
        return None

    @lru_cache(maxsize=512)
    def encode_one(self, text: str):
        v = self.encode([text], is_query=True)
        return None if v is None else v[0]
