# AlphaSight 当前效果分析与高目标修改方案

## 1. 已打包产物

已将以下目录打包：

`/inspire/hdd/project/26summer-camp-03/26210833/Summer-Camp-Projects/output/generate`

压缩包位置：

`/inspire/hdd/project/26summer-camp-03/26210833/output_generate_20260518.zip`

压缩包已通过 `python3 -m zipfile -l` 验证，包含当前 `generate/` 目录下 6 个 Markdown 文件。

## 2. 当前任务理解

比赛包含两类任务：

1. `generate`: 给定研究题目，生成扎根 2025-2026 美股语料的 Markdown 研报。
2. `review`: 给定已有研报，找出事实或逻辑错误，并输出逐字 quote 与错误原因。

最终目标不是简单跑通，而是尽可能提高训练集、验证集以及最终测试集上的得分。高分关键在于：

1. `generate` 要少幻觉、强证据链、强立场、强可验证性。
2. `review` 要高召回但严格控误报，quote 必须与原文逐字一致。
3. 对公开 train GT 要尽量拟合错误类型，但不能写死 request_id，否则泛化到 val/test 会崩。

## 3. 当前产物效果分析

### 3.1 Generate 输出问题

当前 `output/generate` 下只有 6 个文件：

- `gen-0001.md`
- `gen-sample.md`
- `gen-free-1.md`
- `gen-free-2.md`
- `gen-free-3.md`
- `gen-free-4.md`

而正式 generate 题目应覆盖固定题 `gen-1` 到 `gen-6` 加 4 个自由题，共 10 个。当前目录缺少 `gen-1` 至 `gen-6` 的正式输出，存在提交完整性风险。

当前自由题输出质量存在明显硬伤：

1. 证据错配：例如 HD 研报引用了 COST 的 10-Q 作为 HD 仓库扩张证据，WMT 研报也引用 COST 文件支撑自身扩张计划。
2. 跨公司误归因：TSLA 研报引用 NEE、WMT、NFLX 文件作为 TSLA 风险或治理证据，相关性弱。
3. 幻觉数字较多：如成本节约 12-15%、目标价、共识 EPS、市场份额、ROCm 覆盖率等，很多并未由证据块直接给出。
4. 自由题 topic 仍是默认占位描述，没有被改成高质量自选题，导致检索入口过宽，模型容易随意选材。
5. `gen-0001.md` 是示例公司 SAMP，且没有真实来源 citation，不适合正式提交。

结论：当前 generate 文件能证明流程跑通，但离高分报告还有明显差距。核心问题不是文风，而是证据绑定、题目选择、事实核验和输出完整性。

### 3.2 Review 输出问题

当前 `output/review.jsonl` 有 20 行、14 条 issue。经本地检查，它对应 train 请求格式，quote 都能在 train 报告中找到，但与公开 GT 的严格逐字 quote 匹配为 0。

这不代表完全没有抓到相同错误，而是说明当前输出粒度与 GT 严重不一致：

1. GT 通常使用完整句子或完整表格行作为 quote。
2. 当前系统经常只输出短片段，如 `Q4 2025`、`January 2`、`December 31`。
3. 当前 adjudicator 会把“证据支持的正常片段”也误报成 issue，误报风险高。
4. 多数 train 报告实际有 1-3 个错误，但当前输出大量空列表，漏报严重。

公开 train GT 共 28 条 issue。当前输出 14 条，但严格 quote 命中 0；这说明 review 当前不是“差一点调参”，而是需要重构候选生成、quote 对齐和证据验证策略。

### 3.3 代码与检索链路问题

当前 `Submission` 设计方向是正确的：`HybridRetriever + FactStore + GenerateAgent + ReviewAgent`。但实际效果受以下问题限制：

1. `reference_submission/index` 当前没有可用 dense index 文件，线上大概率退化为 BM25 + FactStore。
2. BM25 只在窄化后的少量 chunk 上做检索，遇到中文报告、信源张冠李戴、事件日期类错误时召回不足。
3. FactStore 目前覆盖 EPS、revenue、net_income 和价格，无法覆盖 peers、sec_submissions、analyst rating、新闻事件、召回数量、CEO 原话等高频错误类型。
4. Review 只抽最多 15 个 claim，面对中文报告或密集表格时容易漏掉真正错误。
5. 证据裁决完全依赖单次 LLM，如果候选证据不干净，LLM 会把无关证据解释成错误，造成误报。

## 4. 高目标修改方案

### 阶段 A: 先把 train 打到可观分数

目标：公开 train 上 quote 级别召回显著提升，同时误报可控。

修改建议：

