"""Adversarial export tests: no free-form upstream strings are shareable."""

import copy
import hashlib
import importlib
import json
import re

import pytest


def exporter():
    try:
        return importlib.import_module("perfworkbench.report").export_report
    except ModuleNotFoundError as error:
        if error.name not in {"perfworkbench", "perfworkbench.report"}:
            raise
        pytest.fail("T3 report API has not been implemented")


def sensitive_run():
    secret = "CANARY-secret-8ef12"
    url = "https://private.example/v1"
    return {
        "id": "abcdef12",
        "status": "completed",
        "created_at": "2026-09-21T00:00:00Z",
        "spec": {
            "name": secret,
            "notes": secret,
            "protocol_fixture": True,
            "endpoint": {
                "base_url": url,
                "api_key": secret,
                "api_key_env": secret,
                "model": secret,
                "environment": {"notes": secret},
            },
            "dataset": [{"id": secret, "messages": [{"content": secret}], "category": secret}],
            "load": {"mode": "concurrency", "count": 2, "concurrency": 1},
            "generation": {"stream": True, "max_tokens": 16, "extra": {"headers": secret}},
            "quality": {"mode": "rules", "required_text": [secret]},
            "telemetry": {"sources": [{"url": url, "api_key_env": secret}]},
        },
        "records": [{"output_text": secret, "input": secret, "error": secret, "sample_id": secret}],
        "summary": {
            "sample_count": 2,
            "metrics": {
                "duration_s": 2.0,
                "requests_per_s": 1.0,
                "sent": 2,
                "succeeded": 2,
                "e2e_ms": {"count": 2, "mean": 1000.0, "p50": 1000, "p95": 1000, "p99": 1000},
                "secret": secret,
            },
            "quality": {"pass": 2, "fail": 0, "unknown": 0, "coverage": 1.0, "pass_rate": 1.0},
            "goals": [
                {"name": "min_requests_per_s", "target": 0.5, "actual": 1, "status": "pass"},
                {"name": secret, "target": secret, "actual": url, "status": secret},
            ],
            "groups": {secret: {"requests_per_s": 1}},
            "warnings": [secret, url],
            "definitions": {"requests_per_s": secret},
        },
        "diagnostics": [
            {
                "id": "kv_pressure",
                "title": secret,
                "evidence": [secret, url],
                "adjustment": secret,
                "risk": secret,
                "validation": secret,
            }
        ],
        "error": {"message": secret, "body": url},
        "telemetry": [{"labels": {"secret": secret}}],
        "profile": {"prefix": secret},
        "progress": {"detail": secret},
        "unexpected": secret,
    }


@pytest.mark.parametrize("fmt", ["json", "markdown", "html"])
def test_redacted_export_never_leaks_raw_text_notes_credentials_urls_or_exceptions(fmt):
    run = sensitive_run()
    before = copy.deepcopy(run)
    result = exporter()(run, fmt)
    assert "CANARY-secret-8ef12" not in result
    assert "private.example" not in result
    assert "output_text" not in result
    assert "api_key" not in result
    assert "abcdef12" in result
    assert "requests_per_s" in result
    assert "fixture" in result.lower()
    assert run == before


def test_json_is_standalone_readable_and_contains_metrics_quality_goals_definitions():
    result = json.loads(exporter()(sensitive_run(), "json"))
    assert result["summary"]["metrics"]["requests_per_s"] == 1
    assert result["summary"]["quality"]["pass_rate"] == 1
    assert result["summary"]["goals"][0]["status"] == "pass"
    assert "duration_s" in result["summary"]["definitions"]
    assert "records" not in result
    assert "endpoint" not in result["spec"]


@pytest.mark.parametrize("fmt", ["json", "markdown", "html"])
def test_adversarial_strings_in_numeric_or_metadata_fields_are_removed(fmt):
    run = sensitive_run()
    secret = "CANARY-other-secret"
    run["id"] = secret
    run["status"] = secret
    run["created_at"] = secret
    run["summary"]["sample_count"] = secret
    run["summary"]["metrics"]["requests_per_s"] = secret
    run["summary"]["quality"]["pass_rate"] = secret
    run["spec"]["load"]["count"] = secret
    run["spec"]["generation"]["stream"] = secret
    result = exporter()(run, fmt)
    assert secret not in result


