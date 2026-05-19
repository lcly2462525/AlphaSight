---
name: retrieval-router
description: Route AlphaSight queries across FactStore, filing chunks, news chunks, BM25/dense retrieval, and compression.
version: 1.0.0
---

# Retrieval Router Skill

Use this skill for `reference_submission/retrieval/base.py`, `router.py`, `chunking.py`, `textutil.py`, `compress.py`, and dense/BM25 routing decisions.

## Retrieval Lanes

- **Fact lane**: structured research and prices. Use for numeric claims.
- **Filing lane**: high-authority narrative, risk, management commentary, filing date/form, and original disclosures.
- **News lane**: event timing, media attribution, market narrative.
- **Social lane**: aggregated weak sentiment only.

## Routing Policy

Numeric queries:

- `w_sparse` high, `use_fact_store=true`.
- Prefer FactStore, filing Item 8/MD&A, and source-path constrained ticker scope.

Narrative/causal queries:

- `w_dense` higher, filings and news enabled.
- For risks, prefer Item 1A and MD&A.

Event queries:

- tighten window when possible.
- bias news and 8-K filings.

Default:

- balanced BM25/dense.
- never widen to whole corpus when the generate/review subject should be locked.

## Scope Rules

1. For filing/research evidence, path ticker must match the locked subject ticker.
2. Multi-symbol news can cross-reference peers, but it must still support the specific claim.
3. If a hard time window returns no evidence, relax time while keeping ticker scope.
4. Do not include `research` raw JSON in text retrieval; use FactStore.

## Evidence Compression

Keep sentence-level snippets that contain:

- query tokens
- numbers/dates/percentages
- source names
- claim-relevant management wording

Reject binary/PDF garbage, boilerplate, navigation text, cookie banners, and base64/data URI residue.
