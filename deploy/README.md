# 部署：vLLM 推理端点（4× H200）

把 `/inspire/hdd/global_public/public_models/Qwen` 下的任意 Qwen 模型
起成 OpenAI 兼容的 HTTP 端点。本文以 `Qwen2.5-72B-Instruct` 为例，
换其它模型只需改路径 + `--served-model-name`。

## 0. 前置假设

- **硬件**：4× H200 (141 GB)
- **模型权重**：HuggingFace 标准目录，预放在
  `/inspire/hdd/global_public/public_models/Qwen/<model-dir>/`。

## 1. 起服务

```bash
vllm serve /inspire/hdd/global_public/public_models/Qwen/Qwen2.5-72B-Instruct \
  --served-model-name Qwen2.5-72B-Instruct \
  --tensor-parallel-size 4 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 65536 \
  --port 8000 --host 0.0.0.0
```

换模型：路径替换为 `Qwen/<your-model-dir>`，`--served-model-name` 改成
对应短名（客户端 `model` 字段填的就是这个）。

启动 1–3 分钟，日志里 `INFO:     Application startup complete.` 就 ready。

## 2. 验证

```bash
curl http://localhost:8000/v1/models
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-none" \
  -d '{"model":"Qwen2.5-72B-Instruct","messages":[{"role":"user","content":"hello"}],"max_tokens":16}'
```

## 3. 常用参数

按调优场景分组。`vllm serve --help` 看完整列表。

### 3.1 并行 / 显存

| 参数 | 说明 |
|---|---|
| `--tensor-parallel-size N` (`-tp`) | 把单层矩阵切到 N 张卡，N 必须 = 可见 GPU 数。4× H200 设 4。 |
| `--pipeline-parallel-size N` (`-pp`) | 跨多节点把层切片；单机一般用不到。 |
| `--gpu-memory-utilization F` | 单卡可用显存占比（0~1）；剩余留给 PyTorch / cuBLAS / NCCL。0.95 偏激进，OOM 调到 0.90。 |
| `--swap-space N` | 单卡 swap 到 CPU 内存的容量（GB）。长 prompt 多并发时增加。默认 4。 |
| `--enforce-eager` | 关闭 CUDA Graph，首 token 略慢但稳定；调试 / 低显存时打开。 |

### 3.2 模型加载

| 参数 | 说明 |
|---|---|
| `--dtype {auto,bfloat16,float16,float32,fp8}` | 权重精度。`auto` 跟 HF config 走；H100/H200 原生 bf16，A100 走 fp16。 |
| `--quantization {awq,gptq,fp8,fp8_e5m2,bitsandbytes,...}` | 加载量化权重。要权重目录本身是量化版（如 `Qwen2.5-72B-Instruct-AWQ`）。 |
| `--kv-cache-dtype {auto,fp8,fp8_e5m2,fp8_e4m3}` | KV cache 量化精度，能省一半 KV 显存，吞吐换精度。 |
| `--load-format {auto,pt,safetensors,dummy}` | 权重格式；`dummy` 加载随机权重，benchmark 用。 |
| `--trust-remote-code` | 允许加载 HF 模型代码（自定义架构需要）。Qwen 不需要。 |
| `--download-dir DIR` | HF 下载缓存路径。 |

### 3.3 上下文 / KV cache

| 参数 | 说明 |
|---|---|
| `--max-model-len N` | 单请求 prompt+output 上限 token 数。调高费 KV cache（线性扩张）。 |
| `--max-num-seqs N` | 并发请求数上限（默认 256）。打高对吞吐有利，但 KV cache 不够会拒绝新请求。 |
| `--max-num-batched-tokens N` | 单次前向 batch 的 token 上限。和 `max-num-seqs` 一起决定吞吐 / 显存。 |
| `--enable-prefix-caching` | 缓存共同前缀的 KV，**长 system prompt / few-shot 场景吞吐巨增**。强烈推荐。 |
| `--enable-chunked-prefill` | 把长 prefill 切块和 decode 交错调度，长 prompt 下降低首 token 延迟。 |
| `--block-size {8,16,32}` | KV cache 分块粒度。默认 16，一般不动。 |

### 3.4 服务 / 接口

| 参数 | 说明 |
|---|---|
| `--host HOST` | 监听地址。 |
| `--port N` | 监听端口。 |
| `--served-model-name NAME` | 客户端 `model` 字段要填的字符串；可多个（A/B 测试用）。 |
| `--api-key KEY` | 启用 bearer-token 鉴权。 |
| `--disable-log-stats` / `--disable-log-requests` | 关日志降噪。 |

### 3.5 引导解码 / 工具调用

| 参数 | 说明 |
|---|---|
| `--guided-decoding-backend {outlines,lm-format-enforcer,xgrammar}` | 启用 `guided_json` / `guided_regex` / `guided_choice` 的后端。`xgrammar` 通常最快。 |
| `--enable-auto-tool-choice` | OpenAI function calling 支持，需要配 `--tool-call-parser`。 |
| `--tool-call-parser {hermes,mistral,llama3_json,...}` | 不同模型族的 tool-call 格式 parser。 |

### 3.6 LoRA / 适配

| 参数 | 说明 |
|---|---|
| `--enable-lora` | 允许加载 LoRA adapter。 |
| `--lora-modules NAME=PATH ...` | 注册 adapter；客户端用 `model=NAME` 调用。 |
| `--max-lora-rank N` | LoRA rank 上限。 |
| `--max-loras N` | 同时驻留的 adapter 数量。 |

## 4. 常见问题

**`OSError: [Errno 28] No space left on device`**
模型加载时会展开 65 GB；`/dev/shm` 默认只有 64 MB。
`mount -o remount,size=32G /dev/shm`。

**4 张卡里有 1 张被别的进程占着**
外部 `export CUDA_VISIBLE_DEVICES=0,1,2,3` 选定具体卡；
`--tensor-parallel-size` 数字必须等于可见卡数。

**OOM**
依次试：调低 `--gpu-memory-utilization`（0.90/0.85）→ 调低 `--max-model-len`
→ 调低 `--max-num-seqs` → 开 `--kv-cache-dtype fp8` → 加 `--enforce-eager`。

**首 token 慢 / 长 prompt 卡**
开 `--enable-chunked-prefill`；prompt 复用率高时再开 `--enable-prefix-caching`。

**想换别的同尺寸模型**
把权重路径指到新目录就行；`--served-model-name` 跟着改，客户端
请求里 `model` 字段要对得上。
