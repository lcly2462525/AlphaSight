---
name: alphasight-review-answer-auditor
description: Use when auditing AlphaSight review reports against the offline corpus, learning from review_train_gt.jsonl and review_claude.jsonl answer styles, classifying injected errors, finding original evidence paths, and writing precise quote/reason issues.
---

# AlphaSight Review Answer Auditor

Use this skill when checking a generated equity-research review report for factual issues. The target style is learned from:

- `reference_submission/problem/review_train_gt.jsonl`: fully trusted train answer key.
- `review_claude.jsonl`: validation reference answer; treat as strong SOTA guidance, but still verify against corpus or report-internal contradiction.

Goal: emit only real contradictions. Each issue must contain an exact report quote and a reason with the correct value/date/source/action and the evidence path or evidence class.

## Output Standard

Return issues in this shape:

```json
{"quote": "<verbatim substring from report>", "reason": "<error class>: <correct value/date/source/action> vs reported value, with source path or corpus family>"}
```

Rules:

- `quote` must be copied from the report exactly enough to identify the tampered sentence/row. Prefer the single sentence, bullet, or table row containing the injected error.
- One underlying injected error should normally produce one issue. Do not emit every cascading calculation unless the answer key clearly treats them separately.
- A reason must state the correct value, not just "unsupported".
- Absence of evidence is not a contradiction. Skip if no source gives a different definite value/date/direction/source.
- Minor rounding is not an issue unless the answer key pattern treats the number as materially changed.
- If a sentence is internally inconsistent with the same report and no corpus path is needed, cite the self-contradicting section pattern in the reason.

## Source Priority

Use the most direct corpus source for the claim type:

| Claim type | Primary source path pattern | How to verify |
|---|---|---|
| EPS actual/estimate/surprise/beat-miss | `dataset/corpus/research/<TICKER>/earnings.json` | Match `period`, `year`, `quarter`; compare `actual`, `estimate`, `surprise`, `surprisePercent`. |
| Financial statement metric | `dataset/corpus/research/<TICKER>/financials_reported.json` | Match company, concept/label, period endDate, FY/FQ, and cumulative vs single-quarter scope. |
| Filing date/accession/form | `dataset/corpus/research/<TICKER>/sec_submissions.json` and `dataset/corpus/filings/<TICKER>/<FORM>__<DATE>__<ACCESSION>.htm` | Filename date and accession are authoritative. Do not confuse event date, filing date, and report period. |
| Peer list | `dataset/corpus/research/<TICKER>/peers.json` | Compare exact membership; do not add foreign ADRs or invalid tickers unless present. |
| Daily prices, returns, highs/lows | `dataset/corpus/prices/<TICKER>.csv` | Use the correct price field: open, close, high, low. Recompute returns from the cited endpoints. |
| News/social numbers, event dates, source attribution, polarity | `dataset/corpus/news_merged/<TICKER>.jsonl`, then its `source_paths`; also `dataset/corpus/news/<TICKER>/*.json` and `dataset/corpus/social/<TICKER>/*.json` | Search by ticker + distinctive number/entity/date/action. Prefer `[event, timestamp, polarity, attributed_to, provider, source_paths]`; open `source_paths` for original wording. |
| Report-internal contradiction | The report text itself | Use when the same report repeats a fact differently or contradicts its own table/narrative. |

## Error Taxonomy

### 1. Structured EPS Tampering

Pattern: actual EPS, consensus estimate, surprise amount/percent, or beat/miss direction is altered.

Workflow:

1. Extract ticker, fiscal year/quarter, reported `actual`, `estimate`, and direction.
2. Look up `research/<TICKER>/earnings.json`.
3. Match the period/quarter exactly.
4. Compare all linked fields together; decide which atom is wrong.
5. Quote the row/sentence containing the wrong atom, not unrelated downstream commentary.

Examples:

- Train `report_01`: quote says META Q4 2025 EPS actual `$9.88`; source `corpus/research/META/earnings.json` says actual `$8.88`, while estimate `$8.3992` and surprise `$0.4808` reconcile to `$8.88`.
- Train `report_03`: quote says COST Q1 FY26 `$4.50` vs `$4.65`, a miss; source `corpus/research/COST/earnings.json` says estimate `$4.3571`, surprise `+3.2797%`, so it is a beat.
- Validation `report_05`: BAC Q3 2025 row says estimate `$0.8610` and `+23.1%`; source `earnings.json` says estimate `$0.961` and surprise `+10.30%`.

