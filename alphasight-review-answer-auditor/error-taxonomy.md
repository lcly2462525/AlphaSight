---
name: review-error-taxonomy
description: Error classification and data-source lookup guide for AlphaSight report review. Covers all 7 error types with corpus paths, field names, and worked examples drawn from the training ground-truth and validation SOTA answer sets.
version: 1.0.0
---

# AlphaSight Review: Error Taxonomy & Source Lookup Guide

This skill teaches a review agent **how to find, classify, and cite** the seven error types that appear in AlphaSight financial reports. For each type: the corpus path to check, the exact fields to read, and concrete worked examples from the training GT (`review_train_gt.jsonl`) and validation SOTA (`review_claude.jsonl`).

---

## Corpus Path Reference

| Data Type | Path | Key Fields |
|-----------|------|------------|
| Daily prices | `dataset/prices/{TICKER}.csv` | `date, open, high, low, close, volume` |
| EPS consensus | `dataset/corpus/research/{TICKER}/earnings.json` | `.data[].actual .estimate .surprise .surprisePercent .period .year .quarter` |
| SEC financials | `dataset/corpus/research/{TICKER}/financials_reported.json` | `.data.data[].{startDate,endDate,filedDate,report.ic[].{concept,label,value}}` |
| Peer list | `dataset/corpus/research/{TICKER}/peers.json` | `.data[]` — list of peer tickers (includes self) |
| Filing metadata | `dataset/corpus/research/{TICKER}/sec_submissions.json` | `.data.filings.recent.{accessionNumber,filingDate,form}` |
| Filing docs | `dataset/corpus/filings/{TICKER}/{FORM}__{DATE}__{ACCESSION}.htm` | filename encodes form, filed date, accession |
| Analyst ratings | `dataset/corpus/research/{TICKER}/recommendations.json` | `.data[].{firm,toGrade,fromGrade,date}` |

---

## Error Type 1: 数字篡改 (Number Tampering)

**Definition:** A specific numeric value in the report is replaced with a plausibly close but wrong number. The surrounding context (metric name, period, direction) is often preserved, making detection require exact lookup.

**How to detect:**
1. Identify the claim's metric type (EPS, revenue, price, return %, count).
2. Locate the authoritative source file (see table above).
3. Extract the exact value for the matching ticker + period + basis.
4. Flag if the difference is more than rounding (>1% of the correct value, or more than a penny on EPS).

### Sub-type 1a: EPS Actual / Consensus / Surprise

**Source:** `earnings.json → .data[]`  
Match on: `symbol` + `year` + `quarter` (or `period` as calendar-quarter-end date).  
Fields: `actual`, `estimate`, `surprise` (= actual − estimate), `surprisePercent`.

> **Example — Train report_01 (META):**  
> Report claims: "Q4 2025 diluted EPS: **$9.88** actual vs. consensus $8.3992 — a +5.7% positive surprise"  
> earnings.json (META, year=2025, quarter=4): `actual=8.88, estimate=8.3992, surprise=0.4808, surprisePercent=5.7244`  
> Check: 8.3992 + 0.4808 = **8.88**, not 9.88. The actual EPS was tampered; all downstream figures (full-year EPS sum 30.70 vs correct 29.70) propagate the error.

