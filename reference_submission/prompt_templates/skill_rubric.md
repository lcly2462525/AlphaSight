## 7 error classes (the only ones that score) — match these patterns

Each entry below is a calibrated audit note distilled from prior
review work. Use the same shape when emitting your own issues — name
the exact subject, state the discrepancy concretely, and cite the
authoritative corpus file or report section that contradicts it.

### 1. Number tampering (a single numeric value is altered)

- **META Q4 2025 diluted EPS** — the report cites actual EPS of $9.88, but research/META/earnings.json gives the actual as $8.88, which reconciles with the stated consensus ($8.3992) plus surprise ($0.4808).
- **Goldman Sachs Q4 2025 consensus** — the report shows consensus $13.50 with a +3.8% surprise; the corpus has consensus $12.0225 and surprise +16.53%.
- **Morgan Stanley nine-month 2025 net income** — the report states $13.46B and +39.1% YoY; financials_reported.json shows the FY2025 Q3 YTD value attributable to MS is $12.464B, implying +28.8% YoY.
- **Tesla recall scope** — the report cites a 15,936-vehicle recall; the NHTSA notice records 12,936 (Model 3 and Y).
- **NextEra Energy dividend CAGR since 2007** — the report states roughly 15%; news coverage indexed in news_merged/NEE.jsonl gives the figure at about 10%.
- **Tesla trailing one-year return** — the report cites +82.37% attributed to Benzinga; the source value is +72.37%.
- **Netflix *The Electric State* production budget** — the report estimates $420M; news sources put the budget at $320M.
- **Goldman Sachs M&A league-table lead** — the report places GS $950B ahead of the runner-up; the published gap is $850B.
- **Merck January 2, 2025 open price** — the report shows $110.28; prices/MRK.csv records the open as $100.28.
- **JPMorgan's Nike FY2026 EPS estimate** — the report says JPMorgan raised its estimate to $1.52; news_merged/NKE.jsonl shows the new estimate is $1.32 (up from $1.07).
- **Lilly Mounjaro Japan growth** — the report claims +44% YoY; news sources put the increase at +24%.
- **Morgan Stanley Wealth Management total client assets** — the report says $7.49T; financials_reported.json gives $6.49T (off by exactly $1T).
- **AbbVie market capitalization at Q3 reporting** — the report cites approximately $453.1B; news estimates cluster around $385–$403B.
- **UnitedHealth calendar-year price return** — the report says approximately −50.6% from $504.51 to $330.11; the arithmetic gives −34.6%.
- **NVIDIA Q3 FY26 consensus** — the report shows $1.20 with about a 2% surprise; earnings.json gives consensus $1.2746 and surprise +1.99%.
- **AMD nine-month 2024 net income** — the report has $1.59B; financials_reported.json shows $1.159B, which is what reconciles the reported +143.7% YoY.
- **Bank of America Q3 2025 consensus** — the report shows estimate $0.8610 with +23.1% surprise; earnings.json gives $0.961 and +10.30%.
- **Apple drawdown magnitude** — the report describes a decline "over 30%" from $223.89 to $172.42; the arithmetic gives approximately −23%.
- **Boeing Q2 2025 EPS surprise** — the report shows +28.67%; earnings.json gives +18.67% (matching the stated surprise dollars ÷ estimate).
- **GE three-year return** — the report cites approximately +680%; the same report's summary section gives approximately +580%.
- **Duke Energy lowest close** — the report shows $95.87 on 2025-01-10; prices/DUK.csv shows the close was $105.87 that day (off by $10).
- **Costco Growth score change** — the report cites a jump to 95.06; other sections of the same report give the level as 90.06, sourced from Benzinga Edge.
- **NVIDIA Q3 surprise amount** — the report cites $0.05; earnings.json shows actual $1.30 versus estimate $1.2746, a surprise of $0.0254 (approximately $0.03).

### 2. Date / timeline distortion (a date is moved or mislabeled)

