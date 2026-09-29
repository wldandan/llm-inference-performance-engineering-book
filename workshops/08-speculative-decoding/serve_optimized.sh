#!/usr/bin/env bash
# Optimized: n-gram (a.k.a. prompt-lookup) speculative decoding. Chosen over
# EAGLE/Medusa for this workshop specifically because it needs no separate
# draft model checkpoint -- it speculates by looking up n-grams already seen
# in the prompt, so it's the easiest variant to actually stand up.
#
# NOTE: this script does NOT go through ../common/serve.sh -- that script
# passes EXTRA_ARGS through unquoted word-splitting, which would mangle the
# JSON string below (it contains spaces and quotes). This workshop needs its
# own launcher for that reason.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

exec python3 -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --served-model-name "$MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  --speculative-config '{"method": "ngram", "num_speculative_tokens": 4, "prompt_lookup_min": 2, "prompt_lookup_max": 5}'
