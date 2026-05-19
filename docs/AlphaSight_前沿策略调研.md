# AlphaSight 前沿策略调研方案

> 范围：本文件只做研究、方案与实验设计，不改代码。

## 1. 论文与方法地图

### 1.1 AgentDisCo：探索/利用解耦的双 Agent 对抗协作

参考：arXiv:2605.11732，AgentDisCo: Towards Disentanglement and Collaboration in Open-ended Deep Research Agents。

核心启发：

- 把 deep research 拆成 information exploration 和 information exploitation。
- Critic Agent 评估 outline / query，Generator Agent 检索并修订。
- 两者围绕共享 Document Bank 迭代，不是单个 agent 一把梭。

落到 AlphaSight：

- `Generator` 不直接写完整报告，而是先产出 `Evidence Blueprint`：
  - ticker
  - 时间窗
  - 子问题
  - 必需证据类型
  - 可证伪点
- `Reviewer` 不只审最终报告，而是审 blueprint：
  - 是否缺关键证据？
  - 是否引用了错 ticker？
  - 是否把 news/social 当作 filing 事实？
  - 是否有无法验证的预测数字？
- 通过 2-3 轮 blueprint 修订后再写报告。

实验：

- Baseline：topic -> retrieve -> write。
- +AgentDisCo-style blueprint loop：topic -> blueprint -> critic -> retrieve -> write。
- 指标：source ticker mismatch 数、unsupported numeric claim 数、人工 rubric 分。

### 1.2 SPC：对抗自博弈训练 Critic

参考：arXiv:2504.19162，SPC: Evolving Self-Play Critic via Adversarial Games for LLM Reasoning。

核心启发：

- 一个 sneaky generator 故意产生难以发现的错误。
- critic 学会判断 reasoning step 是否可靠。
- 重点是低标注成本下得到 step-level 监督。

落到 AlphaSight：

- 正确报告作为 base。
- `Sneaky Financial Editor` 注入金融错误：
  - EPS actual 改错。
  - estimate / actual 调换。
  - surprise 方向反转。
  - Q2 改 Q3。
  - GAAP / non-GAAP 口径混淆。
  - source attribution 换媒体。
  - 价格 return 算错。
  - peer list 加入不存在公司。
- 自动产出 `(corrupted_report, gold_issues)`。

实验：

- 错误难度分三级：
  - L1：数字直接翻转，明显错。
  - L2：同一 ticker 不同季度错配。
  - L3：看似合理的因果反转或信源张冠李戴。
- 每类生成 20-50 条，测 reviewer precision / recall。
- 用这个结果调 PrecisionGate 阈值。

### 1.3 CRITIC：工具交互式自我纠错

参考：arXiv:2305.11738，CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing。

核心启发：

- 模型不是只自我反思，而是调用外部工具验证。
- 对事实类任务，工具反馈比纯反思更可靠。

落到 AlphaSight：

- Generate 后不要只让 LLM “自审”，而是强制跑工具：
  - FactStore 查 EPS / revenue / net income。
  - PriceStore 复算 return。
  - FilingStore 查 accession / filing date。
  - NewsStore 查事件日期和原始 source。
- Reviewer 的 reason 也必须带 `evidence_type`：
  - `structured_fact`
  - `price_formula`
  - `filing_metadata`
  - `news_attribution`

实验：

- 关闭工具自审 vs 开启工具自审。
- 统计生成报告中无来源数字和错误数字的下降比例。

### 1.4 Chain-of-Verification：先生成，再计划验证问题

参考：arXiv:2309.11495，Chain-of-Verification Reduces Hallucination in Large Language Models。

核心启发：

- 先写 draft。
- 再生成 verification questions。
- 独立回答验证问题，避免被原 draft 误导。
- 最后生成 verified answer。

落到 AlphaSight：

对每篇 generate 报告自动生成核验问题：

