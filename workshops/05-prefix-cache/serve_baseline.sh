#!/usr/bin/env bash
# Baseline: prefix caching explicitly OFF. Newer vLLM defaults can vary by
# version, so this baseline forces it off rather than assuming a default.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="--no-enable-prefix-caching" \
  exec bash ../common/serve.sh
