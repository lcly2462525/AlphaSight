# AlphaSight 时间戳分析与归一化方案

> 用途：把整个 `dataset/` 里时间戳的**真实形态、数据质量缺陷、对"时间戳扭曲"检测的影响**钉死，并给出一套可落地的**归一化/结构化方案**，使 Review Agent 能用统一时间模型跨源比对、稳定抓出时间线扭曲。
> 编写：Clara，2026-05-19。配套 `RESEARCH.md` / `REVIEW.md` / `review_plan_v2.md`。
> 方法：本机所有 python 仅 numpy（无 pandas/pyarrow），所有结论均由**实测样本 + parquet footer 明文/pandas 元数据硬解析**得到，无推测。parquet 一项已彻底闭合。

---

## 0. 一句话结论

整个数据集有 **8+ 种互不兼容的时间戳格式**，绝大多数**无时区**且采用**互相矛盾的隐含约定**（news=UTC、filings/financials=ET 裸时间、sec acceptance=UTC、twitter=+0000、fetched_at=2026 未来抓取时间）。同一份 filing 的日期在 4 个源里以 3 种格式出现且**会跨日不一致**（ET 收盘后申报 → UTC 滚到次日甚至跨年）。这正是"时间戳扭曲"攻击面，也是当前 Review 只能字符串比对、既漏又误的根因。解决办法是把所有时间事实压成单一规范结构 `TimeAnchor`，并预生成可查询的时间锚索引。

---

## 1. 各类数据时间戳形态（实测）

| 来源 | 时间字段 | 实测样例 | 格式族 | 时区 | 精度 |
|---|---|---|---|---|---|
| `corpus/news/*/*.json` | `published_at` | `2025-09-17T14:43:00Z` | ISO-8601 Z | **UTC 显式** | 秒 |
| `corpus/filings/*.htm`（文件名） | `FORM__YYYY-MM-DD__ACC.htm` | `10-Q__2025-01-31__0000320193-25-000008.htm` | 纯日期 | 无（隐含 ET 申报日） | 日 |
| `catalog.jsonl` | `timestamp` | filing=`2025-01-03`；news=`…T..:..:..Z`；research=`""` | 混合两族 + 空串 | 混合 | 日/秒/无 |
| `research/earnings.json` | `period`+`quarter`+`year` | `period:'2025-12-31', quarter:1, year:2026` | 日期 + 财务整数 | 无 | 日 + **财历≠日历** |
| `research/filings.json` | `filedDate`/`acceptedDate` | `2025-12-05 00:00:00` / `2025-12-05 16:31:42` | 空格分隔无 T | 无（ET） | filed=日 / accepted=秒 |
| `research/financials_reported.json` | `startDate/endDate/filedDate/acceptedDate`+`year/quarter`（字符串） | `endDate:'2025-10-31 00:00:00'`, `year:'2026'`, `quarter:'3'` | 空格分隔 | 无（ET） | 日/秒 |
| `research/sec_submissions.json` | `filingDate`/`acceptanceDateTime`/`reportDate`（列式数组） | `'2025-12-31'` / `'2026-01-01T02:09:16.000Z'` / `'2025-12-30'` | 纯日期 + ISO 毫秒 Z | 混（UTC + 无） | 日/毫秒 |
| `research/*.json` `_meta.fetched_at` | 抓取时间 | `2026-04-28T06:09:02.160681` | ISO 微秒 | **无，且在 2026（未来）** | 微秒 |
| `corpus/social/*/twitter_DATE.json` | 文件名 + 每条 `created_at` | `Wed Jan 01 15:00:02 +0000 2025` | **RFC-822/Twitter，英文 locale** | +0000 | 秒 |
| `prices/*.csv` | `date` | `2025-01-02` | 纯日期 | 无（交易日） | 日 |
| `prices_minute/*/YYYY-MM.parquet` | `ts_utc` | datetime64[ms] | **UTC（tz-aware，显式）** | **UTC** | 毫秒 |

**catalog.jsonl 全量**（116,943 行）：filing 1077 / news 97266 / social 18250 / research 350。timestamp 三种形态：`YYYY-MM-DD`（19327，含 social）、`…TZ`（97266）、空串（350，全是 research）。
**news**：抽样 8000 篇 `published_at` 100% 规整（无缺失、无变体）——唯一干净的一类。
**prices_minute parquet**（全 ticker/月份同构，pyarrow 24.0.0 写出，无 index 列）：

| 列 | 类型 | 关键点 |
|---|---|---|
| `ts_utc` | `datetimetz` / `datetime64[ms]`，timezone 显式 = UTC | 全数据集**最干净**的时间字段，无需归一 |
| `open/high/low/close/vwap` | float64 | |
| `volume` int64 / `transactions` int32 | | |
| `session` | unicode，取值 ∈ **`{pre, regular, post}`** | 盘前/常规/盘后，直接支撑"休市/错会话时点报价"检测 |

---

## 2. 数据质量 / 需清洗的问题（按对任务的危害排序）

