#!/usr/bin/env bash
# One-click runner for the AlphaSight submission.
#
#   ./run.sh                 # generate (sample) + review (sample)
#   ./run.sh generate        # only generate over generate_sample.jsonl
#   ./run.sh review           # only review over review_sample.jsonl
#   ./run.sh index            # build the optional dense index (needs GPU model)
#   ./run.sh all              # index (best-effort) + generate + review
#
# Data paths / LLM endpoint are read from .env if present, else from the
# defaults below. The system runs BM25-only when the embedding model is
# absent, so `index` is optional.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUB="$ROOT/reference_submission"

# ---- load .env if present ----
if [[ -f "$ROOT/.env" ]]; then
  set -a; source "$ROOT/.env"; set +a
fi

# ---- defaults (override via .env or environment) ----
export ALPHASIGHT_CORPUS_DIR="${ALPHASIGHT_CORPUS_DIR:-$ROOT/dataset/corpus}"
export ALPHASIGHT_PRICES_DIR="${ALPHASIGHT_PRICES_DIR:-$ROOT/dataset/prices}"
export ALPHASIGHT_PRICES_MINUTE_DIR="${ALPHASIGHT_PRICES_MINUTE_DIR:-$ROOT/dataset/prices_minute}"
export ALPHASIGHT_CATALOG_PATH="${ALPHASIGHT_CATALOG_PATH:-$ROOT/dataset/catalog.jsonl}"
export ALPHASIGHT_LLM_BASE_URL="${ALPHASIGHT_LLM_BASE_URL:-http://localhost:8000/v1}"
export ALPHASIGHT_LLM_MODEL="${ALPHASIGHT_LLM_MODEL:-inference-model}"

CMD="${1:-default}"
PY="${PYTHON:-python3}"

build_index() {
  echo ">> building dense index (skips cleanly if model absent) ..."
  "$PY" "$SUB/build_index.py" \
    --corpus "$ALPHASIGHT_CORPUS_DIR" \
    --catalog "$ALPHASIGHT_CATALOG_PATH" \
    --out "$SUB/index" || true
}

run_generate() {
  echo ">> generate ..."
  "$PY" "$SUB/run.py" generate \
    --requests "$SUB/problem/generate_sample.jsonl"
}

run_review() {
  echo ">> review ..."
  "$PY" "$SUB/run.py" review \
    --requests "$SUB/problem/review_sample.jsonl"
}

case "$CMD" in
  index)    build_index ;;
  generate) run_generate ;;
  review)   run_review ;;
  all)      build_index; run_generate; run_review ;;
  default)  run_generate; run_review ;;
  *) echo "usage: ./run.sh [generate|review|index|all]"; exit 2 ;;
esac

echo ">> done. output -> $ROOT/output/"
