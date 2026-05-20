# 金融知识辅助库 —— 术语分析报告 + Skill 生成方案

> 目的:让 generate/review 的 LLM 在动手前,被**正则前置注入**必要金融常识(含义+算法+本数据集绑定+陷阱)。
> 数据依据:扫全 50 ticker `financials_reported.json` 的 us-gaap concept 频次 + `review_train.jsonl` 报告正文术语词频。
> 配套:[review_plan_v2.md](review_plan_v2.md)、[review_fix_plan.md](review_fix_plan.md)。

---

## A. 术语分析报告(哪些"常见但专业"的词必须懂/会算)

每条:**含义 → 算法 → 本库在哪 → 陷阱(对应已发现的 FP/FN)**。按"踩坑杀伤力"排。

### A1. 归母净利 vs 合并净利(报告高频,FP/FN 双杀)
- `us-gaap_NetIncomeLoss`(2525 次)= **归属母公司**;`us-gaap_ProfitLoss`(2003 次)= **含少数股东权益的合并净利**。两者不等。
- 算法:EPS、ROE、"公司净利"一律用 **NetIncomeLoss(归母)**,不是 ProfitLoss。
- 绑定:`financials_reported.report.ic[]`。
- 陷阱:report_08「MS net income applicable to Morgan Stanley」——拿 ProfitLoss 对 = 误判。

### A2. EPS:basic vs diluted、GAAP vs 非GAAP、拆股口径(头号坑)
- `EarningsPerShareBasic`(1804)/`EarningsPerShareDiluted`(1804);`WeightedAverageNumberOfDilutedSharesOutstanding`(1441)。
- 算法:diluted EPS = 归母净利 / 摊薄加权股数。**earnings.json 的 actual/estimate 是非 GAAP 一致口径**;financials 反推是 GAAP。
- 陷阱:① report_18 LLY「$6.21(GAAP摊薄)vs $7.02(非GAAP)」混判;② **NFLX 10:1 拆股**——earnings.json 拆后(0.72)、SEC 10-Q 拆前(7.19),比前必须按 `corporate_actions` 归一(见 review_plan_v2 S3′)。

### A3. EPS surprise / beat-miss(刻度无关,最该信)
- 算法:`surprise = actual − estimate`;`surprisePercent = (actual − estimate)/|estimate|×100`;>0 beat,<0 miss。
- 绑定:`earnings.json{actual,estimate,surprise,surprisePercent}`。
- 价值:**拆股/刻度错时它仍正确**(分子分母同步缩放,比例不变)——核查方向类首选信号。

### A4. GAAP vs non-GAAP / 调整后(报告 60+ 次)
- 非GAAP ≈ GAAP 剔除 `ShareBasedCompensation`(1360)、无形摊销、重组、IPR&D、一次性。
- 陷阱:跨口径比 magnitude = 系统性 FP(本次审计我自己都踩到 ABBV/META)。**只允许同口径互判**。

### A5. 同比/环比 + YTD 累计(65% 财报行是累计!)
- YoY=(本期−去年同期)/|去年同期|;QoQ=环比上一季。
- 致命前提:`financials_reported` 利润表/现金流是**财年累计**(2506 行中 1646 行跨度>100天)。算单季/同比**必须先去累计**(差分同财年上一季)。
- 陷阱:report_08 九个月净利当单季;NFLX Q3 净利 8.56B 实为 9 个月。

### A6. 财季 vs 日历季(13/50 ticker 错位)
- `earnings.period`=日历季末;`financials.endDate`=财年末。AAPL/AVGO/COST/DIS… 不重合(AVGO 差≈2 月)。
- 算法:核查走**值锚定**,不靠"翻译 Q3 FY25"。

### A7. 利润率族
- 毛利率=(营收−COGS)/营收;营业利润率=`OperatingIncomeLoss`(1171)/营收;净利率=归母净利/营收。报告 毛利率25/营业利润率11 次。

### A8. 自由现金流 FCF
- FCF = `NetCashProvidedByUsedInOperatingActivities`(1601) − `PaymentsToAcquirePropertyPlantAndEquipment`(1162, capex)。报告 20 次。注意经营现金流也是 YTD 累计。

### A9. 回购与股本(EPS 增长 ≠ 净利增长)
- `PaymentsForRepurchaseOfCommonStock`(1317)。大额回购缩股本 → EPS 同比 > 净利同比。陷阱:把 EPS 增速当利润增速。

### A10. 股息 / 股息增速 CAGR
- DPS、股息率=DPS/价;CAGR=(末/初)^(1/年)−1。陷阱:report_11「2007 以来年化股息增速 10%→篡改 15%」。

### A11. 银行专属:AOCI / NII / 拨备 ACL
- `AccumulatedOtherComprehensiveIncomeLossNetOfTax`(1778):AFS 证券未实现损益,银行 AOCI 修复叙事(report_19)。NII=净利息收入、ACL=信用损失准备/拨备(报告"拨备"9 次)——**无 us-gaap 标准 tag,在正文/10-Q 表内**,靠检索。