1. **【最高危】同一份 filing 有 3+ 个日期、3+ 种格式且会跨日不一致。**
   例：filename/catalog=`2025-12-31`、`sec_submissions.filingDate=2025-12-31`、但 `acceptanceDateTime=2026-01-01T02:09:16Z`（ET 收盘后申报 → UTC 滚到次日，甚至跨年）。报告说"Jan 1 2026 申报"还是"Dec 31 2025"——取决于取哪个字段/哪个时区，**两边都"有据"**。GT report_02（错备案日）即考这个。
2. **财历 vs 日历季混淆。** `earnings.json.period` 是 Finnhub 的**日历季末标签**（`2025-12-31`），`year/quarter` 是**财季**；`financials_reported.endDate` 才是真财季末（WMT FY26Q3 = `2025-10-31`）。GT report_04 即此。
3. **`_meta.fetched_at` 是 2026 抓取时间（相对 2025 语料是未来）**——任何"内容时间"推理必须排除，否则时间戳抽取器会错锚。
4. **无时区的隐含约定混用。** news/sec-acceptance=UTC；filings/financials accepted=ET 裸时间。`fact_store.py:49-50` 现对 `filedDate` 做**字符串 `>=` 比较**，只因同格式才碰巧成立，跨源即错。
5. **`filedDate` 时间恒为 `00:00:00`** 伪装成 datetime，实为日精度；与 `acceptedDate`（真秒）混用会制造假"时序矛盾"。
6. **research catalog 350 行 timestamp 全空**：research 是聚合文件，无单一内容时间戳。
7. **Twitter `created_at` 英文 locale RFC-822**，需专用解析；与文件名 `since/until` 可能错位。
8. **prices 仅交易日**（周末/假日 gap）；分钟线虽 UTC 干净，但与日线对齐须按 **ET 交易日**切分（否则盘后 bar 错归次日）。
9. **读取依赖风险**：`requirements.txt` 把 `pyarrow/pandas` 列为**可选**，当前 `submission.py` 只记 `prices_minute_dir` 路径**根本没读** parquet。任何分钟级时间校验必须 **pyarrow 缺失即降级**，不得崩。

---

## 3. 为什么这关系到最终任务（时间戳扭曲 → 权威锚映射）

GT 已确认三类时间扭曲，全部依赖跨源时间归一：

| 扭曲类型 | GT 例 | 权威锚 |
|---|---|---|
| 错误申报日期 | report_02（10-K 称 2/5 实为 1/30） | filing 文件名 = `sec_submissions.filingDate` = `filings.json.filedDate`，三源应一致，任一被改即矛盾 |
| 财季结束日错 / 财历当日历 | report_04（WMT FY26Q3 称 11/30 实为 10/31） | `financials_reported.endDate` 是真值；`earnings.period` 是日历标签陷阱（永不作财季末） |
| 时间线 / 可得性错位 | （隐式）称信息在某日已知，但 accepted 在其后 | `acceptanceDateTime` 归一到 UTC + ET 双视图；分钟线 `session` 判会话 |

没有统一时间模型，Review 只能字符串比对：格式不一致 → 漏；ET/UTC 跨日、财历/日历 → 误。

### 3.1 【关键收紧】按锚可信度分级 —— 结构化时间 ≠ 数据真实时间

结构化字段给的常常**只是报道/抓取时间**，而 claim 真正断言的**事件/数据时间**藏在自由文本里、格式未知、位置未知。一篇 09-17 发布的新闻**正确地**描述 08-01 的事件是合法的——把"报告里的事件日期" vs 新闻 `published_at` 当矛盾报，会系统性误报。因此时间锚必须按可信度三分，**只有 T1 能进确定性(exact)校验**：

| 级别 | 源 | 结构化字段是 | 数据真实时间 | 进哪一层 |
|---|---|---|---|---|
| **T1 可信** | filings（filename / sec_submissions / financials_reported）、earnings.json、prices_minute `ts_utc`/`session` | 申报时间 **且** 财期/数据时间本身 | **结构化、可靠** | ✅ exact tier |
| **T2 仅出处** | news `published_at`、social `created_at` | 仅报道/发帖时间 | 在正文自由文本，格式/位置未知 | 仅"出处+日期"型扭曲可进 weak tier；事件时间一律不进确定性路径 |
| **T3 排除** | `_meta.fetched_at`（2026 抓取时间） | 抓取时间 | 与内容无关 | 仅审计，不参与任何时间推理 |

**硬约束**：
- 确定性时间戳 issue **只能由 T1 结构化数据时间锚背书**（filing 财期 / earnings / price bar）。事件时间只能从新闻/社媒正文推断的 claim → 最多 weak/narrative tier（带原文段落让 LLM 判），**永不** exact tier。
- 新闻能确定性查的只有**出处类**扭曲（"路透 2025-08-01 报道 X" 比对 `published_at` 这个结构化字段），**不是事件本身的时间**；且仅在报告明确给"媒体+日期"且能定位到文章时算 weak 证据。
- 正文非结构化日期：只做**有界**启发式（仅当正文出现显式 `YYYY-MM-DD`/`Month DD, YYYY` 且紧邻被声称的实体/数字时作弱证据），不做通用时间 NER（离线不可靠，必引入误报）。

