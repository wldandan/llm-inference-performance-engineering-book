"""Local resource observation, never a model-generation benchmark."""

import importlib
import io
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from perfworkbench.config import ExperimentSpec
from perfworkbench.telemetry import TelemetryCollector


def implementation():
    try:
        return importlib.import_module("perfworkbench.local_telemetry")
    except ModuleNotFoundError as error:
        if error.name == "perfworkbench.local_telemetry":
            pytest.fail("Local Ollama/system collector is not implemented", pytrace=False)
        raise


def spec(url="http://127.0.0.1:11434/v1", enabled=True):
    return {
        "endpoint": {"base_url": url, "model": "fixture:latest"},
        "dataset": [{"id": "one", "messages": [{"role": "user", "content": "fixture"}]}],
        "telemetry": {"interval_s": 0.1, "local": {"enabled": enabled}},
    }


@pytest.fixture
def ollama():
    state = {
        "paths": [],
        "auth": [],
        "status": 200,
        "headers": {},
        "delay": 0,
        "body": json.dumps(
            {
                "models": [
                    {"name": "fixture:latest", "size_vram": 1024, "context_length": 4096},
                    {"name": "other", "size_vram": 9999, "context_length": 32768},
                ]
            }
        ).encode(),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            state["paths"].append(self.path)
            state["auth"].append(self.headers.get("Authorization"))
            time.sleep(state["delay"])
            self.send_response(state["status"])
            for name, value in state["headers"].items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(state["body"])))
            self.end_headers()
            try:
                self.wfile.write(state["body"])
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "fixture:latest"}, state
    server.shutdown()
    server.server_close()
    thread.join(2)


def test_old_config_disables_local_sampling():
    value = spec()
    value["telemetry"].pop("local")
    assert ExperimentSpec.model_validate(value).telemetry.model_dump().get("local") == {"enabled": False}


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434/v1", "http://localhost:9", "http://[::1]:9/v1"])
def test_accept_local_model_endpoint(url):
    assert ExperimentSpec.model_validate(spec(url)).telemetry.local.enabled


@pytest.mark.parametrize(
    "url", ["http://remote.example/v1", "http://127.0.0.2/v1", "http://localhost/proxy/v1"]
)
def test_reject_remote_or_ambiguous_endpoint_when_local_enabled(url):
    with pytest.raises(ValidationError, match="local"):
        ExperimentSpec.model_validate(spec(url))


def test_disabled_local_observation_does_not_restrict_remote_endpoint():
    assert not ExperimentSpec.model_validate(spec("http://remote.example/v1", False)).telemetry.local.enabled


def test_collect_ollama_only_gets_ps_and_keeps_model_scope(ollama):
    endpoint, state = ollama
    before = time.time()
    frame = implementation().collect_ollama(endpoint)
    assert frame["source_kind"] == "local_ollama"
    assert before <= frame["timestamp"] <= time.time()
    assert frame["status"] == "ok"
    metrics = frame["metrics"]
    assert metrics["model_memory_bytes"]["value"] == 1024
    assert metrics["model_context_tokens"]["value"] == 4096
    assert "kv_cache_usage_ratio" not in metrics
    assert "device_memory_used_bytes" not in metrics
    assert state["paths"] == ["/api/ps"]


@pytest.mark.parametrize(
    "body,reason",
    [
        ({"models": []}, "model_not_loaded"),
        ({"models": [{"name": "other"}]}, "model_not_loaded"),
        ({"models": "private response"}, "invalid_response"),
        ({"models": [{"name": "fixture:latest"}]}, "field_unavailable"),
    ],
)
def test_ollama_missing_reasons(ollama, body, reason):
    endpoint, state = ollama
    state["body"] = json.dumps(body).encode()
    frame = implementation().collect_ollama(endpoint)
    metric = frame["metrics"]["model_memory_bytes"]
    assert metric["value"] is None
    assert metric["reason"] == reason
    assert "private response" not in json.dumps(frame)


