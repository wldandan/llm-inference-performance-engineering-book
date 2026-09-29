#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
LABEL="baseline" \
CONFIG_NOTE="--enforce-eager (CUDA Graph disabled)" \
CONCURRENCY="${CONCURRENCY:-8}" \
REQUESTS="${REQUESTS:-24}" \
  bash ../common/bench.sh
