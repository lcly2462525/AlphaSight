# AlphaSight

AlphaSight 是一个面向金融研报场景的 **生成 + 审查** 双任务系统，基于本地 vLLM 端点运行。

- **Generate**：给定企业财务数据，自动生成结构化分析报告
- **Review**：对已有报告中的每条声明做事实核查，输出有错误的 issue 列表（F2 评分，召回率优先）

---

## 快速上手

### 1. 启动 vLLM 推理节点

```bash
# 在 GPU 节点上后台启动 vLLM 端点（默认 Qwen3-235B-A22B，4× H200）
bash vllm.sh
```

等日志出现 `INFO: Application startup complete.` 后继续。

### 2. 设置环境变量

```bash
# 复制模板后填入语料路径和端点地址
cp .env.example .env
source .env
```

关键变量：

| 变量 | 说明 |
|---|---|
| `ALPHASIGHT_CORPUS_DIR` | 语料根目录（含 `research/`、`filings/`、`news/`） |
| `ALPHASIGHT_PRICES_DIR` | 日线价格目录 |
| `ALPHASIGHT_PRICES_MINUTE_DIR` | 分钟级价格目录 |
| `ALPHASIGHT_CATALOG_PATH` | `catalog.jsonl` 路径 |
| `ALPHASIGHT_LLM_BASE_URL` | vLLM HTTP 端点，默认 `http://localhost:8000/v1` |
| `ALPHASIGHT_LLM_MODEL` | 模型短名，与 `--served-model-name` 一致 |

### 3. 运行

```bash
# 用 test.sh 内预设的路径一键跑（generate + review）
bash test.sh

# 或分别执行
python3 reference_submission/run.py generate \
    --requests reference_submission/problem/generate_requests.jsonl

python3 reference_submission/run.py review \
    --requests reference_submission/problem/review_val.jsonl
```

输出：
- Generate → `output/generate/<request_id>.md`
- Review → `output/review.jsonl`

---

## 项目结构

```
reference_submission/
├── run.py              # 入口：generate / review 两个子命令
├── submission.py       # Submission 主类，协调两个 Agent
├── agents/             # GenerateAgent、ReviewAgent
├── retrieval/          # BM25 检索 + news 模块
├── tools/              # 数据访问工具（corpus / prices / filings）
├── build_time_index.py # TimeIndex 预构建（4 源交叉验证）
├── build_index.py      # BM25 索引构建
├── llm.py              # OpenAI-compatible LLM 客户端封装
├── schemas.py          # Pydantic 数据模型
└── prompt_templates/   # 所有 LLM prompt 模板
```

---

## Review Agent 设计

Review 流水线：`① 抽 claim → ② 判类型 → ③ 定主体 → ④ 检索/查库 → ⑤ 核对 → ⑥ emit`

核心设计原则：

- **精度门控**：确定性 claim 须解析出唯一 `(ticker, year, quarter)` 绑定才进 exact 路径；叙事类走独立 LLM pass
- **绑定优先**：精度天花板是 prompt 契约和候选绑定逻辑，不是模型能力；FP 主因是错误绑定，换更强模型反而会更忠实地放大
- **检索分层**：数字/日期走 BM25 精确匹配（7/9 命中）；方向词（UPGRADE/DOWNGRADE）走词典；信源归属走软 emit；兜底走 LLM 定向提取
- **时间系统**：`build_time_index.py` 预生成 `time_index.json`，4 源交叉验证（filename / catalog / filings.json / sec_submissions），隔离 Finnhub 日历标签 vs 财季末两个不同语义

---

## vLLM 节点配置（4× H200）

详细参数说明见 [deploy/README.md](deploy/README.md)。当前 `vllm.sh` 默认配置：

```bash
vllm serve /inspire/hdd/global_public/public_models/Qwen/Qwen3-235B-A22B-Instruct-2507 \
  --served-model-name Qwen3-235B-A22B-Instruct-2507 \
  --tensor-parallel-size 4 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 65536 \
  --port 8000 --host 0.0.0.0
```

换模型只需修改权重路径和 `--served-model-name`，同步更新 `.env` 中的 `ALPHASIGHT_LLM_MODEL`。

**常见问题**：
- **OOM**：依次降低 `--gpu-memory-utilization` → `--max-model-len` → `--max-num-seqs` → 开 `--kv-cache-dtype fp8`
- **`/dev/shm` 空间不足**：`mount -o remount,size=32G /dev/shm`
- **卡被占用**：`export CUDA_VISIBLE_DEVICES=0,1,2,3` 后再启动

---

## 依赖

```bash
pip install -r requirements.txt
```
