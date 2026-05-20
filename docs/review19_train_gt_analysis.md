# review(19) vs review_train_gt 审查分析

## 1. 统计口径

对比文件：

- 预测输出：`review(19).jsonl`
- 标准答案：`reference_submission/problem/review_train_gt.jsonl`

对齐口径沿用前几版：

- 同一个 GT 错误只算 1 个 TP；
- 同一错误被拆成多条，额外条目算 FP；
- 只说“没有证据支持”的候选，严格不算 TP；
- 反向错抓不算 TP。例如 `report_10` 中 GT 是报告把股东会写成 `11 月 16 日`，正确值为 `11 月 6 日`；但预测反而说 `11 月 6 日` 错、`11 月 16 日` 对，因此不计 TP。

## 2. 总体结果

| 指标 | 数值 |
|---|---:|
| GT issue 数 | 28 |
| Pred issue 数 | 65 |
| TP | 11 |
| FP | 54 |
| FN | 17 |
| Precision | 16.9% |
| Recall | 39.3% |
| F1 | 23.7% |

`review(19)` 相比 `review(18)` 多输出 9 条，TP 从 10 回升到 11，但 FP 从 46 增加到 54。整体看，轻量 verdict 方案比上一版硬过滤更少杀伤 TP，但没有解决 narrative 类漏报，且误报数量有所反弹。

## 3. 逐题对齐表

| report | GT | Pred | TP | FP | FN | 备注 |
|---|---:|---:|---:|---:|---:|---|
| report_01 | 1 | 3 | 1 | 2 | 0 | META Q4 EPS 抓到；同一 EPS 错误仍拆成多条 |
| report_02 | 1 | 3 | 1 | 2 | 0 | TSLA 10-K 日期抓到；另多报九个月收入和重复 filing date |
| report_03 | 1 | 1 | 1 | 0 | 0 | COST miss/beat 抓准 |
| report_04 | 1 | 5 | 1 | 4 | 0 | WMT 财季截止日抓到；多报收入、净利、单季度推算和 period 标签 |
| report_05 | 1 | 3 | 1 | 2 | 0 | PFE peer NVS 抓到；多报九个月收入和 Q3 standalone |
| report_06 | 1 | 2 | 1 | 1 | 0 | UNH 年收益率抓到；多报净利 |
| report_07 | 1 | 1 | 1 | 0 | 0 | GS Q4 estimate/surprise 抓准 |
| report_08 | 1 | 1 | 0 | 1 | 1 | GT 是 MS 净利；预测误抓 WFC 行 |
| report_09 | 2 | 2 | 1 | 1 | 1 | NEE 8-K 日期抓到；漏 CEO 12.4% -> 9.4% |
| report_10 | 3 | 4 | 1 | 3 | 2 | TSLA Q3 EPS beat/miss 方向抓到；漏召回数和股东会日期，且股东会被反向错抓 |
| report_11 | 2 | 1 | 0 | 1 | 2 | NEE dividend CAGR、XLU 日期均漏；只报 guidance 更新 |
| report_12 | 3 | 2 | 1 | 1 | 2 | TSLA QoQ EPS 方向抓到；漏一年涨幅和股东会日期 |
| report_13 | 1 | 8 | 0 | 8 | 1 | Netflix `The Electric State` 预算漏；多报 EPS、价格、净利、guidance |
| report_14 | 0 | 3 | 0 | 3 | 0 | GT 无错；预测 3 条 PG 误报 |
| report_15 | 1 | 5 | 0 | 5 | 1 | GS M&A lead 950 vs 850 漏；多报 EPS、credit loss、净利和增长率 |
| report_16 | 2 | 8 | 0 | 8 | 2 | MRK 开盘价、WSJ/Fierce Pharma 信源均漏；多报 Q2/Q3、EPS、收入、Keytruda 等 |
| report_17 | 3 | 2 | 0 | 2 | 3 | NKE 三个 GT 全漏；只报价格和收入 |
| report_18 | 1 | 2 | 0 | 2 | 1 | LLY Mounjaro 日本 +44% 漏；多报 EPS/Non-GAAP 净利 |
| report_19 | 1 | 1 | 0 | 1 | 1 | MS 客户资产 $7.49T 漏；误报备案/发布日 |
| report_20 | 1 | 8 | 1 | 7 | 0 | ABBV market cap 抓到；多报价格、guidance、Skyrizi/Rinvoq 和 consensus |

## 4. 与前几版的变化

| 版本 | Pred | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| review (15) | 84 | 11 | 73 | 17 | 13.1% | 39.3% | 19.6% |
| review (17) 语义口径 | 90 | 13 | 77 | 15 | 14.4% | 46.4% | 22.0% |
| review(18) | 56 | 10 | 46 | 18 | 17.9% | 35.7% | 23.8% |
| review(19) | 65 | 11 | 54 | 17 | 16.9% | 39.3% | 23.7% |

变化：

