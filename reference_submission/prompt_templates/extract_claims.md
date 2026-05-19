You are auditing a research report. Extract every CHECKABLE factual
claim and NORMALIZE it into structured fields. You only parse the
text — you do NOT judge whether it is right or wrong. A separate
deterministic checker compares your structured fields against the
authoritative corpus, so be literal and precise.

Ignore opinions, forecasts, valuations, and vague qualitative
statements. Works for English and Chinese identically.

Claim patterns to capture:
- numeric: EPS (actual / consensus / surprise), revenue, net income,
  nine-month (前三季度/9M) figures, market cap, client assets, recall
  counts, percentages, $ amounts
- date / timeline: filing dates, period-end dates, event dates,
  shareholder-meeting dates
- direction: beat/miss, above/below consensus, growth/decline,
  upgrade/downgrade, 高于/低于/超预期/不及预期/上调/下调/增长/下降
- derived: YoY/QoQ %, stock returns
- peer lists: peer basket / 同业 / 可比公司 membership
- source attribution: Bloomberg/CNBC/WSJ/Reuters/Benzinga/SEC/Form 8-K
- management/analyst quotes with embedded numbers

# REPORT
"""{report}"""

# OUTPUT
Return JSON only:
{{"claims": [{{
  "quote": "<verbatim substring from the report, copied EXACTLY incl. markdown/newlines>",
  "kind": "number|date|attribution|peer|direction|other",
  "ticker": "<the US stock ticker the claim is about, e.g. TSLA; null if unclear>",
  "fy": <fiscal year as int, e.g. 2025; null if not stated>,
  "fq": <fiscal quarter 1-4 as int; null if not a single quarter>,
  "metric": "eps_actual|eps_estimate|eps_surprise|revenue|net_income|nine_month_net_income|nine_month_revenue|filing_date|period_end|price_return|peer_list|other",
  "value": <the number the claim states for that metric as a plain float (EPS like 0.50; $13.46B as 13460000000; a percent like -10.5 as -10.5); null if none>,
  "direction": "beat|miss|up|down|null",
  "date": "<YYYY-MM-DD the claim states (for filing_date/period_end/event); null>",
  "form": "<10-K|10-Q|8-K|DEF 14A ... for filing_date; null>",
  "peers": ["<ticker>", ...] or null
}}]}}

Rules:
- `quote` MUST be an exact substring of the report. Quote a full
  sentence, bullet, or table row — never a bare "Q4 2025" / date / number.
- Fill a structured field ONLY if the claim literally states it. Never
  infer or compute. Unknown → null.
- `value` is the figure the REPORT asserts (not the truth). For an EPS
  beat/miss claim with no explicit consensus number, set metric
  "eps_surprise" and direction beat/miss.
- For a Chinese filing-disclosure sentence ("通过 8-K 正式披露…"),
  metric = "filing_date", set form and the stated date.
- At most 40 claims; prioritise load-bearing numeric/date/source/
  direction claims.