> **Example — Train report_08 (MS):**  
> Report claims: "MS nine-month 2025 net income **$13.46B** (+39.1% YoY)"  
> financials_reported.json (MS, FY2025Q3, concept `us-gaap_NetIncomeLoss`): value = **$12.464B**  
> Prior period 9M 2024 = $9.676B → correct YoY = +28.8%, not +39.1%. Tampered NI also flips the rank (GS $12.56B > MS $12.46B, so GS is #4, MS is #5 — not the inverse stated in the report).

> **Example — Validation report_05 (BAC):**  
> Report table: "Q3 2025 (Sep) | $1.06 | **$0.8610** | +23.1%"  
> earnings.json (BAC, 2025-09-30, Q3): `estimate=0.961, surprisePercent=10.30%`  
> The consensus was $0.961, not $0.8610. The surprise % was fabricated to fit the wrong estimate.

### Sub-type 1b: Financial Metrics (Revenue, Net Income, FCF, AUM)

**Source:** `financials_reported.json → .data.data[].report.ic[]`  
Match on: `startDate`/`endDate` for the period, `concept` for the metric (e.g., `us-gaap_NetIncomeLoss`).

> **Example — Train report_19 (MS):**  
> Report claims: "总客户资产 **$7.49万亿**（环比+8%，同比+14%）"  
> financials_reported.json (MS wealth management): correct value = **$6.49万亿**. Off by exactly $1T — a clean substitution.

> **Example — Validation report_03 (AMD):**  
> Report claims: "$2.82B vs. **$1.59B** in [prior year]"  
> financials_reported.json (AMD, nine-month 2024 ended 2024-09-28): net income ≈ **$1.159B**, not $1.59B.  
> The +143.7% YoY only reconciles against $1.16B, not $1.59B.

### Sub-type 1c: Price, Return %, and Count

**Source:** `prices/{TICKER}.csv` for price/return; raw text for counts (recalls, layoffs, deliveries).

> **Example — Train report_06 (UNH):**  
> Report claims: "year-to-date price decline of approximately **-50.6%** (against $504.51 on 2025-01-02)"  
> prices/UNH.csv: 2025-01-02 close = $504.51 ✓; 2025-12-31 close = $330.11 → correct return = (330.11/504.51) − 1 = **−34.6%**, not −50.6%.

> **Example — Train report_10 (TSLA):**  
> Report claims: "召回 **15,936辆** 2025款Model 3 与 2026款Model Y"  
> NHTSA source: correct count = **12,936辆**. Off by 3,000 — a plausible-looking but wrong substitution.

> **Example — Train report_12 (TSLA):**  
> Report claims: "过去一年涨幅约 **82.37%**（Benzinga数据）"  
> Correct figure from source: **72.37%**. Off by 10 percentage points.

---

## Error Type 2: 时间线扭曲 (Date / Timeline Distortion)

**Definition:** A date is shifted by days, weeks, or months — or a seasonal label is applied to the wrong period.

**How to detect:**
1. For price events (high/low close): scan `prices/{TICKER}.csv` for the row matching the claimed price value; check if the `date` column matches the report.
2. For filing dates: check the filename of `dataset/corpus/filings/{TICKER}/` (format: `{FORM}__{YYYY-MM-DD}__{ACCESSION}.htm`) or `sec_submissions.json → .data.filings.recent`.
3. For earnings announcement dates: check `earnings.json → .data[].period` and cross-reference 8-K filings.

> **Example — Train report_02 (TSLA):**  
> Report claims: "10-K filed on **February 5, 2025** (accession 0001628280-25-003063)"  
> Filing filename: `10-K__2025-01-30__0001628280-25-003063.htm` → filed **2025-01-30**, not Feb 5.

> **Example — Train report_09 (NEE):**  
> Report claims: "2025年 **8月23日**, NextEra Energy通过8-K披露Q2业绩"  
> 8-K filename in filings/NEE: date encoded as **2025-07-23**. The month was shifted forward by one month.

> **Example — Validation report_01 (NVDA):**  
> Report claims: "$94.31 (the **April 8** tariff-shock low close)"  
> prices/NVDA.csv: row with close=$94.31 has date **2025-04-04**, not April 8. The April 8 close was $96.30.

> **Example — Validation report_04 (AVGO):**  
> Report claims: "$412.97 (the **autumn** high close)"  
> prices/AVGO.csv: the row with close=$412.97 has date **2025-12-10** — December, not autumn.

> **Example — Validation report_19 (UPS):**  
> Report table: "2025-**02-28** | 114.90 | 单日跌近14%"  
> prices/UPS.csv: 2025-02-28 close ≈ $119.03 (~875万股). The $114.90 / ~41M share / −14% event actually occurred on **2025-01-30** (prev close $133.78 → $114.90).

---

## Error Type 3: 因果反转 (Direction / Cause-Effect Reversal)

**Definition:** The direction of a result is flipped — a beat becomes a miss, an up-move becomes down, an upgrade becomes a downgrade, or a management denial becomes an admission.

**How to detect:**
- EPS beat/miss: `earnings.json → .data[].surprisePercent` — positive = beat, negative = miss.
- Price direction: compare two rows in `prices/{TICKER}.csv`; (close_t1 / close_t0 − 1) gives the sign.
- Rating change: `recommendations.json → .data[].{fromGrade, toGrade}`.

> **Example — Train report_03 (COST):**  
> Report claims: "Q1 FY26 actual $4.50 vs. consensus $4.65 — a **−3.2% miss**"  
> earnings.json (COST, FY26Q1, period 2025-12-31): `actual=4.50, estimate=4.3571, surprisePercent=+3.2797`  
> The sign is inverted: this was a **+3.3% beat**, not a miss. The claim that this is the second consecutive miss is also wrong; only FY25Q4 was a small miss.

> **Example — Train report_17 (NKE):**  
> Report claims: "JPMorgan将评级由 **Overweight下调至Neutral**"  
> recommendations.json (NKE): JPMorgan on 2025-07-28 changed fromGrade=**Neutral** toGrade=**Overweight** — an upgrade, not a downgrade.

> **Example — Validation report_10 (GE):**  
> Report claims: "最终收报306.63美元，较前一交易日（10月20日收盘价302.68美元）**下跌约1.3%**"  
> prices/GE.csv: 2025-10-21 close=306.63, 2025-10-20 close=302.68 → (306.63/302.68−1) = **+1.3%**, not −1.3%. Direction reversed.

> **Example — Validation report_20 (NVDA):**  
> Report claims: "CEO黄仁勋在电话会议中明确**承认**'AI泡沫论'"  
> Context in same report and filing evidence: Huang made the comment as a **rebuttal** of the AI bubble thesis — he was refuting it, not admitting it.

---

## Error Type 4: 内部矛盾 (Internal Contradiction)

**Definition:** The report is self-inconsistent — two sections state different values for the same fact, or a stated calculation is arithmetically wrong given the other numbers in the same report.

**How to detect:** No external data needed. Cross-read all sections of the report and flag any value that contradicts another in the same document. Pay special attention to:
- Tables vs. narrative prose
- Section 4.x vs. Section 7/8
- Stated A, computed B = f(A), but B' ≠ f(A') where A' appears elsewhere.