- 相比 `review(18)`，`review(19)` 恢复了 `report_10` 的 TSLA Q3 EPS beat/miss 方向命中，TP +1。
- Pred 从 56 增到 65，FP 从 46 增到 54，precision 从 17.9% 降到 16.9%。
- Recall 从 35.7% 回升到 39.3%，基本回到 `review(15)` 严格口径水平。
- F1 为 23.7%，和 `review(18)` 的 23.8% 基本持平；收益来自少杀 TP，代价是 FP 反弹。
- 相比 `review(17)`，`review(19)` 仍少 2 个 TP，主要缺口是 NEE 12.4% 和 NKE JPM downgrade 这类 narrative 边界命中。

## 5. 命中情况

### 5.1 稳定命中的类型

| 类型 | 命中 report | 说明 |
|---|---|---|
| EPS actual/estimate/surprise | 01, 03, 07, 10, 12 | 结构化 EPS 又回到 5/5；`report_10` Q3 beat/miss 方向恢复 |
| filing date / fiscal period | 02, 04, 09 | TSLA 10-K、WMT fiscal Q3、NEE 8-K 日期能抓 |
| peer list | 05 | PFE peers 中 NVS 错误抓准 |
| price return arithmetic | 06 | UNH 年收益率错误抓到 |
| market cap narrative | 20 | ABBV market cap 抓到 |

### 5.2 仍未改善的点

| report | 问题 |
|---|---|
| report_09 | NEE 12.4% quote 在 `review(17)` 曾有语义命中，`review(19)` 仍漏 |
| report_10 | Q3 EPS 抓到，但召回数和股东会日期仍漏；股东会还出现反向错抓 |
| report_13 | `The Electric State` $420M vs $320M 漏，预测集中在 NFLX EPS/价格/净利 |
| report_16 | MRK open price 和 WSJ/Fierce Pharma source attribution 全漏 |
| report_17 | NKE 三个 GT 全漏，包括 JPM estimate、rating action、Bloomberg/CNBC source attribution |
| report_19 | MS Wealth Management 总客户资产 $7.49T vs $6.49T 仍漏 |

## 6. 漏报分析

严格口径下 FN=17，主要集中在以下类别：

| 漏报类型 | 数量 | 涉及 report | 说明 |
|---|---:|---|---|
| news/social 细节数字篡改 | 7 | 09, 10, 13, 15, 18, 19 | NEE 12.4%、NHTSA 召回数、电影预算、M&A lead、Mounjaro 区域增长、客户资产等 |
| 事件日期篡改 | 4 | 10, 11, 12 | TSLA 股东会、XLU 创新高等 |
| 信源张冠李戴 | 4 | 16, 17 | WSJ/Fierce Pharma、Bloomberg/CNBC |
| analyst estimate / action 细节 | 2 | 17 | NKE JPM EPS estimate 和 rating action 全漏 |

典型漏报：

- `report_09`：CEO 原话调整后 EPS 同比增长应为 9.4%，报告写成 12.4%；预测只抓到 8-K 日期。
- `report_10`：漏掉 NHTSA 召回数量 15,936 vs 12,936，以及股东会 `11 月 16 日` vs `11 月 6 日`。
- `report_13`：漏掉 `The Electric State` 预算 $420M vs $320M。
- `report_16`：漏掉 MRK 开盘价 $110.28 vs $100.28，以及裁员报道媒体 WSJ vs Fierce Pharma。
- `report_17`：JPMorgan EPS estimate $1.52 vs $1.32、评级动作反转、Bloomberg/CNBC 信源错配全部漏掉。
- `report_19`：漏掉 MS Wealth Management 总客户资产 $7.49T vs $6.49T。

## 7. 误报分析

65 个预测 issue 中，严格 FP=54。主要误报类型如下，类别之间有重叠。

| 误报类型 | 估计数量 | 占 Pred | 典型表现 |
|---|---:|---:|---|
| 指标口径混淆 | 34 | 52.3% | revenue/net income/EPS/Non-GAAP/segment/period 口径混用 |
| 单位/数量级问题泛化 | 25 | 38.5% | 真实数量级错误和中文“亿/亿美元/billion”混杂；也会把近似数误报 |
| 舍入/近似误判 | 18 | 27.7% | `$69.926B` vs `$69.93B`、`$15.806B` vs `158.10 亿` 等 |
| 把缺少证据当错误 | 12 | 18.5% | `no source supports`、`not provided`、`absence` 类仍会进入最终输出 |
| 先承认正确/近似再报错 | 11 | 16.9% | reason 中承认 rounding 或局部一致，但最终仍输出 |
| 反向错抓 | 2 | 3.1% | `report_10` 股东会日期、部分 guidance 方向 |
| 开盘/收盘或时点混用 | 2 | 3.1% | 价格字段、财报日、全年端点混用 |

观察：

- 轻量 verdict 没有像硬过滤那样大量压低 Pred，因此 FP 数回升。
- 误报仍高度集中在 financials/earnings 口径，尤其是 period、GAAP/non-GAAP、quarter/YTD、公司级/分部级混用。
- `report_13`、`report_16`、`report_20` 的多条误报说明模型仍会在同一篇里沿着一个错误检索方向连续输出。
- 对 `no source supports` 的控制比 `review(17)` 好，但仍没有完全截断 unsupported-only 候选。

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

