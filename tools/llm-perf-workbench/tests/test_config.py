"""F01/F02/F04/F14: acceptance before implementation."""

import importlib

import pytest


def config():
    try:
        return importlib.import_module("perfworkbench.config")
    except ModuleNotFoundError:
        pytest.fail("F01-F04 config implementation is missing", pytrace=False)


def minimal():
    return {
        "name": "baseline",
        "endpoint": {"base_url": "http://localhost:8000/v1", "model": "qwen"},
        "dataset": [{"id": "a", "messages": [{"role": "user", "content": "解释 Prefill"}]}],
    }


def test_spec_defaults_and_snapshot_are_json_safe():
    spec = config().ExperimentSpec.model_validate(minimal()).model_dump(mode="json")
    assert spec["load"]["mode"] == "concurrency"
    assert spec["goals"]["mode"] == "offline"
    assert spec["cache_condition"] == "unknown"
    assert spec["endpoint"]["api_key_env"] is None


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://key:secret@localhost/v1",
        "http://localhost/v1?key=abc",
        "https://example.com/#secret",
    ],
)
def test_endpoint_credentials_and_non_http_urls_rejected(url):
    raw = minimal()
    raw["endpoint"]["base_url"] = url
    with pytest.raises(ValueError):
        config().ExperimentSpec.model_validate(raw)


@pytest.mark.parametrize(
    "load",
    [
        {"concurrency": 0},
        {"rate": float("nan")},
        {"mode": "rate", "rate": -1},
        {"count": True},
        {"mix": {"missing": 1}},
        {"mix": {"default": 0}},
        {"scan": [1.5]},
    ],
)
def test_invalid_loads_rejected(load):
    raw = minimal()
    raw["load"] = load
    with pytest.raises(ValueError):
        config().ExperimentSpec.model_validate(raw)


def test_whole_scan_and_warmup_reserved_before_launch():
    raw = minimal()
    raw["load"] = {"count": 10, "warmup": 2, "repeats": 2, "scan": [1, 2, 4]}
    raw["safety"] = {"max_requests": 71}
    with pytest.raises(ValueError, match="request"):
        config().ExperimentSpec.model_validate(raw)
    raw["safety"] = {"max_requests": 72, "max_output_tokens": 100}
    with pytest.raises(ValueError, match="token"):
        config().ExperimentSpec.model_validate(raw)


def test_scan_cannot_exceed_concurrency_guard():
    raw = minimal()
    raw["load"] = {"scan": [1, 65]}
    with pytest.raises(ValueError, match="concurrency"):
        config().ExperimentSpec.model_validate(raw)


@pytest.mark.parametrize("field,value", [("api_key", "secret"), ("url", "http://wrong")])
def test_unknown_endpoint_fields_not_silently_ignored(field, value):
    raw = minimal()
    raw["endpoint"][field] = value
    with pytest.raises(ValueError):
        config().ExperimentSpec.model_validate(raw)


def test_duplicate_ids_and_unsafe_generation_override_rejected():
    raw = minimal()
    raw["dataset"] *= 2
    with pytest.raises(ValueError, match="id"):
        config().ExperimentSpec.model_validate(raw)
    raw = minimal()
    raw["generation"] = {"extra": {"max_tokens": 10000000}}
    with pytest.raises(ValueError):
        config().ExperimentSpec.model_validate(raw)


def test_explicit_report_goal_cannot_be_silently_accepted_as_request_goal():
    raw = minimal()
    raw["goals"] = {"reports_per_hour": 1000}
    with pytest.raises(ValueError):
        config().ExperimentSpec.model_validate(raw)


def test_environment_secrets_and_key_values_not_allowed():
    raw = minimal()
    raw["endpoint"]["environment"] = {"api_key": "secret"}
    with pytest.raises(ValueError):
        config().ExperimentSpec.model_validate(raw)
    raw = minimal()
    raw["endpoint"]["api_key_env"] = "sk-secret-with-dashes"
    with pytest.raises(ValueError):
        config().ExperimentSpec.model_validate(raw)
