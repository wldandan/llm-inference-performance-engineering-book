#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
LABEL="baseline" \
CONFIG_NOTE="no-enable-chunked-prefill, long+short mixed requests" \
CONCURRENCY="${CONCURRENCY:-6}" \
REQUESTS="${REQUESTS:-21}" \
  bash ../common/bench.sh
