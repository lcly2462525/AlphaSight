---
name: social-signal
description: Use AlphaSight social data as aggregated ticker/date sentiment and attention, with strict weak-evidence limits.
version: 1.0.0
---

# Social Signal Skill

Use this skill for social-media data, sentiment, rumor, attention spikes, tweet-count claims, or `social_signal_tool`.

## Role

Social is a weak signal lane. It should become a `SignalStore`, not a primary text retrieval corpus.

Expected aggregate key:

```text
(ticker, date) -> tweet_count, bull_ratio, bear_ratio, top_keywords, source_paths
```

## Availability Check

The catalog may list `social/<T>/twitter_YYYY-MM-DD.json` even when the local corpus directory is empty or incomplete. Before using social:

1. Check the actual file exists under `dataset1/corpus/social`.
2. If missing, return `available=false`.
3. Do not infer tweet counts or sentiment from catalog rows alone.

## Allowed Uses

- Generate: investor attention, sentiment backdrop, rumor/narrative context.
- Review: flag social claims only when the exact social data is available and the claim is about social volume/sentiment/source.
- Event studies: compare attention before/after an event, clearly labeled as weak corroboration.

## Forbidden Uses

- Do not use social to verify EPS, revenue, net income, filing dates, analyst recommendations, or price returns.
- Do not let a tweet contradict a filing unless the task is specifically about rumor-vs-filing divergence.
- Do not quote isolated tweets as decisive evidence unless the claim itself names that tweet/account/date.

## Output Contract

Return:

- `ticker`
- `date_range`
- `available`
- `tweet_count`
- `bull_ratio` / `bear_ratio` if calculable
- `top_keywords`
- `source_paths`
- `evidence_strength="weak"`
