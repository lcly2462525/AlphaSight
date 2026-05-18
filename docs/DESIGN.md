# AlphaSight 系统设计文档

> 目标：在**离线约束**下，对 117K 文档 / 2.4GB 多源语料做到「信息尽量不丢 + 检索高效」，
> 并以此驱动一个能「写研报」也能「审研报」的双 Agent 系统。

---

## 1. 数据画像（设计的出发点）

| kind | 文档数 | 体积 | 单文件 | 性质 | 处理定位 |
|---|---|---|---|---|---|
| filing | 1,077 | 1.2G | ~1MB（10-K/10-Q 巨大） | 半结构化 HTML，**洞察金矿**（Item 1A/7/8） | 分节切块 → 向量+BM25 |
| news | 97,266 | 384M | 几 KB | 短 JSON，数量主体 | 标题+导语切块 → 向量+BM25 |
| research | 350 | 525M | ~1.5MB | **结构化** JSON（earnings/financials/估值） | 字段抽取 → Fact Store（不做文本检索） |
| social | 18,250 | 264M | 中等 | 推文袋，噪声高、信号弱 | 按 ticker+日聚合 → 情绪信号 |

**关键判断：**
- `research` 是结构化数字，走 BM25/embedding 是浪费且不精确 → **单独抽成可精确查询的 Fact Store**。
- `filing` 单文件过大，全文截断会丢掉 Item 1A/Item 7 的关键洞察 → **按 SEC 章节切块**，是「信息保全」的核心战场。
- `news` 数量决定索引规模（97K），是 embedding 成本瓶颈 → 只 embed 标题+导语，正文按需懒加载。
- `social` 信噪比低 → 不进主检索，仅作为情绪辅证（可选）。

---

## 2. 总体架构

```
┌────────────────── 离线索引阶段（build_index.py，跑一次）──────────────────┐
│  raw corpus                                                              │
│    ├─ filing  ─► 章节切块 ─┐                                              │
│    ├─ news    ─► 标题切块 ─┼─► Qwen3-Embedding-8B (batch GPU) ─► FAISS    │
│    │                       └─► BM25 tokenized index                      │
│    ├─ research ─► 字段抽取 ───────────────────────────► Fact Store (SQLite)│
│    ├─ prices   ─► OHLCV 解析 ───────────────────────────► Fact Store      │
│    └─ social   ─► 按 ticker+日聚合情绪 ──────────────────► Signal Store    │
│  产出落盘到 reference_submission/index/（gitignored，可重建）              │
└──────────────────────────────────────────────────────────────────────────┘
                                  │
┌──────────────────── 在线查询阶段（每个 request）─────────────────────────┐
│  topic / report                                                          │
│    │                                                                     │
│    ▼  QueryPlanner: 解析 ticker / 时间窗 / 子问题                          │
│    ▼  QueryRouter:  规则判 query 意图 → 两路权重 + Fact 开关 + kind 偏置   │
│    ▼  HybridRetriever:                                                    │
│         ├─ Dense:  query embed → FAISS ANN top-N                          │
│         ├─ Sparse: BM25 top-N                                            │
│         ├─ Fusion: 加权 RRF（权重由 Router 给）→ rerank                    │
│         └─ Fact lookup: Fact Store 精确查（数字/估值/价格）               │
│    ▼  Compressor: 块内句子级压缩 → 受预算控制的 evidence                   │
│    ▼  GenerateAgent / ReviewAgent                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

设计三原则：
1. **重计算离线化**：8B embedding 只在离线 batch 跑，在线只 embed query（1 次）。
2. **结构化与非结构化分流**：数字进 Fact Store 精确查，文本进 Hybrid 检索。
3. **信息保全靠分块策略，不靠塞长文本**：用更细粒度的块 + 块内压缩，而非全文截断。

---

## 3. 检索方案（核心）

### 3.1 为什么用 Hybrid（BM25 + Embedding）

| | BM25（稀疏） | Qwen3 Embedding（稠密） |
|---|---|---|
| 强项 | 精确术语、ticker、财务科目名 | 语义、同义改写、跨源叙事 |
| 弱项 | 同义/语义关联抓不到 | 精确数字/专有名词易漂移 |
| 离线成本 | 低 | 高（8B，需 GPU batch） |

金融文本里**精确术语**（"deferred revenue"、"Item 1A"）和**语义关联**（"供应链压力" ↔ "component shortage"）都重要 → 单一通道都不够，用 **RRF 融合**：

```
score_rrf(d) = 1/(k + rank_bm25(d)) + 1/(k + rank_dense(d))   # k=60
```

RRF 无需归一化两路分数，鲁棒、零调参，适合 baseline。

### 3.2 QueryRouter（两路加权路由，非二选一）

固定 1:1 RRF 没有利用 query 意图。Router 用**规则**（零 LLM、确定性）把 query 分类，
输出两路权重与检索偏置；**两路始终都跑，只调配比**，因此严格不劣于固定 RRF，
且不损失召回。

**分类信号 → 路由决策：**

| query 意图 | 触发信号（规则） | w_sparse | w_dense | 其他偏置 |
|---|---|---|---|---|
| 数值/财报类 | 数字、`revenue/EPS/margin/guidance`、比较词 | 高 | 低 | `use_fact_store=on` |
| 叙事/因果类 | `影响/原因/趋势/reversal/narrative/为什么` | 低 | 高 | filing 偏重 |
| 事件类 | 日期、`8-K/announce/launch/acquisition` | 中 | 中 | 收紧时间窗 + news 偏重 |
| 默认/混合 | 以上均不强 | 均衡 | 均衡 | — |

**加权融合公式：**
```
score(d) = w_sparse · 1/(k + rank_bm25(d)) + w_dense · 1/(k + rank_dense(d))   # k=60
```

**输出契约：**
```python
@dataclass
class RouteDecision:
    w_sparse: float
    w_dense: float
    use_fact_store: bool
    kind_bias: dict[str, float]      # 各 kind 的召回配额倾斜
    item_filter: list[str] | None    # 风险题 → 限定 filing 的 Item 1A
    tighten_window: bool             # 事件题 → 收紧时间窗