def test_html_is_escaped_standalone_and_has_no_active_content():
    run = sensitive_run()
    run["summary"]["warnings"] = ['<script>alert("secret")</script>']
    result = exporter()(run, "html")
    assert result.lower().startswith("<!doctype html>")
    assert "<script" not in result.lower()
    assert "<iframe" not in result.lower()
    assert "src=" not in result.lower()
    # Report definitions deliberately contain '<='; text rendering must escape it.
    assert "&lt;=" in result
    assert "charset" in result.lower()


def test_nonfinite_values_become_json_null_and_empty_run_is_readable():
    run = sensitive_run()
    run["summary"]["metrics"]["requests_per_s"] = float("nan")
    result = exporter()(run, "json")
    assert "NaN" not in result and "Infinity" not in result
    assert json.loads(result)["summary"]["metrics"]["requests_per_s"] is None
    assert exporter()({})


def test_unsupported_format_is_rejected_without_interpreting_paths():
    with pytest.raises(ValueError, match="format"):
        exporter()({}, "../../secrets")


def test_report_handles_null_metrics_and_huge_numbers_without_invalid_json():
    run = sensitive_run()
    run["summary"]["metrics"] = {"requests_per_s": 10**1000, "ttft_ms": None}
    result = json.loads(exporter()(run, "json"))
    assert result["summary"]["metrics"]["requests_per_s"] is None
    assert result["summary"]["metrics"]["ttft_ms"]["p95"] is None


def test_report_preserves_real_runner_timeout_status():
    run = sensitive_run()
    run["status"] = "timed_out"
    assert json.loads(exporter()(run, "json"))["status"] == "timed_out"


def test_latency_table_distinguishes_token_and_request_units():
    result = exporter()(sensitive_run(), "markdown")
    assert "| Metric | Unit | Count |" in result
    assert "| tpot_ms | ms/token |" in result
    assert "| ttft_ms | ms |" in result


def useful_run():
    run = sensitive_run()
    run["spec"]["protocol_fixture"] = False
    run["spec"]["endpoint"]["context_length"] = 8192
    run["spec"]["endpoint"]["environment"].update(
        device_count=2,
        tensor_parallel_size=2,
        gpu_memory_utilization=0.8,
        precision="bf16",
        engine="vllm",
        declaration_source="CANARY-secret-8ef12",
    )
    run["profile"].update(
        version="a" * 64,
        prompt_hashes=["b" * 64, "CANARY-secret-8ef12"],
        sample_count=1,
        characters={"count": 1, "min": 20, "max": 20, "mean": 20, "p50": 20, "p95": 20, "p99": 20},
        input_tokens=None,
        token_count_source="unavailable",
        duplicate_prompts=0,
        shared_prefix_chars=0,
        categories={"CANARY-secret-8ef12": 1},
    )
    run["summary"]["metrics"].update(actual_sent_per_s=2, offered=3, client_rejected=1, target_rate=4)
    run["telemetry"] = [
        {
            "source": "CANARY-secret-8ef12",
            "status": "ok",
            "metrics": {
                "queue_waiting": {
                    "status": "available",
                    "value": 2,
                    "series": [{"labels": {"url": "https://private.example/v1"}}],
                },
                "kv_cache_usage_ratio": {"status": "available", "value": 0.95},
                "preemptions_total": {"status": "available", "value": 5},
            },
        },
        {"source": "CANARY-secret-8ef12", "status": "error", "error": "CANARY-secret-8ef12", "metrics": {}},
        {
            "source": "CANARY-secret-8ef12",
            "status": "ok",
            "metrics": {
                "queue_waiting": {"status": "available", "value": 4},
                "kv_cache_usage_ratio": {"status": "available", "value": 0.99},
                "preemptions_total": {"status": "available", "value": 8},
            },
        },
    ]
    run["differences"] = [
        {"run_id": "abcdef12", "field": "load.concurrency", "before": 1, "after": 2},
        {"run_id": "abcdef12", "field": "endpoint.model"},
        {"run_id": "abcdef12", "field": "endpoint.environment.tensor_parallel_size", "before": 1, "after": 2},
        {"run_id": "abcdef12", "field": "endpoint.environment.CANARY-secret-8ef12"},
        {"run_id": "abcdef12", "field": "dataset[0].messages[0].CANARY-secret-8ef12"},
    ]
    run["retest"] = {
        "baseline_id": "1234abcd",
        "candidate_id": "abcdef12",
        "criterion": {
            "metric": "requests_per_s",
            "direction": "increase",
            "min_relative_change": 0.1,
            "change": {"field": "load.concurrency", "before": 1, "after": 2},
            "notes": "CANARY-secret-8ef12",
        },
        "result": {
            "status": "effective",
            "change": 0.5,
            "before": 1,
            "after": 1.5,
            "reasons": ["CANARY-secret-8ef12"],
            "differences": run["differences"],
        },
    }
    return run


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def test_environment_retains_hash_identity_numeric_settings_and_honest_declaration_source():
    run = useful_run()
    result = json.loads(exporter()(run, "json"))
    environment = result["environment"]
    assert environment["model_sha256"] == digest(run["spec"]["endpoint"]["model"])
    assert environment["environment_sha256"] == digest(run["spec"]["endpoint"]["environment"])
    assert environment["context_length"] == 8192
    assert environment["settings"]["device_count"] == 2
    assert environment["settings"]["tensor_parallel_size"] == 2
    assert environment["settings"]["precision"] == "bf16"
    assert environment["declaration_source"] == "experiment_spec"
    assert environment["verification"] == "user_declared"


