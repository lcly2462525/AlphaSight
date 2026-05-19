# ToolAgent 与 VL 扩展方案

## 1. 背景

当前 AlphaSight 的基础方法已经围绕细粒度检索展开：

- `filing` 按 SEC section 切块，保留 Item 1A / Item 7 / Item 8 等高价值段落。
- `news` 做标题和正文切块。
- `research` 与 `prices` 进入结构化 Fact Store。
- 在线阶段通过 QueryRouter、HybridRetriever、RRF 融合和 Compressor 生成 evidence。
- Review 任务中，部分数字和 filing date 已经走确定性核查，再交给 LLM adjudicator。

这个方向是正确的，但继续只增加检索粒度会出现边际收益下降。很多金融研报错误不是“找不到材料”，而是需要对数据做确定性计算、单位归一、时间窗口对齐和引用核查。因此下一阶段更适合引入 ToolAgent。

## 2. 核心判断

优先级应为：

```text
细粒度检索 + Python 确定性工具 + LLM 裁决 > 直接引入 VL 模型
```

原因：

1. 评测中的多数事实错误集中在数字、日期、财报周期、价格反应、增长率、单位、事件归因。
2. 这些问题更适合用 Python/pandas/规则工具精确计算，而不是交给 LLM 或 VL 模型推断。
3. VL 模型只在图片表格、截图公告、社交媒体图片、图表读数等场景有明显增益。
4. 当前主语料以 HTML、JSON、CSV 为主，VL 不应替代文本检索和结构化核算。

## 3. 建议新增 ToolAgent 层

新增一个固定工具注册表，而不是开放式让 LLM 任意执行 Python。

推荐架构：

```text
ClaimPlanner / QueryPlanner
  -> ToolRouter
      -> price_event_tool
      -> financial_metric_tool
      -> ratio_calc_tool
      -> filing_lookup_tool
      -> citation_check_tool
      -> social_signal_tool
  -> Writer / Adjudicator
```

ToolAgent 只负责产出结构化 evidence，不直接决定最终答案。最终生成报告或输出 issue 仍由 LLM writer/adjudicator 完成。

## 4. 工具设计

### 4.1 price_event_tool

用途：

- 校验股价涨跌幅。
- 分析事件窗口市场反应。
- 支撑 generate 中的 priced-in / not priced-in 判断。
- 抓 review 中的价格窗口、方向、幅度错误。

输入：

```python
{
    "ticker": "NVDA",
    "event_date": "2025-08-27",
    "window": [-1, 5],
    "frequency": "daily"
}
```

输出：

```python
{
    "ticker": "NVDA",
    "event_date": "2025-08-27",
    "start_date": "2025-08-26",
    "end_date": "2025-09-03",
    "start_close": 123.45,
    "end_close": 130.10,
    "return_pct": 5.39,
    "max_drawdown_pct": -2.14,
    "volume_change_pct": 18.2,
    "source": "prices/NVDA.csv"
}
```

实现要点：

- 使用 `prices/*.csv` 做日频分析。
- 如果存在 `prices_minute`，可对 earnings、8-K、重大公告做分钟级事件反应。
- 对非交易日自动滚动到最近交易日。
- 输出必须包含窗口边界和 source，方便 LLM 引用。

### 4.2 financial_metric_tool

用途：

- 查询和计算 EPS、revenue、net income、gross margin、operating margin、YoY、QoQ、TTM。
- 校验“增长/下降”“加速/放缓”“margin 扩张/收缩”等结论。

输入：

```python
{
    "ticker": "NKE",
    "metric": "revenue_yoy",
    "fiscal_year": 2026,
    "quarter": 2
}
```

输出：

```python
{
    "ticker": "NKE",
    "metric": "revenue_yoy",
    "fiscal_year": 2026,
    "quarter": 2,
    "value": 7.8,
    "current_revenue": 24150000000,
    "prior_revenue": 22400000000,
    "source": "research/NKE/financials_reported.json"
}
```

实现要点：

- 基于现有 `FactStore` 扩展，不重复读取 JSON。
- 对 fiscal year / calendar year 做显式标注。
- 所有派生指标保留分子、分母和 source。

