"""Behavioral contract tests for T3, independent of runner/config imports."""

import copy
import importlib
import json

import pytest


def api():
    try:
        return importlib.import_module("perfworkbench.analysis")
    except ModuleNotFoundError as error:
        if error.name not in {"perfworkbench", "perfworkbench.analysis"}:
            raise
        pytest.fail("T3 analysis API has not been implemented")


def spec(**updates):
    result = {
        "endpoint": {"base_url": "http://localhost:8000/v1", "model": "model-a", "environment": {}},
        "dataset": [{"id": "sample", "messages": [{"role": "user", "content": "question"}]}],
        "load": {"mode": "concurrency", "concurrency": 1, "count": 2, "warmup": 0, "seed": 42},
        "generation": {"stream": True, "max_tokens": 16, "temperature": 0.0},
        "quality": {"mode": "rules", "min_chars": 1, "reject_truncated": True},
        "goals": {"mode": "offline", "min_quality_pass_rate": 1.0, "max_error_rate": 0.0},
        "cache_condition": "cold",
        "protocol_fixture": False,
    }
    result.update(updates)
    return result


def record(**updates):
    result = {
        "request_id": "abc1",
        "sample_id": "sample",
        "category": "default",
        "phase": "measure",
        "start_s": 0.0,
        "end_s": 1.0,
        "status": "success",
        "success": True,
        "is_stream": True,
        "input_tokens": 10,
        "output_tokens": 4,
        "e2e_ms": 1000.0,
        "ttft_ms": 100.0,
        "tpot_ms": 9999.0,
        "inter_chunk_ms": [200.0, 700.0],
        "output_text": "answer",
        "finish_reason": "stop",
        "manual_label": None,
    }
    result.update(updates)
    return result


def run(run_id="aaa1", duration=2.0, config=None, status="completed", **record_updates):
    config = spec() if config is None else config
    records = [
        record(
            request_id=f"abc{i}",
            start_s=i * duration / 2,
            end_s=(i + 1) * duration / 2,
            e2e_ms=duration * 500,
            **record_updates,
        )
        for i in range(2)
    ]
    return {
        "id": run_id,
        "spec": config,
        "status": status,
        "summary": api().analyze(records, config, status=status),
    }


def test_entire_measured_window_includes_failure_tail_and_excludes_warmup():
    rows = [
        record(phase="warmup", start_s=-100, end_s=200),
        record(),
        record(start_s=1, end_s=10, e2e_ms=9000, status="failed", success=False),
    ]
    result = api().analyze(rows, spec())
    m = result["metrics"]
    assert set(result) == {"metrics", "groups", "goals", "quality", "warnings", "definitions", "sample_count"}
    assert result["sample_count"] == 2
    assert m["duration_s"] == 10
    assert (m["sent"], m["succeeded"], m["failed"]) == (2, 1, 1)
    assert m["requests_per_s"] == pytest.approx(0.1)
    assert m["output_tokens_per_s"] == pytest.approx(0.4)
    assert m["error_rate"] == 0.5
    assert result["quality"] == {"pass": 1, "fail": 1, "unknown": 0, "coverage": 1.0, "pass_rate": 0.5}
    assert "failed" in result["definitions"]["duration_s"]


def test_distributions_use_linear_percentiles_with_counts_and_success_only_latency():
    rows = [record(start_s=i, end_s=i + 1, e2e_ms=value) for i, value in enumerate([100, 200, 300, 400])]
    result = api().analyze(rows, spec())
    assert result["metrics"]["e2e_ms"] == {
        "count": 4,
        "mean": 250,
        "p50": 250,
        "p95": pytest.approx(385),
        "p99": pytest.approx(397),
    }
    assert result["metrics"]["inter_chunk_ms"]["count"] == 8
    assert "token" in result["definitions"]["inter_chunk_ms"]


def test_tpot_is_usage_based_estimate_not_supplied_chunk_count():
    m = api().analyze([record()], spec())["metrics"]
    assert m["tpot_ms"]["mean"] == 300
    assert m["output_tokens_per_s"] == 4


@pytest.mark.parametrize(
    "updates",
    [
        {"is_stream": False},
        {"is_stream": None},
    ],
)
def test_nonstream_never_exposes_token_timing(updates):
    m = api().analyze([record(**updates)], spec())["metrics"]
    assert m["ttft_ms"]["count"] == m["tpot_ms"]["count"] == 0
    assert m["inter_chunk_ms"]["count"] == 0