1. 报告中每个数字来自哪个 source？
2. 每个日期是否能在 filing filename / news timestamp / price csv 中找到？
3. 每条因果链是否至少有 event + market reaction 两端证据？
4. 每个 `[SOURCE]` 是否 ticker 匹配？
5. 是否存在 “not in source set” 或未引用背景知识？

实验：

- Draft-only vs CoVe-style verified。
- 指标：unsupported claim、citation mismatch、错 ticker citation。

### 1.5 RARR / post-hoc retrieve-and-revise

参考：arXiv:2210.08726，RARR: Researching and Revising What Language Models Say。

核心启发：

- 不是生成前检索，而是生成后对 claims 做检索和修订。
- 适合已有报告的事实修复。

落到 AlphaSight：

- 对 Generator 输出做 claim segmentation。
- 每条 claim 单独检索证据。
- 找不到强证据的 claim：
  - 删除。
  - 改成更弱说法。
  - 或标成 hypothesis 而不是 fact。

实验：

- 生成前 RAG vs 生成后 RARR-style 修订。
- 指标：每 1000 字 unsupported factual claim 数。

### 1.6 Self-RAG / CRAG：检索质量先判定，再决定是否继续搜

参考：

- arXiv:2310.11511，Self-RAG。
- arXiv:2401.15884，Corrective Retrieval Augmented Generation。

核心启发：

- RAG 失败通常不是 writer 失败，而是 retrieved evidence 质量不够。
- 检索结果应该被评价：相关、无关、矛盾、不足。

落到 AlphaSight：

增加一个 `RetrievalJudge`，在 evidence 进入 writer/reviewer 前打标签：

- `direct_support`: 直接支持 claim。
- `partial_support`: 只支持背景。
- `contradiction`: 反证。
- `irrelevant`: 无关，禁止进入 prompt。
- `wrong_entity`: ticker 或公司不匹配。
- `wrong_period`: 年份/季度不匹配。

这是目前 generate 错引 COST filing 支撑 HD/WMT 的直接修复点。

实验：

- 无 RetrievalJudge vs 有 RetrievalJudge。
- 指标：wrong_entity source rate、wrong_period source rate、最终报告人工分。

### 1.7 HyDE 与 Query Decomposition：解决固定 6 题的多跳检索

参考：

- arXiv:2212.10496，HyDE。
- arXiv:2507.00355，Question Decomposition for RAG。

核心启发：

- HyDE 用假想答案/文档作为检索桥梁，改善 zero-shot dense retrieval。
- 问题分解能为多跳问题收集互补证据。

落到 AlphaSight：

6 个固定题几乎都是多跳题，不适合直接把 topic 丢进 BM25。

例如 Gen-1 NVDA：

1. H20 charge 金额与日期。
2. China revenue / shipment 状态。
3. Blackwell demand / order backlog。
4. SOX vs NVDA 20-day relative return。
5. 新闻/社交情绪是否已经 price-in。

每个子问题走不同 retrieval route，再合并证据。

实验：

- Single query vs decomposed query。
- 指标：证据覆盖度、关键证据命中率、报告事实错误数。

### 1.8 RAPTOR / 分层摘要树：处理 filing 长文档

参考：arXiv:2401.18059，RAPTOR。

核心启发：

- 长文档只切短 chunk 会丢整体结构。
- 可以递归聚类、摘要、建树，在不同抽象层级检索。

落到 AlphaSight：

不一定完整实现 RAPTOR，但可以做轻量版：

- filing item-level summary：
  - Item 1A risk summary。
  - Item 7 MD&A summary。
  - Item 8 financial statement summary。
- 每个 summary 保留 source path、item、ticker、period。
- Generate 先检索 summary 确定方向，再回跳原文 chunk 找引用。

实验：

- 只用 chunk vs item summary + chunk。
- 指标：filing 相关题的证据命中、上下文相关性、报告 insight depth。

