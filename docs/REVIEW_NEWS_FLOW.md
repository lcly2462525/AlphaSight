# Review 任务中 news 的使用流程

> 对应代码：`reference_submission/agents/review.py`、`reference_submission/retrieval/base.py`、
> `reference_submission/retrieval/router.py`、`reference_submission/catalog.py`、
> `reference_submission/tools/build_news_event_catalog.py`、`reference_submission/prompt_templates/grounded_review.md`
>
> 适用版本：`main` @ `4707cbc`（news_merged 事件流以 catalog 增量方式接入共用检索）。

## 0. 背景：两条 news 通道并存

检索完全由 catalog 驱动，`HybridRetriever` 是 generate 与 review **共用的唯一入口**，
所以一处改动两个任务同时生效。news 现在有两条通道，**增量并存，不是替换**：

| 通道 | 匹配内容 | 来源 | 容量 `_CAND_CAP` |
|---|---|---|---|
| `news`（原有，未改） | 原始 news 全文：标题单独成块 + 正文 800 字滑窗（120 重叠） | `news/<T>/<hash>.json` | 400 |
| `news_event`（新增） | 抽取后的单句事件 `[EVENT 日期 \| 极性 \| src: 出处 \| via 提供方 \| scope] 一句话` | news_merged 事件流，经离线构建写入 catalog 增量文件 | 300（前排预留名额） |

- 事件流覆盖全部 50 个 ticker，不依赖原始 news 是否解压齐；原始 news 缺的公司至少有事件句兜底。
- 每条事件的 `path` 指回真实 `news/<T>/<hash>.json`，同一篇报道既能以"一句话要点"命中，又能以"全文窗"命中，两种粒度互补。
- 组委会提供的 `catalog.jsonl` 永不被改写；事件行写在独立增量文件，
  由 `ALPHASIGHT_CATALOG_SUPPLEMENT` 指向，文件不存在时行为与改动前完全一致。

## 1. Review 整体流程

`ReviewAgent.run(report)` 顺序：

1. **抽取声明** `_extract()`：从研报抽出一条条 claim（quote）。
2. **锁定主体** `_primary_ticker()`：定出主体 ticker（即后续检索的 `tickers`）。
3. **中文翻译** `_attach_translations()`：把中文 claim 翻成英文关键词挂到 `c['q_en']`，
   让中文研报也能命中英文 news / 事件流。
4. **确定性层** `_veto_exact()`：earnings / financials / prices 精确比对，**不走 news 检索**。
5. **结构事实** `_facts_block()`：FactStore 的财报数字块。
6. **★ news 检索（唯一入口）** `_evidence_pool(primary, claims)`，见第 2 节。
7. **分段** `_split_sections()`：研报切成若干 section。
8. **逐段核查** `_grounded_check(evidence, facts, sections)`：每个 section 配上
   **同一份**预取的 news 证据 + facts，喂给 `grounded_review.md` 让模型挑错，见第 3 节。
9. `_filter_candidates()` → 输出 `ReviewIssue` 列表。

news 只在第 6 步被取**一次**，之后复用到每个 section。

## 2. news 如何被检索（第 6 步展开）

`_evidence_pool()` 内部：

1. 拼检索 query `q` = 主体 ticker + 每条 claim 的信号词 `_claim_signal()`（数字 / 日期 / 期间）
   + 英文翻译 `q_en` + 出处类 claim 的原文片段。