@pytest.mark.parametrize("count", [None, 0, 1, -1, float("nan"), float("inf"), True, 1.5])
def test_tpot_unavailable_without_two_valid_tokens(count):
    m = api().analyze([record(output_tokens=count)], spec())["metrics"]
    assert m["tpot_ms"]["mean"] is None


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
def test_unknown_tokens_make_rate_nullable_and_warn_about_coverage(field):
    m = api().analyze([record(), record(start_s=1, end_s=2, **{field: None})], spec())
    assert m["metrics"][f"{field}_per_s"] is None
    assert any(field in warning and "coverage" in warning for warning in m["warnings"])


def test_zero_token_counts_are_valid_and_cached_usage_is_not_compute_tps():
    result = api().analyze([record(input_tokens=0, output_tokens=0, cached_tokens=1000)], spec())
    assert result["metrics"]["input_tokens_per_s"] == 0
    assert result["metrics"]["output_tokens_per_s"] == 0
    assert "compute" in result["definitions"]["input_tokens_per_s"]


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -2, "wrong", True])
def test_missing_invalid_endpoint_does_not_shorten_window(bad):
    result = api().analyze([record(), record(end_s=bad, status="failed", success=False)], spec())
    assert result["metrics"]["duration_s"] is None
    assert result["metrics"]["requests_per_s"] is None
    assert result["warnings"]
    json.dumps(result, allow_nan=False)


def test_negative_monotonic_origin_is_valid_but_reverse_interval_is_not():
    assert api().analyze([record(start_s=-5, end_s=-4)], spec())["metrics"]["duration_s"] == 1
    assert api().analyze([record(start_s=5, end_s=4)], spec())["metrics"]["duration_s"] is None


def test_rejected_interrupted_failed_remain_distinct():
    rows = [
        record(),
        record(start_s=1, end_s=2, status="client_rejected", success=False),
        record(start_s=2, end_s=3, status="interrupted", success=False),
        record(start_s=3, end_s=4, status="timeout", success=False),
    ]
    m = api().analyze(rows, spec(), status="cancelled")["metrics"]
    assert (m["sent"], m["succeeded"], m["failed"], m["client_rejected"], m["interrupted"]) == (3, 1, 1, 1, 1)
    assert m["error_rate"] == pytest.approx(1 / 3)
    assert m["duration_s"] == 4


@pytest.mark.parametrize("rows", [[], [record(phase="warmup")]])
def test_empty_measured_data_has_null_metrics_and_quality(rows):
    result = api().analyze(rows, spec())
    assert result["sample_count"] == 0
    assert result["metrics"]["duration_s"] is None
    assert result["quality"]["pass_rate"] is None
    assert result["quality"]["coverage"] is None
    assert result["metrics"]["e2e_ms"]["count"] == 0
    assert any(goal["status"] == "unknown" for goal in result["goals"])


def test_groups_have_their_own_windows_and_counts():
    result = api().analyze([record(category="short"), record(category="long", start_s=1, end_s=5)], spec())
    assert result["groups"]["short"]["requests_per_s"] == 1
    assert result["groups"]["long"]["requests_per_s"] == 0.25
    assert result["groups"]["long"]["sent"] == 1


def test_nonfinite_latency_is_excluded_not_serialized_as_nan():
    result = api().analyze(
        [record(e2e_ms=float("nan"), ttft_ms=float("inf"), inter_chunk_ms=[float("nan"), -1, 20, "bad"])],
        spec(),
    )
    assert result["metrics"]["e2e_ms"]["count"] == 0
    assert result["metrics"]["ttft_ms"]["count"] == 0
    assert result["metrics"]["inter_chunk_ms"]["mean"] == 20
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "label, expected",
    [("pass", "pass"), ("fail", "fail"), (None, "unknown"), ("unknown", "unknown"), ("PASS!", "unknown")],
)
def test_manual_quality_requires_explicit_valid_label(label, expected):
    assert api().evaluate_quality(record(manual_label=label), {"mode": "manual"})["status"] == expected


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "failed", "success": False},
        {"finish_reason": "length"},
        {"finish_reason": "content_filter"},
    ],
)
def test_manual_pass_cannot_override_failure_or_truncation(updates):
    result = api().evaluate_quality(record(manual_label="pass", **updates), {"mode": "manual"})
    assert result["status"] == "fail"
    assert result["reasons"]


