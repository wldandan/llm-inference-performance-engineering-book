"""Manual quality spot-check for KV cache quantization.

FP8 KV cache is a LOSSY optimization (unlike PagedAttention). This script is
NOT an automated quality gate -- it prints a fixed set of factual/reasoning
prompts' outputs so a human can eyeball whether the optimized server's
answers still make sense. Run once against the baseline server, once against
the optimized server, and diff the two output files by hand (or read them
side by side).

Usage:
    python3 quality_check.py --base-url http://127.0.0.1:8000/v1 \
        --model Qwen/Qwen2.5-7B-Instruct --output baseline_quality.txt
"""

from __future__ import annotations

import argparse
import json
import urllib.request

CHECK_PROMPTS = [
    "What is 17 * 24? Show your work in one line, then give the final answer.",
    "In one sentence, what does the acronym TTFT stand for in the context of LLM inference serving?",
    "List the first 5 prime numbers, comma separated, nothing else.",
]


def ask(base_url: str, api_key: str, model: str, prompt: str, timeout: float) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "temperature": 0.0,
        "stream": False,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def run_checks(base_url: str, api_key: str, model: str, timeout: float) -> list[dict[str, str]]:
    return [{"prompt": p, "answer": ask(base_url, api_key, model, p, timeout)} for p in CHECK_PROMPTS]


def format_report(label: str, rows: list[dict[str, str]]) -> str:
    lines = [f"=== quality check: {label} ==="]
    for row in rows:
        lines.append(f"Q: {row['prompt']}")
        lines.append(f"A: {row['answer']}")
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", default="run")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = run_checks(args.base_url, args.api_key, args.model, args.timeout)
    text = format_report(args.label, rows)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
