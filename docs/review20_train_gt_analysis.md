# review (20) vs review_train_gt 审查分析

## 1. 统计口径

对比文件：

- 预测输出：`review (20).jsonl`
- 标准答案：`reference_submission/problem/review_train_gt.jsonl`

对齐口径沿用前几版：

- 同一个 GT 错误只算 1 个 TP；
- 同一错误被拆成多条，额外条目算 FP；
- 只说“没有证据支持”的候选，严格不算 TP；
- reason 中明确承认“无法确认 / 无直接反证 / no contradiction”的候选，不算 TP；
- 本文主表使用“语义命中口径”：quote 指向同一 GT 错误，且 reason 给出基本反证，即算 TP；
- 同时给出“exact-reason 口径”：如果 reason 的 correct value/source 明显偏离 GT，则不计 TP。

边界项：

- `report_09`：同时抓到了 NEE 8-K 日期和 CEO quote 中的 `12.4%`，且 reason 明确给出 `9.4%` 来源；语义口径和 exact-reason 口径均算 TP。
- `report_17`：抓到了 JPMorgan `Overweight -> Neutral` downgrade 这条，但 reason 主要说“没有来源支持 downgrade / target price 不符”，没有完整指出 GT 的正确动作 `Neutral -> Overweight`。语义口径算 TP，exact-reason 口径不算。
- 多个输出 reason 中写了“no contradiction / supported / cannot be flagged”，但仍进入最终 issues；这类全部计 FP。

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

如果 `report_17` 的 JPM downgrade 因 correct action/source 不够准确而不计 TP：

| 指标 | 数值 |
|---|---:|
| TP | 12 |
| FP | 78 |
| FN | 16 |
| Precision | 13.3% |
| Recall | 42.9% |
| F1 | 20.3% |

后续分析主用语义命中口径，但会标注边界项。

## 3. 逐题对齐表

| report | GT | Pred | TP | FP | FN | 备注 |
|---|---:|---:|---:|---:|---:|---|
| report_01 | 1 | 4 | 1 | 3 | 0 | META Q4 EPS 抓到；同一 EPS 错误仍拆成 actual、full-year sum、组合段落三条，另多报开盘/收盘价 |
| report_02 | 1 | 3 | 1 | 2 | 0 | TSLA 10-K 日期抓到；另多报九个月收入舍入和重复 filing date |
| report_03 | 1 | 2 | 1 | 1 | 0 | COST miss/beat 抓到；“back-to-back misses”作为派生叙事重复输出 |
| report_04 | 1 | 5 | 1 | 4 | 0 | WMT 财季截止日抓到；多报收入、净利、单季度推算和 period 标签 |
| report_05 | 1 | 2 | 1 | 1 | 0 | PFE peer NVS 抓到；多报九个月净利 |
| report_06 | 1 | 2 | 1 | 1 | 0 | UNH 年收益率抓到；多报净利 |
| report_07 | 1 | 1 | 1 | 0 | 0 | GS Q4 estimate/surprise 抓准 |
| report_08 | 1 | 1 | 0 | 1 | 1 | GT 是 MS 净利；预测误抓 WFC 行 |
| report_09 | 2 | 5 | 2 | 3 | 0 | NEE 8-K 日期和 CEO `12.4% -> 9.4%` 都抓到；另把正确的 9.4% 又误报、并多报 FPL |
| report_10 | 3 | 4 | 1 | 3 | 2 | TSLA Q3 EPS 方向抓到；漏召回数和股东会日期 |
| report_11 | 2 | 4 | 0 | 4 | 2 | NEE dividend CAGR、XLU 日期均漏；多报 peer EPS、Q3/Q4 EPS 和 guidance |
| report_12 | 3 | 4 | 1 | 3 | 2 | TSLA QoQ EPS 方向抓到；漏一年涨幅和股东会日期 |
| report_13 | 1 | 8 | 0 | 8 | 1 | Netflix `The Electric State` 预算漏；多报 EPS、股价、净利、广告用户和 guidance |
| report_14 | 0 | 8 | 0 | 8 | 0 | GT 无错；预测 8 条 PG 误报，其中多条 reason 自称不可判错仍输出 |
| report_15 | 1 | 5 | 0 | 5 | 1 | GS M&A lead 950 vs 850 漏；多报净利、AUS、融资收入、SCB/CET1 |
| report_16 | 2 | 8 | 0 | 8 | 2 | MRK 开盘价和 WSJ/Fierce Pharma 信源错配均漏；多报 EPS、产品收入数量级、guidance 和 unsupported 候选 |
| report_17 | 3 | 5 | 1 | 4 | 2 | NKE JPM downgrade 语义命中但 reason 不完整；漏 EPS estimate $1.52 和 Bloomberg/CNBC 信源错配 |
| report_18 | 1 | 5 | 0 | 5 | 1 | LLY Mounjaro 日本 +44% 漏；多报收益率、EPS 增长、量价拆解、利润率和价格 |
| report_19 | 1 | 6 | 0 | 6 | 1 | MS 客户资产 $7.49T 漏；多报发布日期、税前利润单位、EPS 序列、资产、VaR 和舍入 |
| report_20 | 1 | 8 | 1 | 7 | 0 | ABBV market cap 抓到；多报 EPS estimate、收益率、分部收入数量级、药名、consensus 和 adjusted EPS |

