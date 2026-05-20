# 时间戳归一化实施方案

> 用途：把 [docs/timestamp_analysis.md](timestamp_analysis.md) 的设计**落地成代码**。
> 编写：Clara，2026-05-20。
> 范围：纯 T1 结构化时间锚（filings / earnings / fiscal periods / price sessions）；T2/T3 按 §3.1 闸门排除。
> 目标：GT report_02（错备案日）/ report_04（错财季末）/ report_09 issue 2（错 8-K 申报日）三类时间扭曲确定性命中；Generate 端拿规范日避免格式转换错。

---

## 0. 关键约束

1. **零 LLM 调用** —— 所有解析走 regex / strptime / 结构化字段查表。
2. **零修改源数据** —— 不在 `dataset/corpus/` 加字段；只生成一个外挂索引 `dataset/time_index.json`。
3. **fact_store 稳态保护** —— 不大改 `fact_store.py`（其他生产者依赖它）；新逻辑放新模块，review.py 通过加性钩子接入。
4. **pyarrow 缺失降级** —— 分钟线 session 校验若 pyarrow 缺失即 skip，不崩。
5. **GT-reason 风格的可追溯证据** —— `reason` 里必须附 `source` 路径（与 GT report_02 完全一致的体例）。

---

## 1. 文件清单

| 文件 | 角色 | 体量 |
|---|---|---|
| `reference_submission/retrieval/timeparse.py` | **新增**：`TimeAnchor` + `parse_temporal()` + 财历桥 + `TimeIndex` 查询 API | ~250 行 |
| `reference_submission/build_time_index.py` | **新增**：一次性 build 脚本，生成 time_index.json | ~150 行 |
| `dataset/time_index.json` | **生成产物**：跨源规范时间锚索引 | < 1 MB |
| `reference_submission/agents/review.py` | **小幅改**：`_date_candidates` 富化证据；`_period_end_candidates` 用财历桥再挂回 `run()` | +~30 行 |
| `reference_submission/retrieval/fact_store.py` | **不改** | 0 |

---

## 2. 数据模型

### 2.1 `TimeAnchor`（运行时对象，非落盘）

```python
@dataclass
class TimeAnchor:
    entity: str                       # ticker
    concept: str                      # filed | period_end | period_start | report_date
    date: str                         # "YYYY-MM-DD"（ET 视图，规范日）
    instant_utc: str | None           # "YYYY-MM-DDTHH:MM:SSZ"，有钟点时才有
    instant_et: str | None            # "YYYY-MM-DDTHH:MM:SS-04:00/-05:00"
    precision: str                    # "day" | "second"
    fiscal: tuple[int, int] | None    # (fy, fq) 1-4，仅 period_end/start
    session: str | None               # pre|regular|post，仅 price_bar
    source: str                       # 文件相对路径 + 字段名，写进 reason
    raw: str                          # 原始字符串
```

### 2.2 `time_index.json`（落盘 schema）

```json
{
  "TSLA": {
    "filings_by_accession": {
      "0001628280-25-003063": {
        "form": "10-K",
        "date": "2025-01-30",
        "sources": {
          "filename":  "2025-01-30",
          "catalog":   "2025-01-30",
          "sec_subm":  "2025-01-30",
          "fil_json":  "2025-01-30"
        },
        "consistency": "ok"            // ok | conflict | partial
      }
    },
    "filings_by_form": {
      "10-K": ["2025-01-30"],
      "10-Q": ["2025-04-22", "2025-07-22", "2025-10-21"],
      "8-K":  ["2025-01-03", "2025-01-30", ...]
    },
    "fiscal_periods": {
      "2026|3": {
        "fy": 2026,
        "fq": 3,
        "start": "2025-02-01",
        "end":   "2025-10-31",
        "form":  "10-Q",
        "source": "research/TSLA/financials_reported.json"
      }
    }
  },
  "WMT": { ... }
}
```

**关键规范化**：
- `date` 永远 ET 日历日（不是 UTC 日；申报跨日靠这个）。
- `filings_by_form[FORM]` 去重排序的日期列表，供"声称日期是否在该 form 的真实集合里"的二值校验。
- `fiscal_periods` key 用 `"fy|fq"` 字符串（JSON 不支持 tuple key）。
- 真值优先级（§4.3）：`financials_reported.{startDate,endDate,year,quarter}` > 文件名 / `sec_submissions.reportDate` > earnings.json（earnings.period **永不**作 fiscal_periods.end，只能作 `_calendar_label` 审计字段，不写进主索引）。

---

## 3. `timeparse.py` 模块接口

