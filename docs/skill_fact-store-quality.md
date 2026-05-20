---
name: fact-store-quality
description: Normalize and verify AlphaSight structured data with availability, basis, period, YTD, and scale safeguards.
version: 1.0.0
---

# Fact Store Quality Skill

Use this skill for `reference_submission/retrieval/fact_store.py`, structured financial facts, and any review/generate logic that compares numbers.

## Inputs

- `dataset1/corpus/research/<T>/earnings.json`
- `dataset1/corpus/research/<T>/financials_reported.json`
- `dataset1/corpus/research/<T>/peers.json`
- `dataset1/prices/<T>.csv`
- `dataset1/catalog.jsonl`

## Required Flags

Every structured fact should carry:

- `source_path`
- `basis`: `nongaap_consensus`, `gaap_sec`, `price`, `filing_catalog`, `derived`
- `period_basis`: `calendar_label`, `fiscal_period_end`, `event_window`, `ytd`, `single_quarter`
- `available`
- `scale_suspect`
- `cumulative`
- `decumulated`

## Rules

1. `earnings.json` is an EPS consensus table, not SEC GAAP truth. Its safest fields are `surprise`, `surprisePercent`, and beat/miss direction.
2. `financials_reported.json` is SEC/GAAP. Income-statement and cash-flow metrics may be fiscal-YTD; de-cumulate only within the same fiscal year and same cumulative start.
3. `prices/*.csv` is the anchor for price/return claims.
4. `peers.json` must be normalized by removing the ticker itself before peer-list contradiction checks.
5. Empty research files create `available=false`; they do not create contradictions.

## EPS Scale Procedure

Use SEC-implied EPS only as a sanity check:

```text
sec_eps_cum = NetIncomeLoss / WeightedAverageNumberOfDilutedSharesOutstanding
sec_eps_single_q = sec_eps_cum - prior_quarter_sec_eps_cum
ratio = sec_eps_single_q / earnings.actual
```

Mark `scale_suspect=true` only when the same ticker shows a stable 10^n factor across multiple adjacent quarters. Do not flag one-off cross-basis differences; ABBV/META-style GAAP vs non-GAAP gaps are expected.

For scale-suspect EPS, do not emit exact absolute EPS errors. Use scale-invariant checks: beat/miss, surprise sign, surprise percent, and direction.

## Failure Mode Addressed

NFLX 2025 EPS values in `earnings.json` are 10x smaller than SEC-implied/report EPS. A report saying EPS was about `$7.19` should not be marked wrong solely because `earnings.json` says `0.719`.

## Generate-Side Audit Addendum

The finance KB is a prompt guardrail, not a source of truth. Any model-written
calculation that uses `financials_reported.json` must still be checked against
FactStore values.

### Revenue Period Checks

For every generated line that locally claims revenue:

- If the prose says `Q1/Q2/Q3 revenue`, compare the nearby money amount against
  that period's `single-quarter revenue`.
- If the prose says `YTD`, `year-to-date`, `cumulative`, or `through Qn`, compare
  the nearby money amount against `revenue_cum`.
- If the prose says `single-quarter`, `standalone`, or `alone`, do not let a
  distant YTD/cumulative phrase in the same sentence change the basis.
- Do not compare segment revenue or product revenue, such as Data Center revenue
  or Blackwell revenue, against total company revenue.
- Do not compare net income values against revenue just because the same line
  later says "revenue growth"; the revenue cue must be local to the money
  amount.

### Direction and Growth Wording

- `A down from B` is wrong when `A > B`; rewrite as `up from`.
- Do not write "triple-digit YTD revenue growth" unless current cumulative
  revenue is at least 100% above the prior-year comparable cumulative period.

### NVDA Validation Example

For NVDA FY2026 Q3:

```text
Q1 single-quarter revenue = 44.062B
Q2 single-quarter revenue = 46.743B
Q3 single-quarter revenue = 57.006B
Q3 fiscal-YTD cumulative revenue = 147.811B
44.062B + 46.743B + 57.006B = 147.811B
```

The audit must reject:

```text
$35.082B in Q1 alone
$30.040B in Q1
147.811B down from 90.805B
triple-digit YTD revenue growth
```

The audit should not reject:

```text
Q3 single-quarter revenue was $57.006B, up from Q2 revenue of $46.743B.
YTD revenue through Q3 was $147.811B.
```
