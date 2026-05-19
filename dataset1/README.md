# 数据集说明 · 参赛者版

本目录是参赛者可见的语料集合，时间窗口 **2025-01-01 ~ 2025-12-31**。
2026 年的数据被组织者保留作为评测基准（held-out test set），参赛者
不直接见到。

## 1. 范围

- **股票池**：50 支美股大盘股，覆盖科技、金融、能源、医药、消费、工业等主要板块。
- **时间窗口**：2025 全年。
- **包含的数据维度**：SEC filings 原文、财经新闻、价格 OHLCV、Twitter 帖子、分析师/财务结构化数据。

50 支 ticker：

```
AAPL  ABBV  AMD   AMT   AMZN  AVGO  BA    BAC   BRK.B CAT
CMCSA COP   COST  CVX   DIS   DUK   GE    GOOGL GS    HD
HON   JNJ   JPM   KO    LLY   MCD   META  MRK   MS    MSFT
NEE   NFLX  NKE   NVDA  PEP   PFE   PG    PLD   SBUX  SLB
SO    SPG   T     TSLA  UNH   UPS   VZ    WFC   WMT   XOM
```

> 票池由 `catalog.jsonl` 决定。请用
> `hackathon.catalog.collect_symbols(catalog)` 在运行期取，**不要硬编码**。

## 2. 目录结构

```
dataset/
├── corpus/
│   ├── filings/<TICKER>/<form>__<YYYY-MM-DD>__<accession>.htm
│   ├── news/<TICKER>/<article_id>.json
│   ├── research/<TICKER>/<file>.json
│   └── social/<TICKER>/twitter_<YYYY-MM-DD>.json
├── prices/<TICKER>.csv                       # 日频 OHLCV
├── prices_minute/<TICKER>/<YYYY-MM>.parquet  # 分钟频 OHLCV（按月切片）
└── catalog.jsonl
```

评测机会用环境变量指向这里：

| 变量 | 内容 |
|---|---|
| `HACKATHON_CORPUS_DIR` | `…/dataset/corpus` |
| `HACKATHON_PRICES_DIR` | `…/dataset/prices` |
| `HACKATHON_PRICES_MINUTE_DIR` | `…/dataset/prices_minute` |
| `HACKATHON_CATALOG_PATH` | `…/dataset/catalog.jsonl` |

## 3. 各维度详解

### 3.1 filings — SEC 备案原文（HTML）

