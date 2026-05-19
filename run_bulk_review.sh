#!/bin/bash
set -e

ROOT=/inspire/hdd/project/26summer-camp-03/26210833/Summer-Camp-Projects

export OPENAI_API_KEY="sk-Pmis7gCC2ZiQqf7B3jUHGnKVq0rM2z1VvUGxaLBJibijMezv"
export OPENAI_BASE_URL="https://apicz.boyuerichdata.com/v1"

cd "$ROOT"

mkdir -p generatedataset

python3 generate_dataset.py \
  --root "$ROOT" \
  --num_samples 2000 \
  --max_context_chars 24000 \
  --writer_models "gpt-4o" \
  --reviewer_models "gpt-4o" \
  --judge_model "gpt-4o"
