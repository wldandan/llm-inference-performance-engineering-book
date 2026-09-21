import importlib

import pytest


def summarize(runs):
    try:
        return importlib.import_module("perfworkbench.sweep").summarize_sweep(runs)
    except ModuleNotFoundError:
        pytest.fail("F06 capacity sweep summary missing", pytrace=False)


def run(point, throughput, status="completed", quality=1, fixture=False):
    return {
        "id": str(point),
        "status": status,
        "spec": {
            "protocol_fixture": fixture,
            "dataset": [{"id": "s"}],
            "endpoint": {"model": "m"},
            "generation": {},
            "quality": {},
            "goals": {},
            "cache_condition": "unknown",
            "load": {"mode": "concurrency", "concurrency": point, "count": 10, "seed": 42},
        },
        "summary": {
            "sample_count": 10,
            "goals": [{"status": "pass"}],
            "quality": {"coverage": 1, "pass_rate": quality},
            "metrics": {
                "requests_per_s": throughput,
                "goodput_per_s": throughput,
                "failed": 0,
                "interrupted": 0,
                "client_rejected": 0,
                "e2e_ms": {"p95": 100 * point},
                "error_rate": 0,
            },
        },
    }


def test_capacity_only_among_measured_eligible_points():
    result = summarize([run(1, 5), run(2, 9), run(4, 8), run(8, 2, status="failed")])
    assert result["variable"] == "concurrency"
    assert result["eligible_points"] == [1, 2, 4]
    assert result["best_point"] == 2
    assert len(result["points"]) == 4
    assert result["points"][0]["requests_per_s"] == 5


def test_fixture_curve_visible_but_not_capacity_recommendation():
    result = summarize([run(1, 5, fixture=True), run(2, 8, fixture=True)])
    assert len(result["points"]) == 2
    assert result["best_point"] is None
    assert result["warnings"]


def test_mixed_models_or_data_not_a_controlled_load_sweep():
    other = run(2, 9)
    other["spec"]["endpoint"]["model"] = "other"
    result = summarize([run(1, 5), other])
    assert not result["comparable"] and result["best_point"] is None


def test_repeats_aggregate_and_quality_regression_disqualifies_point():
    repeated = run(2, 7)
    repeated["id"] = "repeat"
    result = summarize([run(1, 5), run(2, 9), repeated, run(4, 20, quality=0.5)])
    assert result["points"][1]["requests_per_s"] == 8
    assert result["points"][1]["repeats"] == 2
    assert result["best_point"] == 2


def test_rate_sweep_warns_on_actual_send_shortfall():
    first, second = run(1, 5), run(2, 8)
    for candidate, rate in [(first, 10), (second, 20)]:
        candidate["spec"]["load"].update(mode="rate", concurrency=1, rate=rate)
        candidate["summary"]["metrics"]["actual_sent_per_s"] = rate / 2
    result = summarize([first, second])
    assert result["variable"] == "rate"
    assert result["warnings"] and result["best_point"] is None


def test_empty_sweep_has_no_invented_capacity():
    assert summarize([])["best_point"] is None