2. 调用共用检索：`res = self.retriever.search(q[:4000], top_k=20, tickers=primary)`。
3. 进 `HybridRetriever.search()`（`top_k=20`）：
   - `_narrow_chunks`：`filter_docs` 按 ticker / 时间窗筛 → 按 kind 分组
     - `news`（cap 400）→ `doc_text` 读原始 json → `chunk_doc` 切标题块 + 正文 800 字窗
     - `news_event`（cap 300）→ 直接取 catalog 行里的 `event_text`，**零文件 IO**，一句话一块
   - 全体 chunk 跑 BM25 → `sparse` 取分>0 的前 `top_k*4 = 80`
   - **事件独立 BM25 通道**：事件单独打分（短句不会被长 filing/social 挤出截断），
     取前 `top_k//2 = 10` 条作为 `event_lead`
   - **原文扩展**：对 `event_lead` 前 `_EVENT_ORIG_EXPAND = 3` 条事件，按其
     `path`（= source_paths[0]，真实 `news/<T>/<hash>.json`）读原文 →
     **走与 `news` 完全相同的 `chunk_doc(...,"news")` 分块**（标题块 + 800 字窗）
     → 对该原文各窗单独 BM25，保留与 query 最匹配的 **1 个窗** → `orig_lead`。
     原始文件缺失（该 ticker 未解压）时 `doc_text` 返回空，静默跳过，事件句仍独立成立。
   - `weighted_rrf` 融合（`news_event` 偏置 > 该 route 自身的 `news` 偏置）
     → `fused = (event_lead + orig_lead) + 其余去重`
   - 逐块 `compress_chunk`，取满 `top_k=20` 条 / `_TOTAL_BUDGET=12000` 字 → `[(path, snippet)]`
4. `res.evidence_block()` 拼成 `---\n[SOURCE: <path>]\n<snippet>`，截断到 9500 字 → `evidence`。

结果：这 20 条证据里 **前约 10 条是事件句**
`[EVENT 日期 | 极性 | src: 出处 | via 提供方] …`，紧跟着前 3 条事件各自的**原文最佳窗**
（带事件句省略掉的细节数字/上下文），其余是通用 `news` 正文窗 / filing / social。

> 两层原文保障：①通用 `news` 通道独立全文分块检索（广覆盖，仍在 `fused` 里）；
> ②对最高信号的前几条事件做**确定性原文配对**（窄而准）。互补，不重复（按
> `(path, text[:64])` 去重）。

### 为什么需要事件独立通道

单句事件在共享 BM25 池里词频低、长度短，会被长 filing/social chunk 压到
`top_k*4` 截断线以下，融合阶段的 `kind_bias`（基于排名的 RRF 重加权）无法把
"根本没进融合集"的条目救回来。因此事件单独打分 + 预留前排名额，确保高信号事件
确定性地进入证据并排在原始 news 之上（对应 FactStore 那种独立通道思路）。

## 3. news 在核查里如何被用（第 8 步）

`_grounded_check()` 对每个 section 调一次模型，prompt = `grounded_review.md`，填三样：

- `{facts}`：FactStore 结构事实
- `{evidence}`：第 2 节那份 news 证据池（**所有 section 复用同一份**）
- `{section}`：当前段落原文

模型据此判断该段是否与证据矛盾，挑出 quote / reason。news 信号正好对上 review 要查的四类植入扰动：

| 扰动类型 | 命中的 news 信号 |
|---|---|
| 正负反转 | 事件句的 `极性 bearish/bullish` 与原文措辞 |
| 出处张冠李戴 | 事件句 `src: <attributed_to>` |
| 日期篡改 | `[EVENT <日期>]` + 原始 news `published_at` |
| 数字篡改 | 事件句 / 原文正文窗里的数字 + FactStore facts 交叉 |

## 4. 运维 / 复现

事件增量文件由离线构建器生成（一次性，可幂等重跑）：

```bash
python reference_submission/tools/build_news_event_catalog.py \
  --news-merged dataset/corpus/news_merged \
  --out dataset/news_event_catalog.jsonl
```

- 输入：`dataset/corpus/news_merged/<TICKER>.jsonl`（50 文件，149,317 行）
- 去重（按 `event_id`，跨多 ticker 文件合并 symbol）→ **100,028 条唯一事件**
- 输出：`dataset/news_event_catalog.jsonl`（gitignore，数据不入库；构建器入库可复现）
- `run.sh` / `run.py` 自动把该文件挂到 `ALPHASIGHT_CATALOG_SUPPLEMENT`；
  `catalog.load_catalog()` 检测到存在即增量拼接，不存在则零影响。

## 5. 一句话总结

Review 全程只在 `_evidence_pool` 取**一次** news：事件句优先置顶 → 前几条事件确定性
配上各自原文最佳窗 → 通用 `news` 全文分块通道兜底广覆盖；这同一份证据复用到每个
section 的对照核查。事件句负责高精度的极性 / 出处 / 日期信号，原文窗补充细节数字，
二者互补，覆盖四类植入扰动。