Reason style:

```text
Wrong EPS estimate and surprise. Per corpus/research/BAC/earnings.json, BAC Q3 2025 estimate was $0.961 and surprise +10.30%, not $0.8610 / +23.1%.
```

### 2. Financial Statement Metric / Period Mismatch

Pattern: a table row uses the wrong net income/revenue value, wrong fiscal period, or wrong cumulative-vs-quarter scope.

Workflow:

1. Identify metric, entity, period, and whether the report means quarterly or nine-month/YTD.
2. Open `financials_reported.json`.
3. Match concept/label and endDate. Do not compare a company-level value to segment value, or YTD to standalone quarter.
4. Recompute YoY/ranking only after the primary value is confirmed.

Examples:

- Train `report_08`: MS nine-month 2025 net income row says `$13.46B`; `corpus/research/MS/financials_reported.json` says FY2025Q3 YTD "Net income applicable to Morgan Stanley" is `$12.464B`. The YoY and ranking cascade from that single wrong value.
- Validation `report_03`: AMD nine-month 2024 net income says `$1.59B`; `financials_reported.json` gives `$1.159B`, which also reconciles the reported YoY.
- Train `report_04`: WMT fiscal Q3 FY26 is said to end November 30; `financials_reported.json` FY2026Q3 `endDate` is `2025-10-31`. Do not use Finnhub `earnings.json.period` as fiscal-quarter end.

### 3. Filing Date / Accession Date

Pattern: form date, 8-K/10-K filing date, shareholder meeting date, or report release date is moved.

Workflow:

1. Extract form type and accession if present.
2. Check `sec_submissions.json` and filing filename.
3. For shareholder meeting or event dates, search `news_merged`, `news`, and `social` with the event phrase.
4. Quote the sentence that contains the wrong date.

Examples:

- Train `report_02`: TSLA 10-K accession `0001628280-25-003063` is reported as filed `2025-02-05`; source `corpus/filings/TSLA/10-K__2025-01-30__0001628280-25-003063.htm` and `corpus/research/TSLA/sec_submissions.json` show `2025-01-30`.
- Train `report_09`: NEE 8-K date is changed from `2025-07-23` to `2025-08-23`.
- Train `report_10`/`12`: TSLA shareholder meeting is `2025-11-06`, but report variants say `11 月 16 日` or `10 月 6 日`. Use social/news evidence around Tesla shareholder meeting and the report's own correct mentions if present.

### 4. Peer Membership

Pattern: peer list includes a ticker not in `peers.json`, omits a peer, or labels a noisy list as canonical.

Workflow:

1. Open `research/<TICKER>/peers.json`.
2. Compare exact data array.
3. Quote the peer-list phrase or table row.

Examples:

- Train `report_05`: PFE peer basket includes `NVS`; `corpus/research/PFE/peers.json` contains PFE's peer list without `NVS`.
- Validation `report_02`: JPM report calls a list containing `FINN` a canonical money-center/regional bank group. Claude flags this as suspicious because `FINN` is an abnormal/invalid ticker in that peer context. Verify exact peer data before emitting.

### 5. Price Field / Return / High-Low Date

Pattern: wrong close/open/high/low, wrong date for a high/low, return sign flipped, or intraday high mislabeled as closing high.

Workflow:

1. Open `prices/<TICKER>.csv`.
2. Identify whether the report claims open, close, intraday high/low, or 52-week close range.
3. Compare exact date row. For return, recompute from reported endpoints.
4. Do not mix `high` with `close`.

Examples:

- Train `report_06`: UNH says close-to-close return from `$504.51` to `$330.11` is `-50.6%`; `corpus/prices/UNH.csv` implies about `-34.6%`.
- Validation `report_01`: NVDA says `$94.31` low close occurred April 8; `prices/NVDA.csv` puts that close on `2025-04-04`, while April 8 close was `$96.30`.
- Validation `report_16`: TSLA row labels `498.83` on `2025-12-22` as annual high close; `prices/TSLA.csv` shows it is intraday high, not close.
- Validation `report_17`: DUK lowest close is `$105.87` on `2025-01-10`, not `$95.87`.

### 6. Arithmetic and Direction Inversion

Pattern: the raw numbers are present but the derived direction or percentage is flipped.

