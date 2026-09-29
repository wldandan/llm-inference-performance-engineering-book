#!/usr/bin/env bash
# Tier 3: vLLM, default config (continuous batching + PagedAttention + CUDA
# Graph, all of it -- this is NOT an isolated "just continuous batching"
# measurement, see README.md for why that's unavoidable here.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-facebook/opt-125m}" \
EXTRA_ARGS="" \
  bash ../common/serve.sh