> **Example — Validation report_07 (BA):**  
> Section 5 and Section 8: "上半年民用飞机交付从175增至**285架**（+63%）"  
> Section elsewhere: "整体民用飞机交付 **385架**，较2024年同期175架"  
> 385/175 ≈ +120%, contradicts the +63% and 285 figures used consistently elsewhere. One figure is wrong.

> **Example — Validation report_10 (GE):**  
> §4.1 table: "自由现金流 | **32亿美元**"  
> §五 and §八 both state: "本季自由现金流为**24亿美元**"  
> Two different FCF figures in the same report; the table contradicts the narrative.

> **Example — Validation report_11:**  
> Risk factors §3 and conclusion: "裁员**20,000人**"  
> One section: "裁员**25,000个岗位**...削减约2.5万个职位"  
> Off by 5,000 jobs — same report, different sections.

> **Example — Validation report_09 (NFLX):**  
> §4.1 table: "NFLX Q3实际EPS = 0.5870, surprisePercent = **−17.39%**" (miss)  
> §一: "实际EPS 0.687美元...超预期幅度 **+17.39%**" (beat)  
> The sign and even the actual EPS value are contradicted within the same report.

**Tip:** When a report has a summary section (§八 or equivalent), that section often states the correct intended values. Use it as a reference to identify which other section holds the tampered value.

---

## Error Type 5: 信源张冠李戴 (Source Attribution Error)

**Definition:** A factual claim is attributed to the wrong institution, analyst firm, or media outlet. The number itself may be correct; only the source credit is wrong.

**How to detect:**
- Analyst targets/ratings: `recommendations.json → .data[].{firm, toGrade, fromGrade, date, targetPrice}`.
- Media citations: search `dataset/corpus/news/{TICKER}/` for the headline; check the outlet field.

> **Example — Train report_16 (MRK):**  
> Report claims: "公司向 **Wall Street Journal** 披露将裁减约6,000人"  
> Correct source: **Fierce Pharma** was the outlet that broke the MRK restructuring story.

> **Example — Train report_17 (NKE):**  
> Report claims: "2025年7月29日 **Bloomberg** 报道，NIKE北美女装业务负责人离职转投Athleta"  
> Correct source: the report originated at **CNBC**.

> **Example — Validation report_14:**  
> Report claims: "**Morgan Stanley** 给出$515的新高目标价"  
> §七 and §八 of the same report attribute the $515 target to **Wedbush**. recommendations.json also confirms the firm.

