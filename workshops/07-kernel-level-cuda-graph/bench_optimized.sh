#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
LABEL="optimized" \
CONFIG_NOTE="default (CUDA Graph enabled)" \
CONCURRENCY="${CONCURRENCY:-8}" \
REQUESTS="${REQUESTS:-24}" \
  bash ../common/bench.sh
