# review (15) vs review_train_gt 审查分析

## 1. 统计口径

对比文件：

- 预测输出：`review (15).jsonl`
- 标准答案：`reference_submission/problem/review_train_gt.jsonl`

对齐口径沿用上一版：

- 同一个 GT 错误只算 1 个 TP；
- 同一错误被拆成多条，额外条目算 FP；
- 只说“没有证据支持”的候选，严格口径不算 TP；
- `report_17` 的 JPM 降级条目属于弱命中：quote 对到了 GT，但 reason 没给出正确反证，只说缺少支持；严格统计不计 TP，另给弱口径参考。

## 2. 总体结果

| 指标 | 数值 |
|---|---:|
| GT issue 数 | 28 |
| Pred issue 数 | 84 |
| TP | 11 |
| FP | 73 |
| FN | 17 |
| Precision | 13.1% |
| Recall | 39.3% |
| F1 | 19.6% |

弱口径下，如果把 `report_17` 的 JPM 降级条目算作 TP：

| 指标 | 数值 |
|---|---:|
| TP | 12 |
| FP | 72 |
| FN | 16 |
| Precision | 14.3% |
| Recall | 42.9% |
| F1 | 21.4% |

和 `review(13)` 相比，`review (15)` 的预测条数从 88 降到 84，严格 TP 仍为 11，FP 从 77 降到 73，FN 仍为 17。整体略有改善，但主要问题没有变化：误报仍然过多，漏报仍集中在 news/social narrative 的局部篡改。

## 3. 逐题对齐表

| report | GT | Pred | TP | FP | FN | 备注 |
|---|---:|---:|---:|---:|---:|---|
| report_01 | 1 | 4 | 1 | 3 | 0 | META Q4 EPS 抓到；拆成 3 条重复链路，另多报开盘/收盘价 |
| report_02 | 1 | 2 | 1 | 1 | 0 | TSLA 10-K 日期抓到；重复输出 |
| report_03 | 1 | 2 | 1 | 1 | 0 | COST miss/beat 方向抓到；叙事后果重复 |
| report_04 | 1 | 5 | 1 | 4 | 0 | WMT 财季截止日抓到；多报收入、净利、period 标签 |
| report_05 | 1 | 2 | 1 | 1 | 0 | PFE peer NVS 抓到；多报净利舍入/同比 |
| report_06 | 1 | 2 | 1 | 1 | 0 | UNH 年收益率抓到；多报净利 |
| report_07 | 1 | 1 | 1 | 0 | 0 | GS Q4 estimate/surprise 抓准 |
| report_08 | 1 | 1 | 0 | 1 | 1 | GT 是 MS 净利；预测误抓 WFC 行 |
| report_09 | 2 | 7 | 1 | 6 | 1 | NEE 8-K 日期抓到；漏 CEO 12.4% -> 9.4%，且反把 9.4% 报错 |
| report_10 | 3 | 7 | 1 | 6 | 2 | TSLA Q3 EPS 方向抓到；漏召回数和股东会日期，多报 52 周区间/薪酬等 |
| report_11 | 2 | 1 | 0 | 1 | 2 | NEE dividend CAGR、XLU 日期均漏；只报了指引口径 |
| report_12 | 3 | 4 | 1 | 3 | 2 | TSLA QoQ 方向抓到；漏一年涨幅和股东会日期 |
| report_13 | 1 | 8 | 0 | 8 | 1 | Netflix `The Electric State` 预算漏；多报股价/EPS/FCF/净利 |
| report_14 | 0 | 4 | 0 | 4 | 0 | GT 无错；预测 4 条 PG 误报 |
| report_15 | 1 | 7 | 0 | 7 | 1 | GS M&A lead 950 vs 850 漏；多报 CET1/净利/股息/股价 |
| report_16 | 2 | 4 | 0 | 4 | 2 | MRK 开盘价、WSJ/Fierce Pharma 信源均漏 |
| report_17 | 3 | 7 | 0 | 7 | 3 | NKE 三个 GT 严格口径均漏；JPM 降级条目为弱命中但 reason 缺正确反证 |
| report_18 | 1 | 2 | 0 | 2 | 1 | LLY Mounjaro 日本 +44% 漏 |
| report_19 | 1 | 6 | 0 | 6 | 1 | MS 客户资产 $7.49T 漏 |
| report_20 | 1 | 8 | 1 | 7 | 0 | ABBV market cap 抓到；多报大量业务线数量级/指引问题 |

## 4. 命中情况

### 4.1 稳定命中的类型

| 类型 | 命中 report | 说明 |
|---|---|---|
| EPS actual/estimate/surprise | 01, 03, 07, 10, 12 | 结构化 `earnings.json` 对齐较强 |
| filing date / fiscal period | 02, 04, 09 | 10-K 日期、WMT fiscal Q3 结束日、NEE 日期能抓到部分 |
| peer list | 05 | PFE peers.json 中 NVS 错误抓到 |
| price return arithmetic | 06 | UNH 年收益率计算错误抓到 |
| market cap narrative | 20 | ABBV 市值数字篡改抓到 |

### 4.2 重复输出问题

`report_01` 把同一个 META Q4 EPS 错误拆成：

1. EPS actual 错；
2. full-year EPS sum 错；
3. 同一段落的组合错误。

GT 只算一个 cascading issue。这类拆分会显著拉低 precision。

## 5. 漏报分析

严格口径下 FN=17，主要集中在以下类别：

