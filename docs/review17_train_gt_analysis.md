# review (17) vs review_train_gt 审查分析

## 1. 统计口径

对比文件：

- 预测输出：`review (17).jsonl`
- 标准答案：`reference_submission/problem/review_train_gt.jsonl`

对齐口径沿用 `review (15)` 分析：

- 同一个 GT 错误只算 1 个 TP；
- 同一错误被拆成多条，额外条目算 FP；
- 只说“没有证据支持”的候选，严格不计高置信 TP；
- 本文主表使用“语义命中口径”：quote 指向同一 GT 错误，且 reason 给出基本反证，即算 TP；
- 同时给出“exact-reason 口径”：如果 reason 的 correct value/source 明显偏离 GT，则不计 TP。

两个边界项：

- `report_09`：抓到了 NEE CEO quote 中的 `12.4%`，但 reason 给出的正确值是 `9.7%`，而 GT 是 `9.4%`。语义口径算 TP，exact-reason 口径不算。
- `report_17`：抓到了 JPMorgan `Overweight -> Neutral` downgrade 这条，但 reason 没有完整指出 GT 的正确反向动作 `Neutral -> Overweight`。语义口径算 TP，exact-reason 口径不算。
- `report_16`：抓到了 MRK 开盘价 quote，但 reason 明确说 verified facts 不提供 open，无法确认；不计 TP。

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

如果 `report_09` 的 `12.4%` 和 `report_17` 的 JPM downgrade 两条因为 correct value/source 不够准确而不计 TP：

| 指标 | 数值 |
|---|---:|
| TP | 11 |
| FP | 79 |
| FN | 17 |
| Precision | 12.2% |
| Recall | 39.3% |
| F1 | 18.6% |

后续分析主用语义命中口径，但会标注边界项。

## 3. 逐题对齐表

| report | GT | Pred | TP | FP | FN | 备注 |
|---|---:|---:|---:|---:|---:|---|
| report_01 | 1 | 4 | 1 | 3 | 0 | META Q4 EPS 抓到；拆成 3 条重复链路，另多报开盘/收盘价 |
| report_02 | 1 | 2 | 1 | 1 | 0 | TSLA 10-K 日期抓到；重复输出 |
| report_03 | 1 | 2 | 1 | 1 | 0 | COST miss/beat 抓到；叙事后果重复 |
| report_04 | 1 | 5 | 1 | 4 | 0 | WMT 财季截止日抓到；多报收入、净利、period 标签 |
| report_05 | 1 | 2 | 1 | 1 | 0 | PFE peer NVS 抓到；多报净利 |
| report_06 | 1 | 2 | 1 | 1 | 0 | UNH 年收益率抓到；多报净利 |
| report_07 | 1 | 1 | 1 | 0 | 0 | GS Q4 estimate/surprise 抓准 |
| report_08 | 1 | 1 | 0 | 1 | 1 | GT 是 MS 净利；预测误抓 WFC 行 |
| report_09 | 2 | 7 | 2 | 5 | 0 | NEE 8-K 日期和 12.4% quote 都抓到；但 12.4% 的 correct value 写成 9.7% 而非 GT 的 9.4% |
| report_10 | 3 | 4 | 1 | 3 | 2 | TSLA Q3 EPS 方向抓到；漏召回数和股东会日期 |
| report_11 | 2 | 3 | 0 | 3 | 2 | NEE dividend CAGR、XLU 日期均漏 |
| report_12 | 3 | 2 | 1 | 1 | 2 | TSLA QoQ 方向抓到；漏一年涨幅和股东会日期 |
| report_13 | 1 | 8 | 0 | 8 | 1 | Netflix `The Electric State` 预算漏；多报 filing date/股价/EPS/净利/指引 |
| report_14 | 0 | 8 | 0 | 8 | 0 | GT 无错；预测 8 条 PG 误报 |
| report_15 | 1 | 7 | 0 | 7 | 1 | GS M&A lead 950 vs 850 漏；多报 AUS/CET1/ROE/净利/股价 |
| report_16 | 2 | 7 | 0 | 7 | 2 | MRK 开盘价 quote 抓到但 reason 明确无法确认；信源错配漏 |
| report_17 | 3 | 4 | 1 | 3 | 2 | NKE JPM downgrade 抓到；漏 EPS estimate $1.52 和 Bloomberg/CNBC 信源错配 |
| report_18 | 1 | 7 | 0 | 7 | 1 | LLY Mounjaro 日本 +44% 漏；多报毛利率/Non-GAAP/税率/利润率 |
| report_19 | 1 | 6 | 0 | 6 | 1 | MS 客户资产 $7.49T 漏 |
| report_20 | 1 | 8 | 1 | 7 | 0 | ABBV market cap 抓到；多报业务线数量级/adjusted EPS |

## 4. 与 review (15) 的变化