@pytest.mark.parametrize("bad_value", [-1, True, "1024", 1.5, None])
def test_invalid_ollama_numbers_are_not_coerced(ollama, bad_value):
    endpoint, state = ollama
    state["body"] = json.dumps({"models": [{"name": "fixture:latest", "size_vram": bad_value}]}).encode()
    metric = implementation().collect_ollama(endpoint)["metrics"]["model_memory_bytes"]
    assert metric["value"] is None
    assert metric["status"] == "missing"


def test_true_zero_is_not_missing(ollama):
    endpoint, state = ollama
    state["body"] = b'{"models":[{"name":"fixture:latest","size_vram":0}]}'
    metric = implementation().collect_ollama(endpoint)["metrics"]["model_memory_bytes"]
    assert metric["value"] == 0
    assert metric["status"] == "available"


@pytest.mark.parametrize("status,reason", [(401, "http_401"), (302, "redirect_rejected"), (500, "http_500")])
def test_http_failure_is_redacted_and_not_followed(ollama, status, reason):
    endpoint, state = ollama
    state.update(status=status, body=b"PRIVATE-UPSTREAM", headers={"Location": "/secret"})
    frame = implementation().collect_ollama(endpoint)
    assert frame["error"] == reason
    assert "PRIVATE-UPSTREAM" not in json.dumps(frame)
    assert state["paths"] == ["/api/ps"]


def test_auth_uses_environment_without_persisting_it(ollama, monkeypatch):
    endpoint, state = ollama
    endpoint["api_key_env"] = "LOCAL_TEST_KEY"
    monkeypatch.setenv("LOCAL_TEST_KEY", "PRIVATE-KEY")
    frame = implementation().collect_ollama(endpoint)
    assert state["auth"] == ["Bearer PRIVATE-KEY"]
    assert "PRIVATE-KEY" not in json.dumps(frame)


def test_missing_key_does_not_send(ollama, monkeypatch):
    endpoint, state = ollama
    endpoint["api_key_env"] = "LOCAL_TEST_KEY"
    monkeypatch.delenv("LOCAL_TEST_KEY", raising=False)
    frame = implementation().collect_ollama(endpoint)
    assert frame["error"] == "missing_api_key"
    assert not state["paths"]


@pytest.mark.parametrize(
    "body,reason",
    [(b"PRIVATE-INVALID", "invalid_response"), (b"x" * (2 * 1024 * 1024 + 1), "response_too_large")],
    ids=["invalid", "oversized"],
)
def test_invalid_or_oversized_response(ollama, body, reason):
    endpoint, state = ollama
    state["body"] = body
    assert implementation().collect_ollama(endpoint)["error"] == reason


def test_timeout_does_not_reuse_previous_success(ollama):
    endpoint, state = ollama
    module = implementation()
    assert module.collect_ollama(endpoint)["metrics"]["model_memory_bytes"]["value"] == 1024
    state["delay"] = 0.15
    frame = module.collect_ollama(endpoint, timeout_s=0.02)
    assert frame["error"] == "timeout"
    assert frame["metrics"]["model_memory_bytes"]["value"] is None


def test_system_memory_is_separate_from_device_memory(monkeypatch):
    module = implementation()
    monkeypatch.setattr(module.psutil, "virtual_memory", lambda: SimpleNamespace(total=8192, available=2048))
    monkeypatch.setattr(module.psutil, "swap_memory", lambda: SimpleNamespace(total=4096, used=0))
    frame = module.collect_system()
    assert frame["source_kind"] == "local_system"
    assert frame["metrics"]["host_memory_available_bytes"]["value"] == 2048
    assert frame["metrics"]["host_swap_used_bytes"]["value"] == 0
    assert all(key.startswith("host_") for key in frame["metrics"])


