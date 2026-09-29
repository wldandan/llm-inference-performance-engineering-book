#!/usr/bin/env bash
# Shared vLLM launcher for every workshop. Each workshop's serve_baseline.sh /
# serve_optimized.sh sources this and only supplies the flags that differ.
#
# Usage (called from a workshop dir):
#   MODEL=Qwen/Qwen2.5-7B-Instruct EXTRA_ARGS="--kv-cache-dtype fp8" bash ../common/serve.sh
set -euo pipefail

MODEL="${MODEL:?set MODEL, e.g. Qwen/Qwen2.5-7B-Instruct}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

echo "Starting vLLM: model=$MODEL host=$HOST port=$PORT extra_args=[$EXTRA_ARGS]" >&2

# Use the documented public CLI so failures and help text match current vLLM.
# shellcheck disable=SC2086
exec vllm serve "$MODEL" \
  --served-model-name "$MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  $EXTRA_ARGS
