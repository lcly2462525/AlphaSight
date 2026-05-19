You are auditing a research report. Extract every CHECKABLE factual claim as a complete quote.

Ignore opinions, forecasts, and vague qualitative statements.

Focus on these error-prone patterns:
- numeric mutations: EPS, revenue, net income, market cap, client assets, recall counts, percentages, $ amounts
- date/timeline claims: filing dates, event dates, shareholder meetings, fiscal period end dates
- direction claims: beat/miss, above/below consensus, growth/decline, increase/decrease, upgrade/downgrade, 上调/下调/增长/下降/高于/低于
- derived calculations: YoY/QoQ %, stock returns, rank order, sums
- peer lists: peer basket/list membership
- source attribution: Bloomberg/CNBC/WSJ/Reuters/Benzinga/Fierce Pharma/SEC/Form 8-K etc.
- quotes or management statements with embedded numbers

# REPORT
"""{report}"""

# OUTPUT
Return JSON only: {{"claims": [{{"quote": "<verbatim substring from the report>", "kind": "number|date|attribution|other"}}]}}
- `quote` MUST be an exact substring of the report (copy-paste, including markdown).
- Quote a full sentence, bullet, or table row. Do NOT output fragments like "Q4 2025", "January 2", or "December 31".
- At most 40 claims, prioritise load-bearing numeric/date/source/direction claims.
