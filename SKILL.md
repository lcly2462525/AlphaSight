---
name: alphasight-orchestrator
description: Coordinate AlphaSight generate/review work across structured facts, retrieval, news, social signals, tool agents, and evaluation.
version: 2.0.0
---

# AlphaSight Orchestrator

Use this skill for this repository's AlphaSight tasks: offline financial report generation, report review, evidence routing, data-quality hardening, and sub-agent/tool design.

## Core Method

AlphaSight is not a generic RAG task. Treat every claim as one of three lanes:

1. **Deterministic facts**: `research/*.json`, `prices/*.csv`, filing catalog, and report-internal arithmetic.
2. **Text evidence**: filing sections and cleaned news snippets that can support or refute narrative/source claims.
3. **Weak signals**: social/news sentiment and market narrative aggregates. These may support framing but cannot alone overturn a filing, price CSV, or structured fact.

Before emitting an issue or a generated conclusion, check:

- **Availability**: does this ticker/source/capability actually exist in the local corpus?
- **Basis**: GAAP SEC filing, non-GAAP consensus EPS, price, derived calculation, news, or social.
- **Period**: fiscal quarter end, calendar period label, YTD cumulative, single-quarter value, TTM, or event window.
- **Scale**: known or suspected unit/scale mismatch, such as the NFLX EPS `earnings.json` 10x issue.
- **Authority**: structured facts and filings outrank news; news outranks social; social is weak corroboration only.

## Module Skills

Load the relevant module skill when working on that part of the system:

- `alphasight-skills/fact-store-quality/SKILL.md`: structured data, EPS scale, YTD de-cumulation, basis/availability flags.
- `alphasight-skills/retrieval-router/SKILL.md`: BM25/dense routing, kind bias, filing/news chunk policy.
- `alphasight-skills/news-evidence/SKILL.md`: news cleaning, source attribution, event evidence, and news false-positive controls.
- `alphasight-skills/social-signal/SKILL.md`: social dataset use as aggregated weak signal.
- `alphasight-skills/review-agent/SKILL.md`: claim extraction, deterministic candidates, exact/weak tiers, veto/adjudication.
- `alphasight-skills/generate-agent/SKILL.md`: grounded report generation, subject lock, citation discipline, self-audit.
- `alphasight-skills/tool-agent/SKILL.md`: deterministic Python tools for prices, metrics, ratios, filings, citations, and social signals.

## Operating Rules

1. Do not compare raw numbers across different basis values unless the basis is explicitly aligned.
2. Do not treat missing data as contradictory evidence.
3. Do not use social posts as primary evidence for financial numbers, filing facts, or price moves.
4. Do not let news body boilerplate, consent text, navigation text, or duplicate articles enter high-weight evidence.
5. For review, emit only when the claim is contradicted by available same-basis evidence or by a deterministic calculation.
6. For generate, write "not available in corpus" rather than filling gaps with model memory.

## Local References

- Architecture: `docs/DESIGN.md`
- Tool-agent plan: `docs/TOOL_AGENT_VL_PLAN.md`
- Review design: `docs/REVIEW.md`
- Review improvement plan: `docs/review_plan.md`
- Implementation entry points: `reference_submission/submission.py`, `reference_submission/retrieval/`, `reference_submission/agents/`, `reference_submission/tools/`
