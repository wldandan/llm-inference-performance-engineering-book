"""Pure analysis of JSON request records; no runner or configuration dependency."""

import json
import math
from itertools import pairwise

METRIC_DEFINITIONS = {
    "duration_s": "Seconds from first measured start to last measured end, including failed tails; "
    "unknown if any interval is missing/invalid. Warmup excluded; monotonic clock only.",
    "requests_per_s": "Successful measured requests / entire measured duration_s (not reports/hour).",
    "actual_sent_per_s": "Observed dispatch spacing: (sent - 1) / (last sent start_s - first sent start_s). "
    "Includes failed/interrupted sends, excludes warmup and client_rejected. Null with fewer than two sends, "
    "missing starts, or zero start span. Separate from full-window completion throughput.",
    "offered": "Measured arrival records, including client_rejected; not the planned count or sent count.",
    "target_rate": "Configured arrivals per second in rate mode only; not achieved dispatch or completion rate.",
    "input_tokens_per_s": "Known input tokens of successful requests / entire window; includes cached "
    "prompt tokens, so this is NOT compute TPS. All successful counts must be known.",
    "output_tokens_per_s": "Known output tokens of successful requests / entire window; no chunk counting. "
    "All successful counts must be known; zero is valid.",
    "goodput_per_s": "Quality-pass successful requests also meeting every configured per-request "
    "latency limit / entire window. Unknown quality or required latency does not qualify.",
    "error_rate": "Service failures / sent requests, including interrupted requests in denominator. "
    "Client rejection and interruption are separate counts, not service failures.",
    "sent": "Measured records except client_rejected, including failures and interrupted sends.",
    "succeeded": "Measured records with status success AND success true.",
    "failed": "Sent records that failed, excluding interrupted/in-flight records.",
    "client_rejected": "Measured arrivals rejected by client admission; never counted as service failures.",
    "interrupted": "Sent records marked interrupted or lacking a terminal state.",
    "ttft_ms": "First observable output chunk latency, streaming successes only; not server prefill time.",
    "tpot_ms": "Estimated (e2e_ms - ttft_ms) / (output_tokens - 1), streaming successes only; "
    "unknown when output_tokens <= 1. Not per-token ITL.",
    "e2e_ms": "Recorded client latency of successful measured requests; not UTC subtraction.",
    "inter_chunk_ms": "Observable streaming chunk intervals, not token intervals or ITL.",
    "distribution": "Finite nonnegative samples only; mean and linearly interpolated p50/p95/p99 "
    "at (count - 1) * percentile. Each distribution includes its own sample count.",
    "quality": "pass/fail/unknown counts over sent measured requests. coverage=(pass+fail)/sent; "
    "pass_rate=pass/sent. Unknown never counts as pass. Empty denominator is null.",
    "deadline_s": "Projected seconds = target_requests / successful requests_per_s; if target is unset, "
    "actual measured duration. Projection is not a capacity guarantee.",
    "comparison": "Aligned workload only. Eligible completed runs ranked by goodput, requests/s, "
    "then lower p95 e2e. Fixture data never establishes model optimization.",
}

_DISTRIBUTIONS = ("ttft_ms", "tpot_ms", "e2e_ms", "inter_chunk_ms")
_LATENCY_GOALS = {"max_p95_e2e_ms": "e2e_ms", "max_p95_ttft_ms": "ttft_ms", "max_p95_tpot_ms": "tpot_ms"}
_ALIGNED_FIELDS = (
    "dataset",
    "load",
    "generation",
    "quality",
    "goals",
    "cache_condition",
    "tokenizer_path",
    "safety",
    "telemetry",
)
_UNFINISHED = {"interrupted", "started", "running", "pending", "cancelled"}


