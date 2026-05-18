# AlphaSight

基于 **2025–2026 美股多源金融语料** 的研报生成 + 错误检测比赛。
需要实现一个 `Submission` 类，覆盖两类任务，跑出 `output/` 上交评测。

---

## 1. 两类任务

```python
# 你的 submission.py 跟 schemas.py / catalog.py / llm.py 同级（都在
# reference_submission/ 里），直接 import 即可。
from schemas import GenerateRequest, ReviewRequest, Report, ReviewIssue

class Submission:
    def __init__(self) -> None: ...
    def generate(self, request: GenerateRequest) -> Report: ...
    def review(self, request: ReviewRequest) -> list[ReviewIssue]: ...
```

- **`generate(GenerateRequest) -> Report`**：给定研究题目（`request.topic`），产出一份研究报告。
- **`review(ReviewRequest) -> list[ReviewIssue]`**：给定一份已有研报正文
  （`request.report_markdown`），找出其中事实 / 逻辑错误。每条问题：
  - `quote`：从报告原文**逐字摘出**的可疑片段
  - `reason`：一两句话说明错在哪 / 正确版本是什么
  - 找不到错误就返回 `[]`

Schema 定义见 [`reference_submission/schemas.py`](reference_submission/schemas.py)。

---

## 2. 快速上手

### 2.1 qz 平台启动

选择qz平台公开可见镜像 - alphasight:v1 启动实例


把发送的Summer-Camp-Projects.zip文件上传到你的目录 '/inspire/qb-ilm2/project/26summer-camp-03/xxx-xxxxxxxxx/'
解压Summer-Camp-Projects.zip

```bash
unzip Summer-Camp-Projects.zip
```

从public路径拷数据：

```bash
cp -r /inspire/qb-ilm2/project/26summer-camp-03/public/dataset ./Summer-Camp-Projects/
```

### 2.2 起 vLLM 端点（集群）

集群上 4× H200。`/inspire/hdd/global_public/public_models/Qwen` 下的
任意 Qwen 模型都能用，以 `Qwen2.5-72B-Instruct` 为例：

```bash
vllm serve /inspire/hdd/global_public/public_models/Qwen/Qwen2.5-72B-Instruct \
  --served-model-name Qwen2.5-72B-Instruct \
  --tensor-parallel-size 4 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 65536 \
  --port 8000 --host 0.0.0.0
```

换模型只需改路径 + `--served-model-name`。另起终端
`curl -s http://localhost:8000/v1/models` 验活。完整参数说明见
[`deploy/README.md`](deploy/README.md)。

### 2.3 跑 generate + review

设置环境变量（LLM 端点 + 数据路径）：

```bash
# LLM 端点
export ALPHASIGHT_LLM_BASE_URL=http://localhost:8000/v1
export ALPHASIGHT_LLM_MODEL=Qwen2.5-72B-Instruct   # = vllm --served-model-name

# 数据路径 (假设你在仓库根目录, dataset 已解压在此)
export ALPHASIGHT_CORPUS_DIR=$PWD/dataset/corpus
export ALPHASIGHT_PRICES_DIR=$PWD/dataset/prices
export ALPHASIGHT_PRICES_MINUTE_DIR=$PWD/dataset/prices_minute
export ALPHASIGHT_CATALOG_PATH=$PWD/dataset/catalog.jsonl
```

跑通测试（用 `--example` 走 `ExampleSubmission`，不必先实现 `Submission`）：

```bash
python3 reference_submission/run.py generate --example \
    --requests reference_submission/problem/generate_sample.jsonl

python3 reference_submission/run.py review --example \
    --requests reference_submission/problem/review_sample.jsonl
```

Prompt 由 `Submission` 内部自己 load（默认从 `prompt_templates/` 里读
`reference_generate.md` / `reference_review.md`），CLI 不传。产物输出：

- `output/generate/<request_id>.md` —— 每个请求一份 md
- `output/review.jsonl` —— 所有评审聚合，每行一条 `{request_id, issues}`

---

## 3. 实现你的 Submission

[`reference_submission/submission.py`](reference_submission/submission.py)
里有两个类：

- `ExampleSubmission` —— 最小可跑通的 baseline：`catalog → 词重叠 top-k → 读文件 → 单轮 LLM`。**只作参考，刻意做得简单**。
- `Submission` —— 真正被调用的入口。默认是 stub，三个方法都 `raise NotImplementedError`，由你来填。

最快上手：让 `Submission` 继承 `ExampleSubmission` 拿 baseline 行为，再逐方法 override：

```python
class Submission(ExampleSubmission):
    pass
```

**正式跑 generate** 任务：

```bash
python3 reference_submission/run.py generate \
    --requests reference_submission/problem/generate_free.jsonl
```

**正式跑 review** 任务（**val 集是最终提交评测的**）：

```bash
# 在 train 上调试 (有 GT 可以本地对比)
python3 reference_submission/run.py review \
    --requests reference_submission/problem/review_train.jsonl

# 在 val 上跑 (产物 output/review.jsonl 上交评测系统)
python3 reference_submission/run.py review \
    --requests reference_submission/problem/review_val.jsonl
```

LLM 参数（temperature / max_tokens / top_p / vLLM extras 等）见
`reference_submission/submission.yaml`。

---

## 4. 评判标准

### Generate 任务