### A12. CER / 固定汇率(报告 11 次)
- 剔除汇率波动的增速;跨国药企并列 reported 与 CER 两套(report_20 ABBV「+46.0% CER」)。陷阱:把 CER 和 reported 互判矛盾。

### A13. 市值 / 估值倍数
- 市值=价×流通股(时点,非结构化字段,需算);P/E=价/EPS(trailing vs forward、GAAP vs 非GAAP);EV/EBITDA。陷阱:report_20 ABBV 市值 4031→4531 篡改;P/E 口径混。

### A14. 基点 bps
- 100 bps = 1%。报告"基点"4 次。陷阱:bps↔% 混(银行净息差、利率类)。

### A15. 价格字段 / 拆股调整
- `prices`:`vwap`=成交量加权均价,`transactions`=成交笔数。**prices 已全年拆股回溯调整**;报告引拆股前价位(NFLX 11 月 ~$1100)对 CSV ~$110 → 必须拆股感知,否则 -90% 假错。

### A16. 评级/目标价(结构化源全空!)
- `recommendations.json` **50 个全空**。评级上调/下调、目标价(report_17 JPM)**无结构化事实**,只能检索 news/filings 软判。

---

## B. Skill 生成方案:索引期挂靠的「金融知识辅助库」

### B0. 定位
与现有「news 行业/时间范围抽取 skill」**同一插件层**,都是 index-time 富化。但本库是**人工校验的静态知识 + 数据集绑定校验**,不是运行时让 LLM 现编(知识库错比没有更糟)。

### B1. 知识条目 schema(`finance_kb/*.yaml`,人工维护)
```yaml
- id: eps_surprise
  names: [EPS surprise, 盈利惊喜, 超预期, beat, miss, surprisePercent]
  triggers:                       # 正则,命中即注入
    - '(?i)surprise|超预期|不及预期|beat|miss|惊喜'
  category: earnings
  definition: 实际 EPS 与一致预期之差;>0 为 beat,<0 为 miss。
  formula: 'surprisePercent = (actual − estimate)/|estimate|×100'
  data_binding: 'research/<T>/earnings.json {actual,estimate,surprise,surprisePercent}（非GAAP一致口径）'
  pitfalls: ['estimate 是非GAAP,勿与GAAP净利比','拆股/刻度错时此比例仍正确,核查方向首选']
  worked_example: null            # 索引期用真实数据回填
```
覆盖 A1–A16 全部条目。

### B2. 索引期构建(`build_index` 增一步,挂在现有 skill 旁)
1. 加载 `finance_kb/*.yaml`;
2. **绑定校验**:每条 `data_binding` 引用的 us-gaap concept / 文件字段,必须在语料中真实存在(扫一遍 financials concept 集);不存在 → 构建失败(防知识库与数据漂移,例:若哪天 recommendations 有数据了会提醒);
3. **worked_example 回填**:用真实 ticker 算一个当前例子(如 NFLX 拆股 EPS 归一、AMD QoQ 去累计),让示例**绑定本数据集而非泛泛**;
4. 产出 `index/finance_kb.json` + 一张编译好的 `triggers` 总正则(id→entry)。

### B3. 运行期注入(generate & review 共用,纯正则、离线、零额外 LLM)
```
claim/topic/report 文本
  └ 跑 finance_kb 总正则 → 命中的 entry 集(去重、按 category 合并)
  └ 组装「FINANCIAL KNOWLEDGE PREFACE」块(只放命中条目, char 预算上限 ~1500)
  └ 前置进 prompt(review 的 adjudicate / generate 的 writer 之前)
```
- **review**:让 verifier 懂"surprise% 怎么算""归母≠合并""非GAAP≠GAAP""比前先拆股归一""bps≠%"——直接压制 A1/A2/A4/A5/A15 类 FP。
- **generate**:writer 写之前就懂同口径/去累计/拆股,**主动不犯** review 要抓的错(攻防对称,延续 plan.md 原则 4)。

### B4. 与现有体系的接口
- 与 review_plan_v2 的 **S5 能力登记表**联动:KB 条目若 `data_binding` 指向空源(recommendations)→ 标 `structured_unavailable`,提示走检索软判,且触发**铁律1(缺失≠错误)**。
- 与 **S3′ 拆股归一**联动:A2/A15 条目的 worked_example 直接复用 `corporate_actions` 表。

### B5. 维护原则
- KB 人工评审、版本化;**绝不**运行时让模型改写知识;
- 构建期绑定校验失败即 fail,保证知识与数据集同步(不漂移)。

---

## C. 下一步建议
先落 **B1 的 A1–A6 六条**(归母/EPS/ surprise/GAAP-非GAAP/YTD/财季——覆盖 60% 数字篡改 + 20% 趋势 + FP 大头)+ B2 绑定校验 + B3 review 侧注入,小步验证对 FP 的压制,再扩 A7–A16。

---

## D. 当前轻量实现与验证记录

