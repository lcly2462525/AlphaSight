# INTEGRATION — 把 timeparse 接进当前 review.py

> 给云端 agent 看的逐步指令。云端 `reference_submission/agents/review.py` 与本地分歧大（云端 1488 行），不直接 patch。按下文**语义+代码块**找到当前文件对应位置插入。

---

## 第 1 步：加 import

在文件顶部 import 段（其他 `from retrieval.* import …` 旁边）加：

```python
from retrieval.timeparse import TimeIndex
```

---

## 第 2 步：`ReviewAgent.__init__` 注入 time_index

在 `__init__` 末尾（其他 `self._xxx_p = load_prompt(...)` 之后）加：

```python
        try:
            self.time_index = TimeIndex.load()
        except (FileNotFoundError, OSError):
            # build_time_index.py 没跑过 -> 降级, 相关生产者自动 skip
            self.time_index = TimeIndex.empty()
```

---

## 第 3 步：替换 `_date_candidates` 函数体

把现有 `_date_candidates`（仍调 `self.retriever.fact_store.filings_of`）**整段**替换为下面版本。三条路径：

- **path 1**：claim 里有 accession → time_index 精确查 + 四源 attestation reason
- **path 2**：无 accession 但有 form → time_index.filing_dates_of_form 集合校验
- **path 3**：time_index 不可用 → 原 fact_store 路径兜底（不破坏旧行为）

**关键 cue 改动**：原中文 cue 加入 `披露`（必须，否则 GT report_09 #2 漏；安全前提是 `_claim_form` 已先 gate，无 form 不会进来）。

```python
    def _date_candidates(self, claims: list[dict],
                         primary: list[str]) -> list[dict]:
        """Filing-date verifier. Backed by `time_index` so each emitted
        issue cites multi-source attestation (filename + catalog +
        sec_submissions + filings.json), matching GT-style reason."""
        out: list[dict] = []
        ti = self.time_index
        for c in claims:
            q = c["quote"]
            form = _claim_form(q)
            dates = _parse_dates(q)
            if not form or not dates:
                continue
            # cue gate (already form-gated above by _claim_form, so adding
            # bare "披露" is safe — it must co-occur with a recognized form).
            if not re.search(r"filed|submitted|filing date|filed with|"
                             r"提交|备案|披露日期|提交日|披露", q, re.I):
                continue
            tickers = self._scope(q, primary)
            if not tickers:
                continue
            accs = _ACC_RE.findall(q)
            for tk in tickers:
                evidence: str | None = None
                # path 1: claim cites an accession — exact lookup
                if ti and accs:
                    rec = ti.filing_by_accession(tk, accs[0])
                    if rec and not any(d == rec["date"] for d in dates):
                        src_line = "; ".join(
                            f"{k}={v}"
                            for k, v in sorted(rec["sources"].items()))
                        evidence = (
                            f"DETERMINISTIC FACT [SOURCE: time_index] "
                            f"{tk} {rec['form']} accession {accs[0]} was "
                            f"filed on {rec['date']} (sources: {src_line}; "
                            f"consistency={rec['consistency']}). The "
                            f"claim's date {', '.join(dates)} does not "
                            f"match.")
                # path 2: no accession — check claim date against the full
                # set of filing dates for that form on that ticker
                if evidence is None and ti:
                    real = ti.filing_dates_of_form(tk, form)
                    if real and not any(d in real for d in dates):
                        tail = real[-6:] if len(real) > 6 else real
                        evidence = (
                            f"DETERMINISTIC FACT [SOURCE: time_index] "
                            f"{tk} {form} filings on record were filed on "
                            f"{', '.join(tail)} (showing {len(tail)} of "
                            f"{len(real)} dates; sources: filename + "
                            f"sec_submissions + filings.json). The claim's "
                            f"date {', '.join(dates)} does not match any "
                            f"actual {form} filing date for this ticker.")
                # path 3: time_index missing/empty — fall back to original
                # catalog-only fact_store query so the producer still works
                if evidence is None:
                    recs = self.retriever.fact_store.filings_of(
                        tk, form=form,
                        accession=accs[0] if accs else None)
                    if not recs:
                        continue
                    real = sorted({r["date"] for r in recs if r["date"]})
                    if not real or any(d in real for d in dates):
                        break
                    evidence = (
                        f"DETERMINISTIC FACT [SOURCE: catalog] {tk} "
                        f"{form} filings were filed on {', '.join(real)} "
                        f"(accession-encoded). The claim's date "
                        f"{', '.join(dates)} does not match any actual "
                        f"filing date for this form.")
                out.append({
                    "quote": q, "kind": "date", "tier": "exact",
                    "evidence": evidence})
                break
        return out
```

---

## 第 4 步：替换 `_period_end_candidates` 函数体 + 类级正则

历史上这个函数被 `38f2737 drop period-end FP generator` 摘出 `run()` 是因为 Finnhub `earnings.period` 日历标签泄漏。新版**唯一真值源**改成 `time_index.fiscal_period`（只来自 `financials_reported.endDate`，结构上杜绝了标签泄漏），并**只比对紧邻"ending/截至"的日期**——避免段落里同时出现真假日期时被装作合理。

把现有 `_period_end_candidates`（如果还存在）整段替换；同时在 `ReviewAgent` 类内加一个 class-level 正则：

