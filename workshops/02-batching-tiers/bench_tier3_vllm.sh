#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-facebook/opt-125m}" \
LABEL="tier3_continuous_vllm" \
CONFIG_NOTE="vLLM default (continuous batching + PagedAttention + CUDA Graph)" \
CONCURRENCY="${CONCURRENCY:-10}" \
REQUESTS="${REQUESTS:-10}" \
OUTPUT="tier3_continuous_vllm.json" \
  bash ../common/bench.sh