- **Tesla FY2024 10-K filing** — the report dates it February 5, 2025; the filing filename `filings/TSLA/10-K__2025-01-30__0001628280-25-003063.htm` encodes a filing date of January 30, 2025.
- **NextEra Energy Q2 8-K disclosure** — the report dates it August 23, 2025; the 8-K filename encodes July 23, 2025.
- **Tesla shareholder meeting** — the report has November 16, 2025; news coverage shows the meeting was held November 6, 2025.
- **XLU (Utilities Select Sector SPDR) all-time high** — the report dates the high on August 22; news sources record July 22, 2025.
- **Tesla shareholder meeting (variant)** — the report has October 6, 2025; the actual date is November 6, 2025.
- **NVIDIA low close at $94.31** — the report places this on April 8; prices/NVDA.csv has $94.31 on 2025-04-04 (the April 8 close was $96.30).
- **Broadcom $412.97 high close** — the report calls it the "autumn" high; prices/AVGO.csv places this close on 2025-12-10.
- **Netflix low close at $82.84** — the report attributes this to April; prices/NFLX.csv puts the close on 2025-01-14.
- **Netflix Q3 8-K release** — the report dates the release November 21; the same report's narrative sections give October 21 and October 22.
- **GE Q3 results release** — the report says GE filed alongside peers on 2025-10-28; the report's own §一 / §三 / §4.5 and filings.json all give 2025-10-21.
- **Costco $1,076.86 high close** — the report dates it 2025-03-13; prices/COST.csv shows this close occurred on 2025-02-13 (the 3-13 close was around $890.62).
- **UPS −14% single-day event** — the report places the $114.90 close on 2025-02-28; prices/UPS.csv shows it occurred on 2025-01-30 (Feb-28 closed around $119.03 with normal volume).

### 3. Direction / sign reversal (beat ↔ miss, up ↔ down, upgrade ↔ downgrade)

- **Costco Q1 FY26 result** — the report calls $4.50 vs $4.65 a −3.2% miss; earnings.json has estimate $4.3571 and a +3.28% surprise (a beat).
- **Tesla Q3 EPS framing** — the report says Q3 EPS of $0.50 was "about 10.5% above consensus"; earnings.json has estimate $0.5586 and a −10.49% surprise (a miss).
- **Tesla quarter-over-quarter EPS** — the report says Q3 $0.50 vs Q2 $0.40 was "down 25% QoQ"; the arithmetic gives +25% (up).
- **JPMorgan Nike rating action** — the report says JPMorgan downgraded NKE from Overweight to Neutral; news_merged/NKE.jsonl on 2025-07-28 shows JPMorgan upgrading from Neutral to Overweight.
- **GE October 21 move** — the report calls it "down approximately 1.3%" (with $306.63 above $302.68); the arithmetic gives +1.3% (up).
- **Pfizer 13F position** — the report describes a bullish Pfizer call position from Scion; §七 of the same report shows the Q3 13F as a *put* position (about 21.1% of the portfolio).
- **Costco membership commentary** — the quote says members "show clear signs of resisting" the dues increase; §七 of the same report says members "show no signs of resisting."
- **NVIDIA AI-bubble framing** — the report says Huang "openly admitted" the AI-bubble thesis; the surrounding context and §六.1 confirm he was *rebutting* it.

### 4. Internal contradiction (the same report states a fact two different ways)

- **Boeing first-half deliveries** — this quote says deliveries reached 385 (+63%); §五 and §八 of the same report give the figure as 175 → 285 aircraft (+63%).
- **Apple market-cap milestone** — this quote says "first crossed $5 trillion"; §4.2, §五, and §八 of the same report all say the threshold crossed on 2025-10-28 was $4 trillion.
- **Netflix Q3 EPS framing** — this quote says actual EPS of 0.687 was a +17.39% beat; §4.1 table records 0.5870 / −17.39%, and §八 says "approximately 17.39% below consensus."
- **GE Q3 free cash flow** — the §4.1 table shows $32 hundred-million; §五 and §八 of the same report give $24 hundred-million.
- **UPS layoff count** — this quote cites 25,000 positions cut; the risk-factor section and the conclusion of the same report cite 20,000.
- **GE three-year return** — this quote shows +680%; §八 of the same report gives +580%.
- **Amazon tariff guidance** — this quote claims management expects tariffs to have a significant impact; §七 says management explicitly does not expect a tariff impact.
- **NVIDIA $515 target attribution** — this quote attributes the target to Morgan Stanley; §七 and §八 of the same report attribute the same target to Wedbush.
- **Pfizer 2025 low** — the quote calls the $21.59 level a "June low (around April 7–9)"; the annotation itself is internally inconsistent on the month.
- _Tip_: when a summary section (typically §八) restates the correct value, it pins which other section is the tampered one.

### 5. Source misattribution (the fact is correct but the outlet is wrong)

