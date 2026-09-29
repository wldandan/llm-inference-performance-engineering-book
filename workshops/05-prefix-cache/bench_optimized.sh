#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
LABEL="optimized" \
CONFIG_NOTE="enable-prefix-caching" \
CONCURRENCY="${CONCURRENCY:-4}" \
REQUESTS="${REQUESTS:-20}" \
  bash ../common/bench.sh
