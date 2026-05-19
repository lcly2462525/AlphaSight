"""Deterministic finance/economics tools for generation.

The generator already retrieves text well; this layer adds small,
auditable calculations that a sell-side analyst would expect before
writing: growth, margins, TTM, EPS surprise, price reaction, drawdown,
volatility and peer-relative performance. It uses pandas/numpy when
available, with a stdlib fallback so the submission still runs in a
minimal offline judge.
"""

from __future__ import annotations

import math
import json
import re
import statistics
from dataclasses import dataclass

try:  # open-source tabular/quant backend; optional in the judge image.
    import numpy as _np
    import pandas as _pd
except Exception:  # pragma: no cover - depends on runtime image.
    _np = None
    _pd = None


_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _pct(now: float | int | None, before: float | int | None) -> float | None:
    if not isinstance(now, (int, float)):
        return None
    if not isinstance(before, (int, float)) or before == 0:
        return None
    return (now / before - 1.0) * 100.0


def _ratio(num: float | int | None, den: float | int | None) -> float | None:
    if not isinstance(num, (int, float)):
        return None
    if not isinstance(den, (int, float)) or den == 0:
        return None
    return num / den * 100.0


def _fmt(v: float | int | None, digits: int = 1) -> str:
    if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        return "NA"
    return f"{v:+.{digits}f}%"


def _num(v: float | int | None) -> str:
    if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        return "NA"
    return f"{float(v):.0f}"


def _idx(row: dict) -> int:
    y = row.get("year")
    q = row.get("quarter")
    if isinstance(y, int) and isinstance(q, int):
        return y * 4 + q
    return -1


def _latest_year_from_topic(topic: str) -> int | None:
    years = [int(y) for y in _YEAR_RE.findall(topic or "")]
    return max(years) if years else None


def _max_drawdown(closes: list[float]) -> float | None:
    if not closes:
        return None
    peak = closes[0]
    worst = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak:
            worst = min(worst, (c / peak - 1.0) * 100.0)
    return worst


def _annualized_vol(closes: list[float]) -> float | None:
    if len(closes) < 3:
        return None
    rets = [closes[i] / closes[i - 1] - 1.0
            for i in range(1, len(closes)) if closes[i - 1]]
    if len(rets) < 2:
        return None
    if _np is not None:
        return float(_np.std(_np.array(rets), ddof=1) * math.sqrt(252) * 100)
    return statistics.stdev(rets) * math.sqrt(252) * 100


