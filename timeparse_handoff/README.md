# timeparse handoff package

这是时间戳归一化层的原始交接包。当前项目已经完成适配，项目级文档集中放在 `docs/timestamp/`。

## 当前入口

| 路径 | 用途 |
|---|---|
| `docs/timestamp/README.md` | 当前项目共享方式、最终作用和调用方式。 |
| `docs/timestamp/BUILD_AND_IMPLEMENTATION.md` | 构建脚本、索引 schema、Review 接入和验证流程。 |
| `docs/timestamp/archive/` | 原始调研、交接适配步骤和旧实施文档归档。 |

## 交接包保留内容

| 路径 | 用途 |
|---|---|
| `reference_submission/retrieval/timeparse.py` | 原始交接模块副本。当前已落位到 `reference_submission/retrieval/timeparse.py`。 |
| `reference_submission/build_time_index.py` | 原始构建脚本副本。当前已落位到 `reference_submission/build_time_index.py`。 |

## 当前已落地的项目文件

```text
reference_submission/retrieval/timeparse.py
reference_submission/build_time_index.py
reference_submission/agents/review.py
docs/timestamp/README.md
docs/timestamp/BUILD_AND_IMPLEMENTATION.md
docs/timestamp/archive/
dataset/time_index.json
```

`dataset/time_index.json` 是生成物，被 `.gitignore` 的 `dataset/` 规则忽略，不入仓。

## 快速验证

```bash
python3 reference_submission/build_time_index.py
python3 -c "import sys; sys.path.insert(0,'reference_submission'); from retrieval.timeparse import TimeIndex; ti = TimeIndex.load(); assert ti.filing_by_accession('TSLA','0001628280-25-003063')['date']=='2025-01-30'; assert ti.fiscal_period('WMT',2026,3)['end']=='2025-10-31'; assert '2025-07-23' in ti.filing_dates_of_form('NEE','8-K'); assert '2025-08-23' not in ti.filing_dates_of_form('NEE','8-K'); print('build OK')"
```
