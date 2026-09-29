#!/usr/bin/env bash
# Run the Prefix Cache baseline and optimized configuration with the same
# workload, then write versioned JSON reports and a comparison table.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/v1}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-600}"
RESULT_ROOT="${RESULT_ROOT:-results}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RESULT_DIR="$RESULT_ROOT/$RUN_ID"
SERVER_PID=""

print_plan() {
  cat <<'EOF'
1. serve_baseline.sh: vLLM --no-enable-prefix-caching
2. bench_baseline.sh: shared requests.jsonl workload
3. serve_optimized.sh: vLLM --enable-prefix-caching
4. bench_optimized.sh: the same requests.jsonl workload
5. compare.py: ttft_avg_ms ttft_p95_ms output_throughput_tokens_per_second
EOF
}

if [[ "${1:-}" == "--dry-run" ]]; then
  print_plan
  exit 0
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: bash run_experiment.sh [--dry-run]" >&2
  exit 2
fi

for command in python3 curl vllm; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command not found: $command" >&2
    exit 2
  fi
done
if curl --silent --fail "$BASE_URL/models" >/dev/null 2>&1; then
  echo "A server is already responding at $BASE_URL; stop it or choose another BASE_URL/PORT." >&2
  exit 2
fi

mkdir -p "$RESULT_DIR"

stop_server() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  SERVER_PID=""
}
trap stop_server EXIT INT TERM

wait_until_ready() {
  local label="$1"
  local log_file="$2"
  local deadline=$((SECONDS + STARTUP_TIMEOUT))
  while (( SECONDS < deadline )); do
    if curl --silent --fail "$BASE_URL/models" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "$label server exited before becoming ready. Last log lines:" >&2
      tail -n 30 "$log_file" >&2 || true
      return 1
    fi
    sleep 2
  done
  echo "$label server was not ready after ${STARTUP_TIMEOUT}s. See $log_file" >&2
  return 1
}

run_variant() {
  local label="$1"
  local serve_script="$2"
  local bench_script="$3"
  local log_file="$RESULT_DIR/${label}-server.log"

  echo "Starting $label server..." >&2
  bash "$serve_script" >"$log_file" 2>&1 &
  SERVER_PID=$!
  wait_until_ready "$label" "$log_file"
  echo "Running $label workload..." >&2
  OUTPUT="$RESULT_DIR/${label}.json" BASE_URL="$BASE_URL" bash "$bench_script"
  stop_server
}

run_variant baseline serve_baseline.sh bench_baseline.sh
run_variant optimized serve_optimized.sh bench_optimized.sh

python3 ../common/compare.py \
  "$RESULT_DIR/baseline.json" \
  "$RESULT_DIR/optimized.json" \
  --metrics ttft_avg_ms ttft_p95_ms output_throughput_tokens_per_second \
  | tee "$RESULT_DIR/comparison.txt"

echo "Results written to $RESULT_DIR" >&2