@dataclass
class FinancialToolAgent:
    fact_store: object

    @property
    def backend(self) -> str:
        if _pd is not None and _np is not None:
            return "pandas/numpy"
        return "stdlib"

    def analysis_block(self, tickers: list[str], topic: str,
                       max_lines: int = 18) -> str:
        lines = self._run_calls(self._default_calls(tickers, topic))
        return "\n".join(lines[:max_lines]) if lines else "(no tool output)"

    def plan_and_run(self, tickers: list[str], topic: str, llm_cfg,
                     gen_params: dict, max_lines: int = 18
                     ) -> tuple[str, list[str]]:
        """Ask the LLM which finance tools it wants, then execute them.

        This is deliberately a constrained ToolAgent, not arbitrary code
        execution: the model can only choose from a fixed registry, and
        Python computes the results against the offline FactStore.
        """
        calls = self._plan_calls(tickers, topic, llm_cfg, gen_params)
        trace: list[str] = []
        if calls:
            trace.append("LLM requested tools: " + ", ".join(
                f"{c.get('tool')}({c.get('ticker')})" for c in calls))
        else:
            calls = self._default_calls(tickers, topic)
            trace.append("LLM tool plan empty/invalid; using default tools")
        lines = self._run_calls(calls)
        trace.extend(
            f"executed {c.get('tool')} for {c.get('ticker')}"
            for c in calls if c.get("tool"))
        block = "\n".join(lines[:max_lines]) if lines else "(no tool output)"
        return block, trace

    def _default_calls(self, tickers: list[str], topic: str) -> list[dict]:
        year = _latest_year_from_topic(topic)
        out: list[dict] = []
        for ticker in tickers[:3]:
            out.extend([
                {"tool": "financial_metric_tool", "ticker": ticker},
                {"tool": "ratio_calc_tool", "ticker": ticker},
                {"tool": "price_event_tool", "ticker": ticker, "year": year},
                {"tool": "peer_relative_tool", "ticker": ticker, "year": year},
            ])
        return out

    def _plan_calls(self, tickers: list[str], topic: str, llm_cfg,
                    gen_params: dict) -> list[dict]:
        from llm import chat

        planner = (
            "You are a finance ToolAgent planner. Choose the analysis "
            "tools needed before writing an equity research note. Return "
            "ONLY valid JSON with this shape: "
            '{"calls":[{"tool":"financial_metric_tool|ratio_calc_tool|'
            'price_event_tool|peer_relative_tool","ticker":"NVDA",'
            '"year":2025}]}. Use only listed tickers. Prefer 3-5 calls.\n\n'
            "Tools:\n"
            "- financial_metric_tool: revenue/net income growth, margins, "
            "latest EPS surprise.\n"
            "- ratio_calc_tool: TTM revenue/net income/net margin.\n"
            "- price_event_tool: stock return, drawdown, volatility.\n"
            "- peer_relative_tool: peer-average return and relative alpha.\n\n"
            f"TICKERS: {', '.join(tickers)}\nTOPIC: {topic}"
        )
        try:
            raw = chat(
                [{"role": "user", "content": planner}],
                config=llm_cfg,
                **{**gen_params, "temperature": 0.0, "max_tokens": 500,
                   "response_format": {"type": "json_object"}},
            )
        except Exception:
            return []
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            m = re.search(r"\{.*\}", raw or "", re.DOTALL)
            if not m:
                return []
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []
        allowed_tools = {
            "financial_metric_tool", "ratio_calc_tool",
            "price_event_tool", "peer_relative_tool",
        }
        allowed_tickers = set(tickers)
        calls = []
        for c in data.get("calls", []) if isinstance(data, dict) else []:
            if not isinstance(c, dict):
                continue
            tool = c.get("tool")
            ticker = str(c.get("ticker") or "").upper()
            if tool not in allowed_tools or ticker not in allowed_tickers:
                continue
            call = {"tool": tool, "ticker": ticker}
            if isinstance(c.get("year"), int):
                call["year"] = c["year"]
            calls.append(call)
            if len(calls) >= 8:
                break
        return calls

    def _run_calls(self, calls: list[dict]) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for call in calls:
            tool = call.get("tool")
            ticker = str(call.get("ticker") or "").upper()
            year = call.get("year")
            if not ticker:
                continue
            if not isinstance(year, int):
                year = None
            if tool == "financial_metric_tool":
                produced = [x for x in self._financial_metric_lines(ticker)
                            if "TOOL financial_metric_tool" in x]
            elif tool == "ratio_calc_tool":
                produced = [x for x in self._financial_metric_lines(ticker)
                            if "TOOL ratio_calc_tool" in x]
            elif tool == "price_event_tool":
                produced = self._price_lines(ticker, year)
            elif tool == "peer_relative_tool":
                produced = self._peer_lines(ticker, year)
            else:
                produced = []
            for line in produced:
                if line not in seen:
                    lines.append(line)
                    seen.add(line)
        return lines

    def _financial_metric_lines(self, ticker: str) -> list[str]:
        rows = [r for r in self.fact_store.period_rows(ticker)
                if isinstance(r.get("year"), int)
                and isinstance(r.get("quarter"), int)]
        rows.sort(key=_idx, reverse=True)
        by_idx = {_idx(r): r for r in rows}
        out: list[str] = []
        for cur in rows[:4]:
            y, q = cur["year"], cur["quarter"]
            src = f"research/{ticker}/financials_reported.json"
            rev = cur.get("revenue")
            ni = cur.get("net_income")
            gp = cur.get("gross_profit")
            op = cur.get("operating_income")
            prior_y = by_idx.get((y - 1) * 4 + q)
            prior_q = by_idx.get(_idx(cur) - 1)
            rev_yoy = _pct(rev, prior_y.get("revenue") if prior_y else None)
            rev_qoq = _pct(rev, prior_q.get("revenue") if prior_q else None)
            ni_yoy = _pct(ni, prior_y.get("net_income") if prior_y else None)
            margins = {
                "gross_margin": _ratio(gp, rev),
                "operating_margin": _ratio(op, rev),
                "net_margin": _ratio(ni, rev),
            }
            if rev_yoy is None and rev_qoq is None and ni_yoy is None:
                continue
            out.append(
                f"[SOURCE: {src}] TOOL financial_metric_tool {ticker} "
                f"FY{y}Q{q} revenue={_num(rev)} net_income={_num(ni)} "
                f"revenue_yoy={_fmt(rev_yoy)} revenue_qoq={_fmt(rev_qoq)} "
                f"net_income_yoy={_fmt(ni_yoy)} "
                f"gross_margin={_fmt(margins['gross_margin'])} "
                f"operating_margin={_fmt(margins['operating_margin'])} "
                f"net_margin={_fmt(margins['net_margin'])}")
            if len(out) >= 2:
                break

        ttm_rows = [r for r in rows if isinstance(r.get("revenue"), (int, float))]
        if len(ttm_rows) >= 4:
            last4 = ttm_rows[:4]
            rev_ttm = sum(float(r.get("revenue") or 0) for r in last4)
            ni_vals = [r.get("net_income") for r in last4]
            ni_ttm = (sum(float(v or 0) for v in ni_vals)
                      if all(isinstance(v, (int, float)) for v in ni_vals)
                      else None)
            first, last = last4[-1], last4[0]
            out.append(
                f"[SOURCE: research/{ticker}/financials_reported.json] "
                f"TOOL ratio_calc_tool {ticker} TTM through "
                f"FY{last['year']}Q{last['quarter']} "
                f"revenue_ttm={_num(rev_ttm)} net_income_ttm={_num(ni_ttm)} "
                f"net_margin_ttm={_fmt(_ratio(ni_ttm, rev_ttm))} "
                f"quarters=FY{first['year']}Q{first['quarter']}-"
                f"FY{last['year']}Q{last['quarter']}")

        earnings = [e for e in self.fact_store.lookup(ticker).earnings
                    if isinstance(e.get("year"), int)
                    and isinstance(e.get("quarter"), int)]
        earnings.sort(key=lambda e: e["year"] * 4 + e["quarter"],
                      reverse=True)
        if earnings:
            e = earnings[0]
            surprise_pct = e.get("surprisePercent")
            out.append(
                f"[SOURCE: research/{ticker}/earnings.json] "
                f"TOOL financial_metric_tool {ticker} "
                f"FY{e.get('year')}Q{e.get('quarter')} EPS "
                f"actual={e.get('actual')} estimate={e.get('estimate')} "
                f"surprise={e.get('surprise')} "
                f"surprise_percent={surprise_pct}")
        return out

    def _price_lines(self, ticker: str, year: int | None) -> list[str]:
        prices = self.fact_store.lookup(ticker).prices
        days = sorted(prices)
        if not days:
            return []
        if year is not None:
            scoped = [d for d in days if d.startswith(f"{year}-")]
        else:
            scoped = []
        if len(scoped) < 2:
            scoped = days
        start, end = scoped[0], scoped[-1]
        closes = [float(prices[d]["close"]) for d in scoped
                  if isinstance(prices[d].get("close"), (int, float))]
        c0 = prices[start].get("close")
        c1 = prices[end].get("close")
        ret = _pct(c1, c0)
        mdd = _max_drawdown(closes)
        vol = _annualized_vol(closes)
        return [
            f"[SOURCE: prices/{ticker}.csv] TOOL price_event_tool {ticker} "
            f"{start} to {end} start_close={c0} end_close={c1} "
            f"close_return={_fmt(ret)} max_drawdown={_fmt(mdd)} "
            f"annualized_volatility={_fmt(vol)} "
            f"computed_backend={self.backend}"
        ]

    def _peer_lines(self, ticker: str, year: int | None) -> list[str]:
        prices = self.fact_store.lookup(ticker).prices
        days = sorted(prices)
        if not days:
            return []
        scoped = [d for d in days if year and d.startswith(f"{year}-")]
        if len(scoped) < 2:
            scoped = days
        subject_ret = _pct(prices[scoped[-1]].get("close"),
                           prices[scoped[0]].get("close"))
        peer_rets: list[tuple[str, float]] = []
        for peer in self.fact_store.peers(ticker)[:8]:
            if peer == ticker:
                continue
            pp = self.fact_store.lookup(peer).prices
            pdays = sorted(d for d in pp if (not year or d.startswith(f"{year}-")))
            if len(pdays) < 2:
                pdays = sorted(pp)
            if len(pdays) < 2:
                continue
            r = _pct(pp[pdays[-1]].get("close"), pp[pdays[0]].get("close"))
            if isinstance(r, float):
                peer_rets.append((peer, r))
        if not peer_rets or not isinstance(subject_ret, float):
            return []
        avg = sum(r for _, r in peer_rets) / len(peer_rets)
        best = max(peer_rets, key=lambda x: x[1])
        worst = min(peer_rets, key=lambda x: x[1])
        peer_sources = ",".join(f"prices/{p}.csv" for p, _ in peer_rets[:5])
        return [
            f"[SOURCE: prices/{ticker}.csv; {peer_sources}] "
            f"TOOL peer_relative_tool {ticker} subject_return="
            f"{_fmt(subject_ret)} peer_average_return={_fmt(avg)} "
            f"relative_alpha={_fmt(subject_ret - avg)} "
            f"best_peer={best[0]}:{_fmt(best[1])} "
            f"worst_peer={worst[0]}:{_fmt(worst[1])}"
        ]