### 1.9 RAGAS / ARES：把主观调参变成可测指标

参考：

- arXiv:2309.15217，RAGAS。
- arXiv:2311.09476，ARES。

核心启发：

- RAG 评估可以拆成 context relevance、faithfulness、answer relevance。
- ARES 用 synthetic data 训练轻量 judge，并用少量人工标注校准。

落到 AlphaSight：

对 generate：

- Context relevance：source 是否真相关。
- Faithfulness：claim 是否被 source 支持。
- Answer relevance：是否回答题目。

对 review：

- Claim relevance：reviewer 是否审了真正可核验 claim。
- Evidence contradiction：证据是否构成反证。
- Quote alignment：quote 是否是完整错误片段。

实验：

- 对每次 pipeline 修改都跑一个小型 regression suite。
- 不只看最终 LLM 输出，而是看检索、证据、裁决三个环节。

### 1.10 FinanceBench / FinBen / FinGPT：金融任务的基本经验

参考：

- arXiv:2311.11944，FinanceBench。
- arXiv:2402.12659，FinBen。
- arXiv:2306.06031，FinGPT。

核心启发：

- 金融 QA 强依赖 open-book evidence。
- 金融 LLM 最大问题是时间敏感、低信噪比、结构化数字与文本叙事混合。
- 仅靠大模型或长上下文不够，必须做数据治理、证据追踪和领域任务拆分。

落到 AlphaSight：

- 把 review 的错误类型按金融任务拆：
  - EPS / consensus / surprise。
  - fiscal period。
  - price return。
  - peer membership。
  - filing metadata。
  - analyst recommendation。
  - event attribution。
  - causal direction。
- 每种类型单独设计 verifier，而不是一套 prompt 打天下。

## 2. 可加入 Pipeline 的 12 个策略

### 策略 1：对抗自博弈错题工厂

输入：一篇 grounded 正确报告。  
输出：带错报告 + gold issues。

错误类型：

1. 数字篡改：actual EPS、revenue、net income、market cap。
2. 计算错误：return、YoY、QoQ、surprise percent。
3. 时间错位：Q2/Q3、filing date、event date。
4. 口径错位：GAAP/non-GAAP、fiscal/calendar。
5. 实体错位：ticker、peer、competitor。
6. 信源错位：Bloomberg/CNBC/WSJ/Fierce Pharma 等 attribution。
7. 因果反转：beat 写成 miss，upgrade 写成 downgrade。
8. 证据强度错配：social rumor 写成 filing fact。

亮点表达：

> 我们不是等评测系统告诉我们 reviewer 哪里差，而是用 generator 系统性制造金融错题，建立 reviewer 的单元测试集。

### 策略 2：Evidence Court 证据法庭

每个 reviewer candidate 必须进入“证据法庭”：

1. `Claim Parser`: claim 类型、ticker、period、metric。
2. `Evidence Prosecutor`: 找反证。
3. `Evidence Defender`: 找支持证据。
4. `Judge`: 只有反证强于支持时输出 issue。

好处：

- 减少 unsupported 就乱报。
- 对无错误报告更保守。
- 能解释为什么没报某条。

### 策略 3：PrecisionGate

每条 issue 给一个风险分：

- 强结构化反证：0.95。
- price formula 复算反证：0.95。
- filing metadata 反证：0.90。
- news 原文反证：0.80。
- BM25 语义反证：0.55。
- social 反证：0.40。

只输出超过阈值的 issue。阈值由错题工厂和 train GT 标定。

### 策略 4：Quote Expander

当前 review 输出常见问题是 quote 太短。  
解决：先找错误 token，再扩展到完整句子、bullet 或 table row。

规则：

- 若在 Markdown 表格中，quote 扩展到整行。
- 若在中文段落中，扩展到最近 `。！？`。
- 若在英文段落中，扩展到完整 sentence。
- 若是 bullet，扩展到整条 bullet。

