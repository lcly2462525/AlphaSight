"""A/B validate finance_kb prompt impact on one generate topic.

The script builds the same retrieved facts/evidence for both variants,
then calls the configured OpenAI-compatible endpoint twice:

  - without KB: FINANCIAL KNOWLEDGE NOTES = (none)
  - with KB: regex-triggered notes from docs/skill_fact-store-quality.md

It prints only the topic, injected KB block, and lines relevant to
EPS/revenue/YTD/price from each generated report plus a unified diff.
"""

from __future__ import annotations

import difflib
import os
import re
import sys

sys.path.insert(0, "reference_submission")

from agents._util import load_prompt  # noqa: E402
from catalog import collect_symbols, load_catalog  # noqa: E402
from llm import LLMConfig, chat  # noqa: E402
from retrieval.base import HybridRetriever  # noqa: E402
from retrieval.entity import EntityResolver  # noqa: E402
from retrieval.finance_kb import FinanceKnowledgeBase  # noqa: E402


TOPIC = (
    "NVDA FY2026 Q3 EPS surprise and beat/miss direction, "
    "de-cumulated single-quarter revenue versus YTD revenue, "
    "and 2025 price return."
)
KEY = re.compile(
    r"eps|surprise|beat|miss|revenue|ytd|year-to-date|single-quarter|"
    r"cumulative|price|close|return|earnings",
    re.IGNORECASE,
)


def relevant_lines(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s and KEY.search(s):
            out.append(s)
    return out[:35]


def main() -> int:
    os.environ.setdefault("ALPHASIGHT_CORPUS_DIR", "dataset/corpus")
    os.environ.setdefault("ALPHASIGHT_PRICES_DIR", "dataset/prices")
    os.environ.setdefault("ALPHASIGHT_PRICES_MINUTE_DIR", "dataset/prices_minute")
    os.environ.setdefault("ALPHASIGHT_CATALOG_PATH", "dataset/catalog.jsonl")
    os.environ.setdefault("ALPHASIGHT_LLM_RETRIES", "1")
    os.environ.setdefault("ALPHASIGHT_LLM_TIMEOUT", "90")

    catalog = load_catalog(os.environ["ALPHASIGHT_CATALOG_PATH"])
    resolver = EntityResolver(collect_symbols(catalog))
    retriever = HybridRetriever(
        catalog,
        os.environ["ALPHASIGHT_CORPUS_DIR"],
        os.environ["ALPHASIGHT_PRICES_DIR"],
        resolver,
        index_dir=None,
    )
    res = retriever.search(TOPIC, top_k=6, tickers=["NVDA"], require_subject=True)
    facts_block = res.facts or "(none)"
    evidence_block = res.evidence_block()
    knowledge_block = (
        FinanceKnowledgeBase(max_entries=5, max_chars=1200)
        .block_for("\n".join([TOPIC, facts_block[:4000]]))
        or "(none)"
    )
    prompt_tpl = load_prompt("grounded_generate.md")
    subject_block = (
        "This report subject company is NVDA. Make every claim about NVDA "
        "using only NVDA facts/evidence."
    )

    def prompt(kb: str) -> str:
        return prompt_tpl.format(
            topic=TOPIC,
            subject_block=subject_block,
            facts_block=facts_block,
            knowledge_block=kb,
            evidence_block=evidence_block,
        )

    print("===== TOPIC =====")
    print(TOPIC)
    print("\n===== ENABLED_KB_BLOCK =====")
    print(knowledge_block)
    print("\n===== PROMPT_SIZE =====")
    no_kb_prompt = prompt("(none)")
    kb_prompt = prompt(knowledge_block)
    print(f"without_kb_chars={len(no_kb_prompt)}")
    print(f"with_kb_chars={len(kb_prompt)}")
    print(f"delta={len(kb_prompt) - len(no_kb_prompt)}")

    params = {"max_tokens": 900, "temperature": 0.0, "top_p": 1.0}
    print("\n[call] without KB", flush=True)
    without = chat(
        [{"role": "user", "content": no_kb_prompt}],
        config=LLMConfig.from_env(),
        **params,
    )
    print("[call] with KB", flush=True)
    with_kb = chat(
        [{"role": "user", "content": kb_prompt}],
        config=LLMConfig.from_env(),
        **params,
    )

    a = relevant_lines(without)
    b = relevant_lines(with_kb)
    print("\n===== WITHOUT_KB_RELEVANT =====")
    print("\n".join(a))
    print("\n===== WITH_KB_RELEVANT =====")
    print("\n".join(b))
    print("\n===== UNIFIED_DIFF_RELEVANT =====")
    for line in difflib.unified_diff(
        a, b, fromfile="without_kb", tofile="with_kb", lineterm=""
    ):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
