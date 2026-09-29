#!/usr/bin/env bash
# Baseline: standard autoregressive decode, no speculative decoding.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="" \
  bash ../common/serve.sh