def test_dataset_profile_preserves_fingerprints_and_typed_distributions_without_prompt_text():
    run = useful_run()
    profile = json.loads(exporter()(run, "json"))["profile"]
    assert profile["dataset_sha256"] == digest(run["spec"]["dataset"])
    assert profile["profile_sha256"] == digest(run["profile"])
    assert profile["version"] == "a" * 64
    assert profile["prompt_hashes"] == ["b" * 64]
    assert profile["characters"]["mean"] == 20
    assert profile["input_tokens"] is None
    assert profile["token_count_source"] == "unavailable"
    assert profile["categories"] == {"category_1": 1}
    assert profile["duplicate_prompts"] == 0


def test_fingerprints_are_stable_for_key_order_but_change_with_dataset_content():
    run = useful_run()
    first = json.loads(exporter()(run, "json"))["profile"]["dataset_sha256"]
    run["spec"]["dataset"][0] = dict(reversed(list(run["spec"]["dataset"][0].items())))
    assert json.loads(exporter()(run, "json"))["profile"]["dataset_sha256"] == first
    run["spec"]["dataset"][0]["messages"][0]["content"] = "different secret"
    assert json.loads(exporter()(run, "json"))["profile"]["dataset_sha256"] != first


def test_telemetry_export_is_numeric_per_source_and_exposes_missing_coverage():
    result = json.loads(exporter()(useful_run(), "json"))
    telemetry = result["telemetry"]
    assert telemetry["sample_count"] == 3
    source = telemetry["sources"][0]
    assert re.fullmatch(r"[0-9a-f]{64}", source["source_sha256"])
    assert source["error_count"] == 1
    assert source["metrics"]["queue_waiting"] == {
        "count": 2,
        "missing": 1,
        "min": 2,
        "max": 4,
        "mean": 3,
        "last": 4,
        "unit": "requests",
        "kind": "gauge",
    }
    assert source["metrics"]["preemptions_total"]["kind"] == "counter"
    assert "rate" not in source["metrics"]["preemptions_total"]


@pytest.mark.parametrize(
    "identifier",
    [
        "kv_pressure",
        "queueing",
        "service_errors",
        "insufficient_evidence",
        "admission_rejection",
        "generator_shortfall",
    ],
)
def test_advice_risk_validation_and_evidence_are_reconstructed_for_known_ids(identifier):
    run = useful_run()
    run["diagnostics"][0]["id"] = identifier
    result = json.loads(exporter()(run, "json"))
    diagnosis = result["diagnostics"][0]
    assert diagnosis["id"] == identifier
    assert diagnosis["adjustment"] and diagnosis["risk"] and diagnosis["validation"]
    assert diagnosis["status"] == "pending"
    assert diagnosis["evidence"] and all(isinstance(item, dict) for item in diagnosis["evidence"])
    assert all(
        item["value"] is None or isinstance(item["value"], (int, float)) for item in diagnosis["evidence"]
    )
    assert "CANARY" not in json.dumps(diagnosis)


