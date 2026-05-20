# review (19) vs review_train_gt 审查分析

## 1. 统计口径

对比文件：

- 预测输出：`review (19).jsonl`（本次云端 train 跑的产出，共 90 条预测）
- 标准答案：`reference_submission/problem/review_train_gt.jsonl`（28 条 GT 错误）

> 命名说明：本次文件 `review (19).jsonl` 含 90 条预测，与 `docs/review15_train_gt_analysis.md` 中
> "review(19) 版本（65 条）"不是同一份产物（很可能是云端编号或一次重跑产生）。
> 下文统计、对齐表以本次实际文件为准。

口径沿用前几版：

- 同一个 GT 错误只算 1 个 TP；
- 同一错误被拆成多条，额外条目算 FP；
- 只说"没有证据支持 / no source supports / cannot be flagged / no contradiction"的候选，严格不算 TP；
- reason 中明确承认"无法确认 / 无直接反证 / absence of support is not contradiction" 的候选，不算 TP；
- 主表使用"语义命中口径"：quote 指向同一 GT 错误，且 reason 给出基本反证，即算 TP；
- 同时给出"exact-reason 口径"：如果 reason 给出的 correct value / source / action 明显偏离 GT，则不计 TP。

边界项：

- `report_17`：抓到 JPMorgan `Overweight -> Neutral` downgrade 这条，但 reason 主要说
  "no source mentions JPMorgan downgrading from Overweight to Neutral" 与 "target $93 from $64 与 source 不符"，
  **没有完整指出 GT 的正确动作 `Neutral -> Overweight`**。语义口径算 TP，exact-reason 口径不算。
- `report_09`：同时抓到 NEE 8-K 日期与 CEO quote `12.4%`，且 reason 明确给出 `9.4%` 来源；
  语义口径和 exact-reason 口径均算 TP。
- 多条输出 reason 中写了"no contradiction / supported / cannot be flagged / not flagged"
  却仍进入最终 issues —— 这类全部计 FP（`report_11/12/13/14/16/18/19` 都有）。

## 2. 总体结果

### 2.1 语义命中口径

| 指标 | 数值 |
|---|---:|
| GT issue 数 | 28 |
| Pred issue 数 | 90 |
| TP | 13 |
| FP | 77 |
| FN | 15 |
| Precision | 14.4% |
| Recall | 46.4% |
| F1 | 22.0% |

### 2.2 exact-reason 口径

`report_17` 的 JPM downgrade 因 correct action 未明确写出 `Neutral -> Overweight` 而不计 TP：

| 指标 | 数值 |
|---|---:|
| TP | 12 |
| FP | 78 |
| FN | 16 |
| Precision | 13.3% |
| Recall | 42.9% |
| F1 | 20.3% |

后续分析主用语义命中口径，边界项会标注。

## 3. 逐题对齐表