| 漏报类型 | 数量 | 涉及 report | 说明 |
|---|---:|---|---|
| news/social 细节数字篡改 | 7 | 10, 13, 15, 18, 19, 20 | NHTSA 召回数、电影预算、M&A lead、Mounjaro 区域增长、客户资产等 |
| 事件日期篡改 | 4 | 10, 11, 12 | 股东会日期、XLU 创新高日期 |
| 信源张冠李戴 | 4 | 16, 17 | WSJ/Fierce Pharma、Bloomberg/CNBC 等 |
| analyst rating / action 因果反转 | 2 | 17 | NKE JPMorgan EPS estimate 和 rating action |

典型漏报：

- `report_09`：GT 是 CEO 原话从 9.4% 被篡改为 12.4%。预测没有抓 12.4%，反而把正确的 9.4% 报成错。
- `report_10`：漏掉 NHTSA 召回数量 15,936 vs 12,936，以及股东会 11 月 16 日 vs 11 月 6 日。
- `report_13`：漏掉 `The Electric State` 预算 $420M vs $320M。
- `report_16`：漏掉 MRK 开盘价 $110.28 vs $100.28，以及裁员报道媒体 WSJ vs Fierce Pharma。
- `report_19`：漏掉 MS Wealth Management 总客户资产 $7.49T vs $6.49T。

## 6. 误报分析

84 个预测 issue 中，严格 FP=73。主要误报类型如下，类别之间有重叠。

| 误报类型 | 估计数量 | 占 Pred | 典型表现 |
|---|---:|---:|---|
| 先承认正确再报错 | 33 | 39.3% | reason 里说 `correct / consistent / plausible / 可接受`，但仍输出 |
| 指标口径混淆 | 31 | 36.9% | GAAP/Core/Adjusted、reported/non-GAAP、revenue/net income 混用 |
| 单位/数量级问题泛化 | 30 | 35.7% | 有些是真数量级错误，有些是把中文“亿”或近似金额误判 |
| 舍入/近似误判 | 24 | 28.6% | `$16.792B` vs `$16.8B`、14.4% vs 14.5% 等过细误报 |
| 把缺少证据当错误 | 21 | 25.0% | `no source supports` 直接当 contradiction |
| 用全年端点推断局部走势 | 8 | 9.5% | 用 1/2 和 12/31 close 反驳财报日、盘中、YTD |
| 开盘/收盘混用 | 4 | 4.8% | 用 close 去反驳 open |
| reason 否定自身仍输出 | 3 | 3.6% | reason 里承认 unsupported 不应算 contradiction |

典型误报：

- `report_14`：GT 为 0，但预测 4 条 PG issue，仍属于泛审计噪声。
- `report_15`：GT 是 GS M&A lead 金额篡改，但预测集中在 CET1、净利、股息、股价。
- `report_16`：GT 是开盘价和信源错配，但预测集中在 Gardasil、Keytruda、营收同比、股价路径。
- `report_20`：虽然抓到 market cap，但另外 7 条业务线数量级、指引、股价相关 issue 不在 GT 范围内。

## 7. 与 review(13) 的变化

| 版本 | Pred | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| review(13) | 88 | 11 | 77 | 17 | 12.5% | 39.3% | 19.0% |
| review (15) | 84 | 11 | 73 | 17 | 13.1% | 39.3% | 19.6% |

变化：

- FP 少了 4 条，precision 小幅提升；
- TP 和 FN 没变，说明 recall 没改善；
- `report_20` 比上一版更好，抓到了 ABBV market cap；
- `report_09` 退步，上一版抓到了 12.4% 问题，这版反而把 9.4% 报错；
- `report_11` 输出从 6 条降到 1 条，FP 降了，但两个 GT 仍然全漏。

## 8. 根因判断

### 8.1 审查器仍偏“泛审计”

GT 的错误通常是注入式局部错误，而 `review (15)` 仍在大量审查财务主表、估值、股价路径、业务线拆分。很多 issue 即使事实上有争议，也不是 GT 想要的错误。

### 8.2 news/social narrative 检索仍不足

漏报多数来自新闻、社媒、分析师动作、媒体 attribution：

- NHTSA 召回数；
- CNBC/Bloomberg 来源；
- Fierce Pharma/WSJ 来源；
- analyst rating upgrade/downgrade；
- Mounjaro 区域增长；
- MS 客户资产。

这说明新解压的 `news_merged` 如果要用，需要让 claim extractor 和 retriever 更主动查这些 narrative claim。

### 8.3 unsupported 与 contradicted 仍混淆

不少 reason 仍是“没有 source 支持”，但没有给出具体反证。这类在当前评测口径下应丢弃。

### 8.4 单位规则双刃剑

这版对数量级错误更敏感，带来一些真实提升，例如 ABBV 业务线数量级能识别；但也产生了很多中文“亿”、近似金额、四舍五入误报。

## 9. 建议

短期最有效：

1. 每篇默认最多输出 1 条；若输出第 2 条，必须满足强反证条件。
2. 对同一事实链去重，尤其是 EPS actual 错导致的 downstream sum。
3. 删除 reason 中只有 `no source / no evidence / unsupported` 的 issue。
4. 删除 reason 中出现 `correct / consistent / plausible / 可接受` 的候选，除非同一句有明确 `verified X not Y`。
5. news/social 检索要专门覆盖：
   - `reported by <media>`；
   - analyst 机构、rating action、target price、EPS estimate；
   - recall count；
   - market cap / client assets / AUM；
   - quote 中的百分比和金额。

如果沿用上一版的后处理经验，`top1` 截断仍可能显著提升 F1：`review (15)` 前 1 条通常覆盖 10 个 TP 左右，但能把 Pred 从 84 降到 20，核心收益还是强控 FP。