@pytest.mark.parametrize("shape", ["nested", "flat"])
def test_saved_retest_linkage_criterion_result_and_changed_paths_survive_sanitization(shape):
    run = useful_run()
    if shape == "flat":
        result = run["retest"].pop("result")
        run["retest"].update(result)
    retest = json.loads(exporter()(run, "json"))["retest"]
    assert retest["baseline_id"] == "1234abcd"
    assert retest["candidate_id"] == "abcdef12"
    assert retest["criterion"]["metric"] == "requests_per_s"
    assert retest["criterion"]["direction"] == "increase"
    assert retest["criterion"]["min_relative_change"] == 0.1
    assert retest["criterion"]["change"] == {"field": "load.concurrency", "before": 1, "after": 2}
    assert retest["result"] == {"status": "effective", "change": 0.5, "before": 1, "after": 1.5}
    assert "load.concurrency" in retest["changed_fields"]


def test_changed_paths_are_an_exact_allowlist_and_include_numeric_before_after():
    result = json.loads(exporter()(useful_run(), "json"))
    assert {row["field"] for row in result["differences"]} == {
        "load.concurrency",
        "endpoint.model",
        "endpoint.environment.tensor_parallel_size",
    }
    row = next(row for row in result["differences"] if row["field"] == "load.concurrency")
    assert (row["before"], row["after"]) == (1, 2)


@pytest.mark.parametrize("fmt", ["markdown", "html", "json"])
def test_full_useful_export_still_omits_all_free_text_and_is_pure(fmt):
    run = useful_run()
    before = copy.deepcopy(run)
    result = exporter()(run, fmt)
    assert "CANARY" not in result and "private.example" not in result
    assert "output_text" not in result and "api_key" not in result
    assert "load.concurrency" in result and "tensor_parallel_size" in result
    assert "1234abcd" in result and "validation" in result.lower()
    assert run == before


def test_markdown_and_html_have_matching_human_readable_sections_and_tables():
    run = useful_run()
    markdown = exporter()(run, "markdown")
    html = exporter()(run, "html")
    for title in (
        "Environment",
        "Dataset profile",
        "Configuration",
        "Measured performance",
        "Quality",
        "Goals",
        "Telemetry",
        "Configuration differences",
        "Recommendations and verification",
        "Retest",
        "Metric definitions",
    ):
        assert f"## {title}\n" in markdown
        assert f"<h2>{title}</h2>" in html
    assert "| Metric |" in markdown
    assert "<table>" in html and "<th" in html
    assert "```json" not in markdown and "<pre>" not in html
    assert "<script" not in html and "src=" not in html


def test_invalid_new_fields_remain_unknown_not_raw_and_negative_relative_change_is_preserved():
    run = useful_run()
    run["spec"]["endpoint"]["environment"].update(device_count="CANARY-secret", precision="CANARY-secret")
    run["profile"]["version"] = "CANARY-secret"
    run["profile"]["characters"]["mean"] = float("nan")
    run["retest"]["baseline_id"] = "CANARY-secret"
    run["retest"]["criterion"]["metric"] = "CANARY-secret"
    run["retest"]["result"].update(change=-0.5, status="ineffective")
    result = json.loads(exporter()(run, "json"))
    assert result["environment"]["settings"]["device_count"] is None
    assert result["environment"]["settings"]["precision"] == "unknown"
    assert result["profile"]["characters"]["mean"] is None
    assert result["retest"]["result"]["change"] == -0.5
    assert "CANARY" not in json.dumps(result)


def test_fixture_export_cannot_repeat_a_saved_effective_claim():
    run = useful_run()
    run["spec"]["protocol_fixture"] = True
    result = json.loads(exporter()(run, "json"))
    assert result["retest"]["result"]["status"] == "insufficient_evidence"


def test_missing_profile_environment_and_retest_are_explicitly_unavailable():
    result = json.loads(exporter()({}, "json"))
    assert result["environment"]["model_sha256"] is None
    assert result["profile"]["dataset_sha256"] is None
    assert result["profile"]["profile_sha256"] is None
    assert result["retest"] is None