### 策略 5：Data-Type Router 2.0

不同数据源用不同规则，不要都走 BM25：

| 数据类型 | 适合任务 | 核验方式 |
|---|---|---|
| `earnings.json` | EPS / estimate / surprise | 精确 key-value |
| `financials_reported.json` | revenue / net income / endDate | fiscal period 对齐 |
| `prices/*.csv` | return / open / close / volume | 公式复算 |
| `prices_minute` | 事件窗口反应 | event-time window |
| `peers.json` | peer membership | set membership |
| `recommendations.json` | rating / target / analyst | 时间序列查找 |
| `sec_submissions.json` | accession / filing date | metadata exact match |
| `filings/*.htm` | 风险、MD&A、披露原文 | item-level chunk |
| `news/*.json` | 事件与媒体 attribution | title/date/source/entity |
| `social/*.json` | sentiment / rumor | 只能作弱证据 |

### 策略 6：固定 6 题的 Query Blueprint

每个固定题预置 blueprint，而不是泛化 query。

Gen-1 NVDA：

- H20 charge。
- China revenue。
- Blackwell demand。
- SOX relative return。
- market reaction。

Gen-2 PFE：

- GLP-1 discontinuation event。
- stock reaction window。
- oncology revenue / Seagen / pipeline。
- peer valuation。

Gen-3 META：

- Reality Labs loss。
- core ad revenue。
- Llama / AI infra / ad efficiency evidence。
- stock ATH reaction。

Gen-4 GOOGL：

- antitrust remedy。
- Chrome not broken up。
- Cloud / AI valuation narrative。
- price reaction around remedy。

Gen-5 NKE：

- new CEO timeline。
- guidance cut。
- tariff pressure。
- financial metric that improved。

Gen-6 BAC vs JPM：

- AOCI loss repair。
- NII sensitivity。
- capital return。
- buyback/dividend divergence。

### 策略 7：自由 4 题从 train 错误类型反向设计

自由题不要泛泛自选，而要覆盖 reviewer 最容易抓分的数据类型。

建议自由题：

1. **Price-event study**：事件日前后分钟级/日级价格反应，训练 price formula 和 event window。
2. **Analyst revision conflict**：recommendations + news，训练 rating/target/estimate 校验。
3. **Peer basket dislocation**：peers + financials，训练 peer membership 与跨公司对比。
4. **Filing vs social rumor**：filing 权威披露反驳 social/news 叙事，训练证据强度分级。

这样 generate 的自由题也能反哺 review 的错误类型覆盖。

### 策略 8：Claim Ledger

Generate 输出前，内部维护一张 claim ledger：

| claim | source | source_type | ticker | period | confidence |
|---|---|---|---|---|---|

最后报告只是 ledger 的自然语言渲染。  
如果 claim 没有 ledger row，不允许写成事实。

### 策略 9：Counterfactual / Falsifier 模块

每篇报告要求至少一个 falsifier，但 falsifier 不能胡编。

规则：

- falsifier 必须基于可观测指标。
- 指标必须来自当前数据体系未来可核验字段。
- 例如 EPS、revenue、shipment、relative return、margin。

### 策略 10：Contradiction Retrieval

Reviewer 不应只搜支持 claim 的证据，还要主动搜反证。

对每条 claim 生成两类 query：

- support query: “evidence that claim is true”
- contradiction query: “correct value/date/opposite direction”

适合抓因果反转和日期错位。

### 策略 11：Source Strength Ladder

证据强度排序：

1. Structured research / price csv。
2. SEC filing。
3. News。
4. Social。
5. Model inference。

Generate 中低强度证据不能覆盖高强度证据。  
Review 中 social 不能单独推翻 filing。

### 策略 12：Ablation Matrix

答辩最有说服力的是消融，不是堆概念。

建议消融：

