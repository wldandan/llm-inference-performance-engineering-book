#!/usr/bin/env bash
# Serves BOTH Tier 1 (static, /generate) and Tier 2 (continuous, /generate_stream)
# from the same process -- see ../common/naive_baseline_server/NOTICE.md for
# where this server comes from and why it demonstrates both.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../common/naive_baseline_server"

export LLM_MODEL_NAME="${MODEL:-facebook/opt-125m}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"

echo "Starting naive_baseline_server: model=$LLM_MODEL_NAME port=$PORT" >&2
echo "NOTE: this is plain transformers, not vLLM -- expect it to be much slower per-token." >&2
python3 main.py