def test_system_permission_failure_is_missing_not_zero(monkeypatch):
    module = implementation()

    def denied():
        raise PermissionError("PRIVATE-ERROR")

    monkeypatch.setattr(module.psutil, "virtual_memory", denied)
    frame = module.collect_system()
    assert frame["metrics"]["host_memory_total_bytes"]["value"] is None
    assert frame["metrics"]["host_memory_total_bytes"]["reason"] == "system_unavailable"
    assert "PRIVATE-ERROR" not in json.dumps(frame)


def test_local_collector_is_explicit_and_stops_with_experiment(ollama, tmp_path):
    endpoint, state = ollama
    full_spec = spec(endpoint["base_url"])
    destination = tmp_path / "telemetry.jsonl"
    collector = TelemetryCollector(full_spec, destination)
    assert collector.snapshot() == []
    assert not state["paths"] and not destination.exists()
    collector.start()
    deadline = time.monotonic() + 3
    try:
        while len(collector.snapshot()) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        collector.stop()
    frames = collector.snapshot()
    assert {f.get("source_kind") for f in frames} == {"local_system", "local_ollama"}
    count = len(state["paths"])
    time.sleep(0.15)
    assert len(state["paths"]) == count
    assert [json.loads(line) for line in destination.read_text().splitlines()] == frames


def test_disabled_local_collector_is_inert(ollama, tmp_path):
    endpoint, state = ollama
    destination = tmp_path / "telemetry.jsonl"
    collector = TelemetryCollector(spec(endpoint["base_url"], False), destination)
    collector.start()
    collector.stop()
    assert not state["paths"] and not destination.exists()


def test_duplicate_model_entries_are_ambiguous(ollama):
    endpoint, state = ollama
    state["body"] = (
        b'{"models":[{"name":"fixture:latest","size_vram":1},{"name":"fixture:latest","size_vram":2}]}'
    )
    assert implementation().collect_ollama(endpoint)["error"] == "ambiguous_model"


def test_nonfinite_json_is_rejected(ollama):
    endpoint, state = ollama
    state["body"] = b'{"models":[{"name":"fixture:latest","size_vram":NaN}]}'
    assert implementation().collect_ollama(endpoint)["error"] == "invalid_response"


def test_endpoint_snapshot_survives_caller_edit_and_ollama_failure(ollama, tmp_path):
    endpoint, state = ollama
    full_spec = spec(endpoint["base_url"])
    collector = TelemetryCollector(full_spec, tmp_path / "telemetry.jsonl")
    full_spec["endpoint"]["base_url"] = "http://remote.invalid/v1"
    state["status"] = 401
    collector.start()
    deadline = time.monotonic() + 3
    try:
        while len(collector.snapshot()) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        collector.stop()
    frames = collector.snapshot()
    assert frames[0]["source_kind"] == "local_system"
    assert frames[0]["metrics"]["host_memory_total_bytes"]["value"] > 0
    assert frames[1]["error"] == "http_401"
    assert state["paths"] == ["/api/ps"]


def test_shareable_report_keeps_resource_units_and_separates_sources():
    from perfworkbench.report import export_report

    frames = [
        {
            "source": "local-ollama",
            "source_kind": "local_ollama",
            "timestamp": 1,
            "status": "ok",
            "metrics": {
                "model_memory_bytes": {
                    "value": 1024,
                    "status": "available",
                    "series": [{"labels": {"model": "PRIVATE-MODEL"}}],
                }
            },
        },
        {
            "source": "local-ollama",
            "source_kind": "local_ollama",
            "timestamp": 2,
            "status": "error",
            "error": "timeout",
            "metrics": {"model_memory_bytes": {"value": None, "status": "missing", "reason": "timeout"}},
        },
        {
            "source": "local-ollama",
            "timestamp": 2,
            "status": "ok",
            "metrics": {"device_memory_used_bytes": {"value": 4096, "status": "available"}},
        },
    ]
    exported = export_report({"id": "a" * 32, "spec": spec(), "telemetry": frames}, "json")
    sources = json.loads(exported)["telemetry"]["sources"]
    assert len(sources) == 2
    local = next(source for source in sources if source["source_kind"] == "local_ollama")
    assert local["metrics"]["model_memory_bytes"]["unit"] == "bytes"
    assert local["metrics"]["model_memory_bytes"]["count"] == 1
    assert local["latest"]["metrics"]["model_memory_bytes"]["value"] is None
    assert local["latest"]["metrics"]["model_memory_bytes"]["reason"] == "timeout"
    assert "PRIVATE-MODEL" not in exported


