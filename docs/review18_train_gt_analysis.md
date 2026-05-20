# review(18) vs review_train_gt 审查分析

## 1. 统计口径

对比文件：

- 预测输出：`review(18).jsonl`
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
| Pred issue 数 | 56 |
| TP | 10 |
| FP | 46 |
| FN | 18 |
| Precision | 17.9% |
| Recall | 35.7% |
| F1 | 23.8% |

`review(18)` 的主要变化是预测条数大幅下降。相比 `review (17)`，precision 提高，但 recall 降低。

## 3. 逐题对齐表

| report | GT | Pred | TP | FP | FN | 备注 |
|---|---:|---:|---:|---:|---:|---|
| report_01 | 1 | 2 | 1 | 1 | 0 | META Q4 EPS 抓到；仍重复 1 条 |
| report_02 | 1 | 3 | 1 | 2 | 0 | TSLA 10-K 日期抓到；另多报净利和重复 filing date |
| report_03 | 1 | 1 | 1 | 0 | 0 | COST miss/beat 抓准 |
| report_04 | 1 | 4 | 1 | 3 | 0 | WMT 财季截止日抓到；多报收入、净利、period 标签 |
| report_05 | 1 | 3 | 1 | 2 | 0 | PFE peer NVS 抓到；多报收入/Q3 standalone |
| report_06 | 1 | 2 | 1 | 1 | 0 | UNH 年收益率抓到；多报净利 |
| report_07 | 1 | 1 | 1 | 0 | 0 | GS Q4 estimate/surprise 抓准 |
| report_08 | 1 | 1 | 0 | 1 | 1 | GT 是 MS 净利；预测误抓 WFC 行 |
| report_09 | 2 | 2 | 1 | 1 | 1 | NEE 8-K 日期抓到；漏 CEO 12.4% -> 9.4% |
| report_10 | 3 | 3 | 0 | 3 | 3 | TSLA Q3 EPS 方向没直接抓到；股东会日期反向错抓；漏召回数 |
| report_11 | 2 | 1 | 0 | 1 | 2 | NEE dividend CAGR、XLU 日期均漏 |
| report_12 | 3 | 2 | 1 | 1 | 2 | TSLA QoQ EPS 方向抓到；漏一年涨幅和股东会日期 |
| report_13 | 1 | 6 | 0 | 6 | 1 | Netflix `The Electric State` 预算漏；多报 EPS/净利/股价/舍入 |
| report_14 | 0 | 3 | 0 | 3 | 0 | GT 无错；预测 3 条 PG 误报 |
| report_15 | 1 | 4 | 0 | 4 | 1 | GS M&A lead 950 vs 850 漏；多报 credit loss/净利 |
| report_16 | 2 | 7 | 0 | 7 | 2 | MRK 开盘价、WSJ/Fierce Pharma 信源均漏 |
| report_17 | 3 | 1 | 0 | 1 | 3 | NKE 三个 GT 全漏；只报价格 |
| report_18 | 1 | 3 | 0 | 3 | 1 | LLY Mounjaro 日本 +44% 漏 |
| report_19 | 1 | 3 | 0 | 3 | 1 | MS 客户资产 $7.49T 漏 |
| report_20 | 1 | 4 | 1 | 3 | 0 | ABBV market cap 抓到；多报价格/Skyrizi+Rinvoq/guidance |

## 4. 与前两版的变化

| 版本 | Pred | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| review (15) | 84 | 11 | 73 | 17 | 13.1% | 39.3% | 19.6% |
| review (17) 语义口径 | 90 | 13 | 77 | 15 | 14.4% | 46.4% | 22.0% |
| review(18) | 56 | 10 | 46 | 18 | 17.9% | 35.7% | 23.8% |

变化：

- Pred 从 90 降到 56，FP 明显减少。
- Precision 从 14.4% 提到 17.9%。
- Recall 从 46.4% 降到 35.7%。
- F1 小幅提升到 23.8%，主要靠 FP 控制，而不是召回变强。
- `review(18)` 删除了不少泛审计噪声，但也丢掉了 `review (17)` 中的 narrative 边界命中，例如 NEE 12.4%、NKE JPM downgrade。

