#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

python3 ../common/naive_baseline_server/bench_naive.py \
  --base-url "${BASE_URL:-http://127.0.0.1:8000}" \
  --mode continuous \
  --requests-file requests.jsonl \
  --requests "${REQUESTS:-10}" \
  --label "tier2_continuous_naive" \
  --output tier2_continuous_naive.json