```

- 纯规则实现，可单测、可消融对比（router on/off）。
- 不做硬切换：即使判为「数值类」，dense 仍以低权重参与，避免漏掉语义证据。
- 与 §4 的题型自适应衔接：题型已知时 Router 可直接吃题型标签，规则只作兜底。

### 3.3 Embedding 模型使用

- 模型：`Qwen/Qwen3-VL-Embedding-8B`（多模态嵌入，仅用文本通道）。
- **多后端 + 硬降级**（`embedder.py`），按序尝试：
  1. **OpenAI 兼容 `/v1/embeddings` endpoint（首选）** —— 评测机用 vLLM 起嵌入服务，进程内不加载，避开 VL 加载坑 + 与推理 LLM 抢显存。
  2. `sentence-transformers`（`trust_remote_code`）。
  3. `transformers` `AutoModel` + last-token pooling（Qwen embedding 风格）。
  4. 全失败 → 返回 None，HybridRetriever 静默退「纯 BM25」，任何环境不崩。
- **Instruction 感知**：Qwen3 embedding 对 query 加 `Instruct: ...\nQuery: ` 前缀，document 不加；`encode(is_query=)` 区分，混用会掉召回。
- **离线**：document 批量编码 → `index/dense.faiss`(IndexFlatIP) + `chunk_meta.jsonl`。
- **在线**：query 编码 1 次（带 instruction）→ FAISS `search(top_N)`，限定在 BM25 narrowed 路径内。

### 3.4 信息保全：按 kind 差异化切块

这是「尽量不丢信息」的关键。**不做全文截断**，按来源结构切：

**filing（最重要）—— 章节感知切块：**
```
HTML → 去标签 → 按 SEC Item 边界切段
   ├─ 识别 "Item 1A. Risk Factors" / "Item 7. MD&A" / "Item 8" 标题锚点
   ├─ 每个 Item 内再按 ~1000 char 滑窗（overlap 150）切 chunk
   └─ chunk meta 带 {item, form, ticker, date}  ← 检索时可按 Item 过滤
