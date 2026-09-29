#!/usr/bin/env bash
# Baseline: chunked prefill explicitly OFF -- a long prompt's Prefill runs to
# completion in one shot, monopolizing the scheduler slot.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="--no-enable-chunked-prefill" \
  bash ../common/serve.sh