@pytest.mark.parametrize(
    "text, rules, expected",
    [
        ('{"result":"ok"}', {"require_json": True, "json_fields": ["result"]}, "pass"),
        ('{"other":1}', {"json_fields": ["result"]}, "fail"),
        ("broken", {"require_json": True}, "fail"),
        ("[]", {"json_fields": ["result"]}, "fail"),
        ('{"x":NaN}', {"require_json": True}, "fail"),
        ("hello good", {"required_text": ["good"], "min_chars": 3}, "pass"),
        ("hello", {"required_text": ["good"]}, "fail"),
        ("a", {"min_chars": 2}, "fail"),
        (None, {}, "unknown"),
        ("", {}, "fail"),
    ],
)
def test_rule_quality(text, rules, expected):
    result = api().evaluate_quality(record(output_text=text), {"mode": "rules", **rules})
    assert result["status"] == expected
    assert isinstance(result["reasons"], list)


def test_quality_disabled_is_unknown_and_truncation_can_be_explicitly_allowed():
    assert api().evaluate_quality(record(), {"mode": "none"})["status"] == "unknown"
    assert (
        api().evaluate_quality(record(finish_reason="length"), {"mode": "rules", "reject_truncated": False})[
            "status"
        ]
        == "pass"
    )


def test_quality_unknown_uses_all_sent_requests_as_pass_rate_denominator():
    result = api().analyze(
        [record(manual_label="pass"), record(manual_label=None)], spec(quality={"mode": "manual"})
    )
    assert result["quality"] == {"pass": 1, "fail": 0, "unknown": 1, "coverage": 0.5, "pass_rate": 0.5}
    assert result["metrics"]["goodput_per_s"] == 1


def test_goals_include_quality_errors_latency_throughput_and_offline_deadline():
    config = spec(
        goals={
            "mode": "offline",
            "min_requests_per_s": 2,
            "max_p95_e2e_ms": 900,
            "max_p95_ttft_ms": 150,
            "max_p95_tpot_ms": 500,
            "min_quality_pass_rate": 1,
            "max_error_rate": 0,
            "deadline_s": 10,
            "target_requests": 25,
        }
    )
    result = api().analyze([record()], config)
    goals = {goal["name"]: goal for goal in result["goals"]}
    assert goals["min_requests_per_s"]["status"] == "fail"
    assert goals["max_p95_e2e_ms"]["status"] == "fail"
    assert goals["max_p95_ttft_ms"]["status"] == "pass"
    assert goals["max_p95_tpot_ms"]["status"] == "pass"
    assert goals["deadline_s"]["actual"] == 25
    assert goals["deadline_s"]["status"] == "fail"
    assert result["metrics"]["goodput_per_s"] == 0


def test_unknown_ttft_goal_is_unknown_and_partial_run_has_warning():
    config = spec(goals={"max_p95_ttft_ms": 200, "min_quality_pass_rate": 1, "max_error_rate": 0})
    result = api().analyze([record(is_stream=False)], config, status="cancelled")
    assert next(g for g in result["goals"] if g["name"] == "max_p95_ttft_ms")["status"] == "unknown"
    assert result["metrics"]["goodput_per_s"] == 0
    assert any("partial" in w for w in result["warnings"])


def test_analysis_is_pure_and_ignores_wall_clock_for_durations():
    rows = [record(started_at=9e20), record(start_s=1, end_s=2, started_at=-9e20)]
    config = spec()
    before = copy.deepcopy((rows, config))
    result = api().analyze(rows, config)
    assert result["metrics"]["duration_s"] == 2
    assert (rows, config) == before


def test_compare_allows_models_but_requires_same_workload_and_selects_eligible_best():
    slow = run()
    config = spec()
    config["endpoint"]["model"] = "model-b"
    fast = run("bbb2", duration=1, config=config)
    result = api().compare_runs([slow, fast])
    assert result["comparable"] is True
    assert result["best_run_id"] == "bbb2"
    assert result["differences"]
    assert len(result["candidates"]) == 2


