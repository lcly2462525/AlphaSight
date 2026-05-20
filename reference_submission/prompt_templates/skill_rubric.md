## 7 error classes (the only ones that score) — match these patterns

Each line below is a calibrated worked example from train_gt or the
validation reference set. `tg` = train_gt; `val` = validation reference
(`output_review_plan_test/review.jsonl`). Use the same SHAPE when
emitting issues — point to the exact corpus path / field that
contradicts the report sentence.

### 1. Number tampering (single numeric atom altered)

- `tg r01` META Q4 EPS: report `$9.88` actual → `earnings.json` `$8.88` (estimate $8.3992 + surprise $0.4808 = $8.88)
- `tg r07` GS Q4 estimate: report `$13.5` `+3.8%` → `earnings.json` `$12.0225` `+16.5315%`
- `tg r08` MS 9M NI: report `$13.46B` `+39.1%` → `financials_reported.json` FY2025Q3 YTD `$12.464B` `+28.8%`
- `tg r10` NHTSA recall: report `15,936` → news shows `12,936` (Model 3/Y, NHTSA)
- `tg r11` NEE dividend CAGR: report `~15%` since 2007 → `news_merged/NEE.jsonl` says `~10%`
- `tg r12` TSLA 1-yr: report `+82.37%` → news says `+72.37%` (Benzinga)
- `tg r13` NFLX Electric State budget: report `$420M` → news says `$320M`
- `tg r15` GS M&A lead $: report `$950B` ahead of #2 → news shows `$850B`
- `tg r16` MRK Jan 2 open: report `$110.28` → `prices/MRK.csv` shows `$100.28`
- `tg r17` JPM NKE FY26 EPS estimate: report `$1.52` → `news_merged/NKE.jsonl` raised to `$1.32` from $1.07
- `tg r18` LLY Mounjaro Japan: report `+44%` → news says `+24%`
- `tg r19` MS Wealth client assets: report `$7.49T` → `financials_reported.json` `$6.49T` (exactly $1T off)
- `tg r20` ABBV market cap @ Q3: report `$4,531亿` → news shows ~`$4,031亿` (multiple `$385–403B`)
- `tg r06` UNH calendar return: report `-50.6%` (from $504.51 → $330.11) → arithmetic gives `-34.6%`
- `val r01` NVDA Q3 FY26 consensus: report `$1.20` `~2%` → `earnings.json` `$1.2746` `+1.99%`
- `val r03` AMD 9M 2024 NI: report `$1.59B` → `financials_reported.json` `$1.159B` (reconciles +143.7% YoY)
- `val r05` BAC Q3 consensus: report `$0.8610` `+23.1%` → `earnings.json` `$0.961` `+10.30%`
- `val r08` AAPL drop: report `逾 30%` ($223.89→$172.42) → arithmetic `≈ -23%`
- `val r12` BA Q2 surprise: report `+28.67%` → `earnings.json` `+18.67%` ($0.2846/$1.5246)
- `val r13` GE 3-yr return: report `+680%` → §八 says `+580%`
- `val r17` DUK lowest close: report `$95.87` → `prices/DUK.csv` `$105.87` on 2025-01-10 (off by $10)
- `val r18` COST Growth score: report `95.06` → §五/§八 cite `90.06` (Benzinga Edge)
- `val r20` NVDA Q3 surprise: report `$0.05` → `earnings.json` actual $1.30 vs estimate $1.2746 = `$0.0254` (≈$0.03)

### 2. Date / timeline distortion (date moved)