## 4. 与前几版的变化

| 版本 | Pred | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| review (15) | 84 | 11 | 73 | 17 | 13.1% | 39.3% | 19.6% |
| review (17) 语义口径 | 90 | 13 | 77 | 15 | 14.4% | 46.4% | 22.0% |
| review(18) | 56 | 10 | 46 | 18 | 17.9% | 35.7% | 23.8% |
| review(19) | 65 | 11 | 54 | 17 | 16.9% | 39.3% | 23.7% |
| review (20) 语义口径 | 90 | 13 | 77 | 15 | 14.4% | 46.4% | 22.0% |
| review (20) exact-reason 口径 | 90 | 12 | 78 | 16 | 13.3% | 42.9% | 20.3% |

变化：

- 相比 `review(19)`，Pred 从 65 增到 90，TP 从 11 增到 13，FP 从 54 增到 77。
- 语义口径下，recall 回到 `review (17)` 水平，主要新增来自 `report_09` 的 NEE CEO `12.4%` 和 `report_17` 的 JPM downgrade。
- precision 从 `review(19)` 的 16.9% 降到 14.4%，说明召回提升主要靠放宽输出，而不是更精准的候选筛选。
- `review (20)` 比 `review (17)` 的 `report_09` 更好：CEO 12.4% 的 reason 明确写出 9.4%，不再是 correct value 偏差边界项。
- 但 `review (20)` 又恢复了大量 GT=0 或 unsupported-only 误报，尤其 `report_14/16/19/20`。

## 5. 命中情况

### 5.1 稳定命中的类型

| 类型 | 命中 report | 说明 |
|---|---|---|
| EPS actual/estimate/surprise | 01, 03, 07, 10, 12 | 结构化 EPS 再次 5/5 命中 |
| filing date / fiscal period | 02, 04, 09 | TSLA 10-K、WMT fiscal Q3、NEE 8-K 日期能抓 |
| peer list | 05 | PFE peers 中 NVS 错误抓准 |
| price return arithmetic | 06 | UNH 年收益率错误抓到 |
| news/analyst narrative | 09, 17, 20 | NEE CEO 12.4%、NKE JPM downgrade、ABBV market cap 有召回；其中 NKE reason 仍不够完整 |

### 5.2 明显改善项

| report | 改善点 |
|---|---|
| report_09 | `review(18/19)` 漏掉 NEE CEO 12.4%，`review (20)` 抓回，并给出 9.4% 反证 |
| report_17 | `review(18/19)` NKE 三个 GT 全漏，`review (20)` 至少语义上抓回 JPM downgrade |
| report_20 | ABBV market cap 继续稳定命中 |

### 5.3 代价

`review (20)` 的召回提升伴随明显 FP 反弹：

- `report_14` GT 为 0，但输出 8 条；
- `report_16` 输出 8 条，两个 GT 都没中；
- `report_19` 输出 6 条，GT 客户资产没中；
- 多条 reason 明确写了“不构成 contradiction”，但仍进入 final issues。

## 6. 漏报分析

语义口径下 FN=15，主要集中在以下类别：

| 漏报类型 | 数量 | 涉及 report | 说明 |
|---|---:|---|---|
| news/social 细节数字篡改 | 7 | 10, 11, 12, 13, 15, 18, 19 | NHTSA 召回数、NEE dividend CAGR、TSLA 一年涨幅、电影预算、M&A lead、Mounjaro 日本增长、MS 客户资产 |
| 事件日期篡改 | 3 | 10, 11, 12 | TSLA 股东会日期、XLU 创新高日期 |
| 信源张冠李戴 | 2 | 16, 17 | MRK WSJ/Fierce Pharma、NKE Bloomberg/CNBC |
| price 字段细节 | 1 | 16 | MRK 2025-01-02 open $110.28 vs $100.28 |
| financials 表格行错配 | 1 | 08 | MS 九个月净利漏，误抓 WFC |
| analyst estimate 细节 | 1 | 17 | JPM FY2026 EPS estimate $1.52 vs $1.32 漏 |