@pytest.mark.parametrize(
    "path, value",
    [
        (("dataset",), [{"id": "changed", "messages": []}]),
        (("generation", "temperature"), 0.5),
        (("load", "concurrency"), 2),
        (("load", "seed"), 43),
        (("quality", "min_chars"), 100),
        (("goals", "min_quality_pass_rate"), 0.5),
        (("cache_condition",), "warm"),
        (("tokenizer_path",), "/different/tokenizer"),
    ],
)
def test_compare_explicitly_reports_confounded_conditions(path, value):
    config = spec()
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result = api().compare_runs([run(), run("bbb2", config=config)])
    assert result["comparable"] is False
    assert result["best_run_id"] is None
    assert any(path[0] in reason for reason in result["reasons"])


@pytest.mark.parametrize("status", ["cancelled", "failed", "running", "partial"])
def test_incomplete_run_cannot_win(status):
    result = api().compare_runs([run(), run("bbb2", duration=0.5, status=status)])
    assert result["best_run_id"] == "aaa1"
    assert result["candidates"][1]["eligible"] is False


@pytest.mark.parametrize(
    "case", ["fixture", "unknown_quality", "failed_quality", "goal", "empty", "missing_count"]
)
def test_ineligible_evidence_cannot_win(case):
    candidate = run("bbb2", duration=0.5)
    if case == "fixture":
        candidate["spec"]["protocol_fixture"] = True
    elif case == "unknown_quality":
        candidate["summary"]["quality"]["coverage"] = 0.5
    elif case == "failed_quality":
        candidate["summary"]["quality"]["pass_rate"] = 0
    elif case == "goal":
        candidate["summary"]["goals"].append({"name": "constraint", "status": "unknown"})
    elif case == "empty":
        candidate["summary"]["sample_count"] = 0
    else:
        candidate["summary"]["sample_count"] = 1
    result = api().compare_runs([run(), candidate])
    assert result["best_run_id"] in {"aaa1", None}
    assert result["candidates"][1]["eligible"] is False


def test_comparison_needs_two_runs_and_valid_unique_ids():
    assert api().compare_runs([])["best_run_id"] is None
    assert api().compare_runs([run()])["comparable"] is False
    assert api().compare_runs([run(), run()])["comparable"] is False


def tuned_run(duration=1.0):
    config = spec()
    config["endpoint"]["environment"]["precision"] = "fp8"
    return run("bbb2", duration=duration, config=config)


def test_retest_effective_only_with_one_recorded_change_and_threshold():
    criterion = {"metric": "requests_per_s", "direction": "increase", "min_relative_change": 0.5}
    result = api().evaluate_retest(run(), tuned_run(), criterion)
    assert result["status"] == "effective"
    assert result["change"] == 1
    assert api().evaluate_retest(run(), tuned_run(2), criterion)["status"] == "ineffective"


def test_retest_decrease_uses_latency_percentile():
    result = api().evaluate_retest(
        run(), tuned_run(), {"metric": "e2e_ms.p95", "direction": "decrease", "min_relative_change": 0.4}
    )
    assert result["status"] == "effective"
    assert result["change"] == -0.5


@pytest.mark.parametrize(
    "case",
    [
        "unchanged",
        "multiple",
        "fixture",
        "quality",
        "load",
        "zero",
        "nan",
        "bad_direction",
        "bad_metric",
        "negative_threshold",
    ],
)
def test_retest_insufficient_evidence_never_claims_improvement(case):
    baseline, candidate = run(), tuned_run()
    criterion = {"metric": "requests_per_s", "direction": "increase", "min_relative_change": 0}
    if case == "unchanged":
        candidate["spec"] = copy.deepcopy(baseline["spec"])
    elif case == "multiple":
        candidate["spec"]["endpoint"]["environment"]["engine"] = "changed"
    elif case == "fixture":
        candidate["spec"]["protocol_fixture"] = True
    elif case == "quality":
        candidate["summary"]["quality"]["coverage"] = 0.5
    elif case == "load":
        candidate["spec"]["load"]["concurrency"] = 2
    elif case in {"zero", "nan"}:
        baseline["summary"]["metrics"]["requests_per_s"] = 0 if case == "zero" else float("nan")
    elif case == "bad_direction":
        criterion["direction"] = "sideways"
    elif case == "bad_metric":
        criterion["metric"] = "not_a_metric"
    else:
        criterion["min_relative_change"] = -1
    result = api().evaluate_retest(baseline, candidate, criterion)
    assert result["status"] == "insufficient_evidence"
    assert result["reasons"]