## 9. review(19) 按数据源类型的表现

### 9.1 对 GT 来源类型的召回表现

| GT 验证来源类型 | GT 数 | TP | FN | Recall | 评估 |
|---|---:|---:|---:|---:|---|
| `earnings.json` / EPS 结构化数据 | 5 | 5 | 0 | 100.0% | 结构化 EPS 恢复为满召回 |
| filing catalog / SEC filing / event date | 4 | 2 | 2 | 50.0% | 10-K 和 NEE 8-K 日期能抓；TSLA 股东会日期仍弱 |
| `financials_reported.json` / 财务报表结构化数据 | 2 | 1 | 1 | 50.0% | WMT 抓到；MS 表格行仍误抓 WFC |
| `peers.json` | 1 | 1 | 0 | 100.0% | PFE peer list 抓准 |
| `prices/*.csv` / 市场价格数据 | 2 | 1 | 1 | 50.0% | UNH return 抓到；MRK open 漏 |
| news/social/regulatory/analyst narrative | 14 | 1 | 13 | 7.1% | 只抓到 ABBV market cap，narrative recall 仍是最大短板 |
| **合计** | **28** | **11** | **17** | **39.3%** | TP 回升主要来自 EPS，不是 narrative |

### 9.2 按数据源类型看 FP 分布

下面是对 54 个 FP 的主要来源/审查路径归类，互斥归因。

| FP 主要来源/审查路径 | FP 数 | 占 FP | 典型问题 |
|---|---:|---:|---|
| `financials_reported` / 10-Q 财务表 / metric 口径 | 20 | 37.0% | revenue/net income/period/YTD/single-quarter 口径混淆 |
| news/social/analyst narrative | 15 | 27.8% | 抓到非 GT 的新闻、业务线、guidance 或 source 解释 |
| `earnings.json` / EPS | 9 | 16.7% | EPS 重复拆分、consensus/actual 口径泛化 |
| `prices/*.csv` / market data | 5 | 9.3% | 全年端点推断局部走势、交易日价格时点混用 |
| filing/event/guidance catalog | 4 | 7.4% | 备案日/发布日、event date、guidance 更新的 unsupported 推断 |
| other / mixed arithmetic | 1 | 1.9% | 多来源混合推断，缺少单一明确反证 |
| **合计** | **54** | **100.0%** | FP 反弹主要来自 financials 与 narrative/guidance |

## 10. 来源类型层面的结论

1. **轻量 verdict 方案比硬过滤更少杀 TP。**  
   `review(19)` 恢复了 `report_10` 的 TSLA Q3 EPS 方向命中，整体 TP 从 10 回到 11。

2. **但 FP 明显反弹。**  
   Pred 从 56 增到 65，FP 从 46 增到 54，说明只加 `verdict` 字段和硬规则还不够约束最终输出。

3. **结构化 EPS 是当前最稳路径。**  
   `earnings.json` 类 GT 5/5 命中，适合保留，但需要继续做 cascading 去重，避免 `report_01` 和 `report_10` 这类重复拆分。

4. **narrative 召回没有改善。**  
   news/social/regulatory/analyst narrative 仍只有 1/14，和 `review(18)` 一样只抓到 ABBV market cap。

5. **错误方向判断仍然不稳。**  
   `report_10` 股东会日期继续反向错抓，说明模型会把报告内互相矛盾的句子当“证据”，而不是回到原始 source 判断正确日期。

6. **financials FP 是 precision 的最大损耗源。**  
   54 个 FP 中约 20 个来自财务表/metric 口径，主要是 period、YTD、single-quarter、GAAP/non-GAAP、公司级/分部级混用。

## 11. 建议

| 优先级 | 改法 |
|---|---|
| P0 | 保留轻量 verdict，但最终输出前只允许 `verdict=contradict` 且 reason 必须给出明确 correct value/source；`unsupported/ambiguous/match` 全部不得进 final |
| P0 | 增加 event-date 方向性校验：报告内自相矛盾不能作为事实来源，必须回到 filing/news source 判断哪个日期正确 |
| P0 | narrative 检索单独强化：NHTSA、Benzinga、CNBC/Bloomberg、Fierce Pharma/WSJ、JPM analyst action、Mounjaro regional growth、MS client assets 这些 GT 类型需要专门 claim 检索 |
| P1 | financials 校验加 metric namespace：GAAP/core/adjusted、quarter/YTD、segment/company、reported/non-GAAP、period endDate 必须一致 |
| P1 | 数量级判断先做单位规范化，再判 contradiction；中文“亿”、英文 billion、十倍拆股/每股单位不能直接混判 |
| P1 | 对同一 quote/correct source 做 cascading 去重：同一 GT 错误最多输出一条，派生计算不再重复报 |
| P2 | 对每篇报告设置 FP guardrail：如果同一路径连续生成多个 financials/guidance 候选，要求二次确认是否真的对应原文 claim，而不是泛审计 |