### 4.3 ratio_calc_tool

用途：

- 统一单位和比例计算。
- 避免 LLM 在 million/billion、bps、百分比、margin、surprise 计算上出错。

支持能力：

- `million` / `billion` / `thousand` 单位归一。
- `bps` 与 percentage point 转换。
- margin、growth、surprise、P/E、return 的确定性计算。
- 近似匹配时输出 tolerance。

输出示例：

```python
{
    "formula": "(1.52B / 24.15B) * 100",
    "value": 6.29,
    "unit": "%",
    "interpretation": "net margin"
}
```

### 4.4 filing_lookup_tool

用途：

- 查询 filing form、filed date、accession。
- 定位 Item 1A / 7 / 8 / MD&A 中是否出现某个风险、事件、金额或管理层表述。
- 为 Review 的叙事类错误提供更权威的证据。

输入：

```python
{
    "ticker": "META",
    "form": "10-Q",
    "section": "Item 2",
    "query": "Reality Labs operating loss",
    "date_range": ["2025-01-01", "2025-12-31"]
}
```

输出：

```python
{
    "matches": [
        {
            "path": "filings/META/10-Q__2025-10-30__...htm",
            "section": "Item 2",
            "quote": "Reality Labs operating loss was ...",
            "score": 12.4
        }
    ]
}
```

实现要点：

- 复用现有 section-aware chunking。
- 对 Item 1A 风险题、Item 7/MD&A 经营讨论题做显式 section filter。
- 输出 quote 必须来自原文子串。

### 4.5 citation_check_tool

用途：

- 校验 generate 报告中的 citation 是否真实可追溯。
- 防止出现 source path 正确但 quote 改写、拼接或不存在的问题。

输入：

```python
{
    "report_markdown": "...",
    "evidence": [...]
}
```

输出：

```python
{
    "valid": true,
    "bad_citations": [],
    "missing_quote_sources": []
}
```

实现要点：

- 解析 `[SOURCE: <path> | "<quote>"]`。
- 检查 quote 是否是 evidence 或源文件文本的逐字子串。
- 对失败 citation 返回修复建议，由 SelfAudit 触发一次重写。

### 4.6 social_signal_tool

用途：

- 只作为辅助信号，不作为核心事实来源。
- 支撑“市场叙事”“投资者情绪”“社媒关注度”的轻量分析。

输出：

```python
{
    "ticker": "TSLA",
    "date_range": ["2025-10-01", "2025-10-31"],
    "tweet_count": 120,
    "top_keywords": ["recall", "battery", "delivery"],
    "bull_ratio": 0.41,
    "source": "social/TSLA/..."
}
```

## 5. 接入 GenerateAgent

当前 GenerateAgent 主要流程是：

```text
topic -> retriever.search(topic) -> writer -> self_audit
```

建议升级为：

```text
topic
  -> QueryPlanner 拆 2-4 个子问题
  -> HybridRetriever 检索文本证据
  -> ToolAgent 运行结构化工具
  -> EvidenceMerger 合并 facts / calculations / quotes
  -> Writer 写 grounded report
  -> SelfAudit 校验数字与 citation
```

示例：

```text
问题：某事件是否已被市场 priced in？

子查询：
1. 事件本身和管理层表述 -> filing/news retrieval
2. 事件日前后股价反应 -> price_event_tool
3. 财报中相关业务影响 -> financial_metric_tool
4. 同期社媒/新闻情绪 -> social_signal_tool
```

这样 writer 拿到的不只是文本片段，还有确定性计算结果。

## 6. 接入 ReviewAgent

当前 ReviewAgent 已经有：

```text
ClaimExtractor
  -> numeric_candidates
  -> date_candidates
  -> retrieval_candidates
  -> Adjudicator
```

建议增加：

```text
ClaimExtractor
  -> ClaimTypeRouter
  -> tool_candidates
      -> price_event_tool
      -> financial_metric_tool
      -> ratio_calc_tool
      -> filing_lookup_tool
  -> retrieval_candidates
  -> Adjudicator
```

候选 evidence 推荐格式：