def test_diagnose_high_kv_alone_is_insufficient_evidence():
    summary = api().analyze([record()], spec())
    telemetry = {"samples": [{"metrics": {"kv_cache_usage_ratio": 0.99}}]}
    diagnoses = api().diagnose(summary, spec(), telemetry)
    assert not any(d["id"] == "kv_pressure" for d in diagnoses)
    assert any(d["id"] == "insufficient_evidence" for d in diagnoses)


def test_diagnose_correlates_queue_and_preemption_evidence_and_supplies_validation():
    summary = api().analyze([record()], spec())
    telemetry = {
        "samples": [
            {"metrics": {"kv_cache_usage_ratio": 0.95, "preemptions_total": 2, "queue_waiting": 3}},
            {"metrics": {"kv_cache_usage_ratio": 0.99, "preemptions_total": 5, "queue_waiting": 6}},
        ]
    }
    diagnoses = api().diagnose(summary, spec(), telemetry)
    assert any(d["id"] == "kv_pressure" for d in diagnoses)
    for diagnosis in diagnoses:
        assert set(diagnosis) == {
            "id",
            "title",
            "evidence",
            "confidence",
            "adjustment",
            "risk",
            "validation",
            "status",
        }
        assert diagnosis["evidence"] and diagnosis["validation"] and diagnosis["risk"]
        assert diagnosis["status"] == "pending"


def test_counter_reset_and_fixture_do_not_establish_root_cause():
    summary = api().analyze([record()], spec())
    telemetry = {
        "samples": [
            {"metrics": {"kv_cache_usage_ratio": 0.99, "preemptions_total": 9, "queue_waiting": 5}},
            {"metrics": {"kv_cache_usage_ratio": 0.99, "preemptions_total": 1, "queue_waiting": 5}},
        ]
    }
    diagnoses = api().diagnose(summary, spec(protocol_fixture=True), telemetry)
    assert not any(d["id"] == "kv_pressure" for d in diagnoses)
    assert any("fixture" in str(d).lower() for d in diagnoses)


def test_service_errors_have_evidence_but_no_exact_tuning_prescription():
    summary = api().analyze([record(status="failed", success=False)], spec())
    diagnoses = api().diagnose(summary, spec())
    assert any(d["id"] == "service_errors" for d in diagnoses)
    assert all(d["confidence"] in {"low", "medium"} for d in diagnoses)


def test_latency_goal_requires_full_successful_request_coverage():
    config = spec(goals={"max_p95_ttft_ms": 200, "min_quality_pass_rate": 1, "max_error_rate": 0})
    result = api().analyze([record(), record(start_s=1, end_s=2, ttft_ms=None)], config)
    goal = next(goal for goal in result["goals"] if goal["name"] == "max_p95_ttft_ms")
    assert goal["status"] == "unknown"
    candidate = {"id": "bbb2", "spec": config, "summary": result, "status": "completed"}
    baseline = run(config=config)
    assert api().compare_runs([baseline, candidate])["candidates"][1]["eligible"] is False


def test_unknown_request_state_with_missing_end_is_interrupted_not_service_failure():
    result = api().analyze([record(status="", success=False, end_s=None)], spec(), status="partial")
    assert result["metrics"]["interrupted"] == 1
    assert result["metrics"]["failed"] == 0
    assert result["quality"]["unknown"] == 1


def test_successful_rows_with_impossible_ttft_are_not_used_for_latency_goal():
    config = spec(goals={"max_p95_ttft_ms": 2000})
    result = api().analyze([record(ttft_ms=2000)], config)
    assert result["metrics"]["ttft_ms"]["count"] == 0
    assert result["metrics"]["tpot_ms"]["count"] == 0


def test_retest_detects_multiple_changes_inside_new_environment_section():
    candidate = tuned_run()
    candidate["spec"]["endpoint"]["environment"] = {"engine": {"precision": "fp8", "scheduler": "new"}}
    result = api().evaluate_retest(run(), candidate, {"metric": "requests_per_s", "direction": "increase"})
    assert result["status"] == "insufficient_evidence"


@pytest.mark.parametrize("missing", ["dataset", "generation", "quality", "goals", "endpoint"])
def test_comparison_cannot_validate_runs_with_missing_condition_snapshots(missing):
    baseline, candidate = run(), tuned_run()
    baseline["spec"].pop(missing)
    candidate["spec"].pop(missing)
    comparison = api().compare_runs([baseline, candidate])
    assert comparison["best_run_id"] is None
    assert not any(entry["eligible"] for entry in comparison["candidates"])