| 版本 | Pred | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| review (15) | 84 | 11 | 73 | 17 | 13.1% | 39.3% | 19.6% |
| review (17) 语义口径 | 90 | 13 | 77 | 15 | 14.4% | 46.4% | 22.0% |
| review (17) exact-reason 口径 | 90 | 11 | 79 | 17 | 12.2% | 39.3% | 18.6% |

变化：

- 语义口径下，`review (17)` 比 `review (15)` 多 2 个 TP：`report_09` 的 NEE 12.4% 和 `report_17` 的 NKE JPM downgrade。
- 同时 Pred 从 84 增到 90，FP 从 73 增到 77，噪声也变多。
- 如果要求 correct value/source 完全对齐，新增的两个 TP 都不稳定，整体反而略差于 `review (15)`。
- `report_16` 似乎抽到了 MRK 开盘价 GT quote，但 reason 自我否定，因此不能算有效命中。

## 5. 命中情况

### 5.1 稳定命中的类型

| 类型 | 命中 report | 说明 |
|---|---|---|
| EPS actual/estimate/surprise | 01, 03, 07, 10, 12 | 结构化 `earnings.json` 仍是最强项 |
| filing date / fiscal period | 02, 04, 09 | 10-K 日期、WMT fiscal Q3 结束日、NEE 8-K 日期能抓 |
| peer list | 05 | PFE peers.json 中 NVS 错误抓准 |
| price return arithmetic | 06 | UNH 年收益率错误抓到 |
| news/analyst narrative | 09, 17, 20 | NEE 12.4%、NKE JPM downgrade、ABBV market cap 有进步，但前两条 reason 不够精确 |

### 5.2 仍然重复输出

`report_01` 仍把同一个 META Q4 EPS 错误拆成：

1. EPS actual 错；
2. full-year EPS sum 错；
3. 同一段落组合错。

GT 只算一个 cascading issue。这类重复继续拉低 precision。

## 6. 漏报分析

语义口径下 FN=15，主要集中在以下类别：

| 漏报类型 | 数量 | 涉及 report | 说明 |
|---|---:|---|---|
| news/social 细节数字篡改 | 6 | 10, 13, 15, 18, 19 | NHTSA 召回数、电影预算、M&A lead、Mounjaro 区域增长、客户资产等 |
| 事件日期篡改 | 4 | 10, 11, 12 | 股东会日期、XLU 创新高日期 |
| 信源张冠李戴 | 3 | 16, 17 | WSJ/Fierce Pharma、Bloomberg/CNBC 等 |
| analyst estimate / action 细节 | 2 | 17 | NKE JPM EPS estimate $1.52 漏；downgrade 只算部分命中 |

典型漏报：

- `report_10`：漏掉 NHTSA 召回数量 15,936 vs 12,936，以及股东会 11 月 16 日 vs 11 月 6 日。
- `report_11`：NEE dividend CAGR 15% vs 10%、XLU 8 月 22 日 vs 7 月 22 日均漏。
- `report_13`：漏掉 `The Electric State` 预算 $420M vs $320M。
- `report_16`：开盘价 quote 抽到了，但 reason 说无法确认；WSJ/Fierce Pharma 信源错配仍漏。
- `report_19`：漏掉 MS Wealth Management 总客户资产 $7.49T vs $6.49T。

## 7. 误报分析

90 个预测 issue 中，语义口径 FP=77。主要误报类型如下，类别之间有重叠。

| 误报类型 | 估计数量 | 占 Pred | 典型表现 |
|---|---:|---:|---|
| 指标口径混淆 | 46 | 51.1% | GAAP/Core/Adjusted、reported/non-GAAP、revenue/net income 混用 |
| 先承认正确再报错 | 33 | 36.7% | reason 中出现 `matches/correct/consistent/acceptable`，但仍输出 |
| 单位/数量级问题泛化 | 33 | 36.7% | 有真实数量级错误，也有中文“亿”、近似金额、业务线口径误报 |
| 把缺少证据当错误 | 30 | 33.3% | `no source supports`、`not provided` 被当成 contradiction |
| 舍入/近似误判 | 26 | 28.9% | 14.4% vs 14.5%、约数、四舍五入被报错 |
| reason 否定自身仍输出 | 12 | 13.3% | reason 中承认无法确认或无直接反证，但仍输出 |
| 用全年端点推断局部走势 | 8 | 8.9% | 用 1/2 和 12/31 close 反驳财报日、盘中、YTD |
| 开盘/收盘混用 | 7 | 7.8% | 用 close 去反驳 open，或 price 字段混用 |

典型误报：

