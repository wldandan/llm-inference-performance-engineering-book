#!/usr/bin/env bash
# Usage: LABEL=baseline_predictable REQUESTS_FILE=requests_predictable.jsonl bash bench.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}" \
LABEL="${LABEL:?set LABEL, e.g. baseline_predictable / optimized_creative}" \
REQUESTS_FILE="${REQUESTS_FILE:?set REQUESTS_FILE}" \
CONCURRENCY="${CONCURRENCY:-4}" \
REQUESTS="${REQUESTS:-8}" \
OUTPUT="${LABEL}.json" \
  bash ../common/bench.sh