Workflow:

1. Recompute from the numbers in the quote.
2. Confirm with structured data if available.
3. Quote the sentence that states the wrong direction, not every repeated consequence.

Examples:

- Train `report_12`: Q3 EPS `$0.50` vs Q2 `$0.40` is `+25%`, but quote says "环比下降 -25%".
- Train `report_10`: TSLA Q3 EPS `$0.50` vs estimate `$0.5586` is `-10.49% miss`, but quote says above consensus by `10.5%`.
- Validation `report_10`/`13`: GE close `$306.63` is above `$302.68`, so it is about `+1.3%`, not `-1.3%`.
- Validation `report_08`: AAPL `$223.89 -> $172.42` is about `-23%`, not "逾 30%".

### 7. News/Social Number Tampering

Pattern: a narrative number from news, social, analyst commentary, market-cap commentary, product-region growth, recall count, or M&A ranking is changed.

Workflow:

1. Search `news_merged/<TICKER>.jsonl` with ticker + distinctive number/entity.
2. Use the event line to identify the correct atom and `source_paths`.
3. Open `dataset/corpus/news/<TICKER>/<id>.json` or `dataset/corpus/social/<TICKER>/<date>.json` for original wording when needed.
4. Quote the report sentence containing the tampered number.

Examples:

- Train `report_10`: TSLA recall count should be `12,936`, not `15,936`; search `TSLA`, `NHTSA`, `12,936`, Model 3/Y in news/social.
- Train `report_11`: NEE dividend CAGR since 2007 is about `10%`, not `15%`; `dataset/corpus/news_merged/NEE.jsonl` event points to `news/NEE/136524006.json`.
- Train `report_13`: `The Electric State` budget is `$320M`, not `$420M`; search `NFLX`, "Electric State", `320`.
- Train `report_17`: JPMorgan raised NKE FY2026 EPS estimate to `$1.32`, not `$1.52`; search `news_merged/NKE.jsonl` for `JPMorgan`, `EPS`, `1.32`.
- Train `report_18`: LLY Mounjaro Japan growth is `+24%`, not `+44%`; search `LLY`, `Mounjaro`, `Japan`.
- Train `report_20`: ABBV market cap around Q3 report was about `$403.1B`, not `$453.1B`; search `ABBV`, `market cap`, `403.1`.

### 8. News Polarity / Analyst Action Inversion

Pattern: upgrade becomes downgrade, beat becomes miss, raised becomes cut, rose becomes fell, or bullish source event is described as bearish.

Workflow:

1. Search event stream with firm/entity + action words: `upgrade`, `downgrade`, `raise`, `cut`, `beat`, `miss`, `上调`, `下调`.
2. Prefer `news_merged` event fields: `polarity`, `attributed_to`, `provider`, `source_paths`.
3. State the correct action direction explicitly.

Examples:

- Train `report_17`: report says JPMorgan downgraded NKE from Overweight to Neutral; `dataset/corpus/news_merged/NKE.jsonl` has events from `2025-07-28` saying JPMorgan upgraded Nike to Overweight from Neutral and raised target to `$93` from `$64`, with source paths such as `news/NKE/136108482.json`, `news/NKE/136108487.json`, `news/NKE/136124802.json`.
- Train `report_03`: COST Q1 FY26 was a beat, not a miss, per `earnings.json`.
- Validation `report_20`: NVDA "AI bubble" framing is inverted if the same report says Jensen Huang was rebutting bubble claims, not admitting them.

### 9. Source Misattribution

Pattern: the fact is real but attributed to the wrong outlet, firm, or agency.

Workflow:

1. Search for the event in `news_merged`.
2. Compare `attributed_to` and `provider`; if absent, open `source_paths`.
3. Quote the report phrase naming the wrong source.

Examples:

- Train `report_16`: MRK layoffs of about 6,000 workers were disclosed to Fierce Pharma, not Wall Street Journal. Search `MRK`, `6,000`, `Fierce Pharma`; raw social evidence also appears in `dataset/corpus/social/MRK/twitter_2025-07-31.json`.
- Train `report_17`: Nike North America women's-business leader moved to Athleta; answer key says original report was CNBC, not Bloomberg. Search `NKE`, `Athleta`, person/title, then compare `provider` or raw article source.
- Validation `report_14`: if a target price is attributed to Morgan Stanley but repeated elsewhere in the report as Wedbush, flag source/firm misattribution only when the source conflict is definite.

