#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
LABEL="optimized" \
CONFIG_NOTE="kv-cache-dtype fp8" \
CONCURRENCY="${CONCURRENCY:-16}" \
REQUESTS="${REQUESTS:-64}" \
  bash ../common/bench.sh
