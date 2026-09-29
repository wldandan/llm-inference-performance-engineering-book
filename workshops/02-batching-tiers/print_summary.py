"""Print the 3-tier comparison for this workshop.

Tier 1 (naive static) reports one number for the whole batch (it's a single
blocking call), while Tier 2/3 (naive continuous, vLLM continuous) report
per-request percentiles -- the shapes genuinely differ, so this doesn't reuse
../common/compare.py's single metric table.
"""

from __future__ import annotations

import argparse
import json
from typing import Any


def load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def format_tier1(report: dict[str, Any]) -> str:
    s = report["summary"]
    return (
        f"[{report['label']}] batch_size={s.get('batch_size')} "
        f"total_latency_ms={s.get('total_latency_ms')} requests_per_second={s.get('requests_per_second')}"
    )


def format_tier_stream(report: dict[str, Any]) -> str:
    s = report["summary"]
    return (
        f"[{report['label']}] successes={s.get('successes')}/{s.get('requests')} "
        f"ttft_avg_ms={s.get('ttft_avg_ms')} ttft_p95_ms={s.get('ttft_p95_ms')} "
        f"itl_avg_ms={s.get('itl_avg_ms')}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tier1", help="tier1_static.json")
    parser.add_argument("tier2", help="tier2_continuous_naive.json")
    parser.add_argument("tier3", help="tier3_continuous_vllm.json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(format_tier1(load(args.tier1)))
    print(format_tier_stream(load(args.tier2)))
    print(format_tier_stream(load(args.tier3)))
    print()
    print("Tier1 has no TTFT (it's one blocking batch call, not streaming) -- compare")
    print("its requests_per_second against Tier2/3's throughput instead.")
    print("Tier1->Tier2 isolates scheduling (static vs continuous), same naive engine.")
    print("Tier2->Tier3 bundles scheduling + PagedAttention + CUDA Graph + everything")
    print("else vLLM does -- don't attribute all of that gap to batching alone.")


if __name__ == "__main__":
    main()