- `tg r02` TSLA 10-K: report `Feb 5, 2025` → `filings/TSLA/10-K__2025-01-30__0001628280-25-003063.htm`
- `tg r09` NEE 8-K Q2 disclosure: report `8月23日` → filename encodes `2025-07-23`
- `tg r10` TSLA shareholder mtg: report `11月16日` → news shows `2025-11-06`
- `tg r11` XLU all-time high: report `8月22日` → news shows `2025-07-22`
- `tg r12` TSLA shareholder mtg (variant): report `10月6日` → `2025-11-06`
- `val r01` NVDA $94.31 low close: report `April 8` → `prices/NVDA.csv` row is `2025-04-04` (Apr 8 close $96.30)
- `val r04` AVGO $412.97 high close: report `autumn` → `prices/AVGO.csv` row is `2025-12-10`
- `val r06` NFLX $82.84 low close: report `April` → `prices/NFLX.csv` row is `2025-01-14`
- `val r09` NFLX Q3 8-K release: report `11月21日` → §一/§三 say `10月21日 / 10月22日`
- `val r13` GE Q3 release: report `2025-10-28 一同发布` → §一/§三/§4.5 + `filings.json` say `2025-10-21`
- `val r18` COST $1,076.86 high close: report `2025-03-13` → `prices/COST.csv` row is `2025-02-13` (3/13 close ~$890.62)
- `val r19` UPS $114.90 / -14% / 41M-share day: report `2025-02-28` → `prices/UPS.csv` row is `2025-01-30` (Feb-28 close ~$119.03, ~8.75M shares)

### 3. Direction / sign reversal (beat↔miss, up↔down, upgrade↔downgrade, QoQ +/−)

- `tg r03` COST Q1 FY26: report `$4.50 vs $4.65 — -3.2% miss` → `earnings.json` est $4.3571 surp `+3.28%` (beat)
- `tg r10` TSLA Q3 EPS: report `$0.50 高于一致预期约 10.5%` → `earnings.json` est $0.5586 surp `-10.49%` (miss)
- `tg r12` TSLA QoQ EPS: report `Q3 $0.50 较 Q2 $0.40 环比下降 -25%` → arithmetic `+25%`
- `tg r17` NKE JPM rating: report `Overweight 下调至 Neutral` → `news_merged/NKE.jsonl` 2025-07-28 shows `Neutral → Overweight` (upgrade)
- `val r10` GE 2025-10-21 close: report `下跌约 1.3%` ($306.63 > $302.68) → arithmetic `+1.3%` (rose)
- `val r13` GE (variant of above): same `-1.3%` flip + contradicts §三/§八 "盘中新高 / +82.7% 全年"
- `val r15` PFE Burry 13F: report `看涨期权头寸` → §七 shows Scion Q3 13F `新增 Pfizer 看跌期权 (~21.1%)`
- `val r18` COST membership: quote `clear signs of resisting` → §七 `no signs of resisting`
- `val r20` NVDA: report `黄仁勋明确承认 AI 泡沫论` → §六.1 + same sentence context = he was rebutting / refuting

### 4. Internal contradiction (same report, two definite values — no corpus needed)

- `val r07` BA H1 deliveries: this quote `385 架 (+63%)` ↔ §五/§八 `从 175 增至 285 架 (+63%)`
- `val r08` AAPL market cap: this quote `首破 5 万亿美元` ↔ §4.2/§五/§八 `2025-10-28 首破 4 万亿`
- `val r09` NFLX Q3 EPS: this quote `0.687 +17.39% 超预期` ↔ §4.1 表 `0.5870 -17.39%` + §八 `较一致预期低 17.39%`
- `val r10` GE FCF: §4.1 table `32 亿美元` ↔ §五 + §八 `24 亿美元`
- `val r11` UPS layoffs: this quote `25,000 / 2.5 万` ↔ §风险 + §结论 `20,000`
- `val r13` GE 3-yr return: `+680%` ↔ §八 `+580%`
- `val r14` AMZN tariff: this `预期关税显著影响` ↔ §七 `管理层不预期关税影响`
- `val r14` NVDA $515 target: this `Morgan Stanley` ↔ §七 + §八 `Wedbush`
- `val r15` PFE low date: `6月低点 $21.59 (括注 4月7-9日间)` ↔ self-contradicting
- _Tip:_ when a summary section (§八 / 八节) repeats the correct value, it pins which other section is the tamper.

### 5. Source misattribution (fact correct but wrong outlet/firm/agent)

