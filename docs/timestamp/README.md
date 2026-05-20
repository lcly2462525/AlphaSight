# 时间戳索引项目说明

本文档说明当前项目里时间戳索引的共享方式、作用边界和调用方式。原始调研和交接材料已经归档到 `docs/timestamp/archive/`。

## 目录

| 文件 | 用途 |
|---|---|
| `README.md` | 当前项目怎么使用时间戳索引。 |
| `BUILD_AND_IMPLEMENTATION.md` | 构建脚本、索引 schema、review 接入和验证方法。 |
| `archive/timestamp_analysis.md` | 原始时间戳形态分析和方案调研。 |
| `archive/handoff_integration.md` | 原交接包里的云端适配步骤。 |
| `archive/handoff_timestamp_implementation.md` | 原交接包里的实施方案副本。 |

## 当前项目中的文件

| 路径 | 角色 |
|---|---|
| `reference_submission/retrieval/timeparse.py` | 运行时共享模块，提供时间格式解析和 `TimeIndex` 查询 API。 |
| `reference_submission/build_time_index.py` | 一次性构建脚本，从原始 `dataset/` 生成外挂索引。 |
| `dataset/time_index.json` | 构建产物，Review/Generate 共享的时间真值；被 `.gitignore` 忽略，不入仓。 |
| `reference_submission/agents/review.py` | Review 端接入点，备案日和财季末 deterministic exact 校验会查询 `TimeIndex`。 |

## 共享方式

时间戳真值不写回原始语料，也不改 `fact_store.py` 的公共行为。项目通过一个外挂索引共享：

1. `build_time_index.py` 读取 `dataset/corpus/filings`、`catalog.jsonl`、`research/<T>/sec_submissions.json`、`research/<T>/filings.json`、`research/<T>/financials_reported.json`。
2. 构建结果写入 `dataset/time_index.json`。
3. 运行时各模块通过 `from retrieval.timeparse import TimeIndex` 读取同一份索引。
4. 索引不存在时，Review 会降级为 `TimeIndex.empty()`，相关 producer 自动跳过或回退旧 `fact_store` 路径。

## 最终作用

当前实现主要服务 Review 的 deterministic exact tier：

- 带 accession 的备案日校验：例如 TSLA `0001628280-25-003063` 真备案日为 `2025-01-30`。
- 无 accession 但有 form 的备案日集合校验：例如 NEE `8-K` 真实日期集合不含 `2025-08-23`。
- 财季末校验：例如 WMT FY2026 Q3 真 endDate 为 `2025-10-31`，来源只认 `financials_reported.endDate`。

这三类都不调用 LLM，证据会写成 `DETERMINISTIC FACT [SOURCE: time_index]` 或指向 `research/<T>/financials_reported.json`。

## 构建和调用

构建索引：

```bash
python3 reference_submission/build_time_index.py
```

当前本地构建结果：

```text
time_index v2: 50 tickers, 84331 accessions, 2191 fiscal + 172 earnings periods, 250 trading days
```

查询示例：

```python
import sys
sys.path.insert(0, "reference_submission")

from retrieval.timeparse import TimeIndex

ti = TimeIndex.load()
ti.filing_by_accession("TSLA", "0001628280-25-003063")["date"]
ti.filing_dates_of_form("NEE", "8-K")
ti.fiscal_period("WMT", 2026, 3)["end"]
```

离线验证：

```bash
python3 -c "import sys; sys.path.insert(0,'reference_submission'); from retrieval.timeparse import TimeIndex; ti = TimeIndex.load(); assert ti.filing_by_accession('TSLA','0001628280-25-003063')['date']=='2025-01-30'; assert ti.fiscal_period('WMT',2026,3)['end']=='2025-10-31'; assert '2025-07-23' in ti.filing_dates_of_form('NEE','8-K'); assert '2025-08-23' not in ti.filing_dates_of_form('NEE','8-K'); print('build OK')"
```

## 维护原则

- `earnings.json.period` 只作为日历季标签归档在 `earnings_periods`，不得作为财季末真值。
- 备案日比较使用 `date` 字段，不用 `accepted_utc[:10]`，避免 ET/UTC 跨日误判。
- `_period_end_candidates` 只比较紧邻 `ended/ending/截至/结束` 的日期，避免同段落含真假日期时误放过。
- `dataset/time_index.json` 是生成物，重新构建即可恢复，不需要提交。