```python
# ---- 解析器 ----
def parse_iso_z(s: str) -> TimeAnchor | None       # "...Z" / "...000Z"
def parse_space_naive_et(s: str) -> TimeAnchor     # "YYYY-MM-DD HH:MM:SS" 视为 ET
def parse_date_only(s: str) -> TimeAnchor          # "YYYY-MM-DD"
def parse_twitter_created_at(s: str) -> TimeAnchor # "Wed Jan 01 15:00:02 +0000 2025"
def parse_filing_filename(name: str) -> tuple[str, str, str] | None  # (form, date, accession)

def parse_temporal(raw: str, hint: str = "") -> TimeAnchor | None
    """智能分派；hint 给字段名（filedDate/acceptanceDateTime/created_at/...）"""

# ---- 财历桥 ----
class FiscalBridge:
    def add(self, ticker: str, fy: int, fq: int,
            start: str, end: str, form: str, source: str) -> None
    def lookup(self, ticker: str, fy: int, fq: int) -> dict | None
    def by_end_date(self, ticker: str, end: str) -> tuple[int,int] | None

# ---- 索引 ----
class TimeIndex:
    @classmethod
    def load(cls, path: Path = Path("dataset/time_index.json")) -> "TimeIndex"

    # filing 三类查询(都返回 dict 或 None；不抛)
    def filing_by_accession(self, ticker: str, acc: str) -> dict | None
    def filing_dates_of_form(self, ticker: str, form: str) -> list[str]
    def fiscal_period(self, ticker: str, fy: int, fq: int) -> dict | None

    # 跨源一致性
    def has_conflict(self, ticker: str, acc: str) -> bool
```

---

## 4. `build_time_index.py` 流程

```
For each ticker T in 50:
  # 1. 收 filings 真实日期（4 个源）
  src1 = parse_filing_filename for f in corpus/filings/T/*.htm        # → {acc: date}
  src2 = catalog.jsonl rows where kind=filing, T in symbols           # → {acc: date}
  src3 = sec_submissions.json.filings.recent.{accessionNumber,filingDate}
  src4 = filings.json.[*].{accessNumber, filedDate→date}

  For each accession seen in any source:
    canonical = majority vote (强一致优先)；若四源全等 -> consistency=ok
                                              若不等 -> consistency=conflict，date 取多数
    写入 filings_by_accession + filings_by_form

  # 2. 收 fiscal periods（仅 financials_reported.json）
  for r in financials_reported.json.data.data:
    fy, fq = int(r.year), int(r.quarter)
    start = r.startDate[:10]; end = r.endDate[:10]
    写入 fiscal_periods["fy|fq"]
  # earnings.json.period 不写入 fiscal_periods，避免日历陷阱

输出 dataset/time_index.json （UTF-8, sort_keys, indent=0 紧凑）
```

**预期规模**：50 ticker × ~30 filings + ~10 fiscal periods ≈ 2000 条 → < 500 KB JSON。

---

## 5. review.py 接入（最小侵入）

### 5.1 `_date_candidates`（申报日校验，富化证据）

现状：单源 `fact_store.filings_of`（catalog），evidence 只引一个源。
改造：构造时 `self.time_index = TimeIndex.load()`；命中后用 time_index 给四源证据：

```python
# 命中 mismatch 后:
ti = self.time_index
canon = ti.filing_by_accession(tk, acc) if acc else None
if canon:
    sources_line = (
        f"filename={canon['sources'].get('filename','—')}; "
        f"sec_submissions.filingDate={canon['sources'].get('sec_subm','—')}; "
        f"filings.json.filedDate={canon['sources'].get('fil_json','—')}"
    )
    evidence = (
        f"DETERMINISTIC FACT [SOURCE: time_index] {tk} {form} accession {acc}"
        f" was filed on {canon['date']}; sources: {sources_line}. "
        f"The claim's date {','.join(dates)} does not match."
    )
else:
    # 无 accession 的兜底：查该 form 下所有 filing dates
    real = ti.filing_dates_of_form(tk, form)
    if not real or any(d in real for d in dates): continue
    evidence = (
        f"DETERMINISTIC FACT [SOURCE: time_index] {tk} {form} filings were"
        f" filed on {', '.join(real)} (per filename + sec_submissions +"
        f" filings.json). The claim's date {','.join(dates)} does not match"
        f" any actual {form} filing date for this ticker."
    )
```

**带来什么**：
- report_02：`acc 0001628280-25-003063 → 2025-01-30`，附**三源齐证**的 evidence，复刻 GT reason 风格。
- report_09 issue 2：claim 没 acc，走 `filing_dates_of_form("NEE", "8-K")`；声称 2025-08-23 不在真实 8-K 日期集合 → 报错。

### 5.2 `_period_end_candidates`（财季末校验，再挂回）

现状：函数体存在但被 `38f2737 drop period-end FP generator` 从 `run()` 摘掉（怕 earnings.period 日历陷阱误报）。
改造：把 `period_rows` 换成 `TimeIndex.fiscal_period`（**真值只认 financials_reported.endDate**，从源头杜绝陷阱），然后挂回 `run()` 的生产者列表。