| report | GT | Pred | TP | FP | FN | 备注 |
|---|---:|---:|---:|---:|---:|---|
| report_01 | 1 | 4 | 1 | 3 | 0 | META Q4 EPS 抓到；同一 EPS 错误拆成 actual / full-year sum / 组合段落三条，另多报开盘价/收盘价对照 |
| report_02 | 1 | 3 | 1 | 2 | 0 | TSLA 10-K 日期抓到；多报九个月营收 `$69.93B` 舍入与同一 filing date 重复一条 |
| report_03 | 1 | 2 | 1 | 1 | 0 | COST Q1 FY26 miss/beat 抓到；"back-to-back misses"作为派生叙事重复输出 |
| report_04 | 1 | 5 | 1 | 4 | 0 | WMT 财季截止日抓到；多报 9M 营收/净利、单季度推算和 Finnhub period 标签 |
| report_05 | 1 | 2 | 1 | 1 | 0 | PFE peer NVS 抓到；多报 9M 净利 `$9.42B vs $9.452B` 舍入 |
| report_06 | 1 | 2 | 1 | 1 | 0 | UNH 年收益率 -50.6% 抓到；多报 9M 净利 |
| report_07 | 1 | 1 | 1 | 0 | 0 | GS Q4 estimate/surprise 抓准 |
| report_08 | 1 | 1 | 0 | 1 | 1 | GT 是 MS 9M 净利；预测误抓 WFC 行 9M 净利 |
| report_09 | 2 | 5 | 2 | 3 | 0 | NEE 8-K 日期 + CEO 12.4% -> 9.4% 都抓到；另把正确的 9.4% 又误报、并多报 FPL `$1.3B` |
| report_10 | 3 | 4 | 1 | 3 | 2 | TSLA Q3 EPS 方向抓到；漏 NHTSA 召回数 `15,936 vs 12,936`、股东会 `11.16 vs 11.6` |
| report_11 | 2 | 4 | 0 | 4 | 2 | NEE dividend CAGR、XLU 日期均漏；多报 CNP peer EPS、Q3/Q4 EPS 和 guidance |
| report_12 | 3 | 4 | 1 | 3 | 2 | TSLA QoQ EPS 方向抓到；漏一年涨幅 `82.37 vs 72.37` 和股东会日期 |
| report_13 | 1 | 8 | 0 | 8 | 1 | Netflix `The Electric State` 预算漏；多报 EPS、股价、净利、广告用户和 guidance |
| report_14 | 0 | 8 | 0 | 8 | 0 | GT 无错；预测 8 条 PG 误报，其中 6 条 reason 自称不可判错仍输出 |
| report_15 | 1 | 5 | 0 | 5 | 1 | GS M&A lead `950 vs 850` 漏；多报净利、AUS、融资收入、SCB/CET1 |
| report_16 | 2 | 8 | 0 | 8 | 2 | MRK 开盘价 `$110.28 vs $100.28` 与 WSJ/Fierce Pharma 信源错配均漏；多报数量级（"亿"理解错）、guidance 与 unsupported 候选 |
| report_17 | 3 | 5 | 1 | 4 | 2 | NKE JPM downgrade 语义命中（exact-reason 不算）；漏 EPS estimate `$1.52 vs $1.32` 与 Bloomberg/CNBC 信源错配 |
| report_18 | 1 | 5 | 0 | 5 | 1 | LLY Mounjaro 日本 `+44% vs +24%` 漏；多报收益率、EPS 增长、量价拆解、利润率和价格 |
| report_19 | 1 | 6 | 0 | 6 | 1 | MS 客户资产 `$7.49T vs $6.49T` 漏；多报发布日期、税前利润单位、EPS 序列、资产、VaR 与舍入 |
| report_20 | 1 | 8 | 1 | 7 | 0 | ABBV market cap `$453.1B` 抓到；多报 EPS estimate、收益率、分部收入数量级（"亿"理解错）、药名 (`Emrelis`)、consensus 与 adjusted EPS |

## 4. 与前几版的变化

| 版本 | Pred | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| review (15) | 84 | 11 | 73 | 17 | 13.1% | 39.3% | 19.6% |
| review (17) 语义口径 | 90 | 13 | 77 | 15 | 14.4% | 46.4% | 22.0% |
| review(18) | 56 | 10 | 46 | 18 | 17.9% | 35.7% | 23.8% |
| review(19) 旧版（65 条） | 65 | 11 | 54 | 17 | 16.9% | 39.3% | 23.7% |
| **review (19) 本次（90 条）语义口径** | **90** | **13** | **77** | **15** | **14.4%** | **46.4%** | **22.0%** |
| review (19) 本次 exact-reason 口径 | 90 | 12 | 78 | 16 | 13.3% | 42.9% | 20.3% |
| review (20) 语义口径 | 90 | 13 | 77 | 15 | 14.4% | 46.4% | 22.0% |

变化：

- 本次 `review (19).jsonl` 在数值上与 `review (17)` / `review (20)` 完全一致（TP=13、FP=77、FN=15），与上一份"review(19) 旧版（65 条）"不是同一产物。
- 相比 `review(19) 旧版`，Pred 从 65 增到 90，TP 从 11 增到 13，FP 从 54 增到 77；
  recall 从 39.3% 回升到 46.4%，precision 从 16.9% 降到 14.4%。
- 召回提升主要来自 `report_09` 的 NEE CEO `12.4%` 与 `report_17` 的 JPM downgrade；
  但 precision 下降表明召回提升是靠放宽输出，不是更精准的候选筛选。
- 大量 GT=0 或 unsupported-only 误报仍存在，尤其 `report_14/16/19/20`。

## 5. 命中情况

### 5.1 稳定命中的类型

