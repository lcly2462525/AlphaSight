# review(13) vs review_train_gt 审查分析

## 1. 总体结论

对比文件：

- 预测输出：`review(13).jsonl`
- 标准答案：`reference_submission/problem/review_train_gt.jsonl`

按语义对齐统计：同一个 GT 错误只算一个 TP；同一错误的重复拆分算 FP；未覆盖 GT 算 FN。

| 指标 | 数值 |
|---|---:|
| GT issue 数 | 28 |
| Pred issue 数 | 88 |
| TP | 11 |
| FP | 77 |
| FN | 17 |
| Precision | 12.5% |
| Recall | 39.3% |
| F1 | 19.0% |

核心问题：`review(13)` 不是简单漏查，而是把任务做成了泛化财务审计。它抓到了一部分 earnings/date 类硬错误，但输出了大量不符合 GT 标注标准的低置信 issue，导致 precision 很低。

## 2. 逐报告对齐

| report | GT | Pred | TP | FP | FN | 备注 |
|---|---:|---:|---:|---:|---:|---|
| report_01 | 1 | 4 | 1 | 3 | 0 | META Q4 EPS 错误抓到；拆成 EPS 和全年 EPS 两条，另多报股价 |
| report_02 | 1 | 2 | 1 | 1 | 0 | TSLA 10-K filing date 抓到；重复输出 |
| report_03 | 1 | 2 | 1 | 1 | 0 | COST EPS miss/beat 方向抓到；叙事后果重复 |
| report_04 | 1 | 5 | 1 | 4 | 0 | WMT fiscal quarter end date 抓到；多报收入、净利、period 标签 |
| report_05 | 1 | 2 | 1 | 1 | 0 | PFE peer list 中 NVS 错误抓到；多报净利 |
| report_06 | 1 | 2 | 1 | 1 | 0 | UNH 年收益率抓到；多报净利 |
| report_07 | 1 | 1 | 1 | 0 | 0 | GS Q4 estimate/surprise 抓准 |
| report_08 | 1 | 1 | 0 | 1 | 1 | GT 是 MS 九个月净利；预测误抓 WFC |
| report_09 | 2 | 5 | 2 | 3 | 0 | NEE 8-K 日期和 EPS growth 12.4% 抓到；多报 dividend、price、9.4% |
| report_10 | 3 | 4 | 1 | 3 | 2 | 只抓到 TSLA Q3 EPS 方向；漏 NHTSA 召回数、股东会日期 |
| report_11 | 2 | 6 | 0 | 6 | 2 | 漏 NEE dividend CAGR、XLU 日期；大量 unsupported FP |
| report_12 | 3 | 2 | 1 | 1 | 2 | 抓到 TSLA QoQ EPS 方向；漏一年涨幅、股东会日期 |
| report_13 | 1 | 6 | 0 | 6 | 1 | 漏 Netflix `The Electric State` 预算 |
| report_14 | 0 | 8 | 0 | 8 | 0 | GT 无错，预测全为误报 |
| report_15 | 1 | 6 | 0 | 6 | 1 | 漏 GS M&A lead 950B vs 850B |
| report_16 | 2 | 8 | 0 | 8 | 2 | 漏 MRK 开盘价、WSJ/Fierce Pharma 信源错配 |
| report_17 | 3 | 3 | 0 | 3 | 3 | NKE 三个 GT 错误全漏 |
| report_18 | 1 | 7 | 0 | 7 | 1 | 漏 LLY Mounjaro 日本 +44% |
| report_19 | 1 | 6 | 0 | 6 | 1 | 漏 MS wealth management total client assets 7.49T |
| report_20 | 1 | 8 | 0 | 8 | 1 | 漏 ABBV market cap 453.1B |

## 3. 漏报分析

17 个 FN 大致分为 4 类：

| 漏报类型 | 数量 | 涉及 report | 说明 |
|---|---:|---|---|
| news/social 细节数字篡改 | 7 | 10, 13, 15, 18, 19, 20 | NHTSA 召回数、电影预算、M&A lead、Mounjaro 区域增长、市值、客户资产等 |
| 事件日期篡改 | 4 | 10, 11, 12 | 股东会日期、XLU 创新高日期等 |
| 信源张冠李戴 | 4 | 16, 17 | WSJ/Fierce Pharma、Bloomberg/CNBC、analyst action source |
| analyst rating / action 因果反转 | 2 | 17 | NKE JPMorgan EPS 估算、评级上调被写成下调 |

