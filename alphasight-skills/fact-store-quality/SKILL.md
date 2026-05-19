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
