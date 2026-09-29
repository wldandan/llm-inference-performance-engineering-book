#!/usr/bin/env bash
# Optimized: FP8 KV cache. Only this line differs from serve_baseline.sh.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="--max-model-len 8192 --kv-cache-dtype fp8" \
  bash ../common/serve.sh