```
好处：风险归因题直接定位 Item 1A，不被无关章节稀释；长文档不丢中后段。

**news —— 标题优先切块：**
```
title 单独成一个高权重 chunk
body 按 ~800 char 切块（overlap 120）
检索命中 body chunk 时，回挂 title 一起进 evidence（保留上下文）
```

**research —— 不切块，字段抽取进 Fact Store：**
```
earnings.json     → (ticker, fy, q, eps_actual, eps_est, surprise)
financials.json   → (ticker, fy, q, revenue, net_income, yoy)
估值/评级字段     → (ticker, date, rating, target_price, analyst)
摘要性文本字段    → 单独 embed（summary/conclusion 仍有语义价值）
```

**social —— 聚合不保原文：**
```
按 (ticker, date) 分组 → 计数 + 关键词袋 + 粗情绪分
→ Signal Store: (ticker, date, tweet_count, bull_ratio, top_keywords)
（不进向量库；GenerateAgent 需要时按 ticker+window 拉信号）
```

### 3.5 在线压缩（块内）

检索回来的 chunk 仍可能偏长，进 prompt 前做**句子级压缩**：

```
chunk → 句子切分 → 每句按 query token 交集打分
      → 贪心填充 char 预算 → 恢复原文顺序拼接（" ... " 连接）
```
- filing 优先保留含**数字/百分比/日期**的句子（金融洞察密度高处）。
- 全局 char budget（如 ≤ 8000）跨 evidence 硬上限，防止 prompt 溢出。

### 3.6 统一检索接口

```python
class HybridRetriever:
    def search(self, query: str, *, tickers, window, top_k=10,
               route: RouteDecision | None = None) -> RetrievalResult:
        r = route or self.router.decide(query, tickers, window)
        facts  = (self.fact_store.lookup(tickers, window)
                  if r.use_fact_store else [])                  # 结构化精确
        signal = self.signal_store.lookup(tickers, window)      # 情绪辅证
        dense  = self.faiss.search(self.embed(query), N)
        sparse = self.bm25.search(tokenize(query), N)
        fused  = weighted_rrf(sparse, dense,
                              r.w_sparse, r.w_dense,
                              kind_bias=r.kind_bias,
                              item_filter=r.item_filter)         # 文本证据
        comp   = [compress(c, query) for c in fused[:top_k]]
        return RetrievalResult(facts=facts, evidence=comp, signal=signal)
```

---

## 4. Generate Agent

```
topic
  ▼ QueryPlanner    解析 ticker/窗口 + 按题型展开 1~3 子查询
  ▼ HybridRetriever 每个子查询各检索 → 去重合并
  ▼ Writer          填 grounded_generate.md：FACTS 段 + EVIDENCE 段
  ▼ SelfAudit       抽 draft 数字/日期 → 与 Fact Store 核对 → 矛盾则 1 次纠正
  ▼ Report (≤1000 字，每条断言 [SOURCE: path])
```
- 题型自适应：6 固定题型各配一个子查询模板（财报解读→拉 earnings+MD&A；市场反应→拉 prices+news；叙事反转→拉前后两窗对比）。
- SelfAudit 用结构化核对为主，省 token、抓硬伤。

## 5. Review Agent

```
report_markdown
  ▼ ClaimExtractor   LLM 抽可验证声明（数字/日期/归因），quote 逐字来自原文
  ▼ 两路候选生成（逐条 claim）：
      · 数字类 → 解析 (ticker, FYxxQx, 指标) → Fact Store【按周期取那一行】
                 → 与声明数值比；不一致则生成候选，并把【权威值】作为 evidence 附上
      · 其余   → Hybrid 检索证据作为 evidence
  ▼ Adjudicator     所有候选（含确定性数字候选）统一过【一次 LLM 裁决】
                    LLM 拿着权威 fact 做最终判断：确认真错 / 丢弃误报
  ▼ list[ReviewIssue]（quote 必须逐字来自原文）