def test_retest_rejects_quality_regression_even_above_configured_threshold():
    baseline, candidate = run(), tuned_run()
    for item in (baseline, candidate):
        item["spec"]["goals"]["min_quality_pass_rate"] = 0.5
    candidate["summary"]["quality"].update({"pass": 1, "fail": 1, "pass_rate": 0.5})
    result = api().evaluate_retest(baseline, candidate, {"metric": "requests_per_s", "direction": "increase"})
    assert result["status"] == "ineffective"


def test_deadline_without_target_uses_measured_duration():
    config = spec(goals={"deadline_s": 0.5})
    goal = next(goal for goal in api().analyze([record()], config)["goals"] if goal["name"] == "deadline_s")
    assert goal == {"name": "deadline_s", "actual": 1, "target": 0.5, "status": "fail"}


def telemetry_frame(value=2, source="engine", labels=None, available=True):
    return {
        "source": source,
        "metrics": {
            "queue_waiting": {"status": "available", "value": 5},
            "kv_cache_usage_ratio": {"status": "available", "value": 0.99},
            "preemptions_total": {
                "status": "available" if available else "missing",
                "value": value,
                "series": [{"metric": "preemptions", "labels": labels or {"device": "0"}, "value": value}],
            },
        },
    }


def test_diagnose_accepts_collector_metric_objects_and_stable_series():
    summary = api().analyze([record()], spec())
    diagnoses = api().diagnose(summary, spec(), [telemetry_frame(), telemetry_frame(5)])
    assert any(d["id"] == "kv_pressure" for d in diagnoses)


@pytest.mark.parametrize("case", ["source", "labels", "reset", "gap", "error", "separate_signals"])
def test_diagnosis_does_not_merge_incompatible_or_missing_telemetry(case):
    frames = [telemetry_frame(), telemetry_frame(5)]
    if case == "source":
        frames[1]["source"] = "other-engine"
    elif case == "labels":
        frames[1] = telemetry_frame(5, labels={"device": "1"})
    elif case == "reset":
        frames[0] = telemetry_frame(9)
    elif case == "gap":
        frames.insert(1, telemetry_frame(None, available=False))
    elif case == "error":
        frames[1]["error"] = "Authentication failed"
    else:
        frames[0]["metrics"]["queue_waiting"]["value"] = 0
        frames[1]["metrics"]["kv_cache_usage_ratio"]["value"] = 0.1
    diagnoses = api().diagnose(api().analyze([record()], spec()), spec(), frames)
    assert not any(d["id"] == "kv_pressure" for d in diagnoses)


def test_incomplete_telemetry_coverage_is_explicit_and_does_not_leak_error_body():
    result = api().analyze([record()], spec(), telemetry=[{"source": "gpu", "error": "CANARY-secret"}])
    assert any("Telemetry" in warning and "coverage" in warning for warning in result["warnings"])
    assert "CANARY-secret" not in json.dumps(result)


def test_json_quality_rejects_overflowing_numeric_literals():
    result = api().evaluate_quality(record(output_text='{"value":1e999}'), {"require_json": True})
    assert result["status"] == "fail"


def test_large_finite_values_do_not_overflow_metrics_or_export_nan():
    result = api().analyze(
        [
            record(input_tokens=10**1000, output_tokens=10**1000),
            record(input_tokens=10**308, output_tokens=10**308, start_s=1, end_s=2),
        ],
        spec(),
    )
    assert result["metrics"]["input_tokens_per_s"] is None
    json.dumps(result, allow_nan=False)


def test_comparison_and_diagnosis_preserve_inputs():
    runs = [run(), tuned_run()]
    telemetry = [telemetry_frame(), telemetry_frame(5)]
    before = copy.deepcopy((runs, telemetry))
    api().compare_runs(runs)
    api().evaluate_retest(*runs, {"metric": "requests_per_s", "direction": "increase"})
    api().diagnose(runs[0]["summary"], runs[0]["spec"], telemetry)
    assert (runs, telemetry) == before