```python
def _period_end_candidates(...):
    for c in claims:
        if not re.search(r"ended|ending|截至|结束", q, re.I): continue
        dates = _parse_dates(q)
        year, quarter = _parse_period(q)
        if year is None or quarter is None or not dates: continue
        for tk in self._scope(q, primary):
            fp = self.time_index.fiscal_period(tk, year, quarter)
            if not fp: continue
            true_end = fp["end"]
            if any(d == true_end for d in dates): continue
            out.append({
                "quote": q, "kind": "date_timeline", "tier": "exact",
                "evidence": (
                    f"DETERMINISTIC FACT [SOURCE: {fp['source']}] {tk} "
                    f"FY{year} Q{quarter} period endDate is {true_end} "
                    f"(startDate {fp['start']}, form {fp['form']}). "
                    f"The claim's date {','.join(dates)} does not match.")})
            break
```

再在 `run()` 的候选列表加回：

```python
for c in (self._numeric_candidates(claims, primary)
          + self._date_candidates(claims, primary)
          + self._period_end_candidates(claims, primary)     # ← 加回
          + self._price_candidates(claims, primary)
          + self._peer_candidates(claims, primary)
          + self._arithmetic_candidates(claims)
          + self._table_candidates(anc, primary)):
```

**带来什么**：report_04 命中：`WMT FY26Q3 ended 2025-11-30 → fiscal_period(WMT, 2026, 3).end = 2025-10-31`，evidence 直接说 source 是 financials_reported.json，与 GT reason 一字不差。

### 5.3 `__init__` 增量

```python
class ReviewAgent:
    def __init__(self, retriever, llm_cfg, rev_params):
        ...
        from retrieval.timeparse import TimeIndex
        try:
            self.time_index = TimeIndex.load()
        except FileNotFoundError:
            self.time_index = TimeIndex.empty()   # 没建索引就跳过这两个生产者
```

---

## 6. 验证计划

### 6.1 单元（build 阶段）

```
python3 reference_submission/build_time_index.py
# 抽样断言:
python3 -c "
from reference_submission.retrieval.timeparse import TimeIndex
ti = TimeIndex.load()
# report_02
assert ti.filing_by_accession('TSLA', '0001628280-25-003063')['date'] == '2025-01-30'
# report_04
assert ti.fiscal_period('WMT', 2026, 3)['end'] == '2025-10-31'
# report_09 issue 2
dates_8k = ti.filing_dates_of_form('NEE', '8-K')
assert '2025-07-23' in dates_8k and '2025-08-23' not in dates_8k
print('build OK')
"
```

### 6.2 端到端（GT 命中）

```
cd reference_submission
python3 run.py review \
  --requests problem/review_train.jsonl --gt problem/review_train_gt.jsonl \
  --report-ids report_02 report_04 report_09 \
  > /tmp/review_ts_test.jsonl

# 期望:
# - report_02 issues 包含申报日 mismatch（acc 0001628280-25-003063 → 1-30，引三源）
# - report_04 issues 包含财季末 mismatch（FY26Q3 → 10-31，source=financials_reported）
# - report_09 issues 包含 8-K 申报日 mismatch（claimed 8-23 不在真实集合）
```

### 6.3 回归（不动其他 issues）

- report_01 / 03 / 05 / 06 / 07 / 08 等非时间 issues 行为应**完全不变**（仅添加了时间生产者，没改其他）。

---

## 7. 非目标 / 设计上不抓的

按 §3.1 闸门，以下**主动排除**，不视为漏：

- **股东会日期**（report_10/12 issue 2）：DEF 14A proxy 正文里，非结构化锚 → §3.1 T2，留给新闻 BM25 / proxy 文本抽取。
- **ETF 创新高日期**（report_11 issue 2）：XLU 不在 50 ticker prices；且"创高"是 max(close) 派生量。
- **报道事件时间**（任何新闻正文里的事件日）：T2 闸门挡住，不进 exact tier。

这些走 [docs/news_coverage_analysis.md](news_coverage_analysis.md) 的 BM25 + 方向词 + LLM 定向提取路线。

---

## 8. Generate 端反向收益

无需 Generate 端任何改动——只要 Generate prompt / context 里**注入 time_index 查询**：

```
For TSLA's 10-K accession 0001628280-25-003063:
  time_index.filing_by_accession("TSLA", "0001628280-25-003063").date = "2025-01-30"
For WMT FY26 Q3:
  time_index.fiscal_period("WMT", 2026, 3) = {end: "2025-10-31", ...}
```

Generate 直接抄规范字符串，**不再自行从 `'2025-01-30 00:00:00'` / `'2025-07-23T00:00:00.000Z'` 等异构原始字段格式化**——格式转换错从源头消失。这是 Review/Generate **共用一份真值**的关键。

---

## 9. 实施顺序

1. ✅ 写本文件
2. 实现 `timeparse.py`
3. 实现 `build_time_index.py`
4. 跑 build → 检查 time_index.json
5. 改 `review.py`（`_date_candidates` 富化 + `_period_end_candidates` 接回）
6. 跑 GT 验证（§6.2）
7. 报告：命中数 / 误报数 / time_index 一致性冲突统计