```python
    # Date immediately following the period-end cue, within one sentence.
    # Narrowing to the *adjacent* date avoids the FP where a paragraph
    # asserts a wrong "ending" date AND separately mentions the true
    # period-end (e.g. in a `financials_reported` block in the same para).
    _PERIOD_END_NEAR_RE = re.compile(
        r"(?:ending|ended|截至|结束)"
        r"[^.。\n]{0,60}?"
        r"("
        r"20\d{2}-\d{2}-\d{2}|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep(?:t)?|Oct|Nov|Dec)"
        r"[a-z]*\.?\s+\d{1,2},?\s+20\d{2}|"
        r"20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"
        r")",
        re.I)

    def _period_end_candidates(self, claims: list[dict],
                               primary: list[str]) -> list[dict]:
        """Fiscal-quarter-end verifier. Truth is `time_index.fiscal_period`
        whose only source is `financials_reported.endDate` — by
        construction the Finnhub `earnings.period` calendar label cannot
        leak into the truth, fixing the FP-generator regression that got
        this method dropped from `run()`.

        Only the date IMMEDIATELY adjacent to the period-end cue is
        treated as the claim's period-end assertion. A claim that
        mis-states the end-date but separately echoes the true date
        elsewhere in the paragraph would otherwise be silently accepted."""
        out: list[dict] = []
        ti = self.time_index
        if not ti:
            return out
        for c in claims:
            q = c["quote"]
            raws = self._PERIOD_END_NEAR_RE.findall(q)
            if not raws:
                continue
            near_dates: list[str] = []
            for raw in raws:
                near_dates.extend(_parse_dates(raw))
            if not near_dates:
                continue
            year, quarter = _parse_period(q)
            if year is None or quarter is None:
                continue
            for tk in self._scope(q, primary):
                fp = ti.fiscal_period(tk, year, quarter)
                if not fp:
                    continue
                true_end = fp["end"]
                if any(d == true_end for d in near_dates):
                    continue
                out.append({
                    "quote": q,
                    "kind": "date_timeline", "tier": "exact",
                    "evidence": (
                        f"DETERMINISTIC FACT [SOURCE: {fp['source']}] "
                        f"{tk} FY{year} Q{quarter} period endDate is "
                        f"{true_end} (startDate {fp['start']}, form "
                        f"{fp['form']}). The claim's date "
                        f"{', '.join(near_dates)} (asserted as the "
                        f"period end) does not match.")})
                break
        return out
```

---

## 第 5 步：把 `_period_end_candidates` 接回 `run()` 的 det-exact 生产者列表

定位 `run()` 里这段（云端文件大约在 line 440 附近，按文本搜索）：

```python
        for c in (self._numeric_candidates(claims, primary)
                  + self._date_candidates(claims, primary)
                  + self._price_candidates(claims, primary)
                  + self._peer_candidates(claims, primary)
                  + self._arithmetic_candidates(claims)
                  + self._table_candidates(anc, primary)):
```

在 `_date_candidates` 之后插入 `_period_end_candidates`：

```python
        for c in (self._numeric_candidates(claims, primary)
                  + self._date_candidates(claims, primary)
                  + self._period_end_candidates(claims, primary)   # ← 加这行
                  + self._price_candidates(claims, primary)
                  + self._peer_candidates(claims, primary)
                  + self._arithmetic_candidates(claims)
                  + self._table_candidates(anc, primary)):
```

如有"`_period_end_candidates dropped: ...`"那段说明性注释，可一并替换为：

```python
        # _period_end_candidates was once dropped because the old
        # `period_rows` path leaked the Finnhub `earnings.period`
        # calendar-quarter label into the truth (FP source). Now backed
        # by `time_index.fiscal_period` whose only source is
        # `financials_reported.endDate`, so calendar-label is structurally
        # impossible to confuse with fiscal-end.
```

---

## 第 6 步：跑 build + 验证

```bash
python reference_submission/build_time_index.py
# 期望末行: time_index v2: 50 tickers, 84331 accessions ...

python3 -c "
import sys; sys.path.insert(0,'reference_submission')
from retrieval.timeparse import TimeIndex
ti = TimeIndex.load()
print('report_02:', ti.filing_by_accession('TSLA','0001628280-25-003063')['date'])  # 2025-01-30
print('report_04:', ti.fiscal_period('WMT',2026,3)['end'])                           # 2025-10-31
print('report_09 #2:', '2025-08-23' in ti.filing_dates_of_form('NEE','8-K'))         # False
"
```

端到端跑（要 LLM）：

```bash
python reference_submission/run.py review \
  --requests path/to/review_train_3.jsonl \
  --out /tmp/out
# 期望: report_02 / 04 / 09 各 emit 1 个 tier=exact 的 timestamp issue
```

---

## 兼容性 / 不踩坑

1. **不要把 earnings.json.period 接回 `fiscal_periods` 真值**。它在 v2 索引里单独躺在 `earnings_periods["fy|fq"]`，带 `_warning` 字段，仅供 Generate 拿 actual/estimate 时参考。
2. **不要用 `accepted_utc[:10]` 当申报日比对**。规范日永远用 `rec["date"]`（已是 ET 日历日，与 SEC 官方 filing date 对齐）。`accepted_utc/et` 仅当报告做"时间线/可得性"类高精度判断时用。
3. **`TimeIndex` 是只读**。生产环境别在 review 流程中改它，否则索引 stale。
4. **pyarrow 缺失不影响**。timeparse 不读 parquet（按需读由调用方负责），无 pyarrow 也能完整工作。