def concurrency_retest():
    baseline = run(config=spec(safety={"max_concurrency": 4}))
    config = copy.deepcopy(baseline["spec"])
    config["load"]["concurrency"] = 2
    candidate = run("bbb2", duration=1, config=config)
    criterion = {
        "metric": "requests_per_s",
        "direction": "increase",
        "min_relative_change": 0.25,
        "change": {"field": "load.concurrency", "before": 1, "after": 2},
    }
    return baseline, candidate, criterion


def test_declared_bounded_concurrency_retest_is_effective_but_not_fair_model_comparison():
    baseline, candidate, criterion = concurrency_retest()
    before = copy.deepcopy((baseline, candidate, criterion))
    comparison = api().compare_runs([baseline, candidate])
    assert comparison["comparable"] is False
    assert comparison["best_run_id"] is None
    assert any("load" in reason for reason in comparison["reasons"])
    result = api().evaluate_retest(baseline, candidate, criterion)
    assert result["status"] == "effective"
    assert result["change"] == 1
    assert any("load.concurrency" in reason for reason in result["reasons"])
    assert (baseline, candidate, criterion) == before


def test_declared_concurrency_retest_can_be_ineffective():
    baseline, candidate, criterion = concurrency_retest()
    candidate = run("bbb2", duration=3, config=candidate["spec"])
    assert api().evaluate_retest(baseline, candidate, criterion)["status"] == "ineffective"


@pytest.mark.parametrize(
    "case",
    [
        "undeclared",
        "wrong_before",
        "wrong_after",
        "unsupported_field",
        "invalid_declaration",
        "missing_field",
        "second_load_change",
        "environment_change",
        "model_change",
        "dataset_change",
        "goals_change",
        "quality_change",
        "fixture",
        "partial",
        "quality_unknown",
        "quality_failed",
        "goal_failed",
        "missing_bound",
        "exceeds_bound",
        "noninteger",
        "wrong_load_mode",
        "zero",
        "nonfinite",
        "bool",
    ],
)
def test_concurrency_declaration_cannot_bypass_confounds_bounds_or_gates(case):
    baseline, candidate, criterion = concurrency_retest()
    if case == "undeclared":
        criterion.pop("change")
    elif case in {"wrong_before", "wrong_after"}:
        criterion["change"][case.removeprefix("wrong_")] = 3
    elif case == "unsupported_field":
        criterion["change"]["field"] = "generation.max_tokens"
    elif case == "invalid_declaration":
        criterion["change"] = ["load.concurrency"]
    elif case == "missing_field":
        criterion["change"].pop("field")
    elif case == "second_load_change":
        candidate["spec"]["load"]["seed"] = 99
    elif case == "environment_change":
        candidate["spec"]["endpoint"]["environment"]["precision"] = "fp8"
    elif case == "model_change":
        candidate["spec"]["endpoint"]["model"] = "other"
    elif case == "dataset_change":
        candidate["spec"]["dataset"][0]["messages"][0]["content"] = "different"
    elif case in {"goals_change", "quality_change"}:
        field = case.removesuffix("_change")
        candidate["spec"][field]["mode"] = "different"
    elif case == "fixture":
        baseline["spec"]["protocol_fixture"] = candidate["spec"]["protocol_fixture"] = True
    elif case == "partial":
        candidate["status"] = "cancelled"
    elif case == "quality_unknown":
        candidate["summary"]["quality"]["coverage"] = 0.5
    elif case == "quality_failed":
        candidate["summary"]["quality"]["pass_rate"] = 0.5
    elif case == "goal_failed":
        candidate["summary"]["goals"][0]["status"] = "fail"
    elif case == "missing_bound":
        baseline["spec"].pop("safety")
        candidate["spec"].pop("safety")
    elif case == "wrong_load_mode":
        baseline["spec"]["load"]["mode"] = candidate["spec"]["load"]["mode"] = "rate"
    else:
        values = {"exceeds_bound": 8, "noninteger": 1.5, "zero": 0, "nonfinite": float("nan"), "bool": True}
        candidate["spec"]["load"]["concurrency"] = criterion["change"]["after"] = values[case]
    result = api().evaluate_retest(baseline, candidate, criterion)
    assert result["status"] == "insufficient_evidence"
    assert result["reasons"]


