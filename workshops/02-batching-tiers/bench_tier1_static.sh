#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

python3 ../common/naive_baseline_server/bench_naive.py \
  --base-url "${BASE_URL:-http://127.0.0.1:8000}" \
  --mode static \
  --requests-file requests.jsonl \
  --requests "${REQUESTS:-10}" \
  --label "tier1_static" \
  --output tier1_static.json