本届以**功能性**为先——参赛者需要为 10 道题各产出一份扎根语料、有立场的 Markdown 研究报告。

### Review 任务

主办方提供三组含错研报（train / val / test）作为测试集（见 §5）；你的 `review()` 输出 `{quote, reason}` 列表，由判分 LLM 与 gold 标签做 issue-level 匹配。

最终在 leaderboard 上展示的是 **val 集** 提交分数（比赛末切换到 test 集）。

> **命名硬约束**：考生输出 `review.jsonl` 里每条记录的 `request_id` 必须与题目 `ReviewRequest.request_id` 完全一致（即 `report_01` ~ `report_20`），判分按此键对齐 ground truth，命名错位即视为漏检。


---

## 5. 题库

题库放在 `reference_submission/problem/` 内，作为参赛者提交的一部分：

```
reference_submission/problem/
├── generate_requests.jsonl   # 6 道固定题（gen-1..6），公司/行业级深度问题
├── generate_free.jsonl       # 4 个自由槽（gen-free-1..4），参赛者自填 topic
├── generate_sample.jsonl     # 1 条 generate 样例（测试用）
├── review_sample.jsonl       # 1 条 review 样例（测试用）
├── review_sample_gt.jsonl    # review 样例的 ground truth（参考输出）
│
├── review_train.jsonl        # train 集: 20 题, 公开 GT 用于调试
├── review_train_gt.jsonl     # train 集的标准答案 (训练用)
└── review_val.jsonl          # val 集: 20 题, GT 不公开, 提交后自动评测
```

**4 个自由题** (`gen-free-1..4`)：由参赛者自己改写 topic 后一起提交——这部分自定题目也是参赛内容的一部分。

### Review 任务的三个题集

Review 任务（研报错误检测）的题目分三份：

| 集合 | 题量 | 说明 | GT 是否公开 |
|---|---|---|---|
| **train** | 20 | 调试用，含中英文。 `review_train.jsonl` + `review_train_gt.jsonl` | ✅ 全公开 |
| **val** | 20 | 提交后自动评测，分数上 leaderboard。 `review_val.jsonl` | ❌ 不公开 |
| **test** | 20 | 比赛最终评测用 | ❌ 不公开  |

每篇研报每行格式 `{request_id, report_markdown}`，每篇可能注入 **0~N 个**事实/逻辑错误（存在整篇无错误的题目）。


---

## 6. 数据

完整语料以**压缩包**形式分发（`dataset.zip`），解压到本仓库根目录`dataset/` 文件夹下。
详情见[`dataset/README.md`](dataset/README.md)。


---

## 7. 打包提交

参赛者直接复制 `reference_submission/` 改名为 `submission/`，
在内部填好自己的代码 + 自由槽题目 + 可选资产：

```
submission/
├── submission.yaml           # team_id + LLM 参数（已包含丰富的 chat() 参数样板）
├── submission.py             # 你的 Submission 类
├── run.py                    # 入口（一般不动，直接用参考版本）
├── problem/
│   ├── generate_requests.jsonl   # 6 道固定题（不要改）
│   ├── generate_free.jsonl       # 4 个自由槽：把 topic 填成你自选方向
│   ├── generate_sample.jsonl     # 样例
│   ├── review_sample.jsonl       # 样例 (1 条)
│   ├── review_train.jsonl        # train 集 (20 题, 含 GT)
│   ├── review_train_gt.jsonl     # train 标签
│   └── review_val.jsonl          # val 集 (20 题, 提交后评测)
├── inference/                # 可选：自定义推理服务
│   ├── start_vllm.sh
│   ├── model_weights/
│   └── inference_config.yaml
├── index/                    # 可选：预构建索引 / embedding 缓存
├── env/                      # 可选：离线依赖
│   ├── requirements.txt
│   └── wheels/
└── README.md                 # 可选：自述
```


**评测无外网**：运行期不允许联网。运行时依赖需要打包`env/`，模型权重必须打包 `inference/model_weights/`。

---

## 8. 仓库结构

```
.
├── README.md
├── .env.example
├── requirements.txt
│
├── reference_submission/           参赛者要提交的整个目录（SDK + 题库 + 参考代码）
│   ├── run.py                      入口：python reference_submission/run.py
│   ├── submission.py               ExampleSubmission（参考） + Submission
│   ├── submission.yaml             team_id + LLM 参数
│   ├── schemas.py                  GenerateRequest / Report / ReviewRequest / ReviewIssue / DocMeta
│   ├── catalog.py                  catalog.jsonl 加载 / 过滤 / 票池
│   ├── llm.py                      OpenAI 兼容客户端（含 vLLM extras）
│   ├── prompt_templates/
│   │   ├── reference_generate.md
│   │   └── reference_review.md
│   └── problem/
│       ├── generate_requests.jsonl     6 道固定题
│       ├── generate_free.jsonl         4 个自由题
│       ├── generate_sample.jsonl       generate 样例（1 条）
│       ├── review_sample.jsonl         review 样例（1 条）
│       ├── review_sample_gt.jsonl      review 样例对应的 GT
│       ├── review_train.jsonl          review train 集（20 题）
│       ├── review_train_gt.jsonl       review train 标签
│       └── review_val.jsonl            review val 集（20 题, GT 不公开）
│
├── deploy/                         vLLM 端点部署说明（基础设施，不属于提交内容）
│   └── README.md
│
└── dataset/                        语料
    └── README.md
```
