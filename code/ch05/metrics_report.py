#!/usr/bin/env python3
"""Calculate a synthetic client-side LLM metrics report from JSONL records."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def nearest_rank_percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(percentile / 100 * len(ordered))
    return ordered[rank - 1]


def _number(record: dict, name: str) -> float:
    value = record.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    return value


def request_metrics(record: dict) -> dict[str, object]:
    request_id = record.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("request_id must be a non-empty string")
    start_ms = _number(record, "start_ms")
    end_ms = _number(record, "end_ms")
    if end_ms < start_ms:
        raise ValueError("end_ms must not precede start_ms")

    success = record.get("success")
    if not isinstance(success, bool):
        raise ValueError("success must be a boolean")
    quality_pass = record.get("quality_pass")
    if not isinstance(quality_pass, bool):
        raise ValueError("quality_pass must be a boolean")
    quality_metric = record.get("quality_metric")
    evaluator_name = record.get("evaluator_name")
    evaluator_version = record.get("evaluator_version")
    if not all(isinstance(value, str) and value for value in (
        quality_metric,
        evaluator_name,
        evaluator_version,
    )):
        raise ValueError("quality metric and evaluator fields must be non-empty strings")
    quality_score = _number(record, "quality_score")
    quality_threshold = _number(record, "quality_threshold")
    if not math.isfinite(quality_score) or not math.isfinite(quality_threshold):
        raise ValueError("quality score and threshold must be finite")
    if quality_pass != (quality_score >= quality_threshold):
        raise ValueError("quality_pass must equal quality_score >= quality_threshold")
    prompt_tokens = record.get("prompt_tokens")
    output_tokens = record.get("output_tokens")
    if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        raise ValueError("prompt_tokens must be a non-negative integer")
    if not isinstance(output_tokens, int) or output_tokens < 0:
        raise ValueError("output_tokens must be a non-negative integer")
    cost_usd = _number(record, "cost_usd")
    if cost_usd < 0:
        raise ValueError("cost_usd cannot be negative")

    token_times = record.get("token_times_ms")
    if not isinstance(token_times, list) or any(
        not isinstance(value, (int, float)) or isinstance(value, bool)
        for value in token_times
    ):
        raise ValueError("token_times_ms must be a list of numbers")
    if token_times != sorted(token_times):
        raise ValueError("token_times_ms must be sorted")
    if token_times and (token_times[0] < start_ms or token_times[-1] > end_ms):
        raise ValueError("token timestamps must stay inside the request window")

    if success and output_tokens <= 0:
        raise ValueError("successful records require output_tokens > 0")
    if len(token_times) != output_tokens:
        raise ValueError("output_tokens must equal the token_times_ms count")

    itls = [current - previous for previous, current in zip(token_times, token_times[1:])]
    return {
        "request_id": request_id,
        "success": success,
        "quality_pass": quality_pass,
        "quality_metric": quality_metric,
        "quality_score": quality_score,
        "quality_threshold": quality_threshold,
        "evaluator_name": evaluator_name,
        "evaluator_version": evaluator_version,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "e2e_ms": end_ms - start_ms,
        "ttft_ms": token_times[0] - start_ms if token_times else None,
        "itls_ms": itls,
        "tpot_ms": sum(itls) / len(itls) if itls else None,
    }


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "p50": nearest_rank_percentile(values, 50),
        "p95": nearest_rank_percentile(values, 95),
        "p99": nearest_rank_percentile(values, 99),
    }


UNMEASURED_BUDGET_SEGMENTS = (
    {
        "segment": "first_token -> first_chunk_received",
        "belongs_to": "ttft",
        "why_unavailable": "no server-side event pair in this sample; see chapter 2 section 7",
        "consumes": "part of unallocated_before_first_token_ms",
    },
)


def build_latency_budget(
    *,
    ttft_slo_ms: float,
    e2e_slo_ms: float,
    client_to_gateway_ms: float,
    admission_ms: float,
    queue_ms: float,
    scheduled_to_first_token_ms: float,
    decode_streaming_ms: float,
    response_tail_ms: float,
) -> dict[str, object]:
    """Split an SLO into allocated per-stage budgets plus one shared slack pool.

    The two slack numbers are NOT additive with the allocated stages: total slack
    is ``e2e_slo - e2e_allocated``, and the part of it that must be spent before
    the first token is ``ttft_slo - ttft_allocated``. Adding every row of a budget
    table together is exactly the mistake this function exists to prevent.
    """
    values = {
        "client_to_gateway_ms": client_to_gateway_ms,
        "admission_ms": admission_ms,
        "queue_ms": queue_ms,
        "scheduled_to_first_token_ms": scheduled_to_first_token_ms,
        "decode_streaming_ms": decode_streaming_ms,
        "response_tail_ms": response_tail_ms,
    }
    if ttft_slo_ms <= 0 or e2e_slo_ms <= 0 or any(value < 0 for value in values.values()):
        raise ValueError("SLO and latency budget values must be non-negative, with positive SLOs")
    ttft_allocated = (
        client_to_gateway_ms + admission_ms + queue_ms + scheduled_to_first_token_ms
    )
    if ttft_allocated > ttft_slo_ms:
        raise ValueError("TTFT budget exceeds TTFT SLO")
    e2e_allocated = ttft_allocated + decode_streaming_ms + response_tail_ms
    if e2e_allocated > e2e_slo_ms:
        raise ValueError("E2E budget exceeds E2E SLO")
    slack_total = e2e_slo_ms - e2e_allocated
    slack_before_first_token = ttft_slo_ms - ttft_allocated
    slack_after_first_token = slack_total - slack_before_first_token
    if slack_after_first_token < 0:
        raise ValueError(
            "TTFT slack exceeds total E2E slack: the TTFT budget cannot be honoured "
            "inside the E2E SLO, lower a TTFT stage or raise the E2E SLO"
        )
    return {
        "components_ms": values,
        "ttft_slo_ms": ttft_slo_ms,
        "ttft_allocated_ms": ttft_allocated,
        "e2e_slo_ms": e2e_slo_ms,
        "e2e_allocated_ms": e2e_allocated,
        "unallocated_total_ms": slack_total,
        "unallocated_before_first_token_ms": slack_before_first_token,
        "unallocated_after_first_token_ms": slack_after_first_token,
        "slack_is_not_additive": (
            "unallocated_before_first_token_ms is part of unallocated_total_ms, "
            "not a separate row; allocated stages plus unallocated_total_ms equals the E2E SLO"
        ),
        "unmeasured_segments": [dict(item) for item in UNMEASURED_BUDGET_SEGMENTS],
    }


def build_report(
    records: list[dict],
    *,
    ttft_slo_ms: float,
    e2e_slo_ms: float,
    workload: dict | None = None,
    latency_budget: dict[str, object] | None = None,
) -> dict[str, object]:
    if not records:
        raise ValueError("records cannot be empty")
    if ttft_slo_ms <= 0 or e2e_slo_ms <= 0:
        raise ValueError("SLO thresholds must be positive")

    per_request = [request_metrics(record) for record in records]
    successful = [item for item in per_request if item["success"]]
    failed = [item for item in per_request if not item["success"]]
    starts = [_number(record, "start_ms") for record in records]
    ends = [_number(record, "end_ms") for record in records]
    window_ms = max(ends) - min(starts)
    if window_ms <= 0:
        raise ValueError("measurement window must be positive")
    window_seconds = window_ms / 1000

    successful_output_tokens = sum(int(item["output_tokens"]) for item in successful)
    partial_output_tokens = sum(int(item["output_tokens"]) for item in failed)
    observed_output_tokens = successful_output_tokens + partial_output_tokens
    good_requests = sum(
        1
        for item in successful
        if float(item["ttft_ms"]) <= ttft_slo_ms
        and float(item["e2e_ms"]) <= e2e_slo_ms
        and bool(item["quality_pass"])
    )
    ttfts = [float(item["ttft_ms"]) for item in successful]
    e2es = [float(item["e2e_ms"]) for item in successful]
    tpots = [float(item["tpot_ms"]) for item in successful if item["tpot_ms"] is not None]
    itls = [float(value) for item in successful for value in item["itls_ms"]]
    total_cost = sum(float(item["cost_usd"]) for item in per_request)
    quality_contracts = {
        (
            str(item["quality_metric"]),
            float(item["quality_threshold"]),
            str(item["evaluator_name"]),
            str(item["evaluator_version"]),
        )
        for item in per_request
    }
    if len(quality_contracts) != 1:
        raise ValueError("all records must use the same quality evaluation contract")
    quality_metric, quality_threshold, evaluator_name, evaluator_version = next(
        iter(quality_contracts)
    )

    return {
        "mode": "synthetic_client_metrics",
        "note": "报告用于演示指标口径，不是 Benchmark，也不代表任何真实服务性能。",
        "measurement_contract": {
            "source": "synthetic_request_records",
            "clock": "client_wall_clock_ms",
            "window": "min(start_ms) to max(end_ms)",
            "percentile_method": "nearest_rank",
            "tpot_definition": "mean interval between observed output tokens",
            "failure_output_policy": (
                "partial tokens are observed work but excluded from successful output rate"
            ),
            "goodput_definition": (
                "success AND quality_pass AND TTFT/E2E within SLO"
            ),
            "quality": {
                "metric": quality_metric,
                "threshold": quality_threshold,
                "evaluator_name": evaluator_name,
                "evaluator_version": evaluator_version,
            },
            "slo": {"ttft_ms": ttft_slo_ms, "e2e_ms": e2e_slo_ms},
        },
        "workload": workload or {},
        "latency_budget": latency_budget,
        "requests": {
            "total": len(per_request),
            "successful": len(successful),
            "failed": len(failed),
        },
        "latency_ms": {
            "ttft": _distribution(ttfts),
            "e2e": _distribution(e2es),
            "tpot": _distribution(tpots),
            "itl": _distribution(itls),
        },
        "throughput": {
            "measurement_window_seconds": window_seconds,
            "output_tokens": successful_output_tokens,
            "successful_output_tokens": successful_output_tokens,
            "partial_output_tokens": partial_output_tokens,
            "observed_output_tokens": observed_output_tokens,
            "submitted_requests_per_second_over_run_window": len(per_request) / window_seconds,
            "successful_requests_per_second": len(successful) / window_seconds,
            "successful_output_tokens_per_second": successful_output_tokens / window_seconds,
            "observed_output_tokens_per_second": observed_output_tokens / window_seconds,
            "good_requests": good_requests,
            "goodput_requests_per_second": good_requests / window_seconds,
        },
        "cost": {
            "total_cost_usd": total_cost,
            "usd_per_million_output_tokens": (
                total_cost / successful_output_tokens * 1_000_000
                if successful_output_tokens
                else None
            ),
            "usd_per_successful_request": (
                total_cost / len(successful) if successful else None
            ),
            "usd_per_good_request": (
                total_cost / good_requests if good_requests else None
            ),
            "denominator_note": (
                "usd_per_good_request uses the same definition as goodput: success AND "
                "quality_pass AND TTFT/E2E within SLO. It is the higher number because "
                "requests that ran but did not qualify still consumed resources. "
                "Tightening an SLO lowers goodput and therefore raises this cost without "
                "the service itself having changed."
            ),
        },
        "per_request": per_request,
    }


def load_jsonl(path: Path) -> list[dict]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"line {line_number}: record must be an object")
        records.append(value)
    return records


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", default=Path(__file__).with_name("sample.jsonl"))
    parser.add_argument("--ttft-slo-ms", type=float, default=250)
    parser.add_argument("--e2e-slo-ms", type=float, default=800)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--client-to-gateway-budget-ms", type=float, default=20)
    parser.add_argument("--admission-budget-ms", type=float, default=20)
    parser.add_argument("--queue-budget-ms", type=float, default=60)
    parser.add_argument("--scheduled-to-first-token-budget-ms", type=float, default=130)
    parser.add_argument("--decode-streaming-budget-ms", type=float, default=500)
    parser.add_argument("--response-tail-budget-ms", type=float, default=40)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = build_report(
        load_jsonl(args.input),
        ttft_slo_ms=args.ttft_slo_ms,
        e2e_slo_ms=args.e2e_slo_ms,
        workload={"name": "sample-interactive-chat", "source": args.input.name},
        latency_budget=build_latency_budget(
            ttft_slo_ms=args.ttft_slo_ms,
            e2e_slo_ms=args.e2e_slo_ms,
            client_to_gateway_ms=args.client_to_gateway_budget_ms,
            admission_ms=args.admission_budget_ms,
            queue_ms=args.queue_budget_ms,
            scheduled_to_first_token_ms=args.scheduled_to_first_token_budget_ms,
            decode_streaming_ms=args.decode_streaming_budget_ms,
            response_tail_ms=args.response_tail_budget_ms,
        ),
    )
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