来源：[SEC EDGAR](https://www.sec.gov/edgar) 原始 `.htm` 文件，未做任何
文本提取，保留全部 HTML 结构（表格、标题、章节锚点）。

文件名格式：`<form>__<YYYY-MM-DD>__<accession>.htm`

涵盖的 form 类型（按数量）：

| Form | 数量 | 说明 |
|---|---:|---|
| 8-K | ~660 | 重大事件即时披露（盈利发布、CEO 离任、并购、债务发行等）|
| 10-Q | ~170 | 季度报告（含 MD&A、风险更新、未审计财报）|
| DEFA14A | ~120 | 代理增补（股东会议增补材料）|
| DEF 14A | ~50 | 委托书（代理投票材料、薪酬、董事会信息）|
| 10-K | ~45 | 年度报告（最权威：业务概述、Risk Factors、MD&A、审计财报）|
| ARS | ~35 | Annual Report to Shareholders |

每份 filing 可能 40 KB（小型 8-K）到 1 MB（10-K 全文）。HTML 解析推荐用
SDK 提供的 `hackathon.extract.extract_text(path)`，它会自动调用合适的
parser。

### 3.2 news — 综合财经新闻

来源：Polygon.io + Finnhub 双源。每文一文件，**v2.0 flat schema**：

```json
{
  "title": "...",
  "text": "<full article body>",
  "published_at": "2025-09-15T13:30:00Z",
  "provider": "Reuters",
  "url": "...",
  "symbols": ["AAPL", "MSFT"]
}
```

`text` 字段优先填全文（trafilatura 抽取），全文不可得时退回 description /
summary。**付费墙站点**（WSJ / Bloomberg / FT / Barron's / Economist）
`text` 可能是空字符串或仅头几句——这是上游限制，参赛者需要从其他维度
（标题 + 推特讨论 + 后续无墙报道）补足。

每票 500 ~ 9000 篇；行业热点票（NVDA、AMZN、MSFT）量大，公用事业票
（DUK、SO、SPG）量小。

### 3.3 research — 结构化财务/分析师数据

每票 7 个 JSON：

| 文件 | 来源 | 用途 |
|---|---|---|
| `earnings.json` | Finnhub | EPS 实际 vs 预期，按季度 |
| `recommendations.json` | Finnhub | 分析师 buy/hold/sell 计数时间序列 |
| `financials_reported.json` | Finnhub | 季报全文报送的三大表（数百行 us-gaap concept→value）|
| `filings.json` | Finnhub | SEC filing 元数据列表（form / date / URL）|
| `peers.json` | Finnhub | 行业对标公司列表 |
| `sec_financials.json` | SEC EDGAR | XBRL company facts，所有 us-gaap concept 的历史时间序列 |
| `sec_submissions.json` | SEC EDGAR | EDGAR 完整提交历史（accession / form / date / 文档 URL）|

> 注意：`sec_financials.json` 和 `sec_submissions.json` 已按 cutoff 过滤
> 到 2025-12-31 之前；其余几个 Finnhub 文件也按 `period` / `filedDate`
> / `endDate` 过滤过。

这块是**数字密集型**的好材料：算 EPS surprise、跑同比/环比、看
sell-side sentiment 走势、找行业 peers 做对比，都很方便。

### 3.4 social — Twitter / X 上的相关讨论

按日聚合，每票每天一个 JSON，包含当天 `$<ticker>` cashtag 搜索的 top 20
英文推文。每条推文带：`id` / `text` / `created_at` / `url`，
`author.{username,name,followers,verified}`，`metrics.{likes,retweets,
replies,views,quotes}`。

365 天 × 50 票 ≈ 18,250 个文件。注意噪声很大（机器人、重复转发、与公司
无关的 cashtag 撞车），用前先按 `metrics.followers` / `metrics.views`
过滤一波。

### 3.5 prices — 日 OHLCV

来源：Polygon.io aggregates API（adjusted）。

CSV 列：`date, open, high, low, close, volume, vwap, transactions`。

约 250 个交易日 × 50 票。

### 3.6 prices_minute — 分钟 OHLCV

来源：Polygon.io aggregates API（adjusted），1-minute bars，按月切片，单文件 Parquet。

路径：`prices_minute/<TICKER>/<YYYY-MM>.parquet`，50 票 × 12 月 = 600 份。

Parquet schema：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_utc` | timestamp[ns, UTC] | bar 开始时刻（UTC，含时区） |
| `open` / `high` / `low` / `close` | double | 价格 |
| `volume` | int64 | 成交量 |
| `vwap` | double | 成交量加权均价 |
| `transactions` | int32 | tick 数 |
| `session` | string | `pre` / `regular` / `post` —— 盘前 / 盘中 / 盘后 |

一份 AAPL 2025-01 约 16k 行；行业活跃票（NVDA / MSFT / AMZN）显著更大。
读取建议用 `pyarrow.parquet.read_table` 或 `pandas.read_parquet`。

不在 catalog 里——按 ticker + 月份直接拼路径访问。

## 4. catalog.jsonl

一行一条 `DocMeta`，把 corpus/ 下每个文件的元数据集中起来，方便参赛者
按 `kind` / `symbols` / `time_range` 过滤。

字段示例：

```json
{
  "path": "filings/AAPL/10-K__2025-10-31__0000320193-25-000079.htm",
  "kind": "filing",
  "symbols": ["AAPL"],
  "timestamp": "2025-10-31",
  "form": "10-K",
  "extra": {}
}
```

`kind ∈ {filing, news, research, social}`。`prices/*.csv` **不在 catalog
里**——价格按 ticker 直接查 `HACKATHON_PRICES_DIR/<TICKER>.csv` 即可。

## 5. 数据规模一览

| 维度 | 文件数 | catalog 行数 |
|---|---:|---:|
| filings | 1,077 | 1,077 |
| news | 97,266 | 97,266 |
| research | 350 | 350 |
| social | 18,250 | 18,250 |
| prices | 50 (CSV) | 不计入 catalog |
| prices_minute | 600 (Parquet, 50 × 12 月) | 不计入 catalog |
| **总计** | | **116,943** |

总体积约 2.5 GB。

## 6. 已知限制

- **付费墙新闻全文缺失**：WSJ / Bloomberg / FT / Barron's / Economist 的
  `text` 字段可能为空。需要时从 Polygon 的 `description` 字段 + 标题
  推断。
- **Finnhub filings 索引截断**：少数高发行量票（BAC、GS、JPM、WFC）
  Finnhub 端只回近期 filings；本数据集已用 SEC EDGAR `submissions.json`
  补齐 2025 年完整 10-K / 10-Q / 8-K。
- **Twitter 噪声**：cashtag 容易混入无关讨论，参赛者需自行清洗。

## 7. 时间一致性保证

本目录里**所有日期相关字段**（`published_at` / `filing_date` /
`period` / `endDate` / `filedDate` / 价格 `date` 列等）严格 < 2026-01-01。
任何形如"2026 年 3 月 NVDA 业绩"的事实在本数据集里都查不到——这是
有意为之，请不要尝试通过其他渠道补足。
