# AlphaSight Skill Design

This document maps the repository design in `docs/DESIGN.md`, `docs/TOOL_AGENT_VL_PLAN.md`, and `docs/REVIEW.md` into local skills.

## Registry

| Skill | File | Purpose |
|---|---|---|
| Orchestrator | `SKILL.md` | Top-level operating rules and module routing |
| Financial fact root | `finskills/SKILL.md` | Offline financial verification method |
| Fact store quality | `alphasight-skills/fact-store-quality/SKILL.md` | Availability, basis, period, YTD, EPS scale |
| Retrieval router | `alphasight-skills/retrieval-router/SKILL.md` | Fact/filing/news/social lanes and hybrid routing |
| News evidence | `alphasight-skills/news-evidence/SKILL.md` | News cleaning, attribution, event evidence |
| Social signal | `alphasight-skills/social-signal/SKILL.md` | Aggregated weak social signals |
| Review agent | `alphasight-skills/review-agent/SKILL.md` | Claim verification and issue emission |
| Generate agent | `alphasight-skills/generate-agent/SKILL.md` | Grounded report generation and self-audit |
| Tool agent | `alphasight-skills/tool-agent/SKILL.md` | Deterministic Python tool contracts |

## Design Fixes Captured

1. **News false positives**: news is cleaned and used for events/source attribution, not as numeric authority.
2. **Social underuse/misuse**: social becomes a weak aggregate SignalStore; availability must be checked against actual files, not catalog rows alone.
3. **Sub-agent boundaries**: review/generate/tool agents have separate contracts; tools calculate, LLM writes/adjudicates.
4. **P-SCALE**: EPS absolute values must pass basis/scale alignment before exact comparison; NFLX-style 10x data-source errors degrade to scale-invariant checks.
5. **P-TIME/P-DATA**: fiscal period, calendar label, YTD cumulative, and source availability are first-class flags.

## Implementation Notes

- `index.ts` and `finskills/index.ts` now expose a declarative registry instead of importing an external prediction-market news feed.
- The Python runtime remains under `reference_submission/`; these skills document the intended behavior and are safe to load independently.
- Future code changes should make these skill contracts executable through `FactStore` flags, a `SignalStore`, and a `tools/registry.py`.
