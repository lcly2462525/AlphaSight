"""LLM rereviewer for rounding-only review false positives."""

from __future__ import annotations

import json
import re
from typing import Any

from llm import LLMConfig, chat
from schemas import ReviewIssue


_PROMPT = """You are a rereviewer for ONE generated fact-check issue.

You are given exactly one JSON object:
- quote: the report text that was flagged
- reason: why another reviewer said the quote is wrong

Your only task is to decide whether this issue should be DROPPED because the
reason is essentially only a rounding / approximation / decimal precision
complaint.

DROP if the reason's claimed error is only normal rounding or approximation,
for example:
- 17.3938% vs 17.4%
- 3.2797% vs 3.28%
- 14.608B vs 14.61B
- "as rounded", "within rounding guard", "precision/tolerance", "not a contradiction beyond rounding"
- Chinese equivalents such as 四舍五入、近似、精度误差

KEEP if the reason alleges any substantive factual error beyond rounding:
- wrong date / wrong source / wrong company / wrong period
- wrong direction or sign, beat vs miss, increase vs decrease
- wrong unit or scale, such as 22.5B vs 224.9B
- wrong underlying actual/estimate/consensus value
- a range or phrase implies a different substantive value
- source attribution, peer membership, intraday-vs-close, open-vs-close

Important:
- Do not decide whether the issue is true in the real world.
- Do not use outside knowledge.
- Interpret the semantics of the reason, not keyword matching.
- When unsure, KEEP.

# ISSUE
{item}

Return JSON only:
{{"action": "keep", "why": "<brief>"}}
or
{{"action": "drop", "why": "<brief>"}}
"""


def _parse_json_obj(raw: str) -> dict[str, Any]:
    txt = (raw or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```\w*\n?", "", txt).rstrip("`").rstrip()
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    try:
        data = json.loads(m.group(0) if m else txt)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_rounding_only_issue(
    issue: ReviewIssue,
    *,
    llm: LLMConfig,
    max_tokens: int = 128,
) -> tuple[bool, str]:
    """Return (drop, why). Fail-open: exceptions propagate to caller."""
    item = json.dumps({
        "quote": issue.quote[:900],
        "reason": issue.reason[:1200],
    }, ensure_ascii=False)
    raw = chat(
        [{"role": "user", "content": _PROMPT.format(item=item)}],
        config=llm,
        temperature=0.0,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    data = _parse_json_obj(raw)
    action = str(data.get("action", "keep")).strip().lower()
    why = str(data.get("why", "")).strip()
    return action == "drop", why


def filter_rounding_issues(
    issues: list[ReviewIssue],
    *,
    llm: LLMConfig,
    max_tokens: int = 128,
) -> tuple[list[ReviewIssue], list[dict[str, Any]]]:
    kept: list[ReviewIssue] = []
    dropped: list[dict[str, Any]] = []
    for issue in issues:
        try:
            drop, why = is_rounding_only_issue(
                issue, llm=llm, max_tokens=max_tokens)
        except Exception as e:  # fail open: never lose an issue on rereviewer failure
            kept.append(issue)
            dropped.append({
                "quote": issue.quote,
                "reason": issue.reason,
                "rereviewer_error": f"{type(e).__name__}: {e}",
                "kept": True,
            })
            continue
        if drop:
            dropped.append({
                "quote": issue.quote,
                "reason": issue.reason,
                "rereviewer_why": why,
                "kept": False,
            })
        else:
            kept.append(issue)
    return kept, dropped
