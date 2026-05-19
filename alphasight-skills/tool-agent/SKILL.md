---
name: tool-agent
description: Deterministic AlphaSight tool-agent contracts for prices, financial metrics, ratios, filings, citations, and social signals.
version: 1.0.0
---

# Tool Agent Skill

Use this skill for deterministic Python tools under `reference_submission/tools/` and for integrating tool outputs into generate/review.

## Principle

Tools calculate and retrieve facts. They do not decide final report text or final review issues. Writer/adjudicator consumes tool outputs.

## Tool Registry

### price_event_tool

Input: ticker, event date, window, frequency.

Output: adjusted trading-window boundaries, start/end close, return, volume change, source path.

Authority: high for price/return claims.

### financial_metric_tool

Input: ticker, metric, fiscal year/quarter.

Output: value, basis, cumulative/single-quarter flag, numerator/denominator, source path.

Authority: high only when basis and period match the claim.

### ratio_calc_tool

Input: formula operands and units.

Output: normalized values, formula, result, tolerance.

Authority: high for arithmetic, margins, growth, bps/percentage-point conversion.

### filing_lookup_tool

Input: ticker, form/section/query/date range.

Output: source path, section, literal quote, score.

Authority: high for filing text and filing metadata.

### citation_check_tool

Input: report markdown and evidence/source files.

Output: valid citations, bad citations, missing literal quotes, repair hints.

Authority: high for citation faithfulness.

### social_signal_tool

Input: ticker and date range.

Output: availability, tweet_count, top_keywords, sentiment ratios, source paths.

Authority: weak; never primary for financial numbers or filings.

## Candidate Format

Tool output entering review should be explicit:

```text
DETERMINISTIC TOOL FACT [tool=<name> source=<path> basis=<basis>]
Claim: ...
Verified: ...
Flags: ...
```

If the tool cannot align ticker, period, basis, or source availability, return an abstention object rather than a contradiction.