## 5. 命中情况

### 5.1 稳定命中的类型

| 类型 | 命中 report | 说明 |
|---|---|---|
| EPS actual/estimate/surprise | 01, 03, 07, 12 | 结构化 EPS 仍是强项，但 `report_10` 的 Q3 EPS 方向这版没直接抓到 |
| filing date / fiscal period | 02, 04, 09 | TSLA 10-K、WMT fiscal Q3、NEE 8-K 日期能抓 |
| peer list | 05 | PFE peers 中 NVS 错误抓准 |
| price return arithmetic | 06 | UNH 年收益率错误抓到 |
| market cap narrative | 20 | ABBV market cap 抓到 |

### 5.2 退步项

| report | 退步点 |
|---|---|
| report_09 | `review (17)` 抓到 NEE 12.4%，`review(18)` 漏掉 |
| report_10 | Q3 EPS beat/miss 方向没有直接抓到；股东会日期还反向错抓 |
| report_17 | `review (17)` 语义上抓到 JPM downgrade，`review(18)` 完全漏 |

## 6. 漏报分析

严格口径下 FN=18，主要集中在以下类别：

| 漏报类型 | 数量 | 涉及 report | 说明 |
|---|---:|---|---|
| news/social 细节数字篡改 | 7 | 09, 10, 13, 15, 18, 19 | NEE 12.4%、NHTSA 召回数、电影预算、M&A lead、Mounjaro 区域增长、客户资产等 |
| 事件日期篡改 | 5 | 10, 11, 12 | TSLA 股东会、XLU 创新高等 |
| 信源张冠李戴 | 4 | 16, 17 | WSJ/Fierce Pharma、Bloomberg/CNBC |
| analyst estimate / action 细节 | 2 | 17 | NKE JPM EPS estimate 和 rating action 全漏 |

典型漏报：

- `report_10`：三个 GT 全漏，其中股东会日期还被反向判错。
- `report_13`：漏掉 `The Electric State` 预算 $420M vs $320M。
- `report_16`：漏掉 MRK 开盘价 $110.28 vs $100.28，以及 WSJ/Fierce Pharma 信源错配。
- `report_17`：NKE 三个 GT 全漏。
- `report_19`：漏掉 MS Wealth Management 总客户资产 $7.49T vs $6.49T。

## 7. 误报分析

56 个预测 issue 中，严格 FP=46。主要误报类型如下，类别之间有重叠。

| 误报类型 | 估计数量 | 占 Pred | 典型表现 |
|---|---:|---:|---|
| 指标口径混淆 | 30 | 53.6% | revenue/net income/EPS/Non-GAAP/segment 口径混用 |
| 单位/数量级问题泛化 | 23 | 41.1% | 有真实数量级错误，也有中文“亿”和近似金额误报 |
| 先承认正确再报错 | 20 | 35.7% | 硬过滤后仍有部分 reason 先承认近似/可接受再输出 |
| 把缺少证据当错误 | 10 | 17.9% | `no support`、`cannot verify` 类仍存在 |
| 舍入/近似误判 | 9 | 16.1% | 小数、约数、百分比近似仍被报错 |
| reason 否定自身仍输出 | 4 | 7.1% | reason 承认无法验证或没有明确反证 |
| 用全年端点推断局部走势 | 4 | 7.1% | 价格类局部走势推断 |
| 开盘/收盘混用 | 2 | 3.6% | 比上一版减少，但未完全消失 |

观察：

- 硬过滤起效，FP 总量下降明显。
- 但剩余 FP 更集中在 metric 口径和数量级判断。
- `report_14` 从 `review (17)` 的 8 条降到 3 条，是 precision 改善的重要来源。

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

## 9. review(18) 按数据源类型的表现

### 9.1 对 GT 来源类型的召回表现