1. 增强 claim extraction：
   - 对数字、日期、季度、表格行、引用句、评级变更、信源归属分别抽取。
   - 中文报告不要只抽短语，优先抽整句、整条 bullet、整行表格。
   - 把 claim 上限从 15 提升到 30-50，并按类型分批审查。

2. 增加 deterministic verifier：
   - EPS actual / estimate / surprise / surprisePercent。
   - revenue / net_income / endDate。
   - price open / close / return 计算。
   - peer list。
   - SEC accession 与 filing date。
   - analyst rating / target price / EPS estimate。
   - 新闻事件日期、召回数量、引用原话。

3. quote 对齐策略：
   - 不输出短 phrase。
   - 先定位错误数字或日期所在的完整句子或表格行。
   - quote 必须是原文完整片段，接近 GT 标注风格。

4. train GT 驱动的错误类型归纳：
   - 数字篡改。
   - 时间线扭曲。
   - 因果反转。
   - 信源张冠李戴。
   - peer membership 错误。
   - return / YoY / QoQ 计算错误。

预期目标：

- train 严格 quote 命中率先达到 40%-60%。
- 语义命中率达到 70%+。
- 每篇误报控制在 0-1 条。

### 阶段 B: 提升 val/test 泛化

目标：不靠记忆 train request，而是把高频错误模式产品化。

修改建议：

1. 建立 Evidence Lookup 层：
   - 输入 ticker + claim type + period/date/event。
   - 返回结构化权威值和 source。
   - 避免把整篇报告直接丢给 BM25。

2. 建立中文金融错误模板：
   - “同比增长 X%”必须能反查原文或结构化数字。
   - “某媒体报道”必须能反查新闻 source。
   - “评级由 A 到 B”必须检查方向是否反了。

3. Adjudicator 改为保守二段式：
   - 第一段只判断 claim 是否与权威证据冲突。
   - 第二段把冲突映射为原文完整 quote 和简洁 reason。

4. 对无错误报告要更谨慎：
   - 没有强反证不输出。
   - 对 unsupported 与 contradicted 区分，优先只报 contradicted。

预期目标：

- val/test 上 issue-level precision 保持较高。
- 避免 baseline 那种 80+ 条 issue 的误报灾难。
- 对数字、日期、因果反转类错误形成稳定召回。

### 阶段 C: Generate 重新产出高质量报告

目标：10 个正式 generate 输出完整、高可信、有区分度。

修改建议：

1. 先补齐正式固定题：
   - 必须生成 `gen-1.md` 到 `gen-6.md`。
   - 删除或不提交 `gen-0001.md` 这种示例文件。

2. 重写 4 个自由题 topic：
   - 每个自由题必须指定 ticker、事件窗口、研究冲突和可验证判断。
   - 避免泛泛的“自选研究方向”。

3. 生成前做 evidence gating：
   - 题目 ticker 是 HD，就不允许 COST filing 作为核心事实来源，除非明确写作 peer comparison。
   - 每个 quantitative claim 必须来自 FactStore 或可定位 source。

4. 加入 post-generation audit：
   - 检查 source ticker 与主题 ticker 是否一致。
   - 检查是否有未引用数字。
   - 检查是否有 “not in source set” 这类违规表达。
   - 检查每个 `[SOURCE: ...]` 是否真实存在。

预期目标：

- 10 篇报告全部完整。
- 每篇至少 5 个真实 source，且来源覆盖 filing/research/news/prices 中至少 2-3 类。
- 无明显跨公司错引。
- 无无来源数字。
- 立场明确，且包含可证伪条件。

## 5. 推荐优先级

1. 最高优先级：修 review，因为它有公开 GT，可量化迭代，最容易拉分。
2. 第二优先级：补齐 generate 正式 10 篇，并修正自由题 topic。
3. 第三优先级：构建更强 FactStore 和事件索引。
4. 第四优先级：dense index。如果时间有限，先做结构化校验和规则召回，比盲目上 embedding 更直接。

## 6. 高要求目标

建议把内部目标定得更高一些：

1. train 集不满足于“看起来抓到错误”，而要追求 quote 粒度贴近 GT。
2. 所有数字类错误都必须用程序可复算，不交给 LLM 猜。
3. 所有日期类错误必须能定位到 filing filename、sec_submissions 或新闻日期。
4. 所有信源归属错误必须用新闻 source 或 filing source 反查。
5. generate 任何没有 source 支撑的数字都默认视为失败。

最终期望：

- Review: 高召回、高精度、quote 对齐稳定。
- Generate: 完整覆盖 10 题、事实扎实、证据链清楚、立场明确。
- 代码: 从“LLM 单轮判断”升级为“结构化校验 + 检索证据 + LLM 保守裁决”的可控系统。

