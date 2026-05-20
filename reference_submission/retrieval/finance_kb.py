"""Lightweight finance knowledge guardrails.

This module is intentionally small and offline. It reads the external
markdown knowledge file when available, runs regex triggers over the
current topic/facts, and returns a short prompt block. The knowledge is
used as calculation/basis guidance only, never as evidence.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeEntry:
    id: str
    title: str
    triggers: tuple[str, ...]
    note: str


_DEFAULT_ENTRIES: tuple[KnowledgeEntry, ...] = (
    KnowledgeEntry(
        id="earnings_consensus",
        title="EPS consensus basis",
        triggers=(
            r"\beps\b", r"earnings per share", r"consensus|estimate",
            r"surprise|beat|miss", r"每股收益|一致预期|超预期|不及预期",
        ),
        note=(
            "earnings.json is an EPS consensus table, not SEC GAAP truth. "
            "Its safest fields are actual, estimate, surprise, "
            "surprisePercent, and beat/miss direction; do not mix those "
            "absolute EPS values with SEC GAAP financials without a basis "
            "check."
        ),
    ),
    KnowledgeEntry(
        id="eps_scale",
        title="EPS scale safeguards",
        triggers=(
            r"\beps\b", r"split|stock split|拆股", r"scale|10x|10\s*x",
            r"每股收益",
        ),
        note=(
            "If SEC-implied EPS and earnings.json EPS differ by a stable "
            "10^n factor, treat absolute EPS scale as suspect and prefer "
            "scale-invariant checks such as surprise sign, surprisePercent, "
            "and beat/miss direction."
        ),
    ),
    KnowledgeEntry(
        id="gaap_ytd",
        title="SEC GAAP and YTD periods",
        triggers=(
            r"financials_reported|10-Q|10-K|SEC|GAAP",
            r"revenue|sales|net income|profit|cash flow|FCF",
            r"营收|收入|净利|利润|现金流|自由现金流|同比|环比",
            r"\bYTD\b|year-to-date|nine-month|six-month|累计",
        ),
        note=(
            "financials_reported.json is SEC/GAAP. Income-statement and "
            "cash-flow metrics may be fiscal-YTD; use single-quarter values "
            "only when they have been de-cumulated within the same fiscal "
            "year and same cumulative start. Do not invent missing Q1/Q2/Q3 "
            "values; quote the provided single-quarter FACT rows, and say "
            "unavailable if a period is not present."
        ),
    ),
    KnowledgeEntry(
        id="price_anchor",
        title="Price and return anchors",
        triggers=(
            r"price|close|open|high|low|return|52-week",
            r"股价|收盘|开盘|盘中|高点|低点|涨幅|跌幅|收益率",
        ),
        note=(
            "prices/*.csv is the anchor for price, OHLC, and return claims. "
            "Keep open/high/low/close distinct; intraday high is not a "
            "closing price."
        ),
    ),
    KnowledgeEntry(
        id="availability",
        title="Availability and contradiction",
        triggers=(
            r"recommendation|rating|target price|analyst|peer|peers",
            r"评级|目标价|分析师|同业|可比公司|缺失|没有数据",
        ),
        note=(
            "Empty or unavailable structured files mean available=false; "
            "missing data does not create a contradiction. For peers, remove "
            "the subject ticker itself before comparing peer lists."
        ),
    ),
)


class FinanceKnowledgeBase:
    def __init__(self, doc_paths: list[Path] | None = None,
                 max_entries: int = 5, max_chars: int = 1600) -> None:
        self.max_entries = max_entries
        self.max_chars = max_chars
        self.doc_paths = doc_paths if doc_paths is not None else _default_paths()
        self._doc_text = self._read_docs()

    def _read_docs(self) -> str:
        chunks: list[str] = []
        for p in self.doc_paths:
            try:
                if p.exists():
                    chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
        return "\n\n".join(chunks)

    def block_for(self, text: str) -> str:
        """Return a compact triggered knowledge block, or an empty string."""
        if os.environ.get("ALPHASIGHT_FINANCE_KB_DISABLE") == "1":
            return ""
        if not text:
            return ""
        matched: list[KnowledgeEntry] = []
        for entry in _DEFAULT_ENTRIES:
            if any(re.search(rx, text, re.IGNORECASE) for rx in entry.triggers):
                matched.append(entry)
            if len(matched) >= self.max_entries:
                break
        if not matched:
            return ""

        lines = [
            "Use these notes only as financial calculation/basis guards; "
            "they are NOT corpus evidence and must NOT be cited."
        ]
        doc_hint = self._source_hint()
        if doc_hint:
            lines.append(f"Knowledge source: {doc_hint}")
        for entry in matched:
            note = self._doc_backed_note(entry)
            lines.append(f"- {entry.title}: {note}")
        block = "\n".join(lines)
        if len(block) <= self.max_chars:
            return block
        return block[: self.max_chars].rsplit("\n", 1)[0]

    def _source_hint(self) -> str:
        names = [p.name for p in self.doc_paths if p.exists()]
        return ", ".join(names[:2])

    def _doc_backed_note(self, entry: KnowledgeEntry) -> str:
        """Return the compact curated rule.

        The external markdown files are still the source-of-truth anchor
        for this KB, but the generation prompt needs bounded guardrails.
        Long extracted markdown snippets can crowd out later rules, which
        is worse than a concise curated note.
        """
        return entry.note


def _default_paths() -> list[Path]:
    raw = os.environ.get("ALPHASIGHT_FINANCE_KB_PATHS", "").strip()
    if raw:
        return [Path(x).expanduser() for x in raw.split(os.pathsep) if x]

    names = [
        "docs/skill_fact-store-quality.md",
        "docs/finance_knowledge_skill.md",
    ]
    roots = [Path.cwd()]
    here = Path(__file__).resolve()
    roots.extend(here.parents)
    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for name in names:
            p = (root / name).resolve()
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _clean_md_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[-*]\s+", "", line)
    line = re.sub(r"^#+\s*", "", line)
    line = line.replace("`", "")
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def _skip_doc_line(line: str) -> bool:
    low = line.lower()
    if not line:
        return True
    if low.startswith(("name:", "description:", "version:", "inputs",
                       "required flags", "failure mode addressed",
                       "use this skill for", "basis:", "period_basis:")):
        return True
    if "dataset1/" in low or low.startswith(("|", ">")):
        return True
    return False


def _doc_matchers(entry: KnowledgeEntry) -> tuple[str, ...]:
    by_id = {
        "earnings_consensus": (
            r"earnings\.json", r"surprisePercent", r"beat/miss",
        ),
        "eps_scale": (
            r"SEC-implied EPS", r"scale_suspect", r"scale-invariant",
            r"10x smaller",
        ),
        "gaap_ytd": (
            r"financials_reported\.json", r"fiscal-YTD", r"de-cumulate",
            r"cumulative",
        ),
        "price_anchor": (
            r"prices/\*\.csv", r"price/return", r"\bOHLC", r"intraday",
        ),
        "availability": (
            r"available=false", r"Empty research files", r"peers\.json",
        ),
    }
    return by_id.get(entry.id, entry.triggers)