| 实验 | 关闭项 | 观察指标 |
|---|---|---|
| A | 无 FactStore | 数字错误召回 |
| B | 无 Quote Expander | strict quote match |
| C | 无 PrecisionGate | false positives |
| D | 无 Query Blueprint | generate source coverage |
| E | 无 RetrievalJudge | wrong entity source |
| F | 无错题工厂 | 阈值调参稳定性 |

## 3. 可作为答辩亮点的叙事

### 亮点 1：从 RAG 到 Evidence-Governed RAG

普通 RAG 是“检索到什么就写什么”。  
我们的方法是“证据先进入法庭，按金融规则判定强弱，再决定能不能写/能不能报错”。

### 亮点 2：生成器和评审器不是两个孤立模块

Generator 给 Reviewer 造错题，Reviewer 给 Generator 找薄弱证据。  
这形成一个闭环：

`generate correct report -> inject errors -> train/evaluate reviewer -> reviewer audits generator -> generator revises evidence blueprint`

### 亮点 3：金融错误类型学

不是泛泛事实核查，而是金融专属 taxonomy：

- 数字。
- 口径。
- 周期。
- 价格公式。
- 证券申报元数据。
- 分析师评级。
- 同行集合。
- 信源归属。
- 因果方向。

### 亮点 4：自由题反哺 Reviewer

4 个自由题不是为了“写得好看”，而是主动覆盖 review 需要的难点：

- price event。
- analyst revision。
- peer comparison。
- filing vs social contradiction。

这能体现你们对比赛整体目标的系统理解。

## 4. 推荐执行顺序

### 第一步：不动主代码，先做错题 taxonomy

产物：

- `error_taxonomy.md`
- 30 条 train GT 映射表：每条 GT 属于哪类错误。

价值：

- 马上能解释当前 reviewer 为什么漏。
- 后续脚本和 prompt 都围绕 taxonomy 做。

### 第二步：做错题工厂的规则设计

产物：

- 每种错误 3-5 个 injection template。
- 每个 template 标明适用数据源和 gold quote 生成方式。

价值：

- 形成零人工标注扩增能力。

### 第三步：做评测协议

产物：

- 每类错误的 precision / recall。
- quote exact match / relaxed match。
- false positive by evidence type。

价值：

- 让调参有客观抓手。

### 第四步：再和队友合并到代码

优先落地：

1. Quote Expander。
2. Price return verifier。
3. Filing metadata verifier。
4. Peer verifier。
5. PrecisionGate。

## 6. 当前项目的直接改进点

结合当前代码和输出，最该优先处理：

1. `output/generate` 缺正式 `gen-1` 到 `gen-6`，后续必须补齐。
2. 自由题 topic 仍是占位符，应改成带 ticker / 时间窗 / 证据类型的高质量题。
3. 当前 generate 有明显 wrong-entity citation，例如用 COST filing 支撑 HD/WMT。
4. 当前 review quote 太短，严格匹配 GT 会吃亏。
5. 当前 FactStore 只覆盖少量数值，应扩展到 peers、recommendations、sec_submissions、price returns。
6. 当前 dense index 可能没有建成，检索质量主要依赖 BM25，应先补结构化 verifier，不要把希望全放 embedding。

## 7. 参考清单

- AgentDisCo: arXiv:2605.11732
- SPC: arXiv:2504.19162
- CRITIC: arXiv:2305.11738
- Chain-of-Verification: arXiv:2309.11495
- RARR: arXiv:2210.08726
- Self-RAG: arXiv:2310.11511
- Corrective RAG: arXiv:2401.15884
- HyDE: arXiv:2212.10496
- RAPTOR: arXiv:2401.18059
- Question Decomposition for RAG: arXiv:2507.00355
- RAGAS: arXiv:2309.15217
- ARES: arXiv:2311.09476
- FinanceBench: arXiv:2311.11944
- FinBen: arXiv:2402.12659
- FinGPT: arXiv:2306.06031