```text
DETERMINISTIC TOOL FACT [tool=price_event_tool source=prices/NVDA.csv]
NVDA 2025-08-26 close=... to 2025-09-03 close=..., return=...
The claim says the stock fell 8%, but the verified window return is +5.39%.
```

关键原则：

- 工具只产出候选，不直接产出最终 `ReviewIssue`。
- 所有候选统一交给 adjudicator。
- 对 `DETERMINISTIC TOOL FACT` 的证据，prompt 应要求 adjudicator 高度信任。
- quote 必须逐字来自原报告。

## 7. 是否引入 VL 模型

### 7.1 不建议作为主路径

VL 模型不应替代现有检索和工具链。当前主要语料是：

- filing HTML
- news JSON
- research JSON
- prices CSV
- social JSON

这些数据大多可以通过文本解析、结构化抽取和 Python 计算处理。VL 对 EPS、revenue、price return、filing date、growth rate 等核心错误帮助有限。

### 7.2 VL 有价值的场景

VL 适合处理：

- filing 或 news 中嵌入的图片表格。
- 社交媒体图片中的公告截图、图表、产品图。
- HTML/PDF 中无法用文本解析提取的 chart。
- 图像中的 visible text、坐标轴、趋势线、表格单元格。

### 7.3 推荐方式：离线视觉抽取

不要在线每个 request 调 VL。推荐离线构建视觉事实：

```text
image / chart / screenshot
  -> VL or OCR
  -> visible text / markdown table / chart facts
  -> vision_facts.jsonl
  -> 进入普通 BM25 / dense / FactStore
```

输出示例：

```json
{
  "path": "news/NVDA/xxx.json#image_1",
  "ticker": "NVDA",
  "kind": "vision_fact",
  "extracted_text": "Data Center revenue increased ...",
  "table_markdown": "| Segment | Revenue | YoY | ... |",
  "confidence": 0.82
}
```

这样做的优点：

- 运行期稳定，不依赖在线 VL 推理。
- 视觉信息可以复用普通检索链路。
- 方便缓存、调试和消融。
- 避免 VL 模型与主 LLM 抢显存。

## 8. 推荐落地顺序

### P0：工具框架

- 新增 `reference_submission/tools/registry.py`。
- 定义统一 `ToolResult` 数据结构。
- ToolAgent 只允许调用白名单工具。

### P1：高收益确定性工具

- `price_event_tool`
- `financial_metric_tool`
- `ratio_calc_tool`
- `filing_lookup_tool`

### P2：接入 Review

- 新增 `_tool_candidates()`。
- 将价格、增长率、margin、单位错误转为 deterministic candidates。
- 继续由 adjudicator 统一裁决。

### P3：接入 Generate

- QueryPlanner 拆子问题。
- ToolAgent 输出进入 `FACTS` 段。
- SelfAudit 增加 citation check 和 ratio check。

### P4：离线 VL 抽取

- 仅当真实数据中图片/图表信号占比较高时投入。
- 输出 `vision_facts.jsonl`，并入普通检索。

## 9. 消融实验建议

为证明新增工具有效，建议做以下消融：

| 实验 | 配置 | 观察指标 |
|---|---|---|
| baseline | 细粒度检索 + FactStore | review F1 / generate 人评 |
| + price tool | 增加事件窗口价格核查 | 价格类错误 recall |
| + financial tool | 增加 YoY/QoQ/margin 核查 | 数字类错误 recall |
| + citation tool | 生成后引用校验 | citation faithfulness |
| + VL offline | 加 vision_facts | 图片/图表相关样本收益 |

如果评测集主要是文本和结构化数字，前 3 个工具的收益应明显高于 VL。

## 10. 总结

当前系统不缺“更长上下文”，也不只是缺“更强模型”。更关键的是把金融任务中可计算、可验证、可复现的部分从 LLM 中拆出来。

推荐主线：

```text
细粒度检索负责找证据
Python ToolAgent 负责算事实
LLM 负责规划、写作和裁决
VL 只负责离线补足图片/图表证据
```

这条路线更稳定、更容易做消融，也更符合离线评测环境。