- **Merck restructuring disclosure** — the report attributes the ~6,000-position layoff disclosure to *The Wall Street Journal*; the original outlet is *Fierce Pharma*.
- **Nike North America women's leadership move to Athleta** — the report attributes the 2025-07-29 story to Bloomberg; the original outlet is CNBC.
- **NVIDIA $515 price target** — the report attributes the new high target to Morgan Stanley; recommendations.json and §七 / §八 attribute it to Wedbush.
- **Costco Growth score source** — the report attributes the figure to Morningstar; the §五 table and §八 of the same report attribute it to Benzinga Edge.

### 6. Intraday vs close confusion (a high/low value is labeled as a closing price)

- **Tesla 2025-12-22** — the report labels $498.83 as the "year-high close"; prices/TSLA.csv shows that day's close was $488.73 and $498.83 was the intraday high (the actual year-high close was $489.88 on 2025-12-16).
- **Duke Energy year-high close** — the report records $130.03 (with the cell itself parenthetically noting "intraday high"); prices/DUK.csv shows the close was $129.03 and $130.03 was the intraday high.
- **Duke Energy year-low close** — the report has $95.87 on 2025-01-10; the close was actually $105.87 (also the year low close).
- _Rule_: a value claimed as "收盘价 / closing price" must come from the `close` column; the `high` and `low` columns are never substitutes.

### 7. Classification / membership (an entity is wrongly included or excluded from a list)

- **Pfizer peer basket** — the report appends NVS to the basket; research/PFE/peers.json does not list NVS as a peer.
- **Bank of America peer list** — the report lists FINN as part of a "canonical money-center plus regional banks" group; peers.json shows FINN is an anomalous / inactive ticker rather than a bank.

## False-positive guards — do not flag

- A claim that is merely unsupported by retrieval ("no source confirms / cannot verify / 未确认 / 无法确认 / absence"). Absence of evidence is not a contradiction.
- Rounding within 1% of the metric, EPS within $0.005, or dates within one calendar day.
- A period mismatch — do not use Q3 evidence to refute a Q2 report claim (or vice versa). Cross-check timestamps and fiscal-quarter labels.
- A metric namespace mismatch — net vs operating income, segment vs company total, GAAP vs adjusted, YTD/9-month vs single-quarter, reported vs non-GAAP. Different concepts are not contradictions.
- The Chinese 亿 unit — `X 亿美元` equals X × 100M USD, i.e. (X/10) billion USD. Do not flag `$11.30 亿` as a 10× overstatement of `$11.30B`.
- Cascading derivatives of a single underlying tamper — emit one issue per root error, not every downstream consequence.
- The corroborated sister sentence — if the report has two sentences about the same subject (one matching the corpus, one not), flag only the mismatched sentence; never the correct sibling.
- Reasons whose own wording concedes uncertainty ("matches the verified", "report is correct", "consistent with", "报告其实是对的") — drop them.

## Quote selection discipline

- The quote must be a verbatim substring of the report, preserving markdown and newlines.
- Choose the single sentence, bullet, or table row that contains the wrong atom.
- Do not quote a correct sister sentence to flag an error that lives elsewhere in the report.

## Reason templates — match the class, fill in exact values

| Class | Template |
|---|---|
| Structured (EPS / financial) | Wrong *metric*. Per corpus/research/*TICKER*/*file*, *TICKER* *period* *metric* was *correct*, not *reported*. |
| Filing | Wrong filing date. corpus/filings/*TICKER*/*FORM*__*correct YYYY-MM-DD*__*ACCESSION*.htm shows *correct*, not *reported*. |
| Price | Wrong *field*. Per corpus/prices/*TICKER*.csv on *date*, *field* = *correct*, not *reported*. |
| Intraday/close | Intraday *high* / *low*, not close. corpus/prices/*TICKER*.csv on *date*: close = *X*, high = *Y*; the report labels *Y* as a closing price. |
| News (number / date / polarity) | *Class* tampering. Per *news/social path*, *correct atom*; the report changes it to *reported atom*. |
| Source attribution | Source misattribution. Per *news_merged event src + source_paths*, the original outlet is *correct*, not *reported*. |
| Internal contradiction | Report-internal contradiction: section *A* states *correct*; this quote says *reported*. |
| Peer | Wrong peer membership. Per corpus/research/*TICKER*/peers.json, the list is *correct*; the report adds or omits *ticker*.
