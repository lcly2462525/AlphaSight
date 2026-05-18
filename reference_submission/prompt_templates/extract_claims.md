You are auditing a research report. Extract every CHECKABLE factual claim: specific numbers (revenue, EPS, %, $ amounts, price moves), dates/quarters, and attributed statements ("X said Y").

Ignore opinions, forecasts, and vague qualitative statements.

# REPORT
"""{report}"""

# OUTPUT
Return JSON only: {{"claims": [{{"quote": "<verbatim substring from the report>", "kind": "number|date|attribution|other"}}]}}
- `quote` MUST be an exact substring of the report (copy-paste, including markdown).
- At most 15 claims, prioritise the load-bearing ones.