def test_declared_rate_retest_keeps_concurrency_cap_and_workload_aligned():
    baseline, candidate, criterion = concurrency_retest()
    for item, rate in ((baseline, 1), (candidate, 2)):
        item["spec"]["load"].update(mode="rate", rate=rate, concurrency=1)
    criterion["change"] = {"field": "load.rate", "before": 1, "after": 2}
    assert api().evaluate_retest(baseline, candidate, criterion)["status"] == "effective"
    candidate["spec"]["load"]["concurrency"] = 2
    assert api().evaluate_retest(baseline, candidate, criterion)["status"] == "insufficient_evidence"


def test_latency_retest_criterion_requires_full_coverage_even_without_latency_goal():
    baseline, candidate = run(), tuned_run()
    candidate["summary"]["metrics"]["e2e_ms"]["count"] = 1
    criterion = {"metric": "e2e_ms.p95", "direction": "decrease"}
    assert api().evaluate_retest(baseline, candidate, criterion)["status"] == "insufficient_evidence"


def test_protocol_fixtures_never_produce_a_best_model():
    runs = [run(config=spec(protocol_fixture=True)), run("bbb2", config=spec(protocol_fixture=True))]
    comparison = api().compare_runs(runs)
    assert comparison["best_run_id"] is None
    assert not any(candidate["eligible"] for candidate in comparison["candidates"])


def test_actual_sent_rate_uses_start_intervals_and_includes_failed_sends_not_rejections():
    rows = [
        record(start_s=2, end_s=3),
        record(start_s=4, end_s=30, status="failed", success=False),
        record(start_s=6, end_s=31, status="interrupted", success=False),
        record(start_s=50, end_s=50, status="client_rejected", success=False),
        record(start_s=-100, end_s=100, phase="warmup"),
    ]
    result = api().analyze(rows, spec(load={"mode": "rate", "rate": 10, "count": 4}))
    assert result["metrics"]["actual_sent_per_s"] == 0.5
    assert result["metrics"]["requests_per_s"] == pytest.approx(1 / 48)
    assert result["metrics"]["offered"] == 4
    assert result["metrics"]["target_rate"] == 10
    assert "sent - 1" in result["definitions"]["actual_sent_per_s"]
    assert result["groups"]["default"]["actual_sent_per_s"] == 0.5


@pytest.mark.parametrize("starts", [[], [1], [1, 1], [0, None], [0, float("nan")], [0, True]])
def test_actual_sent_rate_unknown_without_valid_distinct_starts(starts):
    result = api().analyze([record(start_s=start) for start in starts], spec())
    assert result["metrics"]["actual_sent_per_s"] is None
    assert any("actual_sent_per_s" in warning for warning in result["warnings"])


def test_actual_sent_rate_is_order_independent_and_does_not_require_completed_tail():
    result = api().analyze([record(start_s=5, end_s=None), record(start_s=-1, end_s=0)], spec())
    assert result["metrics"]["actual_sent_per_s"] == pytest.approx(1 / 6)
    assert result["metrics"]["duration_s"] is None
    assert result["metrics"]["target_rate"] is None


def test_admission_and_generator_signals_are_evidence_not_a_server_root_cause():
    config = spec(load={"mode": "rate", "rate": 10, "count": 3})
    rows = [
        record(start_s=0),
        record(start_s=2, end_s=3),
        record(start_s=3, end_s=3, status="client_rejected", success=False),
    ]
    diagnoses = api().diagnose(api().analyze(rows, config), config)
    by_id = {entry["id"]: entry for entry in diagnoses}
    assert {"admission_rejection", "generator_shortfall"} <= by_id.keys()
    for identifier in ("admission_rejection", "generator_shortfall"):
        diagnosis = by_id[identifier]
        assert diagnosis["confidence"] == "low"
        assert diagnosis["evidence"] and diagnosis["risk"] and diagnosis["validation"]
        assert "root cause" in diagnosis["risk"].lower()


def test_unknown_or_met_target_has_no_generator_shortfall_signal():
    for config in (spec(), spec(load={"mode": "rate", "rate": 0.5, "count": 2})):
        summary = api().analyze([record(), record(start_s=1, end_s=2)], config)
        assert not any(d["id"] == "generator_shortfall" for d in api().diagnose(summary, config))


def test_retest_result_retains_typed_metric_values_and_changed_paths_for_reports():
    baseline, candidate, criterion = concurrency_retest()
    result = api().evaluate_retest(baseline, candidate, criterion)
    assert (result["before"], result["after"]) == (1, 2)
    assert {difference["field"] for difference in result["differences"]} == {"load.concurrency"}
