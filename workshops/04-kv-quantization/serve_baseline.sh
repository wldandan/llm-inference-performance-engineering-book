#!/usr/bin/env bash
# Baseline: default KV cache dtype (fp16/bf16, whatever the model's native dtype is).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="--max-model-len 8192" \
  bash ../common/serve.sh