| 类型 | 命中 report | 说明 |
|---|---|---|
| EPS actual/estimate/surprise | 01, 03, 07, 10, 12 | 结构化 EPS 再次 5/5 命中 |
| filing date / fiscal period | 02, 04, 09 | TSLA 10-K、WMT fiscal Q3、NEE 8-K 日期能抓 |
| peer list | 05 | PFE peers 中 NVS 错误抓准 |
| price return arithmetic | 06 | UNH 年收益率错误抓到 |
| news/analyst narrative | 09, 17, 20 | NEE CEO 12.4%、NKE JPM downgrade、ABBV market cap 有召回；NKE reason 不够完整 |

### 5.2 改善 / 命中亮点

| report | 亮点 |
|---|---|
| report_09 | NEE CEO 12.4% 反证给出 9.4% 出处与具体数值，命中干净 |
| report_17 | NKE JPM downgrade 至少语义上抓回（虽 reason 不写正确方向） |
| report_20 | ABBV market cap `$453.1B` 命中，反证列出多个 SOURCE 显示低于该值 |

### 5.3 代价

- `report_14` GT 为 0，但输出 8 条；其中 6 条 reason 已写明无法判错；
- `report_16` 输出 8 条全部不中 GT，主要是把 中文"亿"误读为 billion 量级的数量级错；
- `report_19` 输出 6 条，GT 客户资产没中；
- `report_20` 在命中 market cap 同时多报 7 条非 GT。

## 6. 漏报分析

语义口径下 FN=15，主要集中在以下类别：

| 漏报类型 | 数量 | 涉及 report | 说明 |
|---|---:|---|---|
| news/social 细节数字篡改 | 7 | 10, 11, 12, 13, 15, 18, 19 | NHTSA 召回数、NEE dividend CAGR、TSLA 一年涨幅、电影预算、M&A lead、Mounjaro 日本增长、MS 客户资产 |
| 事件日期篡改 | 3 | 10, 11, 12 | TSLA 股东会日期、XLU 创新高日期 |
| 信源张冠李戴 | 2 | 16, 17 | MRK WSJ/Fierce Pharma、NKE Bloomberg/CNBC |
| price 字段细节 | 1 | 16 | MRK 2025-01-02 open `$110.28 vs $100.28` |
| financials 表格行错配 | 1 | 08 | MS 九个月净利漏，误抓 WFC 行 |
| analyst estimate 细节 | 1 | 17 | JPM FY2026 EPS estimate `$1.52 vs $1.32` 漏 |

典型漏报：

- `report_10`：漏掉 NHTSA 召回数量 15,936 vs 12,936，以及股东会 11 月 16 日 vs 11 月 6 日。
- `report_11`：NEE dividend CAGR 15% vs 10%、XLU 8 月 22 日 vs 7 月 22 日均漏。
- `report_13`：漏掉 `The Electric State` 预算 `$420M vs $320M`。
- `report_16`：MRK 开盘价 `$110.28 vs $100.28`、裁员报道媒体 WSJ vs Fierce Pharma 均漏。
- `report_19`：漏掉 MS Wealth Management 总客户资产 `$7.49T vs $6.49T`。

## 7. 误报分析

90 个预测中 FP=77。主要误报类型（互斥归因）：

| 误报类型 | 估计数量 | 占 Pred | 典型表现 |
|---|---:|---:|---|
| 指标口径混淆 | 24 | 26.7% | revenue / net income / EPS / Non-GAAP / segment / period / YTD 混用 |
| 中文"亿"量级误读 | 13 | 14.4% | `report_16` (Gardasil/Keytruda/Verona/guidance)、`report_20` (Immunology/Neuroscience/Oncology/Aesthetics) 集中爆发 |
| 把缺少证据当错误 | 14 | 15.6% | `no source supports`、`not provided`、`absence` 类进入最终输出 |
| 舍入/近似误判 | 9 | 10.0% | `$69.926B` vs `$69.93B`、`$16.792B` vs `$16.8B` 等 |
| reason 否定自身仍输出 | 12 | 13.3% | reason 写明 `no contradiction`、`cannot be flagged`、`statement is supported`、`not flagged` 仍输出 |
| cascading / 派生重复 | 6 | 6.7% | 同一 EPS 错误被拆成 actual、surprise、全年 sum、叙事后果 |
| 价格时点混用 | 5 | 5.6% | 全年端点、拆股后价格、52-week range 反驳局部时点 |
| 反向错抓或方向不清 | 4 | 4.4% | event/guidance/rating action 的正确方向没回到原始 source 确认 |