| GT 验证来源类型 | GT 数 | TP | FN | Recall | 评估 |
|---|---:|---:|---:|---:|---|
| `earnings.json` / EPS 结构化数据 | 5 | 4 | 1 | 80.0% | 仍强，但漏了 TSLA Q3 beat/miss 方向 |
| filing catalog / SEC filing / event date | 4 | 2 | 2 | 50.0% | 10-K 和 NEE 8-K 日期能抓；股东会日期仍弱 |
| `financials_reported.json` / 财务报表结构化数据 | 2 | 1 | 1 | 50.0% | WMT 抓到；MS 表格行仍误抓 WFC |
| `peers.json` | 1 | 1 | 0 | 100.0% | PFE peer list 抓准 |
| `prices/*.csv` / 市场价格数据 | 2 | 1 | 1 | 50.0% | UNH return 抓到；MRK open 漏 |
| news/social/regulatory/analyst narrative | 14 | 1 | 13 | 7.1% | 只抓到 ABBV market cap，narrative recall 退回低位 |
| **合计** | **28** | **10** | **18** | **35.7%** | 主要短板仍是 narrative 类 |

### 9.2 按数据源类型看 FP 分布

下面是对 46 个 FP 的主要来源/审查路径归类，互斥归因。

| FP 主要来源/审查路径 | FP 数 | 占 FP | 典型问题 |
|---|---:|---:|---|
| `financials_reported` / 10-Q 财务表 / metric 口径 | 18 | 39.1% | revenue/net income/EPS/segment 口径混淆 |
| news/social/analyst narrative | 11 | 23.9% | 抓到非 GT 新闻/业务线问题，或来源不够精确 |
| `prices/*.csv` / market data | 6 | 13.0% | 全年端点推断局部走势、open/close 问题 |
| `earnings.json` / EPS | 6 | 13.0% | EPS 重复拆分、估计值/actual 口径混用 |
| filing/event/guidance catalog | 3 | 6.5% | event date/guidance unsupported 推断 |
| other / mixed arithmetic | 2 | 4.3% | 多来源混合推断 |
| **合计** | **46** | **100.0%** | FP 数下降，但 financials 口径仍是最大来源 |

## 10. 来源类型层面的结论

1. **硬过滤有效，但主要是控 FP。**  
   Pred 从 90 降到 56，FP 从 77 降到 46，precision 提升明显。

2. **召回受损，尤其是 narrative。**  
   `review(18)` 的 news/social/regulatory/analyst narrative TP 只有 1/14，只保留了 ABBV market cap。

3. **结构化 EPS 也略退步。**  
   `report_10` 的 TSLA Q3 EPS beat/miss 方向没有直接命中，导致 earnings recall 从 100% 降到 80%。

4. **remaining FP 更集中。**  
   剩余误报主要集中在 financials metric namespace 和单位/数量级判断，说明下一步应针对 metric consistency，而不是继续泛化硬过滤。

5. **股东会/事件日期仍需要专门处理。**  
   `report_10` 中预测把正确日期 `11 月 6 日` 当错，说明 event date 的证据选择和内部矛盾处理仍不稳。

## 11. 建议

| 优先级 | 改法 |
|---|---|
| P0 | 修复 event-date 方向性：如果 GT/来源显示 `11 月 6 日` 正确，不能因报告内另一处写 `11 月 16 日` 就反向判错 |
| P0 | 对 narrative claim 不要只依赖硬过滤；需要提升 recall，尤其是 NHTSA、Benzinga、CNBC/Bloomberg、Fierce Pharma/WSJ、JPM analyst action、Mounjaro regional growth、MS client assets |
| P1 | financials 校验加 metric namespace：GAAP/core/adjusted、quarter/YTD、segment/company、reported/non-GAAP |
| P1 | 数量级判断加中文单位规范化，避免把“亿/亿美元/billion”混用导致误报 |
| P1 | EPS 结构化路径恢复 TSLA Q3 beat/miss 方向检查，同时保持 cascading 去重 |
| P2 | 每篇 top1/top2 仍是可选后处理，但不要再进一步压缩，否则 recall 会继续下降 |