---

## 4. 归一化 / 结构化方案

核心：把**结构化时间事实**压成**单一规范结构 `TimeAnchor`**（T2/T3 不进索引），预生成按 (ticker, 概念) 可查的时间锚索引，Review 按 §3.1 分级使用。

### 4.1 规范模型

```
TimeAnchor = {
  entity:       ticker,
  concept:      filed | accepted | period_end | period_start |
                report_date | published | scraped | price_bar,
  date:         "YYYY-MM-DD",            # 规范日（交易/申报语义，ET 视图）
  instant_utc:  ISO-8601 Z | None,       # 有钟点时的 UTC 瞬时
  instant_et:   ISO-8601 -05/-04 | None, # ET 视图（申报语义用）
  precision:    day | second,
  fiscal:       {fy:int, fq:1-4} | None,
  session:      pre | regular | post | None,  # 仅 price_bar
  source:       文件相对路径 + 字段名,   # 可追溯，写进 reason
  raw:          原始字符串               # 审计
}
```

### 4.2 解析分派器 `parse_temporal()`（按格式族）

- **`…TZ` / `…T..:..:..(.fff)Z`**（news / sec acceptanceDateTime）→ UTC 瞬时；date 取 **ET 日**（关键：申报跨日靠这个）。
- **`YYYY-MM-DD HH:MM:SS`**（filings/financials accepted）→ 视为 **ET 裸时间**，补 `America/New_York` 再转 UTC；`filed` 的 `00:00:00` 降为 `precision=day`（不参与时序先后判断，只定日）。
- **`YYYY-MM-DD` 纯日期** → `precision=day`，instant=None。
- **Twitter `created_at`** → `%a %b %d %H:%M:%S %z %Y`（`+0000`=UTC）。
- **财务三元组 `period/quarter/year`** → **不**当内容日期；转 `fiscal={fy,fq}`，用 §4.3 映射真实 `period_end`；`earnings.period` 单独标 `calendar_label`，**永不作财季末**。
- **`_meta.fetched_at`** → `concept=scraped`，默认从所有内容时间推理中**排除**（仅审计）。
- **parquet `ts_utc`** → 已是 tz-aware UTC，直接用（唯一无需归一的源）；`session` 写入 `TimeAnchor.session`。pyarrow 缺失则跳过分钟级，不崩。

### 4.3 财历 ↔ 日历桥

- 真值优先级：`financials_reported.{startDate,endDate,year,quarter}` > filing 文件名 / `sec_submissions.reportDate` > `earnings`（其值仅用于 actual/estimate，`period` 永不作财季末）。
- 产出每 ticker 一份 `(fy,fq) ↔ (period_start,period_end)` 双向表；Review 比对"财 Qx FYxx 截止某日"时直接查表，不一致即 issue（覆盖 report_04 型）。

### 4.4 跨源一致性校验（清洗副产物，离线预生成 `time_index.json`）

对每个 (ticker, accession) 收集：filename-date / catalog / `filings.json.filedDate` / `sec_submissions.filingDate`。规范化后应**全等**；不等则记入"语料内部时间冲突表"——既是数据清洗报告，也是 Review 高精度证据源（报告与多数源不一致即扭曲）。

### 4.5 Review 集成

- 在 `retrieval/fact_store.py` 旁加 `time_index`（预构建或首次加载缓存）。把现有 `filedDate` 字符串 `>=` 比较（`fact_store.py:49-50`）换成 `TimeAnchor` 比较，消除 ET/UTC 跨日假矛盾。
- 新增确定性 verifier（走重设计的 **exact tier**）：报告 claim 抽出 (form/accession/fiscal/声称日期) → 查 `time_index` → 规范日不一致则发 issue，reason 带 `source` 路径（符合 GT reason 的可追溯风格）。
- 分钟线 `session` 校验进 exact tier：报告称"收盘价/盘中价"但对应 `ts_utc` 的 `session≠regular`，或声称报价时点无对应 bar（休市/停牌）→ issue。
- **分级闸门（§3.1）**：verifier 入口先判 claim 的时间锚是否 T1。非 T1（事件时间只能从新闻/社媒正文推断）→ 不进 exact，最多打包成 weak 候选交 LLM，**绝不**确定性发 issue。这是防"报道时间 vs 事件时间"系统性误报的关键。

---

## 5. 落地建议（待 Clara 复核后实施）

1. `reference_submission/retrieval/timeparse.py`：纯标准库（无 pandas 依赖；parquet 复用现有读取层 + pyarrow 缺失降级），实现 `TimeAnchor` + `parse_temporal()` + 财历桥。
2. 预生成脚本 → `time_index.json`（含跨源一致性冲突表）。
3. 接入 review 的 exact-tier 时间戳 verifier，跑 GT 验证 report_02 / report_04 类是否命中。

> 复核重点：§4.3 财历真值优先级、§4.4 冲突判定阈值（多数表决 or 严格全等）、§4.5 是否替换 `fact_store.py:49` 的字符串比较。