> 注：分类有重叠（如 `report_14` 的多条同时占"reason 否定自身"和"指标口径混淆"），上表按主要归因计。

典型误报：

- `report_14`：GT 为 0，但输出 8 条 PG issue；其中 6 条 reason 自称不能判错。最终 filter 失效。
- `report_16`：MRK 8 条全部不中 GT，4 条直接是把中文"亿"当成 billion 反报数量级错。
- `report_19`：MS 客户资产没抓到，却输出发布日期、EPS 序列、资产、VaR、收入舍入等 6 条。
- `report_20`：抓到 market cap，但另外 7 条围绕"亿"量级、drug name (`Emrelis`)、consensus `$1.77 vs $1.78`。

## 8. train_gt 错误来源分布

按"需要用哪类数据源才能验证 GT 错误"归类：

| GT 验证来源类型 | GT 数 | 占比 | 典型错误 | 涉及 report |
|---|---:|---:|---|---|
| `earnings.json` / EPS 结构化 | 5 | 17.9% | actual/estimate/surprise、beat/miss 方向、QoQ EPS 方向 | 01, 03, 07, 10, 12 |
| filing catalog / SEC filing / event date | 4 | 14.3% | 10-K filing date、8-K 日期、股东会日期 | 02, 09, 10, 12 |
| `financials_reported.json` / 财务报表结构化 | 2 | 7.1% | fiscal quarter endDate、9M net income | 04, 08 |
| `peers.json` | 1 | 3.6% | peer list 多加 ticker | 05 |
| `prices/*.csv` / 市场价格 | 2 | 7.1% | 年收益率计算、开盘价数字篡改 | 06, 16 |
| news/social/regulatory/analyst narrative | 14 | 50.0% | 新闻数字篡改、媒体归因、分析师动作、召回数量、市值、客户资产、产品区域增长 | 09, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20 |

## 9. review (19) 按数据源类型的表现

### 9.1 对 GT 来源类型的召回

| GT 验证来源类型 | GT 数 | TP | FN | Recall | 评估 |
|---|---:|---:|---:|---:|---|
| `earnings.json` / EPS 结构化 | 5 | 5 | 0 | 100.0% | 结构化 EPS 仍是最稳路径 |
| filing catalog / SEC filing / event date | 4 | 2 | 2 | 50.0% | 10-K 和 NEE 8-K 日期能抓；TSLA 股东会日期仍漏 |
| `financials_reported.json` / 财务报表结构化 | 2 | 1 | 1 | 50.0% | WMT 抓到；MS 表格行仍误抓 WFC |
| `peers.json` | 1 | 1 | 0 | 100.0% | PFE peer list 抓准 |
| `prices/*.csv` / 市场价格 | 2 | 1 | 1 | 50.0% | UNH return 抓到；MRK open 漏 |
| news/social/regulatory/analyst narrative | 14 | 3 | 11 | 21.4% | NEE CEO、NKE JPM、ABBV market cap 抓到；NKE 为边界命中 |
| **合计** | **28** | **13** | **15** | **46.4%** | recall 提升集中在 narrative，但 precision 代价大 |

exact-reason 口径下，narrative 行变为 TP=2、FN=12、Recall=14.3%（`report_17` JPM 不计 TP）。

### 9.2 FP 按数据源类型分布

77 个 FP 的主要审查路径（互斥归因）：

| FP 主要来源 / 审查路径 | FP 数 | 占 FP | 典型问题 |
|---|---:|---:|---|
| `financials_reported` / 10-Q 财务表 / metric 口径 | 22 | 28.6% | revenue/net income/period/YTD/single-quarter/segment 口径混淆 |
| news/social/analyst narrative | 21 | 27.3% | 抓到非 GT 的新闻、业务线、guidance、drug name 或 source 解释 |
| 中文"亿"量级误读（专属类） | 13 | 16.9% | `report_16/20` 把"亿美元"反报为 billion 量级错 |
| `earnings.json` / EPS | 9 | 11.7% | EPS 重复拆分、estimate/actual 口径混用、叙事派生重复 |
| `prices/*.csv` / market data | 6 | 7.8% | 全年端点、拆股时点、52-week range、open/close 混用 |
| filing/event/guidance catalog | 4 | 5.2% | 备案日/发布日、event date、guidance 更新的 unsupported 推断 |
| other / mixed arithmetic | 2 | 2.6% | 多来源混合推断，缺单一明确反证 |
| **合计** | **77** | **100.0%** | FP 反弹主要来自 financials 与 narrative 泛审计 + "亿"误读 |