def test_local_observation_cannot_invalidate_same_named_engine_evidence():
    from perfworkbench.analysis import _kv_evidence

    def engine(preemptions):
        return {
            "source": "local-system",
            "metrics": {
                "queue_waiting": {"value": 2},
                "kv_cache_usage_ratio": {"value": 0.95},
                "preemptions_total": {
                    "value": preemptions,
                    "series": [{"metric": "p", "labels": {}, "value": preemptions}],
                },
            },
        }

    frames = [engine(1), {"source": "local-system", "source_kind": "local_system", "metrics": {}}, engine(3)]
    assert len(list(_kv_evidence(frames))) == 1


def test_missing_sampler_dependency_closes_output_and_surfaces_failure(tmp_path, monkeypatch):
    collector = TelemetryCollector(spec(), tmp_path / "telemetry.jsonl")
    output = io.StringIO()
    monkeypatch.setitem(sys.modules, "perfworkbench.local_telemetry", None)
    collector._poll(output)
    assert output.closed
    with pytest.raises(RuntimeError, match="^telemetry_collection_failed$"):
        collector.stop()


@pytest.mark.parametrize("local", [{}, {"enabled": False}])
def test_disabled_local_is_compatible_with_legacy_comparison_and_retest(local):
    from copy import deepcopy

    from test_analysis import run, tuned_run

    from perfworkbench.analysis import compare_runs, evaluate_retest

    baseline, candidate = run(), tuned_run()
    baseline["spec"]["telemetry"] = {"sources": [], "interval_s": 1}
    candidate["spec"]["telemetry"] = {"sources": [], "interval_s": 1, "local": local}
    before = deepcopy([baseline, candidate])
    comparison = compare_runs([baseline, candidate])
    assert comparison["comparable"]
    assert not any(row["field"].startswith("telemetry") for row in comparison["differences"])
    criterion = {"metric": "requests_per_s", "direction": "increase", "min_relative_change": 0.5}
    assert evaluate_retest(baseline, candidate, criterion)["status"] == "effective"
    assert [baseline, candidate] == before
    candidate["spec"]["telemetry"]["local"] = {"enabled": True}
    assert not compare_runs([baseline, candidate])["comparable"]


def test_latest_resource_preserves_legacy_scalar_metrics():
    from perfworkbench.report import export_report

    frames = [{"source": "engine", "timestamp": 1, "metrics": {"device_memory_used_bytes": 4096}}]
    exported = json.loads(export_report({"telemetry": frames}, "json"))
    source = exported["telemetry"]["sources"][0]
    assert source["source_kind"] == "prometheus"
    assert source["latest"]["metrics"]["device_memory_used_bytes"]["value"] == 4096


@pytest.mark.parametrize("fmt", ["markdown", "html"])
def test_human_report_exposes_latest_failure_separately_from_historical_value(fmt):
    from perfworkbench.report import export_report

    frames = [
        {
            "source": "private-source",
            "source_kind": "local_ollama",
            "timestamp": 1790000000,
            "metrics": {"model_memory_bytes": {"value": 1024}},
        },
        {
            "source": "private-source",
            "source_kind": "local_ollama",
            "timestamp": 1790000010.123456,
            "status": "error",
            "error": "timeout",
            "metrics": {"model_memory_bytes": {"value": None, "reason": "timeout"}},
        },
    ]
    exported = export_report({"telemetry": frames}, fmt)
    assert "Latest telemetry" in exported
    assert "local_ollama" in exported
    assert "1790000010.123456" in exported
    assert "timeout" in exported
    assert "Last valid (historical)" in exported
    assert "1024" in exported
    assert "private-source" not in exported