### D1. 已落地方式
- 运行期模块:`reference_submission/retrieval/finance_kb.py`。
- generate 接入点:`reference_submission/agents/generate.py` 在检索出 `facts_block` 后,用 `topic + 英文检索关键词 + facts_block` 做正则触发,生成 `FINANCIAL KNOWLEDGE NOTES`。
- prompt 接入点:`reference_submission/prompt_templates/grounded_generate.md` 的 `VERIFIED STRUCTURED FACTS` 与 `NARRATIVE EVIDENCE` 之间。
- 开关:`ALPHASIGHT_FINANCE_KB_DISABLE=1` 可关闭知识库注入,用于 A/B。
- 预算:默认最多 5 条规则、约 1600 字符;只注入短 guardrail,不注入长文档摘录,防止挤掉证据与后续规则。

### D2. 当前内置轻量规则
- EPS consensus basis:`earnings.json` 是 EPS consensus 表,优先信 `actual/estimate/surprise/surprisePercent/beat-miss direction`;不要和 SEC GAAP 绝对 EPS 混口径。
- EPS scale safeguards:若 SEC-implied EPS 与 `earnings.json` 存在稳定 10^n 缩放,绝对 EPS 标 `scale_suspect`,优先用 surprise sign / surprisePercent。
- SEC GAAP and YTD periods:`financials_reported.json` 是 SEC/GAAP;利润表/现金流可能是 fiscal-YTD;单季值只能使用已去累计的 `single-quarter FACT` 行。**不要自行发明 Q1/Q2/Q3 数字;缺失就写 unavailable。**
- Price and return anchors:`prices/*.csv` 是价格/收益率锚点;open/high/low/close 不可混用;盘中 high 不是 close。
- Availability and contradiction:空结构化源只表示 `available=false`,缺失不构成矛盾;peer list 比较前移除公司自身。

### D3. A/B 验证用例
验证脚本:`reference_submission/tools/run_finance_kb_full_ab.py`。

测试 topic:
```text
NVDA FY2026 Q3 EPS surprise and beat/miss direction, de-cumulated single-quarter revenue versus YTD revenue, and 2025 price return.
```

命中规则:
- EPS surprise / beat-miss;
- SEC GAAP / YTD / de-cumulated revenue;
- price return anchor。

输出位置:
```text
output_ab/finance_kb_main/no_kb.md
output_ab/finance_kb_main/with_kb.md
output_ab/finance_kb_main/diff.md
output_ab/finance_kb_main/relevant_diff.md
```

### D4. 验证结论
- KB 注入有效:with-KB 版本明显更倾向显式区分 `single-quarter revenue` 与 `fiscal-YTD cumulative revenue`。
- 修正了无 KB 版的 EPS 趋势表述风险:无 KB 版容易把 Q1 `+0.8297%` 到 Q3 `+1.9928%` 写成持续扩大,但 Q2 是 `+2.1301%`;with-KB 版改为“third consecutive positive EPS surprises”,更稳。
- 修正了早期 with-KB 版的 YTD/单季幻觉:曾出现 `$35.082B in Q1 alone`、`$30.040B in Q1`、`down from prior cumulative figures`、`triple-digit YTD revenue growth`;加入 self-audit 后新版不再出现。
- 最新 with-KB 核心收入链路正确:
```text
FY2026Q1 single-quarter revenue = $44.062B
FY2026Q2 single-quarter revenue = $46.743B
FY2026Q3 single-quarter revenue = $57.006B
FY2026Q3 fiscal-YTD cumulative revenue = $147.811B
$44.062B + $46.743B + $57.006B = $147.811B
```

### D5. 配套 deterministic self-audit
为防止“知识提示让模型更敢算但算错”,generate 自审增加了 revenue/YTD 检查:
- 明确季度金额如 `Q1/Q2/Q3 revenue` 必须对齐 FactStore `single-quarter revenue`。
- `YTD/cumulative/through Qn` 金额必须对齐 `revenue_cum`。
- 拦截 `down from` 方向错误,例如 `147.811B down from 90.805B`。
- 拦截 `triple-digit YTD revenue growth` 这类与累计 YoY 不符的定性。
- 收紧上下文窗口,避免把 `net income` 行误当 revenue 行、避免 segment revenue/Blackwell revenue 与 total revenue 混判。

### D6. 剩余风险与下一步
- 已收紧 generate 证据入口:`social/*.json` 不再进入主生成检索池,只保留 filings / FactStore / prices 等更稳的数字来源;fallback baseline 也禁用 news/social,避免主链路异常时回退到跨 ticker news/social 佐证。
- 自审增加了 `social/...` 财务数字引用拦截:若报告仍用 social 支撑 EPS、revenue、guidance、price/return、valuation、segment/product revenue,触发一次重写并要求改用 verified facts/filings/prices 或删除该数字。
- 当前 KB 只接入 generate 主路径;review 侧可复用同一模块,但必须保持 contradiction-only,避免“常识压过 corpus”。
- 若扩展到 YAML 条目库,仍需保留当前短 guardrail 预算;不要直接把长 Markdown 条目注入 prompt。