- `tg r16` MRK layoffs ~6,000: report `Wall Street Journal 披露` → correct outlet is `Fierce Pharma`
- `tg r17` NIKE 北美女装 Athleta: report `2025-07-29 Bloomberg` → correct outlet is `CNBC`
- `val r14` NVDA $515 target: report `Morgan Stanley` → `recommendations.json` + §七/§八 show `Wedbush`
- `val r18` COST Growth score: report `Morningstar` → §五 + §八 show `Benzinga Edge`

### 6. Intraday vs close confusion (value matches `high`/`low`, labeled as 收盘价)

- `val r16` TSLA: `2025-12-22 收盘价 498.83` → `prices/TSLA.csv` row `close=488.73, high=498.83` (年最高收盘 489.88 on 2025-12-16)
- `val r17` DUK 年最高收盘: `$130.03 (2025-10-22 盘中高点)` → row `close=129.03, high=130.03` (单元格自标"盘中高点"亦自矛盾)
- `val r17` DUK 年最低收盘: `$95.87 (2025-01-10)` → row `close=105.87` (also year low close)
- _Rule:_ "收盘价" claims must match the `close` column only; `high`/`low` are NEVER substitutes.

### 7. Classification / membership (extra/missing/anomalous in list)

- `tg r05` PFE peer basket adds `NVS` → `peers.json` data array has no NVS
- `val r02` BAC peer list cites `FINN` as "canonical money-center plus regional banks" → `peers.json`: FINN is anomalous/inactive, not a bank

## False-positive guards — DO NOT flag

- Only "no source supports / cannot confirm / 未确认 / 无法确认 / absence" → SKIP (absence ≠ contradiction).
- Rounding ≤ 1% of metric / EPS ≤ $0.005 / date ≤ 1 calendar day.
- Period mismatch: do NOT use a Q3 figure to refute a Q2 report claim (or vice versa). Check timestamps + 财季 labels.
- Metric namespace: net vs operating, segment vs company, GAAP vs adjusted, YTD/9M vs single-quarter, reported vs non-GAAP — different families.
- Chinese 亿 unit: `X 亿美元` = X × 100M USD = (X/10) billion USD. Do NOT flag `$11.30 亿` as a 10× overstatement of `$11.30B`.
- Cascading derivatives of the same underlying tamper: one tamper → one issue, not N consequences.
- The corroborated sibling sentence: if the report has two sentences about the same subject (one matches corpus, one doesn't), flag ONLY the mismatched one — never the correct sibling.
- Reasons whose own wording concedes uncertainty ("matches the verified / 报告其实是对的 / consistent with / is correct") — drop.

## Quote selection discipline

- Verbatim substring of the report (markdown / newlines preserved).
- Single sentence, bullet, or table row containing the wrong atom.
- Do NOT quote a correct sister sentence to flag an error that lives elsewhere.

## Reason templates — match class, fill exact values

| class | template |
|---|---|
| Structured (EPS/financial) | `Wrong <metric>. Per corpus/research/<T>/<file>, <T> <period> <metric> was <correct>, not <reported>.` |
| Filing | `Wrong filing date. corpus/filings/<T>/<FORM>__<correct YYYY-MM-DD>__<ACCESSION>.htm shows <correct>, not <reported>.` |
| Price | `Wrong <field>. Per corpus/prices/<T>.csv on <date>, <field>=<correct>, not <reported>.` |
| Intraday/close | `Intraday <high\|low>, not close. corpus/prices/<T>.csv on <date>: close=<X>, high=<Y>; the report labels <Y> as 收盘价.` |
| News (number/date/polarity) | `<class> tampering. Per <news/social path>, <correct atom>; the report changes it to <reported atom>.` |
| Source attribution | `Source misattribution. Per <news_merged event src + source_paths>, the original outlet/firm is <correct>, not <reported>.` |
| Internal contradiction | `Report-internal contradiction: section <A> states <correct>; this quote says <reported>.` |
| Peer | `Wrong peer membership. Per corpus/research/<T>/peers.json, <correct list>; the report adds/omits <ticker>.` |
