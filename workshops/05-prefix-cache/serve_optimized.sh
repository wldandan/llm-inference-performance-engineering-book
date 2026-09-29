#!/usr/bin/env bash
# Optimized: prefix caching ON. Only this line differs from serve_baseline.sh.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
EXTRA_ARGS="--enable-prefix-caching" \
  exec bash ../common/serve.sh
