---
name: generate-agent
description: Generate AlphaSight reports with subject lock, grounded evidence, deterministic tool facts, citations, and self-audit.
version: 1.0.0
---

# Generate Agent Skill

Use this skill for `reference_submission/agents/generate.py`, `grounded_generate.md`, report generation, and self-audit design.

## Pipeline

```text
topic
  -> subject ticker lock
  -> query planning
  -> hybrid retrieval
  -> deterministic tools
  -> evidence merge
  -> writer
  -> self-audit
  -> report
```

## Subject Lock

Every generated report must have a locked subject ticker. If no subject can be resolved or selected from the valid universe, fall back rather than write from whole-corpus evidence.

Filing/research facts must come from the subject path unless the section is explicitly labeled as peer comparison.

## Evidence Use

- Facts block: structured numbers, price returns, filing metadata, tool outputs.
- Evidence block: filing/news quotes.
- Social block: weak sentiment/attention summary if available.

Do not write facts from model memory. If a needed fact is absent, say it is not available in the corpus.

## Citation Rules

Use source-specific support:

- price claims cite `prices/<T>.csv` or deterministic price tool output.
- financial values cite `research/<T>/...json` or filing text, with basis identified.
- event/source claims cite cleaned news or filings.
- social claims cite social aggregate output and mark it weak.

Generated citations should include a source path and a short literal support snippet when possible.

## Self-Audit

Run a final pass for:

- EPS actual/estimate/surprise direction
- revenue/net income magnitude and YTD/single-quarter wording
- price return arithmetic
- citation path/quote validity
- basis mismatches
- missing-data hallucinations

For scale-suspect facts, rewrite absolute EPS claims or qualify them; do not "correct" them to an unaligned raw value.