## 10. 来源类型层面的结论

1. **review (19) 本次是"放宽召回"而不是"提高判别"**：与 review (17)/(20) 数据完全一致，
   recall 46.4%，但 precision 仅 14.4%；继续走"多输出换召回"的路线，没有强化 filter。

2. **结构化 EPS 仍然可靠**：`earnings.json` 类 GT 5/5 命中，但 `report_01/03` 仍把同一事实链
   拆成多条，cascading FP 没有去重。

3. **narrative 召回不稳**：NEE CEO `12.4%` 抓得干净；NKE JPM downgrade 语义命中、exact-reason 不稳。

4. **final filter 明显漏网**：`report_14/16/18/19` 多条 reason 明确写了
   `no contradiction / supported / cannot be flagged / not flagged`，但最终仍输出，
   直接拉低 precision。这是这一版最容易拿分的修正点。

5. **中文"亿"量级误读是这一版的新爆点**：`report_16/20` 共 13 条 FP 是把"亿美元"
   当作 billion 量级反报数量级错。原文里"$11.30 亿"（≈ $1.13B）被预测器读成 `$11.30B`
   而触发"过大十倍"误报。**这是一个可以一次性规避的明确 bug**。

6. **financials 单位与 metric namespace 仍是 FP 重灾区**：`report_14/15/19` 集中在 GAAP/core/adjusted、
   quarter/YTD、segment/company 口径混用，没有强约束。

7. **事件日期和信源归因仍是主要漏报区**：TSLA 股东会、XLU 日期、MRK WSJ/Fierce、NKE Bloomberg/CNBC
   这些需要回到原始 news/filing source 的错误仍大多漏掉。

## 11. 建议（按优先级）

| 优先级 | 改法 |
|---|---|
| P0 | final filter 必须删除 reason 中含 `no contradiction`、`cannot be flagged`、`supported`、`absence of support is not contradiction`、`not flagged`、`cannot be confirmed` 的候选 —— 这一项预计直接砍掉 ~12 条 FP |
| P0 | 中文"亿"和 billion 之间做单位归一化预处理（`X亿美元 = (X/10) billion USD`）；专门加 metric magnitude sanity check，避免 `report_16/20` 那类十倍量级的反报 |
| P0 | 最终输出只允许 `verdict=contradict` 且必须给出明确 correct value/source；unsupported/ambiguous/match 不得进入 final |
| P0 | 对 narrative 命中做 correct-value/action 校验：NKE 这类 rating action 必须写出正确方向 `Neutral -> Overweight` 才算强命中 |
| P1 | event-date router 回到原始 filing/news source 判定日期，不能用报告内自相矛盾句子或"无来源支持"替代反证 |
| P1 | financials 校验加 metric namespace：GAAP/core/adjusted、quarter/YTD、segment/company、reported/non-GAAP、period endDate 必须一致 |
| P1 | 对同一 quote/correct source 做 cascading 去重：同一 GT 错误最多输出一条，派生叙事不再重复报 |
| P1 | 信源归因比对：MRK WSJ vs Fierce、NKE Bloomberg vs CNBC 这类需要在 news_event `attributed_to` / `provider` 字段做精确比对 |
| P2 | 对 GT=0 或低置信报告设置 FP guardrail：如果没有明确反证，整篇允许输出空 issues |
| P2 | 利用 main 上新接入的 `news_event` 流（`[EVENT 日期 \| 极性 \| src \| via]` 单句 + 前几条事件的原文窗）做 narrative 命中加强 —— 召回缺口集中在 news/social narrative，事件流的极性/出处/日期正好对应 |

## 12. 一句话总结

review (19) 本次 = review (17)/(20) 同样的"放宽召回"产物：recall 46.4%、precision 14.4%、F1 22.0%；
**最容易拿分的两个修正点是 (a) 砍掉 reason 自我否定却仍输出的 ~12 条 FP，(b) 修复中文"亿"量级误读的 ~13 条 FP**。
narrative 召回缺口（漏 11 条）需要靠 main 上新接入的 news_event 事件流（极性/出处/日期）配合原文窗补齐。