典型漏报：

- `report_10`：漏掉 NHTSA 召回数量 15,936 vs 12,936，以及股东会 11 月 16 日 vs 11 月 6 日。
- `report_11`：NEE dividend CAGR 15% vs 10%、XLU 8 月 22 日 vs 7 月 22 日均漏。
- `report_13`：漏掉 `The Electric State` 预算 $420M vs $320M。
- `report_16`：MRK 开盘价 $110.28 vs $100.28、裁员报道媒体 WSJ vs Fierce Pharma 均漏。
- `report_19`：漏掉 MS Wealth Management 总客户资产 $7.49T vs $6.49T。

## 7. 误报分析

90 个预测 issue 中，语义口径 FP=77。主要误报类型如下，类别之间有重叠。

| 误报类型 | 估计数量 | 占 Pred | 典型表现 |
|---|---:|---:|---|
| 指标口径混淆 | 44 | 48.9% | revenue/net income/EPS/Non-GAAP/segment/period/YTD 混用 |
| 单位/数量级问题泛化 | 32 | 35.6% | 中文“亿”、billion、segment revenue、产品销售额数量级被反复误报 |
| 把缺少证据当错误 | 28 | 31.1% | `no source supports`、`not provided`、`absence` 类进入最终输出 |
| 舍入/近似误判 | 18 | 20.0% | `$69.926B` vs `$69.93B`、`$16.792B` vs `$16.8B` 等 |
| reason 否定自身仍输出 | 13 | 14.4% | reason 写明 `no contradiction`、`cannot be flagged`、`statement is supported` 仍输出 |
| cascading / 派生重复 | 8 | 8.9% | 同一 EPS 错误被拆成 actual、surprise、全年 sum、叙事后果 |
| 价格时点混用 | 7 | 7.8% | 用全年端点、拆股后价格、52-week range 反驳局部时点 |
| 反向错抓或方向不清 | 3 | 3.3% | event/guidance/rating action 的正确方向没有回到原始 source 确认 |

典型误报：

- `report_14`：GT 为 0，但输出 8 条 PG issue；其中多条 reason 自称不能判错，说明 final filter 失效。
- `report_16`：MRK 8 条预测均未命中 GT，主要围绕产品收入数量级、guidance 和 unsupported 候选泛审计。
- `report_19`：MS 客户资产没抓到，却输出发布日期、EPS 序列、资产、VaR、收入舍入等 6 条。
- `report_20`：抓到 market cap，但另外 7 条集中在 segment 数量级、drug name、consensus 和 adjusted EPS。

## 8. train_gt 错误来源分布

按“需要用哪类数据源才能验证 GT 错误”归类：

| GT 验证来源类型 | GT 数 | 占比 | 典型错误 | 涉及 report |
|---|---:|---:|---|---|
| `earnings.json` / EPS 结构化数据 | 5 | 17.9% | actual/estimate/surprise、beat/miss 方向、QoQ EPS 方向 | 01, 03, 07, 10, 12 |
| filing catalog / SEC filing / event date | 4 | 14.3% | 10-K filing date、8-K 日期、股东会日期 | 02, 09, 10, 12 |
| `financials_reported.json` / 财务报表结构化数据 | 2 | 7.1% | fiscal quarter endDate、9M net income | 04, 08 |
| `peers.json` | 1 | 3.6% | peer list 多加/错加 ticker | 05 |
| `prices/*.csv` / 市场价格数据 | 2 | 7.1% | 年收益率计算、开盘价数字篡改 | 06, 16 |
| news/social/regulatory/analyst narrative | 14 | 50.0% | 新闻数字篡改、媒体归因、分析师动作、召回数量、市值、客户资产、产品区域增长 | 09, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20 |

## 9. review (20) 按数据源类型的表现

### 9.1 对 GT 来源类型的召回表现