- `report_14`：GT 为 0，但预测 8 条 PG issue，是最典型的过度审计。
- `report_15`：GT 是 GS M&A lead 金额篡改，但预测集中在 AUS、CET1、ROE、净利、股价。
- `report_18`：GT 是 LLY Mounjaro 日本 +44%，预测却输出毛利率、Non-GAAP EPS、税率、营业利润率等 7 条。
- `report_20`：抓到 market cap，但另外 7 条业务线数量级和 adjusted EPS 问题不在 GT 范围内。

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

## 9. review (17) 按数据源类型的表现

### 9.1 对 GT 来源类型的召回表现

| GT 验证来源类型 | GT 数 | TP | FN | Recall | 评估 |
|---|---:|---:|---:|---:|---|
| `earnings.json` / EPS 结构化数据 | 5 | 5 | 0 | 100.0% | 仍然最稳定 |
| filing catalog / SEC filing / event date | 4 | 2 | 2 | 50.0% | 10-K 和 NEE 日期能抓；TSLA 股东会日期仍漏 |
| `financials_reported.json` / 财务报表结构化数据 | 2 | 1 | 1 | 50.0% | WMT 抓到；MS 表格行误抓 WFC |
| `peers.json` | 1 | 1 | 0 | 100.0% | PFE peer list 抓准 |
| `prices/*.csv` / 市场价格数据 | 2 | 1 | 1 | 50.0% | UNH return 抓到；MRK open quote 抓到但 reason 无效 |
| news/social/regulatory/analyst narrative | 14 | 3 | 11 | 21.4% | 比 review (15) 的 1/14 有提升，但其中 2 条是边界命中 |
| **合计** | **28** | **13** | **15** | **46.4%** | recall 改善主要来自 narrative 类 |

exact-reason 口径下，news/social/regulatory/analyst narrative 为 TP=1、FN=13、Recall=7.1%，即退回到 `review (15)` 水平。说明新增的 narrative 命中还不够扎实。

### 9.2 按数据源类型看 FP 分布

下面是对 77 个语义口径 FP 的主要来源/审查路径归类，互斥归因。

| FP 主要来源/审查路径 | FP 数 | 占 FP | 典型问题 |
|---|---:|---:|---|
| `financials_reported` / 10-Q 财务表 / metric 口径 | 25 | 32.5% | revenue/net income/core EPS/FCF productivity/ROE/segment 口径混淆 |
| news/social/analyst narrative | 23 | 29.9% | 抓到非 GT 的新闻或业务线问题，或 correct value 不精确 |
| `prices/*.csv` / market data | 12 | 15.6% | 用全年首尾价反驳财报日、盘中价、YTD；open/close 混用 |
| `earnings.json` / EPS | 9 | 11.7% | EPS downstream 重复拆分，或将正确表述误报 |
| filing/event/guidance catalog | 6 | 7.8% | filing date、event date、guidance 更新的 unsupported 推断 |
| other / mixed arithmetic | 2 | 2.6% | 多来源混合推断，缺少单一明确反证 |
| **合计** | **77** | **100.0%** | FP 仍主要来自泛审计和口径混淆 |

## 10. 来源类型层面的结论

1. **结构化 earnings 仍然是强项。**  
   `earnings.json` 类 GT 5/5 命中，适合保留现有结构化校验逻辑，但要做 cascading 去重。

2. **narrative 召回有进步，但证据质量不稳定。**  
   `review (17)` 抓到了 NEE 12.4% 和 NKE JPM downgrade，但 correct value/source 不完全对齐。说明 news_merged/retrieval 有开始发挥作用，但 claim-to-source alignment 还不稳。

3. **price 类没有实质改善。**  
   MRK open quote 抽到了，但 reason 说无法确认，说明价格字段层级没有用好：open/close/high/low 需要分别校验。

4. **financials 类 FP 更严重。**  
   `review (17)` 的指标口径混淆计数比 `review (15)` 更高，说明模型更频繁转向财务主表泛审计。

5. **GT=0 的 report_14 仍然失败。**  
   对无错报告输出 8 条 issue，说明 final filter 对 unsupported、近似、口径歧义的控制不足。

## 11. 建议

| 优先级 | 改法 |
|---|---|
| P0 | 对 narrative 命中增加 correct-value 校验：必须输出正确值和来源，不只是说原文不支持 |
| P0 | 对 reason 自我否定或无法确认的 issue 直接删除，例如 `report_16` open price |
| P0 | 每篇最多输出 1-2 条，第二条必须有强反证；否则 `report_14/18/20` 会持续拉低 precision |
| P1 | news/social router 增加字段化抽取：媒体名、机构名、评级动作、target price、EPS estimate、召回数量、market cap、client assets、产品区域增长 |
| P1 | price 校验区分 open/close/high/low；无同日字段时不得用全年首尾点反推 |
| P1 | financials 校验强制 metric namespace 一致：GAAP/core/adjusted、quarter/YTD、segment/company、reported/non-GAAP |
| P2 | EPS 结构化错误做 cascading 合并，避免同一事实链拆成多条 FP |