```
- **逐条周期对齐**：声明里解析出财年/季度 + 指标（EPS/revenue/net_income），
  到 Fact Store 取**那一个周期的那一行**比对，能抓「右数错季」「营收对不上」，
  比旧版「跟所有季度集合反证」精确得多。
- **确定性不直接出 issue**：数字核查只产出「带权威值的高精度候选」，
  仍交 LLM 终判 —— 解析误报（数字对但指标/口径不同）被 LLM 丢弃；
  比赛对误报扣分，这一步把确定性的高召回与 LLM 的高精度结合。
- 周期解析覆盖 `FY26 Q1` / `FY2026Q3` / `first quarter of fiscal 2026`
  / `Q1 2025` 等形态；解析不到周期时退化为全周期集合反证（仍过 LLM）。
- 单次 LLM 裁决批处理所有候选，控延迟与成本。

---

## 6. 文件结构

```
reference_submission/
├── submission.py            # Orchestrator（薄调度层）
├── build_index.py           # 离线索引构建入口
├── retrieval/
│   ├── base.py              # HybridRetriever + RetrievalResult
│   ├── embedder.py          # Qwen3-Embedding 封装（+ BM25 fallback）
│   ├── dense.py             # FAISS 建/查
│   ├── sparse.py            # BM25 建/查
│   ├── router.py            # QueryRouter：规则路由 → RouteDecision
│   ├── fusion.py            # 加权 RRF（权重由 router 给）
│   ├── chunking.py          # 按 kind 切块（filing 章节感知）
│   ├── compress.py          # 块内句子级压缩
│   ├── fact_store.py        # research/prices 结构化抽取与查询
│   └── signal_store.py      # social 情绪聚合
├── agents/
│   ├── generate.py          # Planner + Writer + SelfAudit
│   └── review.py            # Extractor + Verifier + Adjudicator
├── prompt_templates/
│   ├── grounded_generate.md
│   ├── extract_claims.md
│   └── adjudicate.md
├── index/                   # 离线产出（gitignored，可重建）
│   ├── dense.faiss
│   ├── chunk_meta.jsonl
│   ├── bm25.pkl
│   ├── facts.sqlite
│   └── signals.sqlite
├── catalog.py / llm.py / schemas.py / run.py   # 不动
```

---

## 7. 实现优先级

| 阶段 | 内容 | 验收 |
|---|---|---|
| P0 | `chunking.py` + `sparse.py` + `fact_store.py`：纯 BM25 + Fact Store 跑通 | generate/review 不依赖 GPU 可跑 |
| P1 | `embedder.py` + `dense.py` + `build_index.py`：离线建 FAISS | 索引落盘，在线 ANN 可查 |
| P2 | `router.py` + `fusion.py` 接入 → HybridRetriever 完整 | 加权 RRF 生效，router on/off 可消融 |
| P3 | `agents/`：Planner / SelfAudit / Verifier 精化 | 消融对比提分 |
| P4 | `signal_store.py` + 题型自适应模板 | 覆盖 6 题型 + 自由题 |

---

## 8. 工程权衡

- **离线 vs 在线**：8B embedding 重，全部离线 batch；在线只 1 次 query 编码 → 满足离线约束且低延迟。
- **信息保全 vs 成本**：filing 章节切块保住高价值段；news 只 embed 标题导语控规模（97K）；research 不进向量库（结构化精确查更优）。
- **路由 vs 召回**：Router 只调两路权重不做硬切换，最坏退化为等权 RRF，不损失召回；纯规则零 LLM，可单测、可消融（router on/off 是答辩里的天然 ablation）。
- **鲁棒性**：embedding 不可用自动退 BM25；Fact Store 缺失自动跳过；任何环境 `run.py` 不崩。
- **可复现**：`index/` 全部由 `build_index.py` 从 dataset 重建，不入 git。

---

## 9. 待定 / 风险

1. Qwen3-VL-Embedding-8B 的文本编码 API/维度需在云端确认（输出维度、是否需 instruction prefix）。
2. filing 的 Item 锚点正则需用真实样本校准（不同 form 模板差异）。
3. FAISS 索引类型按最终 chunk 总量定（< 50 万用 Flat，更大用 IVF）。
4. research JSON 的字段 schema 需抽样确认键名。