观察：

- 当前系统更擅长查 `earnings.json` 和 `financials_reported.json`，所以 EPS actual/estimate/surprise 类 TP 较多。
- 对 news/social/filing narrative 的细粒度事实检索弱，尤其是“原文是谁说的”“哪个媒体报道”“具体日期/金额被改了多少”。
- GT 中很多错误并不是财务报表主表项，而是研报叙事中的局部篡改；当前 review pipeline 没有稳定抽取这些局部 claim。

## 4. 误报分析

88 个预测 issue 中，FP 约 77 个。主要问题如下，类型之间有重叠。

| 误报类型 | 估计数量 | 典型表现 |
|---|---:|---|
| 先承认正确又输出为错误 | 60 | reason 中出现 matches/correct/consistent，但最终仍作为 issue 输出 |
| 指标口径混淆 | 31 | GAAP/Non-GAAP、reported/adjusted、EPS/net income/revenue 混用 |
| 把缺少证据当错误 | 25 | “no source supports” 被当成 contradiction |
| reason 否定自身仍输出 | 15 | reason 中写 cannot confirm / not contradicted，但仍输出 |
| 舍入/近似误判 | 14 | `$16.792B` vs `$16.8B`、`about/roughly` 被误判 |
| 用全年端点推断局部走势 | 6 | 用 1/2 和 12/31 close 反驳财报日、YTD、盘中高低点 |
| 开盘/收盘混用 | 4 | 用 close 去反驳 open，或把 open 当 close 校验 |

典型误报：

- `report_14`：GT 为空，但预测 8 条 issue，主要是 unsupported claim、口径混淆和外部指标无法验证。
- `report_16`：GT 是 MRK 开盘价和信源错配，但预测集中在总部地址、Elanco 收购、GAAP/adjusted EPS、Gardasil 单位等，偏离 GT。
- `report_20`：GT 是 ABBV 市值数字篡改，但预测输出了 8 条业务线、股息、药品、区间走势相关问题。

## 5. 根因判断

### 5.1 审查目标偏移

GT 的标注风格是“找注入错误”，通常每篇 0-3 个明确错误。`review(13)` 的行为是“全量审计研报”，因此会抓出大量不在 GT 范围内、或证据不足的疑点。

### 5.2 缺少 final adjudication

候选 issue 生成后没有严格判断：

- 是否有明确反证；
- 是否只是证据缺失；
- 是否只是舍入；
- 是否与同一 claim 重复；
- reason 是否已经否定该 issue。

这导致很多低质量候选进入最终 JSONL。

### 5.3 检索偏向结构化财务表

系统对 `earnings.json` 的 EPS 检查较强，但对 news/social/filing narrative 的检索和对齐不足。漏报的多数 GT 都在这类来源中。

### 5.4 实体和表格行锁定不足

`report_08` GT 是 MS，但预测抓 WFC；说明同行表格中定位行时没有强制锁定目标 ticker 或 claim 所在行。

### 5.5 数值和单位规范化不稳

存在两类相反问题：

- 有些合理近似被误报，例如 `$16.792B` 写成 `$16.8B`；
- 有些真实单位错误没有被优先抓，例如 `亿美元`、million/billion、market cap 数字改写。

## 6. 可执行修复建议

### P0：先降 FP

1. 增加 final filter：如果 reason 包含 `cannot confirm`、`no source supports`、`not contradicted`、`matches`、`correct`，默认不输出，除非同时存在明确 `verified X not Y`。
2. 区分 `unsupported` 与 `contradicted`：只有有明确反证才输出 issue。
3. 同一事实链去重：例如 EPS actual 错导致 full-year EPS 错，应合并为一条 cascading issue。
4. 每篇 report 设置候选上限或置信阈值；GT 风格下每篇通常 0-3 条，输出 6-8 条基本意味着过滤失败。

### P1：补 recall

1. 增加 news/social claim extractor，专门抽取：
   - 日期；
   - 金额；
   - 百分比；
   - 媒体名；
   - analyst 机构、评级动作、目标价、EPS estimate；
   - 管理层/CEO/CFO 引语。
2. 对每个 claim 做 source-type routing：
   - `earnings/financials` 查结构化表；
   - `reported by / according to / media` 查 news/social；
   - `filed on / 8-K / 10-Q / accession` 查 filing catalog；
   - `peer / analyst / rating` 查 peers、news、social。
