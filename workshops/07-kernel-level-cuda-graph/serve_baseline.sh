#!/usr/bin/env bash
# Baseline: --enforce-eager disables CUDA Graph capture/replay, forcing plain
# eager-mode PyTorch execution -- every Decode step pays full kernel launch
# and CPU dispatch overhead.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="--enforce-eager" \
  bash ../common/serve.sh