| GT 验证来源类型 | GT 数 | TP | FN | Recall | 评估 |
|---|---:|---:|---:|---:|---|
| `earnings.json` / EPS 结构化数据 | 5 | 5 | 0 | 100.0% | 结构化 EPS 仍是最稳路径 |
| filing catalog / SEC filing / event date | 4 | 2 | 2 | 50.0% | 10-K 和 NEE 8-K 日期能抓；TSLA 股东会日期仍漏 |
| `financials_reported.json` / 财务报表结构化数据 | 2 | 1 | 1 | 50.0% | WMT 抓到；MS 表格行仍误抓 WFC |
| `peers.json` | 1 | 1 | 0 | 100.0% | PFE peer list 抓准 |
| `prices/*.csv` / 市场价格数据 | 2 | 1 | 1 | 50.0% | UNH return 抓到；MRK open 漏 |
| news/social/regulatory/analyst narrative | 14 | 3 | 11 | 21.4% | NEE CEO、NKE JPM、ABBV market cap 抓到；但 NKE 为边界命中 |
| **合计** | **28** | **13** | **15** | **46.4%** | recall 提升主要来自 narrative，但 precision 代价很高 |

exact-reason 口径下，news/social/regulatory/analyst narrative 为 TP=2、FN=12、Recall=14.3%，因为 `report_17` 的 JPM action reason 不完整。

### 9.2 按数据源类型看 FP 分布

下面是对 77 个语义口径 FP 的主要来源/审查路径归类，互斥归因。

| FP 主要来源/审查路径 | FP 数 | 占 FP | 典型问题 |
|---|---:|---:|---|
| `financials_reported` / 10-Q 财务表 / metric 口径 | 27 | 35.1% | revenue/net income/period/YTD/single-quarter/segment 口径混淆 |
| news/social/analyst narrative | 25 | 32.5% | 抓到非 GT 的新闻、业务线、guidance、drug name 或 source 解释 |
| `earnings.json` / EPS | 10 | 13.0% | EPS 重复拆分、estimate/actual 口径混用、叙事派生重复 |
| `prices/*.csv` / market data | 8 | 10.4% | 全年端点、拆股时点、52-week range、open/close 混用 |
| filing/event/guidance catalog | 5 | 6.5% | 备案日/发布日、event date、guidance 更新的 unsupported 推断 |
| other / mixed arithmetic | 2 | 2.6% | 多来源混合推断，缺少单一明确反证 |
| **合计** | **77** | **100.0%** | FP 反弹主要来自 financials 与 narrative 泛审计 |

## 10. 来源类型层面的结论

1. **review (20) 是“放宽召回”而不是“提高判别”。**  
   TP 回到 13，但 Pred 也回到 90，FP 回到 77，整体更像 `review (17)` 的高噪声版本。

2. **结构化 EPS 仍然可靠。**  
   `earnings.json` 类 GT 5/5 命中，但 `report_01/03` 仍会把同一个事实链拆成多条。

3. **narrative 召回有恢复，但还不稳。**  
   NEE CEO `12.4%` 这次抓得比 `review (17)` 更准；NKE JPM downgrade 仍是语义命中、exact-reason 不稳。

4. **final filter 存在明显漏网。**  
   `report_14/16/18` 中多条 reason 明确写了 no contradiction、supported、cannot be flagged，但最终仍输出，直接损害 precision。

5. **financials 和单位数量级仍是 FP 最大来源。**  
   `report_16/20` 特别明显：产品/分部收入的“亿美元 / billion / million”转换和 metric namespace 没有被严格约束。

6. **事件日期和信源归因仍是主要漏报区。**  
   TSLA 股东会、XLU 日期、MRK WSJ/Fierce、NKE Bloomberg/CNBC 这些需要回到原始 news/filing source 的错误仍大多漏掉。

## 11. 建议

| 优先级 | 改法 |
|---|---|
| P0 | final filter 必须删除 reason 中含 `no contradiction`、`cannot be flagged`、`supported`、`absence of support is not contradiction` 的候选 |
| P0 | 最终输出只允许 `verdict=contradict` 且必须给出明确 correct value/source；unsupported/ambiguous/match 不得进入 final |
| P0 | 对 narrative 命中做 correct-value/action 校验：NKE 这类 rating action 必须写出正确方向 `Neutral -> Overweight` 才算强命中 |
| P1 | event-date router 回到原始 filing/news source 判定日期，不能用报告内自相矛盾句子或“无来源支持”替代反证 |
| P1 | financials 校验加 metric namespace：GAAP/core/adjusted、quarter/YTD、segment/company、reported/non-GAAP、period endDate 必须一致 |
| P1 | 数量级判断先做单位规范化，特别是中文“亿”、英文 billion、million、segment/product revenue |
| P1 | 对同一 quote/correct source 做 cascading 去重：同一 GT 错误最多输出一条，派生叙事不再重复报 |
| P2 | 对 GT=0 或低置信报告设置 FP guardrail：如果没有明确反证，整篇应允许输出空 issues |
