---
name: review-agent
description: Design and operate AlphaSight report review with typed claim extraction, deterministic evidence, and contradiction-only adjudication.
version: 1.0.0
---

# Review Agent Skill

Use this skill for `reference_submission/agents/review.py`, review prompts, false-positive/false-negative analysis, and issue emission policy.

## Pipeline

```text
report
  -> Anchored normalization
  -> claim extraction: regex + LLM
  -> subject ticker lock
  -> typed candidates
  -> exact-tier drop-only veto
  -> weak/narrative grounded contradiction check
  -> focused verify
  -> list[ReviewIssue]
```

## Candidate Types

- EPS actual/estimate/surprise direction: `earnings.json`, with scale/basis rules.
- Financial metrics: `financials_reported.json`, YTD-aware and basis-tagged.
- Filing form/date/accession: catalog/path metadata.
- Fiscal period end: financials `endDate`.
- Price/return/range: `prices/*.csv`.
- Peer list: `peers.json` after removing self.
- Arithmetic: report-internal calculation.
- Source/narrative: cleaned filing/news evidence.
- Social: only exact social-volume/sentiment claims when data exists.

## Exact Tier

Emit only after a drop-only veto. Exact candidates must be:

- same ticker
- same basis
- same period/window
- same metric
- available source
- not scale-suspect in a way that invalidates absolute comparison

## Weak Tier

Weak candidates go through contradiction-only adjudication:

- default is drop/abstain
- keep only when evidence explicitly refutes the quote
- missing data is not contradiction
- social-only contradiction is weak and usually insufficient

## Quote Discipline

Every emitted `quote` must be a verbatim substring of the report. Do not emit tiny fragments such as a date alone unless that fragment is the full erroneous claim.

## FP Controls

- Do not parse `actual <num>` from unrelated price or volume prose.
- Do not compare GAAP SEC EPS to non-GAAP consensus EPS as exact contradiction.
- Do not treat low EPS as scale error.
- Do not use catalog social rows as proof when social files are absent.
- Do not let news boilerplate become contradiction evidence.