def _number(value, *, nonnegative=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        valid = math.isfinite(value) and (not nonnegative or value >= 0)
    except OverflowError:
        return None
    return value if valid else None


def _tokens(value):
    number = _number(value)
    return number if number is not None and number == int(number) else None


def _ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return _number(numerator / denominator, nonnegative=False)


def _sum(values):
    try:
        return _number(math.fsum(values))
    except OverflowError:
        return None


def _kind(record):
    status = record.get("status")
    if status == "client_rejected":
        return "client_rejected"
    if status in _UNFINISHED or not status:
        return "interrupted"
    if status == "success" and record.get("success") is True:
        return "succeeded"
    return "failed"


def _reject_json_constant(_value):
    raise ValueError("nonfinite JSON constant")


def _json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite JSON number")
    return number


def evaluate_quality(record: dict, quality: dict) -> dict:
    """Evaluate completion, hard quality failures, then explicit manual/rule checks."""
    kind = _kind(record)
    if kind in {"client_rejected", "interrupted"}:
        return {"status": "unknown", "reasons": ["No completed service response to evaluate."]}
    if kind == "failed":
        return {"status": "fail", "reasons": ["Service request failed."]}
    finish = record.get("finish_reason")
    if finish == "content_filter":
        return {"status": "fail", "reasons": ["Response was filtered."]}
    if finish == "length" and quality.get("reject_truncated", True):
        return {"status": "fail", "reasons": ["Response was truncated."]}
    mode = quality.get("mode", "rules")
    if mode == "manual":
        label = record.get("manual_label")
        if label in {"pass", "fail"}:
            return {"status": label, "reasons": ["Explicit manual label for this request."]}
        return {"status": "unknown", "reasons": ["Manual label is missing or unknown."]}
    if mode != "rules":
        return {"status": "unknown", "reasons": ["Quality has not been evaluated."]}
    text = record.get("output_text")
    if not isinstance(text, str):
        return {"status": "unknown", "reasons": ["Response text is unavailable."]}
    reasons = []
    if len(text) < quality.get("min_chars", 1):
        reasons.append("Response is shorter than the minimum character count.")
    if any(required not in text for required in quality.get("required_text", [])):
        reasons.append("Required text is missing.")
    fields = quality.get("json_fields", [])
    if quality.get("require_json", False) or fields:
        try:
            parsed = json.loads(text, parse_constant=_reject_json_constant, parse_float=_json_float)
        except (ValueError, RecursionError):
            reasons.append("Response is not valid finite JSON.")
        else:
            if fields and (not isinstance(parsed, dict) or any(field not in parsed for field in fields)):
                reasons.append("Required top-level JSON fields are missing.")
    return {"status": "fail" if reasons else "pass", "reasons": reasons}


def _distribution(values):
    samples = sorted(value for item in values if (value := _number(item)) is not None)
    result = {"count": len(samples), "mean": None, "p50": None, "p95": None, "p99": None}
    if samples:
        result["mean"] = _sum(value / len(samples) for value in samples)
        for name, percentile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
            rank = (len(samples) - 1) * percentile
            lower, upper = math.floor(rank), math.ceil(rank)
            # Weighted sum avoids overflow from adding two very large samples.
            result[name] = _sum((samples[lower] * (1 - (rank - lower)), samples[upper] * (rank - lower)))
    return result


def _timings(record):
    e2e = _number(record.get("e2e_ms"))
    ttft, tpot = None, None
    if record.get("is_stream") is True:
        ttft = _number(record.get("ttft_ms"))
        if e2e is not None and ttft is not None and ttft > e2e:
            ttft = None
        count = _tokens(record.get("output_tokens"))
        if e2e is not None and ttft is not None and count is not None and count > 1:
            tpot = _number((e2e - ttft) / (count - 1))
    return {"e2e_ms": e2e, "ttft_ms": ttft, "tpot_ms": tpot}


def _meets_latency(record, goals):
    timings = _timings(record)
    for name, metric in _LATENCY_GOALS.items():
        if goals.get(name) is not None:
            limit = _number(goals[name])
            if limit is None or timings[metric] is None or timings[metric] > limit:
                return False
    return True


def _metrics(records, spec):
    counts = {
        name: sum(_kind(row) == name for row in records)
        for name in ("succeeded", "failed", "client_rejected", "interrupted")
    }
    counts["sent"] = len(records) - counts["client_rejected"]
    intervals = [
        (_number(row.get("start_s"), nonnegative=False), _number(row.get("end_s"), nonnegative=False))
        for row in records
    ]
    valid_window = bool(intervals) and all(
        start is not None and end is not None and end >= start for start, end in intervals
    )
    duration = (
        _number(max(end for _, end in intervals) - min(start for start, _ in intervals))
        if valid_window
        else None
    )
    successful = [row for row in records if _kind(row) == "succeeded"]
    evaluations = [
        (row, evaluate_quality(row, spec.get("quality", {})))
        for row in records
        if _kind(row) != "client_rejected"
    ]
    quality = {
        state: sum(evaluation["status"] == state for _, evaluation in evaluations)
        for state in ("pass", "fail", "unknown")
    }
    quality["coverage"] = _ratio(quality["pass"] + quality["fail"], counts["sent"])
    quality["pass_rate"] = _ratio(quality["pass"], counts["sent"])
    good = sum(
        evaluation["status"] == "pass" and _meets_latency(row, spec.get("goals", {}))
        for row, evaluation in evaluations
    )
    metrics = {
        **counts,
        "offered": len(records),
        "target_rate": _number(spec.get("load", {}).get("rate"))
        if spec.get("load", {}).get("mode") == "rate"
        else None,
        "duration_s": duration,
        "requests_per_s": _ratio(counts["succeeded"], duration),
        "error_rate": _ratio(counts["failed"], counts["sent"]),
        "goodput_per_s": _ratio(good, duration),
    }
    starts = [
        _number(row.get("start_s"), nonnegative=False) for row in records if _kind(row) != "client_rejected"
    ]
    start_span = (
        _number(max(starts) - min(starts))
        if len(starts) >= 2 and all(value is not None for value in starts)
        else None
    )
    metrics["actual_sent_per_s"] = _ratio(counts["sent"] - 1, start_span)
    warnings = []
    if metrics["actual_sent_per_s"] is None:
        warnings.append("actual_sent_per_s is unknown: need two valid sent starts with a positive span.")
    if duration is None or duration == 0:
        warnings.append(
            "Measured time coverage is missing, invalid or zero; completion/token rates are unknown."
        )
    for field in ("input_tokens", "output_tokens"):
        values = [_tokens(row.get(field)) for row in successful]
        complete = bool(values) and all(value is not None for value in values)
        metrics[f"{field}_per_s"] = _ratio(_sum(values), duration) if complete else None
        if not complete:
            warnings.append(f"{field} coverage is incomplete; rate is unknown.")
    timings = [_timings(row) for row in successful]
    for field in ("ttft_ms", "tpot_ms", "e2e_ms"):
        metrics[field] = _distribution(row[field] for row in timings)
        if metrics[field]["count"] < len(successful):
            warnings.append(f"{field} coverage is incomplete; inspect distribution sample count.")
    metrics["inter_chunk_ms"] = _distribution(
        value
        for row in successful
        if row.get("is_stream") is True
        for value in (row.get("inter_chunk_ms") or [])
    )
    return metrics, quality, warnings


def _goals(metrics, quality, goals):
    actuals = {
        "min_requests_per_s": metrics.get("requests_per_s"),
        "max_error_rate": metrics.get("error_rate"),
        "min_quality_pass_rate": quality.get("pass_rate"),
    }
    for name, metric in _LATENCY_GOALS.items():
        distribution = metrics.get(metric) or {}
        covered = distribution.get("count", 0) > 0 and distribution.get("count") == metrics.get("succeeded")
        actuals[name] = distribution.get("p95") if covered else None
    target_requests = _number(goals.get("target_requests"))
    actuals["deadline_s"] = (
        _ratio(target_requests, metrics.get("requests_per_s"))
        if target_requests is not None
        else metrics.get("duration_s")
    )
    limits = {"min_quality_pass_rate": 1.0, "max_error_rate": 0.0, **goals}
    result = []
    for name, actual in actuals.items():
        if limits.get(name) is None:
            continue
        target = _number(limits[name])
        actual = _number(actual)
        status = "unknown"
        if target is not None and actual is not None:
            passed = actual >= target if name.startswith("min_") else actual <= target
            status = "pass" if passed else "fail"
        result.append({"name": name, "target": target, "actual": actual, "status": status})
    return result


def analyze(records: list[dict], spec: dict, telemetry=None, status="completed") -> dict:
    """Summarize measured rows without changing records or hiding failed tails."""
    measured = [row for row in records if row.get("phase") == "measure"]
    metrics, quality, warnings = _metrics(measured, spec)
    grouped = {}
    for row in measured:
        category = row.get("category") or "default"
        grouped.setdefault(category, []).append(row)
    groups = {category: _metrics(rows, spec)[0] for category, rows in grouped.items()}
    if status != "completed":
        warnings.append("Run is partial or not completed; observations cannot establish an optimization.")
    expected = _tokens(spec.get("load", {}).get("count"))
    if expected is not None and expected != len(measured):
        warnings.append(
            "Measured sample count differs from the planned count; completion coverage is incomplete."
        )
    if quality["unknown"]:
        warnings.append("Quality coverage is incomplete; unknown responses are not passes.")
    if spec.get("protocol_fixture"):
        warnings.append(
            "Protocol fixture only; these measurements do not prove model performance or optimization."
        )
    if not telemetry:
        warnings.append("Telemetry is unavailable; resource bottlenecks cannot be established.")
    elif any(
        frame.get("error")
        or not frame.get("metrics")
        or any(
            isinstance(metric, dict) and metric.get("status", "available") != "available"
            for metric in (frame.get("metrics") or {}).values()
        )
        for frame in _telemetry_frames(telemetry)
    ):
        warnings.append("Telemetry coverage is incomplete; inspect missing sources in the private local run.")
    return {
        "metrics": metrics,
        "groups": groups,
        "goals": _goals(metrics, quality, spec.get("goals", {})),
        "quality": quality,
        "warnings": warnings,
        "definitions": dict(METRIC_DEFINITIONS),
        "sample_count": len(measured),
    }


def _differences(left, right, prefix=""):
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(left.keys() | right.keys()):
            path = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                value = left[key] if key in left else right[key]
                result.extend(_differences({}, value, path) if isinstance(value, dict) and value else [path])
            else:
                result.extend(_differences(left[key], right[key], path))
        return result
    return [] if left == right else [prefix]


def _eligibility(run):
    summary, spec = run.get("summary") or {}, run.get("spec") or {}
    metrics, quality = summary.get("metrics") or {}, summary.get("quality") or {}
    reasons = []
    for field in ("dataset", "load", "generation", "quality", "goals", "endpoint"):
        if field not in spec or spec[field] is None:
            reasons.append(f"Required {field} condition snapshot is missing.")
    if run.get("status") != "completed":
        reasons.append("Run is not completed.")
    if spec.get("protocol_fixture"):
        reasons.append("Protocol fixture cannot be ranked as model performance.")
    if any(
        (_number(value) or 0) <= 0
        for value in (
            summary.get("sample_count"),
            metrics.get("sent"),
            metrics.get("succeeded"),
            metrics.get("duration_s"),
        )
    ):
        reasons.append("Measured completion evidence is missing.")
    expected = _tokens(spec.get("load", {}).get("count"))
    if expected is None or expected != summary.get("sample_count"):
        reasons.append("Planned and measured request counts do not align.")
    if metrics.get("interrupted", 0) or metrics.get("client_rejected", 0):
        reasons.append("Interrupted or client-rejected workload is not eligible.")
    if quality.get("coverage") != 1:
        reasons.append("Quality coverage is incomplete.")
    for goal in _goals(metrics, quality, spec.get("goals", {})):
        if goal["status"] != "pass":
            reasons.append(f"Goal {goal['name']} is not passed.")
    if any(goal.get("status") != "pass" for goal in (summary.get("goals") or [])):
        reasons.append("Recorded goal constraints are failed or unknown.")
    if _number(metrics.get("requests_per_s")) is None or _number(metrics.get("goodput_per_s")) is None:
        reasons.append("Comparable throughput evidence is missing.")
    return reasons


def _comparison_spec(spec):
    """Ignore only the new opt-out default without changing stored experiment snapshots."""
    telemetry = spec.get("telemetry")
    if isinstance(telemetry, dict):
        local = telemetry.get("local")
        if isinstance(local, dict) and set(local) <= {"enabled"} and local.get("enabled", False) is False:
            return {**spec, "telemetry": {key: value for key, value in telemetry.items() if key != "local"}}
    return spec


def compare_runs(runs: list[dict]) -> dict:
    """Compare aligned experiments; expose confounds and each run's gate failures."""
    reasons, differences, candidates = [], [], []
    ids = [run.get("id") for run in runs]
    if len(runs) < 2:
        reasons.append("At least two runs are required.")
    if any(not isinstance(run_id, str) or not run_id for run_id in ids) or len(set(ids)) != len(ids):
        reasons.append("Run identifiers must be present and unique.")
    if runs:
        reference = _comparison_spec(runs[0].get("spec") or {})
        for run in runs[1:]:
            config = _comparison_spec(run.get("spec") or {})
            paths = _differences(reference, config)
            differences.extend({"run_id": run.get("id"), "field": path} for path in paths)
            for field in _ALIGNED_FIELDS:
                if reference.get(field) != config.get(field):
                    reasons.append(f"Differing {field}: workload conditions are not aligned.")
    for run in runs:
        failures = _eligibility(run)
        candidates.append({"id": run.get("id"), "eligible": not failures, "reasons": failures})
    comparable = not reasons
    eligible = [run for run, candidate in zip(runs, candidates) if candidate["eligible"]]
    best = None
    if comparable and eligible:

        def rank(run):
            metrics = run["summary"]["metrics"]
            p95 = _number(metrics.get("e2e_ms", {}).get("p95"))
            return (
                metrics["goodput_per_s"],
                metrics["requests_per_s"],
                -p95 if p95 is not None else -math.inf,
            )

        best = max(eligible, key=rank)["id"]
    return {
        "comparable": comparable,
        "reasons": list(dict.fromkeys(reasons)),
        "candidates": candidates,
        "best_run_id": best,
        "differences": differences,
    }


def _metric_value(summary, name):
    metrics = summary.get("metrics") or {}
    if not isinstance(name, str):
        return None
    if name in {"requests_per_s", "input_tokens_per_s", "output_tokens_per_s", "goodput_per_s", "error_rate"}:
        return _number(metrics.get(name))
    parts = name.split(".") if isinstance(name, str) else []
    if len(parts) == 2 and parts[0] in _DISTRIBUTIONS and parts[1] in {"mean", "p50", "p95", "p99"}:
        distribution = metrics.get(parts[0]) or {}
        if parts[0] != "inter_chunk_ms" and distribution.get("count") != metrics.get("succeeded"):
            return None
        return _number(distribution.get(parts[1]))
    return None


def _retest_conditions(baseline, candidate, criterion):
    """Only a declared bounded load intervention may relax model-comparison alignment."""
    comparison = compare_runs([baseline, candidate])
    changes = _differences(
        baseline.get("spec", {}).get("endpoint", {}),
        candidate.get("spec", {}).get("endpoint", {}),
        "endpoint",
    )
    changes = [path for path in changes if path != "endpoint.api_key_env"]
    if "change" not in criterion:
        reasons = (
            []
            if len(changes) == 1
            else [
                "Retest requires one recorded endpoint/environment change or an explicit bounded load change."
            ]
        )
        return comparison, reasons, "Recorded endpoint/environment intervention."
    declaration = criterion["change"]
    if not isinstance(declaration, dict) or declaration.get("field") not in ("load.concurrency", "load.rate"):
        return comparison, ["Change declaration must identify load.concurrency or load.rate."], None
    field = declaration["field"]
    key = field.split(".")[1]
    before_spec, after_spec = baseline.get("spec") or {}, candidate.get("spec") or {}
    before_load, after_load = before_spec.get("load") or {}, after_spec.get("load") or {}
    before, after = _number(before_load.get(key)), _number(after_load.get(key))
    reasons = []
    if (
        before is None
        or after is None
        or before <= 0
        or after <= 0
        or before == after
        or _number(declaration.get("before")) != before
        or _number(declaration.get("after")) != after
    ):
        reasons.append("Declared before/after values must match the positive observed load change.")
    if key == "concurrency" and (before != _tokens(before) or after != _tokens(after)):
        reasons.append("Concurrency values must be integers.")
    mode = "concurrency" if key == "concurrency" else "rate"
    if before_load.get("mode") != mode or after_load.get("mode") != mode:
        reasons.append("Declared load variable must match the load mode.")
    if _differences(before_load, after_load, "load") != [field] or changes:
        reasons.append(
            "Only the declared load variable may change; model/environment and remaining load must align."
        )
    for config in (before_spec, after_spec):
        cap = _tokens((config.get("safety") or {}).get("max_concurrency"))
        concurrency = _tokens((config.get("load") or {}).get("concurrency"))
        if cap is None or concurrency is None or not 0 < concurrency <= cap:
            reasons.append("A recorded positive concurrency safety bound must cover both runs.")
            break
    if reasons:
        return comparison, reasons, None
    # A private comparison view masks exactly the declared intervention. Original
    # snapshots and metrics remain untouched, and all other compare/gate rules run.
    comparison_view = {**candidate, "spec": {**after_spec, "load": {**after_load, key: before_load[key]}}}
    comparison = compare_runs([baseline, comparison_view])
    return comparison, [], f"Declared {field} changed from {before} to {after}; other conditions aligned."


def evaluate_retest(baseline: dict, candidate: dict, criterion: dict) -> dict:
    """Assess a single environment intervention or an explicitly declared load change.

    Optional criterion.change: {field: "load.concurrency"|"load.rate", before, after}.
    A declared load test is a workload-tuning experiment, not a fair model ranking.
    Both runs must respect an unchanged safety bound and pass all evidence gates.
    """
    comparison, condition_reasons, intervention = _retest_conditions(baseline, candidate, criterion)
    reasons = [*comparison["reasons"], *condition_reasons]
    for entry in comparison["candidates"]:
        reasons.extend(entry["reasons"])
    metric = criterion.get("metric")
    before = _metric_value(baseline.get("summary") or {}, metric)
    after = _metric_value(candidate.get("summary") or {}, metric)
    threshold = _number(criterion.get("min_relative_change", 0))
    direction = criterion.get("direction")
    evidence = {
        "before": before,
        "after": after,
        "differences": [
            {"run_id": candidate.get("id"), "field": field}
            for field in _differences(baseline.get("spec") or {}, candidate.get("spec") or {})
        ],
    }
    if before is None or after is None or before == 0:
        reasons.append("Metric evidence is missing or the relative-change baseline is zero.")
    if threshold is None or direction not in {"increase", "decrease"}:
        reasons.append("Criterion direction or relative threshold is invalid.")
    if reasons:
        return {
            "status": "insufficient_evidence",
            "reasons": list(dict.fromkeys(reasons)),
            "change": None,
            **evidence,
        }
    change = _number((after - before) / abs(before), nonnegative=False)
    if change is None:
        return {
            "status": "insufficient_evidence",
            "reasons": ["Relative change is nonfinite."],
            "change": None,
            **evidence,
        }
    quality_before = baseline["summary"]["quality"]["pass_rate"]
    quality_after = candidate["summary"]["quality"]["pass_rate"]
    improved = change if direction == "increase" else -change
    effective = improved > 0 and improved >= threshold and quality_after >= quality_before
    return {
        "status": "effective" if effective else "ineffective",
        "change": change,
        **evidence,
        "reasons": [
            "Observed improvement meets the criterion with no quality regression; repeat to validate."
            if effective
            else "Improvement threshold was not met or quality regressed.",
            intervention,
        ],
    }


def _telemetry_frames(telemetry):
    if isinstance(telemetry, list):
        return telemetry
    if isinstance(telemetry, dict):
        return telemetry.get("samples", [telemetry])
    return []


def _observations(telemetry, key):
    observations = []
    for frame in _telemetry_frames(telemetry):
        value = _observation(frame, key)
        if value is not None:
            observations.append(value)
    return observations


def _observation(frame, key):
    if frame.get("error"):
        return None
    metric = (frame.get("metrics") or {}).get(key)
    if isinstance(metric, dict):
        if metric.get("status", "available") != "available":
            return None
        metric = metric.get("value")
    return _number(metric)


def _counter_series(frame):
    metric = (frame.get("metrics") or {}).get("preemptions_total")
    series = metric.get("series", []) if isinstance(metric, dict) else []
    return {
        (item.get("metric"), tuple(sorted((item.get("labels") or {}).items()))): _number(item.get("value"))
        for item in series
    }


def _kv_evidence(telemetry):
    """Keep source and series identity; gaps/resets invalidate counter deltas."""
    sources = {}
    for frame in _telemetry_frames(telemetry):
        identity = (frame.get("source_kind", "prometheus"), frame.get("source"))
        sources.setdefault(identity, []).append(frame)
    for frames in sources.values():
        counters = [_observation(frame, "preemptions_total") for frame in frames]
        if len(counters) < 2 or any(value is None for value in counters):
            continue
        if any(b < a for a, b in pairwise(counters)) or counters[-1] <= counters[0]:
            continue
        series = [_counter_series(frame) for frame in frames]
        if any(
            current.keys() != series[0].keys() or any(value is None for value in current.values())
            for current in series
        ):
            continue
        if any(right[key] < left[key] for left, right in pairwise(series) for key in left):
            continue
        corroborating = []
        for frame in frames:
            queue = _observation(frame, "queue_waiting")
            occupancy = _observation(frame, "kv_cache_usage_ratio")
            if queue is not None and queue > 0 and occupancy is not None and 0.9 <= occupancy <= 1:
                corroborating.append((queue, occupancy))
        if corroborating:
            yield {
                "queue": max(queue for queue, _ in corroborating),
                "occupancy": max(occupancy for _, occupancy in corroborating),
                "preemptions": counters[-1] - counters[0],
            }


def diagnose(summary: dict, spec: dict, telemetry=None) -> list[dict]:
    """Emit candidates for investigation, never infer a KV cause from occupancy alone."""
    diagnoses = []

    def add(identifier, title, evidence, adjustment, risk, validation, confidence="low"):
        diagnoses.append(
            {
                "id": identifier,
                "title": title,
                "evidence": evidence,
                "confidence": confidence,
                "adjustment": adjustment,
                "risk": risk,
                "validation": validation,
                "status": "pending",
            }
        )

    if spec.get("protocol_fixture"):
        add(
            "insufficient_evidence",
            "Protocol fixture is not optimization evidence",
            ["Fixture measurements validate protocol behavior only."],
            "Collect real model measurements.",
            "Synthetic timing does not predict model performance.",
            "Repeat the same workload on the target model.",
        )
        return diagnoses
    metrics = summary.get("metrics") or {}
    rejected = _number(metrics.get("client_rejected")) or 0
    if rejected:
        add(
            "admission_rejection",
            "Client admission rejected measured arrivals",
            [
                f"Rejected arrivals: {rejected}; measured offered arrivals: {metrics.get('offered')}.",
                f"Sent requests: {metrics.get('sent')}; observed sent rate: {metrics.get('actual_sent_per_s')}.",
            ],
            "Inspect client concurrency bounds and arrival scheduling; test one explicitly declared load change.",
            "Admission rejection is an observed client signal, not a server root cause or service failure.",
            "Compare offered, sent, rejected, quality, and completion rates under the same safety bounds.",
        )
    actual, target = _number(metrics.get("actual_sent_per_s")), _number(metrics.get("target_rate"))
    if (
        spec.get("load", {}).get("mode") == "rate"
        and actual is not None
        and target is not None
        and actual < target
    ):
        add(
            "generator_shortfall",
            "Observed dispatch rate is below the configured arrival rate",
            [f"Target arrivals/s: {target}; observed sent/s: {actual}.", f"Rejected arrivals: {rejected}."],
            "Inspect generator scheduling, transport, and client admission with aligned request-start evidence.",
            "Start-span rates use a different window from completion throughput; this does not identify a root cause.",
            "Repeat with enough measured starts and compare offered, rejected, and actual sends before tuning service settings.",
        )
    failed = _number(metrics.get("failed")) or 0
    if failed:
        add(
            "service_errors",
            "Service failures constrain useful throughput",
            [f"Failed measured requests: {failed}; error rate: {metrics.get('error_rate')}."],
            "Inspect local failure categories and service health before tuning load.",
            "Reducing load may reduce capacity; raw errors may contain private data.",
            "Repeat aligned requests after one recorded change and verify error and quality gates.",
        )
    queues = _observations(telemetry, "queue_waiting")
    ttft = _number(metrics.get("ttft_ms", {}).get("p95"))
    queue_present = bool(queues) and max(queues) > 0
    if queue_present and ttft is not None:
        add(
            "queueing",
            "Queueing is a candidate contributor to first-output latency",
            [f"Observed queue maximum: {max(queues)} requests.", f"Client p95 TTFT: {ttft} ms."],
            "Inspect arrival rate, admission, and scheduling; vary one load parameter in a separate sweep.",
            "Client TTFT also includes transport and prefill; correlation does not isolate their contributions.",
            "Align telemetry to the measured interval and compare TTFT, queueing, quality, and goodput.",
            "medium",
        )
    for evidence in _kv_evidence(telemetry):
        add(
            "kv_pressure",
            "KV pressure is a candidate with corroborating preemptions",
            [
                f"Corroborating KV occupancy: {evidence['occupancy']}.",
                f"Same-source preemptions increased by {evidence['preemptions']} without an observed reset.",
                f"Corroborating queue: {evidence['queue']} requests.",
            ],
            "Inspect KV allocation, request lengths, and scheduler preemption; change one resource setting.",
            "High KV occupancy alone is normal; changing capacity can trade memory for concurrency.",
            "Verify stable telemetry series in the measured window; retest the same workload and quality gates.",
            "medium",
        )
    if not diagnoses or not telemetry:
        add(
            "insufficient_evidence",
            "Insufficient evidence for a resource bottleneck",
            ["Missing corroborating queue, resource, preemption, or timing evidence."],
            "Collect aligned resource telemetry and complete measured requests.",
            "A single latency or KV metric cannot identify the root cause.",
            "Validate source coverage and stable series; repeat with one recorded change.",
        )
    return diagnoses
