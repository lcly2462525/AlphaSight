"""ExampleSubmission (runnable baseline) + Submission (your stub).

The harness imports `Submission`. Prompts are loaded internally by the
Submission itself; `run.py` does not pass them in.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml
from rank_bm25 import BM25Okapi

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import build_symbol_re, collect_symbols, filter_docs, load_catalog  # noqa: E402
from llm import LLMConfig, chat                              # noqa: E402
from schemas import (                                         # noqa: E402
    DocMeta,
    GenerateRequest,
    Report,
    ReviewIssue,
    ReviewRequest,
)


_EN_WORD = re.compile(r"[A-Za-z0-9]{2,}")
_CN_CHAR = re.compile(r"[一-鿿]")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _tokenize(text: str) -> list[str]:
    en = [w.lower() for w in _EN_WORD.findall(text)]
    cn = _CN_CHAR.findall(text)
    return en + cn


def _read_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = _HTML_TAG_RE.sub(" ", raw)
    return re.sub(r"\s+", " ", raw)


def _read_news_json(path: Path) -> str:
    try:
        d = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(d, dict):
        return ""
    parts: list[str] = []
    for k in ("title", "text", "summary", "description"):
        v = d.get(k)
        if isinstance(v, str) and v:
            parts.append(v)
    return "\n".join(parts)


def _read_research_json(path: Path) -> str:
    try:
        d = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, ValueError):
        return ""
    return json.dumps(d, ensure_ascii=False)


def _read_social_json(path: Path) -> str:
    try:
        d = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, ValueError):
        return ""
    tweets = []
    if isinstance(d, dict) and isinstance(d.get("tweets"), list):
        tweets = d["tweets"]
    elif isinstance(d, list):
        tweets = d
    out: list[str] = []
    for t in tweets[:30]:
        if isinstance(t, dict):
            txt = t.get("text") or ""
            if isinstance(txt, str) and txt:
                out.append(txt)
    return "\n".join(out)


@lru_cache(maxsize=4096)
def _cached_doc_text(path_str: str, kind: str) -> str:
    p = Path(path_str)
    if not p.exists():
        return ""
    if kind == "filing":
        return _read_html(p)
    if kind == "news":
        return _read_news_json(p)
    if kind == "research":
        return _read_research_json(p)
    if kind == "social":
        return _read_social_json(p)
    return p.read_text(encoding="utf-8", errors="ignore")


def _extract_tickers(query: str, sym_re: re.Pattern[str]) -> list[str]:
    return sorted({m.group(1) for m in sym_re.finditer(query)})


def _extract_time_window(query: str) -> tuple[str, str] | None:
    years = sorted(set(_YEAR_RE.findall(query)))
    if not years:
        return None
    return (f"{years[0]}-01-01", f"{years[-1]}-12-31")


_SELF_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _SELF_DIR / "prompt_templates"

# Per-kind candidate caps to keep BM25 build bounded on a 100k+ corpus.
_MAX_CANDIDATES = {"filing": 2000, "news": 5000, "research": 1000, "social": 5000}


class ExampleSubmission:
    def __init__(self) -> None:
        self.corpus = Path(os.environ["ALPHASIGHT_CORPUS_DIR"])
        self.prices_dir = Path(os.environ.get("ALPHASIGHT_PRICES_DIR", ""))
        self.prices_minute_dir = Path(os.environ.get("ALPHASIGHT_PRICES_MINUTE_DIR", ""))
        self.catalog = load_catalog(os.environ["ALPHASIGHT_CATALOG_PATH"])
        self.symbols = collect_symbols(self.catalog)
        self._symbol_re = build_symbol_re(self.symbols)
        self.llm = LLMConfig.from_env()
        meta = yaml.safe_load((_SELF_DIR / "submission.yaml").read_text(encoding="utf-8"))
        self.team_id = meta.get("team_id", "unknown")
        self._gen_params = meta.get("generate") or {"max_tokens": 2048, "temperature": 0.2}
        self._rev_params = meta.get("review") or {
            "max_tokens": 1024,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        self._gen_prompt = (_TEMPLATES_DIR / "reference_generate.md").read_text(encoding="utf-8")
        self._rev_prompt = (_TEMPLATES_DIR / "reference_review.md").read_text(encoding="utf-8")

    def _narrow(self, query: str) -> list[DocMeta]:
        tickers = _extract_tickers(query, self._symbol_re)
        time_range = _extract_time_window(query)
        return filter_docs(
            self.catalog,
            symbols=tickers or None,
            time_range=time_range,
        )

    def _bm25_top_k(
        self,
        query_tokens: list[str],
        candidates: list[DocMeta],
        k: int,
        snippet_limit: int,
    ) -> list[tuple[DocMeta, str]]:
        if not candidates or not query_tokens or k <= 0:
            return []
        texts = [_cached_doc_text(str(self.corpus / d.path), d.kind) for d in candidates]
        tokenized = [_tokenize(t) for t in texts]
        # BM25Okapi requires every doc to have at least one token.
        kept = [(d, t, toks) for d, t, toks in zip(candidates, texts, tokenized) if toks]
        if not kept:
            return []
        bm25 = BM25Okapi([toks for _, _, toks in kept])
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(zip(kept, scores), key=lambda kv: -kv[1])[:k]
        return [(d, t[:snippet_limit]) for (d, t, _toks), s in ranked if s > 0]

    def _select_evidence(self, *, query: str) -> list[tuple[str, str]]:
        narrowed = self._narrow(query)
        q_toks = _tokenize(query)

        by_kind: dict[str, list[DocMeta]] = {"filing": [], "news": [], "research": [], "social": []}
        for d in narrowed:
            if d.kind in by_kind:
                by_kind[d.kind].append(d)

        for kind, docs in by_kind.items():
            cap = _MAX_CANDIDATES.get(kind, 500)
            if len(docs) > cap:
                docs.sort(key=lambda x: x.timestamp or "", reverse=True)
                by_kind[kind] = docs[:cap]

        out: list[tuple[str, str]] = []
        for kind, k, snip in (
            ("filing", 3, 30_000),
            ("news", 6, 6_000),
            ("research", 2, 6_000),
            ("social", 4, 4_000),
        ):
            for d, snippet in self._bm25_top_k(q_toks, by_kind[kind], k, snip):
                out.append((d.path, snippet))
        return out

    def _evidence_block(self, evidence: list[tuple[str, str]]) -> str:
        if not evidence:
            return "(no evidence selected)"
        return "\n".join(f"---\n[SOURCE] {p}\n{t}" for p, t in evidence)

    def generate(self, request: GenerateRequest) -> Report:
        evidence = self._select_evidence(query=request.topic)
        prompt = self._gen_prompt.format(
            topic=request.topic,
            evidence_block=self._evidence_block(evidence),
        )
        content = chat(
            [{"role": "user", "content": prompt}],
            config=self.llm,
            **self._gen_params,
        )
        return Report(request_id=request.request_id, content=content)

    def review(self, request: ReviewRequest) -> list[ReviewIssue]:
        evidence = self._select_evidence(query=request.report_markdown)
        prompt = self._rev_prompt.format(
            report_markdown=request.report_markdown,
            evidence_block=self._evidence_block(evidence),
        )
        raw = chat(
            [{"role": "user", "content": prompt}],
            config=self.llm,
            **self._rev_params,
        )
        return self._parse_issues(raw)

    @staticmethod
    def _parse_issues(raw: str) -> list[ReviewIssue]:
        txt = raw.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```\w*\n?", "", txt).rstrip("`").rstrip()
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        try:
            data = json.loads(m.group(0) if m else txt)
        except json.JSONDecodeError:
            return []
        out: list[ReviewIssue] = []
        for it in (data.get("issues", []) if isinstance(data, dict) else []):
            if not isinstance(it, dict):
                continue
            quote = str(it.get("quote", "")).strip()
            reason = str(it.get("reason", "")).strip()
            if quote and reason:
                out.append(ReviewIssue(quote=quote, reason=reason))
        return out


# ----------------------------------------------------------------------------
# Submission — you fill this in. Quickest start: `class Submission(ExampleSubmission): pass`
# ----------------------------------------------------------------------------


class Submission(ExampleSubmission):
    """Orchestrator: thin dispatch over the unified retrieval layer.

    Inherits ExampleSubmission only for env/catalog/LLM bootstrap and as
    a last-resort fallback so run.py never crashes.
    """

    def __init__(self) -> None:
        def _log(m: str) -> None:
            print(f"[init] {m}", file=sys.stderr, flush=True)

        _log("loading catalog / symbols / prompts ...")
        super().__init__()
        _log(f"catalog={len(self.catalog)} docs, "
             f"symbols={len(self.symbols)}; "
             f"LLM={self.llm.model} @ {self.llm.base_url}")
        from retrieval.base import HybridRetriever
        from retrieval.entity import EntityResolver
        from agents.generate import GenerateAgent
        from agents.review import ReviewAgent

        resolver = EntityResolver(self.symbols)
        self._retriever = HybridRetriever(
            self.catalog, self.corpus, self.prices_dir, resolver,
            index_dir=_SELF_DIR / "index",
        )
        self._gen_agent = GenerateAgent(
            self._retriever, self.llm, self._gen_params)
        self._rev_agent = ReviewAgent(
            self._retriever, self.llm, self._rev_params)
        _log("ready (BM25 retrieval; dense inactive unless index built)")

    def generate(self, request: GenerateRequest) -> Report:
        try:
            content = self._gen_agent.run(request.topic)
            if isinstance(content, str) and content.strip():
                return Report(request_id=request.request_id, content=content)
        except Exception:
            pass
        return ExampleSubmission.generate(self, request)

    def review(self, request: ReviewRequest) -> list[ReviewIssue]:
        try:
            issues = self._rev_agent.run(request.report_markdown)
            if isinstance(issues, list):
                return issues
        except Exception:
            pass
        return ExampleSubmission.review(self, request)
