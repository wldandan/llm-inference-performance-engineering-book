"""Split a bench_client.py report into 'long request' vs 'short request'
results and print percentiles for each separately.

Why this exists: compare.py's default summary aggregates every request
together, which dilutes exactly the signal this workshop is about (chunked
prefill protects SHORT requests' tail latency from a co-scheduled LONG
request's Prefill -- the aggregate p95 across both classes hides that).

requests.jsonl for this workshop has row 0 as the long request and rows 1-6
as short requests, cycled by bench_client.load_request_plan in that order,
and bench_client.main() preserves submission order in `results`, so
`results[i]` corresponds to `requests.jsonl` line `i % 7`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from bench_client import percentile  # noqa: E402

LONG_REQUEST_ROW_INDEX = 0
ROWS_PER_CYCLE = 7


def split_by_class(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    long_results = []
    short_results = []
    for i, result in enumerate(results):
        if i % ROWS_PER_CYCLE == LONG_REQUEST_ROW_INDEX:
            long_results.append(result)
        else:
            short_results.append(result)
    return long_results, short_results


def class_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    values = [r["total_latency_ms"] for r in results if r.get("success") and r.get("total_latency_ms") is not None]
    return {
        "count": len(results),
        "p50_total_latency_ms": percentile(values, 50),
        "p95_total_latency_ms": percentile(values, 95),
        "p99_total_latency_ms": percentile(values, 99),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", help="A bench_client.py JSON report (baseline.json or optimized.json)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    with open(args.report, encoding="utf-8") as f:
        report = json.load(f)
    long_results, short_results = split_by_class(report["results"])
    print(f"label: {report.get('label')}")
    print("short requests:", json.dumps(class_stats(short_results), indent=2))
    print("long request:  ", json.dumps(class_stats(long_results), indent=2))


if __name__ == "__main__":
    main()
