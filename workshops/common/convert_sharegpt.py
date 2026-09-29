"""Convert the book's ch09/sharegpt_samples.json into a workshop requests.jsonl.

Source: `Hands-On LLM Serving and Optimization` (Chi Wang & Peiheng Hu, O'Reilly),
ch09/sharegpt_samples.json -- a real ShareGPT-derived sample set with prompt_len /
expected_output_len already computed. See workshops/common/naive_baseline_server/NOTICE.md
for the same attribution note.

Picking real short and real long prompts (rather than hand-written ones) gives every
"long/short mixed workload" workshop (02, 09, ...) a believable, reusable request set
instead of each workshop inventing its own toy prompts.

Usage:
    python3 convert_sharegpt.py --source /path/to/sharegpt_samples.json \
        --short-n 5 --long-n 3 --max-tokens-cap 300 --output requests.jsonl
"""

from __future__ import annotations

import argparse
import json
from typing import Any


def pick_short_and_long(rows: list[dict[str, Any]], short_n: int, long_n: int) -> list[dict[str, Any]]:
    by_len = sorted(rows, key=lambda r: r["prompt_len"])
    shortest = by_len[:short_n]
    longest = by_len[-long_n:] if long_n else []
    return shortest + longest


def to_request_rows(rows: list[dict[str, Any]], max_tokens_cap: int) -> list[dict[str, Any]]:
    return [
        {"prompt": row["prompt"], "max_tokens": min(row.get("expected_output_len", max_tokens_cap), max_tokens_cap)}
        for row in rows
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="Path to sharegpt_samples.json")
    parser.add_argument("--short-n", type=int, default=5)
    parser.add_argument("--long-n", type=int, default=3)
    parser.add_argument("--max-tokens-cap", type=int, default=300)
    parser.add_argument("--output", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    with open(args.source, encoding="utf-8") as f:
        rows = json.load(f)
    selected = pick_short_and_long(rows, args.short_n, args.long_n)
    request_rows = to_request_rows(selected, args.max_tokens_cap)
    with open(args.output, "w", encoding="utf-8") as f:
        for row in request_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(request_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
