vllm serve /inspire/hdd/global_public/public_models/Qwen/Qwen3-30B-A3B-Instruct-2507 \
  --served-model-name Qwen3-30B-A3B-Instruct-2507 \
  --tensor-parallel-size 4 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 262144 \
  --port 8000 --host 0.0.0.0
