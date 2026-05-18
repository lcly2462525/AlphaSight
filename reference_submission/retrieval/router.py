"""QueryRouter: rule-based, zero-LLM, deterministic.

Tilts the BM25/dense weights and retrieval bias by query intent. Never
a hard switch — both paths always run, so worst case is plain RRF and
recall is never lost. Designed to be the natural router-on/off ablation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUMERIC = re.compile(
    r"\b(revenue|eps|margin|guidance|growth|yoy|qoq|profit|earnings|"
    r"减计|营收|利润|增长|同比|环比|\d+%|\$\d)\b", re.IGNORECASE)
_NARRATIVE = re.compile(
    r"(影响|原因|为什么|趋势|叙事|反转|逻辑|narrative|reversal|because|"
    r"why|impact|driver|thesis|risk|归因)", re.IGNORECASE)
_EVENT = re.compile(
    r"(8-K|announce|launch|acquisition|merger|recall|lawsuit|发布|收购|"
    r"事件|公告|\b20\d{2}-\d{2}-\d{2}\b)", re.IGNORECASE)


@dataclass
class RouteDecision:
    w_sparse: float = 0.5
    w_dense: float = 0.5
    use_fact_store: bool = True
    kind_bias: dict[str, float] = field(default_factory=dict)
    item_filter: list[str] | None = None
    tighten_window: bool = False
    intent: str = "default"


class QueryRouter:
    def decide(self, query: str) -> RouteDecision:
        numeric = bool(_NUMERIC.search(query))
        narrative = bool(_NARRATIVE.search(query))
        event = bool(_EVENT.search(query))

        if numeric and not narrative:
            return RouteDecision(
                w_sparse=0.65, w_dense=0.35, use_fact_store=True,
                kind_bias={"research": 1.3, "filing": 1.1},
                intent="numeric")
        if narrative:
            d = RouteDecision(
                w_sparse=0.4, w_dense=0.6, use_fact_store=True,
                kind_bias={"filing": 1.3, "news": 1.1},
                intent="narrative")
            if re.search(r"(risk|风险|归因)", query, re.IGNORECASE):
                d.item_filter = ["item 1a", "item 7"]
            return d
        if event:
            return RouteDecision(
                w_sparse=0.5, w_dense=0.5, use_fact_store=True,
                kind_bias={"news": 1.3, "filing": 1.1},
                tighten_window=True, intent="event")
        return RouteDecision()