3. 对信源错配加专项规则：如果 claim 中含 `reported by X`，必须验证 source passage 中是否确实是 X。

### P2：数值规则

1. 舍入 tolerance：
   - 金额：允许 0.5%-1% 或按小数位判断；
   - 百分比：允许 0.1pp；
   - `about/roughly/approximately` 放宽。
2. 单位规范化：
   - million/billion/trillion；
   - 中文“亿/万亿”；
   - 美元符号和中文单位混写。
3. 股价核查：
   - open 只用 open 反驳；
   - close 只用 close 反驳；
   - 财报日/盘中/YTD 必须有对应日期或区间数据，不能用全年首尾点推断。

## 7. 推荐下一步实验

先不要追求更强检索，建议先做一个低成本后处理版本：

1. 对 `review(13)` 的候选 issue 应用 P0 filter；
2. 合并重复 issue；
3. 每篇保留 top 3 高置信 issue；
4. 再和 train_gt 对齐。

预期结果：

- Recall 可能从 39% 小幅下降；
- Precision 应明显提升；
- F1 大概率提升，因为当前主要瓶颈是 FP 过多。

## 8. 后处理模拟

我额外做了两个低成本模拟：

1. 基于 reason 关键词过滤明显低置信 issue；
2. 按每篇 report 保留原始输出前 K 条。

### 8.1 关键词过滤

过滤规则：

- 删除 reason 自我否定的 issue，例如 `not a clear contradiction`、`no flag`、`cannot confirm`；
- 删除纯 unsupported issue，例如只有 `no source supports`，没有明确反证；
- 删除明显 open/close 混用；
- 删除 reason 已承认 `matches/correct/consistent` 且只是舍入差异的 issue。

结果：

| 项目 | 数值 |
|---|---:|
| 原始 Pred | 88 |
| 过滤后 Pred | 71 |
| 删除 | 17 |

删除原因：

| 删除原因 | 数量 |
|---|---:|
| self-negating reason | 9 |
| unsupported only | 5 |
| rounding or matches | 2 |
| open/close mismatch | 1 |

结论：这类关键词过滤有用，但太保守，不能解决核心 FP 问题。

### 8.2 保留原始前 K 条

因为 `review(13)` 的输出顺序通常把最强候选放在前面，所以直接截断比后续重排更有效。

| 策略 | Pred | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 原始全量 | 88 | 11 | 77 | 17 | 12.5% | 39.3% | 19.0% |
| 每篇 top1 | 20 | 10 | 10 | 18 | 50.0% | 35.7% | 41.7% |
| 每篇 top2 | 38 | 11 | 27 | 17 | 28.9% | 39.3% | 33.3% |
| 每篇 top3 | 51 | 11 | 40 | 17 | 21.6% | 39.3% | 27.8% |

结论：

- 如果评测更重 F1，`top1` 是当前最强的低成本策略。
- 如果更重 recall，`top2` 可以保留全部 11 个 TP，但 FP 明显增加。
- `top3+` 收益很低，基本只是在增加误报。

### 8.3 不建议做简单重排

我试了一个启发式分数：奖励 `verified fact`、`not X but Y`、`filing date`、`peer list`、`EPS surprise` 等强反证词，惩罚 `no source`、`matches`、`roughly`、`open/close`。

结果不如原始顺序：

| 策略 | Pred | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ranked top1 | 20 | 7 | 13 | 21 | 35.0% | 25.0% | 29.2% |
| ranked top2 | 38 | 10 | 28 | 18 | 26.3% | 35.7% | 30.3% |
| ranked top3 | 51 | 11 | 40 | 17 | 21.6% | 39.3% | 27.8% |

原因：启发式会把结构化财务表里的“看起来很硬”的泛审计 issue 排到前面，而 GT 中很多真正错误是 news/social narrative 的局部篡改。简单 scoring 会进一步偏向错的方向。

## 9. 当前最推荐的改法

短期最稳方案：

1. 先对候选 issue 做同一事实链去重；
2. 删除明显自我否定、unsupported-only、舍入-only issue；
3. 每篇最多输出 1 条，或最多输出 2 条但要求第二条必须满足强反证；
4. 对 `review_train` 调参时以 F1 为目标，默认从 `top1` baseline 开始。

按当前手工对齐，单独一个 `top1` 截断就能把 F1 从 19.0% 拉到 41.7%。这说明现阶段最有效的优化不是加更多检索，而是强力控 FP。