> **Example — Validation report_18 (COST):**  
> Report claims: "Costco的Growth评分由57.41跃升至**95.06**（**Morningstar**数据）"  
> §五 table and §八 both cite **Benzinga Edge** as the source and give the target as **90.06**, not 95.06. Two errors combined: wrong source and wrong number.

---

## Error Type 6: 盘中/收盘混淆 (Intraday vs. Close Price)

**Definition:** The report labels an intraday high (or low) as a closing price, or vice versa. The value is correct for one column but wrong for the stated metric.

**How to detect:**
1. Find the date in `prices/{TICKER}.csv`.
2. Compare the reported value against both `close` and `high` (or `low`) columns.
3. Flag if the reported value matches `high`/`low` but is labeled as a closing price (or "收盘价").

> **Example — Validation report_16 (TSLA):**  
> Report table §4.5: "2025-12-22（年内高点） | **498.83** | [列标题：收盘价]"  
> prices/TSLA.csv, 2025-12-22: `close=488.73`, `high=498.83`  
> 498.83 is the intraday high, not the close. The year's highest close was $489.88 on 2025-12-16.

> **Example — Validation report_17 (DUK):**  
> Report: "全年最高收盘价 | **$130.03**（2025-10-22 盘中高点）"  
> prices/DUK.csv, 2025-10-22: `close=129.03`, `high=130.03`  
> The cell itself notes "盘中高点" — a self-contradiction. The correct highest close is $129.03.

**Rule:** When a report cites a price as "收盘价" (close), verify against the `close` column only. The `high` and `low` columns are never valid substitutes for close in this context.

---

## Error Type 7: 分类/成员错误 (Classification / Membership Error)

**Definition:** A ticker or entity is placed in the wrong category (wrong peer group, wrong sector, wrong index), or an entity that does not belong to a list is included.

**How to detect:**
- Peer group: `peers.json → .data[]` — this is the authoritative list. The array includes the ticker itself; strip self before comparing to report.
- Sector/index membership: cross-reference with known sector data or filing SIC codes in `sec_submissions.json`.

> **Example — Train report_05 (PFE):**  
> Report claims: "PFE's peer basket is LLY, JNJ, MRK, BMY, ZTS, RPRX, VTRS, ELAN, AXSM and **NVS**"  
> peers.json (PFE).data = ['LLY', 'JNJ', 'MRK', 'PFE', 'BMY', 'ZTS', 'RPRX', 'VTRS', 'ELAN', 'AXSM']  
> NVS (Novartis) is **not** in the Finnhub peer list. The report appended a tenth name that doesn't belong.

> **Example — Validation report_02 (BAC):**  
> Report claims: "USB, FITB, KEY, FCNCA and **FINN** — canonical money-center plus regional banks"  
> peers.json (BAC): FINN is a non-standard/inactive ticker, not a bank. Calling this group "canonical money-center plus regional banks" is inaccurate given FINN's presence.

---

## Detection Priority Order

When reviewing a report, apply checks in this order (highest precision first):

1. **Intraday/close confusion** (Type 6) — single-row price CSV lookup, near-zero false-positive rate.
2. **EPS actual/estimate/surprise** (Type 1a) — direct field match in earnings.json; exact arithmetic check.
3. **Filing date** (Type 2) — filename of filing doc encodes the date; zero ambiguity.
4. **Peer membership** (Type 7) — set membership in peers.json; binary yes/no.
5. **Financial metrics** (Type 1b) — match concept + period in financials_reported.json.
6. **Price event date** (Type 2) — scan prices CSV for the claimed price value; check date column.
7. **Price direction / return sign** (Type 3) — arithmetic on two CSV rows.
8. **Internal contradiction** (Type 4) — cross-section read; no external data needed.
9. **Source attribution** (Type 5) — recommendations.json or news corpus lookup.
10. **Number tampering in counts/quotes** (Type 1c) — requires raw text evidence; lower confidence.

---

## Emit Rules

- **Quote** must be a verbatim substring of the report. Never paraphrase.
- **Reason** must cite the authoritative source (file path + field name + observed value) and state the contradiction explicitly.
- Default to **abstain** when: the source file is missing, the period is ambiguous, or the discrepancy is within rounding (≤1% for metrics, ≤$0.005 for EPS, ≤1 calendar day for dates).
- **Internal contradiction** (Type 4): quote the clearly wrong section; reason should reference the correct section by heading (e.g., "§八 states X, contradicting this claim of Y").
- One issue per distinct claim. Do not merge two separate errors into one quote.
