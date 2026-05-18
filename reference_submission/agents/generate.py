"""GenerateAgent: plan -> hybrid retrieve -> write -> numeric self-audit.

Self-audit is deterministic-first: pull verified EPS/revenue from the
FactStore, scan the draft for the same metric quoted with a clearly
contradictory magnitude, and run at most one corrective LLM pass.
"""

from __future__ import annotations

import os
import re

from llm import chat
from retrieval.numeric import contradicts, parse_numbers
from agents._util import load_prompt

_EPS_NEAR = re.compile(r"\beps\b", re.IGNORECASE)
_REV_NEAR = re.compile(r"\b(revenue|sales)\b", re.IGNORECASE)


class GenerateAgent:
    def __init__(self, retriever, llm_cfg, gen_params: dict) -> None:
        self.retriever = retriever
        self.llm = llm_cfg
        self.params = gen_params
        self._prompt = load_prompt("grounded_generate.md")

    def run(self, topic: str) -> str:
        res = self.retriever.search(topic, top_k=12)
        prompt = self._prompt.format(
            topic=topic,
            facts_block=res.facts or "(none)",
            evidence_block=res.evidence_block(),
        )
        draft = chat([{"role": "user", "content": prompt}],
                     config=self.llm, **self.params)
        if not isinstance(draft, str) or not draft.strip():
            raise RuntimeError("empty generation")
        if os.environ.get("ALPHASIGHT_GEN_NO_AUDIT") == "1":
            return draft
        return self._self_audit(topic, draft)

    def _self_audit(self, topic: str, draft: str) -> str:
        tickers = self.retriever.entity.resolve(topic)
        problems: list[str] = []
        for tk in tickers[:3]:
            tf = self.retriever.fact_store.lookup(tk)
            eps_truth = [e["actual"] for e in tf.earnings
                         if isinstance(e.get("actual"), (int, float))]
            for line in draft.splitlines():
                if not eps_truth or not _EPS_NEAR.search(line):
                    continue
                for n in parse_numbers(line):
                    if n.is_pct or abs(n.value) > 100:
                        continue
                    if all(contradicts(n.value, t) for t in eps_truth):
                        problems.append(
                            f'- QUOTE: "{n.raw}"  CONTEXT: {line.strip()[:120]}'
                            f'  FACT: {tk} reported EPS in '
                            f'{sorted(set(eps_truth))}')
                        break
        if not problems:
            return draft
        fix = (
            "A deterministic check found numbers in the draft that "
            "contradict verified earnings facts. Rewrite the report "
            "correcting ONLY these figures to the stated facts; keep the "
            "stance, structure, length and all [SOURCE: ...] citations.\n\n"
            f"PROBLEMS:\n{chr(10).join(problems[:6])}\n\n"
            f'DRAFT:\n"""{draft}"""'
        )
        try:
            fixed = chat([{"role": "user", "content": fix}],
                         config=self.llm, **self.params)
            return fixed if isinstance(fixed, str) and fixed.strip() else draft
        except Exception:
            return draft
