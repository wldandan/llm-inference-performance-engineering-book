#!/usr/bin/env bash
# Optimized: chunked prefill ON -- the long prompt's Prefill gets split into
# chunks that interleave with other requests' Decode steps.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="--enable-chunked-prefill" \
  bash ../common/serve.sh