def test_category_aliases_match_between_profile_and_measured_groups():
    run = useful_run()
    run["profile"]["categories"] = {"private-first": 7, "private-second": 3}
    run["summary"]["groups"] = {"private-second": {"sent": 3}, "private-first": {"sent": 7}}
    result = json.loads(exporter()(run, "json"))
    for alias, count in result["profile"]["categories"].items():
        assert result["summary"]["groups"][alias]["sent"] == count
    assert "private-first" not in json.dumps(result)


def test_declared_retest_change_populates_configuration_differences_without_other_snapshot():
    run = useful_run()
    run.pop("differences")
    run["retest"]["result"].pop("differences")
    result = json.loads(exporter()(run, "json"))
    assert result["differences"] == [
        {"run_id": "abcdef12", "field": "load.concurrency", "before": 1, "after": 2}
    ]


def test_safe_configuration_keeps_rule_flags_numeric_sampler_settings_and_fingerprints():
    run = useful_run()
    run["spec"]["quality"].update(require_json=True, reject_truncated=False, json_fields=["CANARY-secret"])
    run["spec"]["generation"]["extra"].update(top_k=40, presence_penalty=-0.5, enable_thinking=False)
    run["spec"]["safety"] = {"max_concurrency": 4, "max_requests": 100}
    result = json.loads(exporter()(run, "json"))
    assert result["spec"]["quality"]["require_json"] is True
    assert result["spec"]["quality"]["reject_truncated"] is False
    assert result["spec"]["quality"]["json_field_count"] == 1
    assert result["spec"]["quality"]["rules_sha256"] == digest(run["spec"]["quality"])
    assert result["spec"]["generation"]["extra"]["presence_penalty"] == -0.5
    assert result["spec"]["generation"]["extra"]["top_k"] == 40
    assert result["spec"]["generation"]["extra"]["enable_thinking"] is False
    assert result["spec"]["safety"]["max_concurrency"] == 4


def test_numeric_nan_missing_and_distinct_telemetry_sources_do_not_merge():
    run = useful_run()
    run["telemetry"][2]["source"] = "CANARY-second"
    run["telemetry"][2]["metrics"]["queue_waiting"]["value"] = float("nan")
    run["telemetry"][2]["metrics"]["kv_cache_usage_ratio"]["value"] = 3
    result = json.loads(exporter()(run, "json"))
    assert len(result["telemetry"]["sources"]) == 2
    second = result["telemetry"]["sources"][1]
    assert second["metrics"]["queue_waiting"]["count"] == 0
    assert second["metrics"]["kv_cache_usage_ratio"]["max"] is None


def test_html_shows_source_error_counts_and_no_serialized_objects():
    run = useful_run()
    result = exporter()(run, "html")
    assert "<h2>Telemetry sources</h2>" in result
    assert "Error count" in result
    assert "{&#x27;" not in result


@pytest.mark.parametrize(
    "field",
    [
        "endpoint.environment.notes",
        "endpoint.api_key_env",
        "load.concurrency.evil",
        "__class__",
        "load.CANARY-secret",
        "<script>bad</script>",
    ],
)
def test_difference_paths_do_not_accept_prefix_only_matches(field):
    run = useful_run()
    run["differences"] = [{"field": field, "before": "CANARY-secret", "after": "https://private.example"}]
    run.pop("retest")
    result = json.loads(exporter()(run, "json"))
    assert result["differences"] == []


def test_both_positive_and_negative_retest_outcomes_survive_rendering():
    run = useful_run()
    run["retest"]["result"].update(status="ineffective", change=-0.25, before=2, after=1.5)
    for fmt in ("json", "markdown", "html"):
        result = exporter()(run, fmt)
        assert "ineffective" in result and "-0.25" in result


def test_unrecognized_diagnoses_and_retest_vocabulary_never_copy_source_prose():
    run = useful_run()
    run["diagnostics"].append({"id": "CANARY-secret", "evidence": ["https://private.example"]})
    run["retest"]["criterion"].update(direction="CANARY-secret", min_relative_change=float("nan"))
    result = json.loads(exporter()(run, "json"))
    assert len(result["diagnostics"]) == 1
    assert result["retest"]["result"]["status"] == "insufficient_evidence"
    assert "CANARY" not in json.dumps(result)