### 10. Report-Internal Contradiction

Pattern: validation reference often flags contradictions within the report itself, especially when the report repeats the correct value elsewhere.

Workflow:

1. Search the report for the same entity/date/number/action.
2. If multiple sections repeat a different value and one version is supported by corpus, quote the wrong sentence only.
3. If the contradiction is purely internal and materially factual, the reason can say "与报告自身矛盾".

Examples:

- Validation `report_07`: one sentence says BA deliveries `385` vs `175`, but other sections say `285` and `+63%`; `385/175` also does not match `+63%`.
- Validation `report_11`: UPS layoffs are `25,000` in one place but `20,000` in risk/conclusion sections.
- Validation `report_14`: a section says tariffs will significantly affect AMZN, while another says management does not expect tariffs to affect the business.
- Validation `report_18`: COST membership quote says "clear signs of resisting" but another section says "no signs of resisting".

## Quote Selection Discipline

Use this order:

1. Exact sentence or table row with the wrong atom.
2. If table row is too wide, quote the row cells around ticker/metric/value.
3. If the wrong number is inside a longer paragraph, include enough context for ticker, period, and metric.
4. Do not quote a correct sister sentence. Example: if one NEE sentence says `12.4%` and another says the correct `9.4%`, flag only the `12.4%` sentence.

## Search Recipes

Use focused searches rather than generic prose:

```bash
rg -n "JPMorgan|Overweight|Neutral|1\\.32|Athleta" dataset/corpus/news_merged/NKE.jsonl dataset/corpus/news/NKE
rg -n "12,936|NHTSA|Model 3|Model Y" dataset/corpus/news_merged/TSLA.jsonl dataset/corpus/news/TSLA dataset/corpus/social/TSLA
rg -n "dividend.*2007|10% compound|XLU|July 22" dataset/corpus/news_merged/NEE.jsonl dataset/corpus/news/NEE dataset/corpus/social/NEE
rg -n "6,000|Fierce Pharma|jobs|layoff" dataset/corpus/news_merged/MRK.jsonl dataset/corpus/news/MRK dataset/corpus/social/MRK
rg -n "market cap|403\\.1|453\\.1" dataset/corpus/news_merged/ABBV.jsonl dataset/corpus/news/ABBV
```

For structured JSON, inspect the smallest file first:

```bash
rg -n '"period"|"actual"|"estimate"|"surprisePercent"' dataset/corpus/research/<TICKER>/earnings.json
rg -n '"endDate"|"fy"|"fp"|Net income|Revenues' dataset/corpus/research/<TICKER>/financials_reported.json
rg -n '<ACCESSION>|<FORM>|filedDate' dataset/corpus/research/<TICKER>/sec_submissions.json
```

## False Positive Guards

Do not emit:

- A claim that is merely unsupported.
- A difference caused only by reasonable rounding, e.g. `$69.926B` vs `$69.93B`.
- A period mismatch, e.g. using Q3 evidence to refute a Q2 sentence.
- A metric namespace mismatch, e.g. net income vs operating income, company vs segment, GAAP vs adjusted, YTD vs quarter.
- A Chinese unit misread: `X 亿美元` means `X * 100M USD`, i.e. `X/10` billion USD.
- A report-internal duplicate if it is the same underlying error already counted once.

## Preferred Reason Templates

Structured:

```text
Wrong <metric>. Per corpus/research/<TICKER>/<file>, <TICKER> <period> <metric> was <correct>, not <reported>. <Derived consequence if needed>.
```

Filing:

```text
Wrong filing date. Source: corpus/filings/<TICKER>/<FORM>__<YYYY-MM-DD>__<ACCESSION>.htm and corpus/research/<TICKER>/sec_submissions.json show <correct date>, not <reported date>.
```

Price:

```text
Wrong price/date/return. Per corpus/prices/<TICKER>.csv, <field> on <date> was <correct>; recomputing from <start> to <end> gives <correct return>, not <reported>.
```

News:

```text
<number/date/polarity/source> tampering. Per <news/social path or news_merged source_paths>, <correct atom>; the report changes it to <reported atom>.
```

Internal contradiction:

```text
Report-internal contradiction: section <A> states <correct/other value>, while this quote says <wrong value>; the arithmetic/source context supports <correct>.
```
