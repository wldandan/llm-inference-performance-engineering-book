#!/usr/bin/env bash
# Optimized: omit --enforce-eager so vLLM captures and replays CUDA Graphs
# for Decode (its default behavior). Only this line differs from
# serve_baseline.sh -- no other flag changes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="" \
  bash ../common/serve.sh
