# review_agent news 检索实施方案

## 目标

首要目标是提升 news 召回：先能找到与报告 claim 相似、覆盖同一事件/数字/日期/方向的新闻，再交给现有 grounded review 判断是否矛盾。

## 依据

`docs/news-coverage.md` 的实测结论显示，新闻库对三类问题最有效：

- 数字精确替换：EPS 增速、召回量、股息 CAGR、年涨幅、分析师 EPS 目标。
- 日期偏移：财报电话会日期、股东会日期、事件发布日期。
- 方向/措辞反转：upgrade/downgrade、refuted/admitted、no signs of/resistance 等。

因此实现不追求复杂语义检索，优先使用 ticker 约束下的 news-only BM25 宽召回，并保留数字、日期、机构名、方向词等高信号 token。

## 实施计划

1. 在 `HybridRetriever` 增加专用 `search_news()` 接口。
   - 只检索 `kind == news`。
   - ticker 优先限定；没有 ticker 时允许全 news 退化检索。
   - 默认不使用年份硬窗口，避免 FY2026/2025 表述错配导致新闻被过滤。
   - 候选上限高于通用检索，目标是召回优先。
2. 在 `ReviewAgent` 增加 `_news_evidence_pool()`。
   - 对每条 claim 生成一个宽 query：ticker + 原文 quote + `q_en` + 高信号 token。
   - 对数字/日期/方向/信源类 claim 优先检索。
   - 去重后汇总为 SOURCE 块，作为独立 news-only evidence pool。
3. 保持裁决逻辑保守。
   - 本次不直接 emit news issue，避免赶工引入误报。
   - 通用 evidence 和 news-only evidence 分别跑 `grounded_review`，候选取并集后统一进入 `filter_candidates`。

## 当前进度

- 已阅读 `news-coverage.md`，确认 P0 目标是 BM25 召回数字/日期/方向类新闻。
- 已定位代码入口：`reference_submission/agents/review.py` 的 `_evidence_pool()` 和 `reference_submission/retrieval/base.py` 的 `HybridRetriever.search()`。
- 已实现 `HybridRetriever.search_news()`：
  - `kind == news` 专项检索。
  - ticker 约束下候选上限提高到 8000，单 ticker 时优先并尽量限定到 `news/<ticker>/` 公司对应文件夹。
  - 默认不启用年份窗口，避免 FY2026/2025 表述错配漏召回。
  - 对每篇新闻去重，只返回最相关片段。
- 已实现 `ReviewAgent._news_evidence_pool()`：
  - 优先选择数字、日期、方向、信源、价格/涨跌类 claim。
  - 对每条 claim 用 `ticker + 原文 + 英文翻译 q_en + 高信号 token` 检索。
  - news evidence 不再混入通用 evidence；通用 evidence 会过滤 `news/`，news-only 单独跑 grounded check，最后和原有候选取并集。
  - 当报告 primary ticker 明确时，news 分支优先锁定 primary ticker，避免 `AI` 这类短 ticker 或多 symbol 标注把检索扩到其他公司目录。
- 已补强误报防线：
  - 找不到相关 news/filing 证据时不报错。
  - source/fact 与 report match 时不报错，禁止 "data matches but contradiction" 这类假阳性。
  - 正常四舍五入、近似措辞、单位表达差异不报错。
- 已按 recall-first 目标调整两阶段逻辑：
  - 第一阶段 `ReviewAgent._grounded_check_detailed()`：通用 evidence 与 news-only evidence 各自独立筛选，返回 `issues` 和 `rejected`。第一阶段 `issues` 直接进入最终候选，不再被第二阶段过滤。
  - 第二阶段 `ReviewAgent._revive_rejected_detailed()`：只处理第一阶段 `rejected`，做复活赛。只要可能有矛盾或不确定就 `revive` 放回最终 issues；只有明确 match、rounding、opinion、无可检查事实等才保留为 rejected。
  - `ReviewAgent.last_review_debug()` 可读取最近一次 run 的调试输出：`stage1_rejected`、`revived`、`final_rejected`、`final_grounded`。
  - 本地 `reference_submission/run.py review` 现在输出两个 JSONL：`review.jsonl` 是最终 issues；`review_rejected.jsonl` 是仍被杀掉的 rejected，并包含 `revived` 与 `stage1_rejected` 便于追踪。
- 已通过 `python3 -m py_compile reference_submission/retrieval/base.py reference_submission/agents/review.py`。
- 已跑离线召回小样例：
  - TSLA recall query 命中 `news/TSLA/...` battery connection failure recall。
  - NKE JPM upgrade/EPS query 命中 JPMorgan analyst upgrade / EPS estimate 相关文章。
  - NVDA Huang AI bubble query 命中 "Huang refuted the notion of an AI bubble" 相关文章。
  - NEE 9.4% adjusted EPS growth query 可命中 `news/NEE/136536602.json`，但排位不是所有 query 下都第一；当前满足“先能找到类似/包含目标”，后续可再加数字字段 boost。
- 已发现并修复重复新闻问题：同一新闻会复制到多个 ticker 目录，现按文件 basename 去重，并在单 ticker 检索时优先 `news/<ticker>/...` 路径。
- 已优化性能：ticker 级 news BM25 缓存，首次构建后同 ticker 后续 query 从数秒降到约 0.1 秒。

## 后续可优化

- 对 claim 中出现的百分比/日期做轻量 boost，让 NEE 这类精确数字文章更靠前。
- 为 provider/source attribution 单独读取 JSON provider/source 字段，当前主要依赖标题和正文。
