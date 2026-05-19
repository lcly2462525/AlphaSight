---
name: news-evidence
description: Clean and use AlphaSight news evidence for events and source attribution without letting news noise create false positives.
version: 1.0.0
---

# News Evidence Skill

Use this skill whenever a claim depends on `dataset1/corpus/news`, media attribution, event timing, or market-moving narrative.

## What News Can Prove

News may support or refute:

- event happened / did not happen within the corpus window
- source attribution, such as Bloomberg vs CNBC vs Reuters
- announcement timing and market narrative
- analyst or market commentary when structured recommendations are unavailable

News must not override:

- `prices/*.csv` for price moves
- filing catalog for filing dates/forms/accessions
- `financials_reported.json` for GAAP numbers
- same-basis `earnings.json` for EPS surprise table facts

## Cleaning Requirements

Before news enters evidence:

1. Prefer title and lead/summary over full body.
2. Remove cookie banners, consent text, navigation, unrelated market-roundup boilerplate, and duplicated syndicated bodies.
3. De-duplicate repeated articles by normalized title + provider + date.
4. Require ticker/path relevance or explicit subject mention.
5. Keep provider/source metadata visible when the claim is about attribution.

## Review Rules

For source-attribution claims, evidence must support both:

- the underlying event or statement
- the named outlet/provider

If the news snippet supports the event but not the alleged source, do not emit unless another snippet clearly proves a different source.

For narrative claims, default to abstain unless the evidence directly contradicts the report. Vague disagreement or missing article text is not enough.

## Generate Rules

Use news as a secondary narrative layer:

- "News coverage framed the event as..."
- "The article title/summary indicates..."

Do not cite news for audited financial values unless the claim is explicitly about how media described the value.
