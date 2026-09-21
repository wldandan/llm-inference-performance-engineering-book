"""F08 behavior tests: real parsing and loopback HTTP, without network mocks."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from perfworkbench import telemetry


def mapping(key="queue_waiting", metric="queue", **changes):
    return {
        "key": key,
        "metric": metric,
        "kind": "gauge",
        "scale": 1.0,
        "labels": {},
        "aggregation": "sum",
        **changes,
    }


@pytest.mark.parametrize("aggregation,expected", [("sum", 10), ("max", 7), ("mean", 5)])
def test_parser_aggregates_selected_devices_and_preserves_labels(aggregation, expected):
    text = (
        "# HELP queue Waiting requests\n# TYPE queue gauge\n"
        'queue{device="0",model="chosen",zone="east"} 3\n'
        'queue{device="1",model="chosen",zone="west"} 7\n'
        'queue{device="2",model="other",zone="east"} 90\n'
    )
    result = telemetry.parse_metrics(text, [mapping(labels={"model": "chosen"}, aggregation=aggregation)])
    assert result == {
        "queue_waiting": {
            "value": expected,
            "unit": "requests",
            "kind": "gauge",
            "status": "available",
            "reason": None,
            "series": [
                {"value": 3, "metric": "queue", "labels": {"device": "0", "model": "chosen", "zone": "east"}},
                {"value": 7, "metric": "queue", "labels": {"device": "1", "model": "chosen", "zone": "west"}},
            ],
        }
    }


def test_percentage_scaling_retains_raw_values():
    result = telemetry.parse_metrics(
        'util{device="0"} 20\nutil{device="1"} 80\n',
        [mapping("device_utilization_ratio", "util", scale=0.01, aggregation="mean")],
    )
    metric = result["device_utilization_ratio"]
    assert metric["value"] == pytest.approx(0.5)
    assert metric["unit"] == "ratio"
    assert [s["value"] for s in metric["series"]] == [20, 80]


@pytest.mark.parametrize("raw_name", ["custom_hits", "custom_hits_total"])
def test_counter_keeps_exact_wire_name(raw_name):
    result = telemetry.parse_metrics(
        f'# TYPE {raw_name} counter\n{raw_name}{{rank="0"}} 12\n',
        [mapping("prefix_hits_total", raw_name, kind="counter")],
    )
    assert result["prefix_hits_total"]["kind"] == "counter"
    assert result["prefix_hits_total"]["unit"] == "tokens"
    assert result["prefix_hits_total"]["series"][0]["metric"] == raw_name
    assert result["prefix_hits_total"]["value"] == 12


@pytest.mark.parametrize(
    "text,labels,reason",
    [
        ("other 2\n", {}, "metric_not_found"),
        ('queue{device="0"} 0\n', {"device": "1"}, "labels_not_matched"),
    ],
)
def test_missing_is_null_not_zero(text, labels, reason):
    metric = telemetry.parse_metrics(text, [mapping(labels=labels)])["queue_waiting"]
    assert metric == {
        "value": None,
        "unit": "requests",
        "kind": "gauge",
        "series": [],
        "status": "missing",
        "reason": reason,
    }


def test_zero_is_available():
    metric = telemetry.parse_metrics("queue 0\n", [mapping()])["queue_waiting"]
    assert metric["value"] == 0
    assert metric["status"] == "available"


@pytest.mark.parametrize("value", ["NaN", "+Inf", "-Inf", "1e999"])
def test_nonfinite_series_invalidates_aggregate_without_emitting_nonfinite_json(value):
    metric = telemetry.parse_metrics(f'queue{{device="0"}} 2\nqueue{{device="1"}} {value}\n', [mapping()])
    assert metric["queue_waiting"]["value"] is None
    assert metric["queue_waiting"]["reason"] == "non_finite_value"
    assert metric["queue_waiting"]["series"][1]["value"] is None
    json.dumps(metric, allow_nan=False)


@pytest.mark.parametrize(
    "text,aggregation",
    [
        ('util{device="0"} -1\n', "max"),
        ('util{device="0"} 101\n', "mean"),
        ('util{device="0"} 20\nutil{device="1"} 180\n', "mean"),
        ('util{device="0"} 80\nutil{device="1"} 90\n', "sum"),
    ],
)
def test_invalid_ratios_are_missing_even_if_averaging_would_hide_bad_series(text, aggregation):
    metric = telemetry.parse_metrics(
        text, [mapping("device_utilization_ratio", "util", scale=0.01, aggregation=aggregation)]
    )["device_utilization_ratio"]
    assert metric["value"] is None
    assert metric["status"] == "missing"
    assert metric["reason"] == "ratio_out_of_range"
    assert metric["series"]


def test_counter_negative_is_not_available():
    metric = telemetry.parse_metrics(
        "hits_total -1\n", [mapping("prefix_hits_total", "hits_total", kind="counter")]
    )["prefix_hits_total"]
    assert metric["reason"] == "negative_counter"
    assert metric["value"] is None
    assert metric["series"][0]["value"] == -1


def test_overflow_is_missing_and_large_mean_is_finite():
    text = 'queue{device="0"} 1e308\nqueue{device="1"} 1e308\n'
    result = telemetry.parse_metrics(text, [mapping()])["queue_waiting"]
    assert result["reason"] == "non_finite_value"
    assert result["value"] is None
    assert telemetry.parse_metrics(text, [mapping(aggregation="mean")])["queue_waiting"]["value"] == 1e308


def test_metric_parse_error_does_not_echo_payload():
    with pytest.raises(ValueError, match="^invalid_metrics$"):
        telemetry.parse_metrics('queue{token="private-secret"} definitely-not-a-number\n', [mapping()])


def test_defaults_are_verified_vllm_metrics_only():
    text = (
        "vllm:num_requests_waiting 0\nvllm:num_requests_running 2\n"
        'vllm:kv_cache_usage_perc{engine="0"} 0.4\n'
        'vllm:kv_cache_usage_perc{engine="1"} 0.7\n'
        "# TYPE vllm:num_preemptions_total counter\nvllm:num_preemptions_total 4\n"
        "vllm:prefix_cache_hits_total 10\nvllm:prefix_cache_queries_total 20\n"
    )
    result = telemetry.parse_metrics(text, [])
    assert set(result) == {
        "queue_waiting",
        "requests_running",
        "kv_cache_usage_ratio",
        "preemptions_total",
        "prefix_hits_total",
        "prefix_queries_total",
    }
    assert result["kv_cache_usage_ratio"]["value"] == 0.7
    assert result["preemptions_total"]["value"] == 4
    assert result["prefix_hits_total"]["value"] == 10
    assert result["prefix_queries_total"]["value"] == 20
    assert all(v["status"] == "available" for v in result.values())


def test_bytes_conversion_is_explicit():
    result = telemetry.parse_metrics(
        "memory_mib 2\n", [mapping("device_memory_used_bytes", "memory_mib", scale=1048576)]
    )
    assert result["device_memory_used_bytes"]["unit"] == "bytes"
    assert result["device_memory_used_bytes"]["value"] == 2097152


def test_duplicate_series_is_missing_instead_of_double_counted():
    metric = telemetry.parse_metrics('queue{device="0"} 2\nqueue{device="0"} 3\n', [mapping()])[
        "queue_waiting"
    ]
    assert metric["reason"] == "duplicate_series"
    assert metric["value"] is None


@pytest.fixture
def exporter():
    """A real HTTP endpoint with configurable responses and recorded requests."""
    state = {"requests": [], "routes": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["requests"].append((self.path, dict(self.headers)))
            route = state["routes"].get(self.path, {})
            if route.get("disconnect"):
                self.close_connection = True
                return
            if route.get("entered"):
                route["entered"].set()
            if route.get("release"):
                route["release"].wait(5)
            time.sleep(route.get("delay", 0))
            body = route.get("body", b'queue{device="0"} 2\n')
            status = route.get("status", 200)
            if route.get("auth") and self.headers.get("Authorization") != route["auth"]:
                status, body = 401, b"private credential and server message"
            self.send_response(status)
            headers = route.get("headers", {})
            for name, value in headers.items():
                self.send_header(name, value)
            if "Content-Length" not in headers and not route.get("no_length"):
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                for chunk in route.get("chunks", [body]):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    time.sleep(route.get("chunk_delay", 0))
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    yield state
    for route in state["routes"].values():
        if route.get("release"):
            route["release"].set()
    server.shutdown()
    server.server_close()
    thread.join(2)


def source(exporter, path="/metrics", **changes):
    return {
        "name": "test-engine",
        "url": exporter["url"] + path,
        "api_key_env": None,
        "mappings": [mapping()],
        **changes,
    }


def test_scrape_uses_env_bearer_key_and_ignores_proxy_environment(exporter, monkeypatch):
    exporter["routes"]["/metrics"] = {"auth": "Bearer test-secret"}
    monkeypatch.setenv("F08_TEST_KEY", "test-secret")
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(variable, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    before = time.time()
    result = telemetry.scrape_source(source(exporter, api_key_env="F08_TEST_KEY"))
    assert before <= result["timestamp"] <= time.time()
    assert result["source"] == "test-engine"
    assert result["status"] == "ok"
    assert result["metrics"]["queue_waiting"]["value"] == 2
    assert "test-secret" not in json.dumps(result)
    assert len(exporter["requests"]) == 1
    assert exporter["requests"][0][1]["Authorization"] == "Bearer test-secret"


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_http_errors_are_redacted_and_no_retries(exporter, status):
    path = "/metrics?key=url-secret"
    exporter["routes"][path] = {"status": status, "body": b"private-server-body"}
    result = telemetry.scrape_source(source(exporter, path))
    assert result["status"] == "error"
    assert result["error"] == f"http_{status}"
    assert result["metrics"]["queue_waiting"]["value"] is None
    assert result["metrics"]["queue_waiting"]["status"] == "missing"
    assert len(exporter["requests"]) == 1
    for secret in ("url-secret", "private-server-body", exporter["url"]):
        assert secret not in json.dumps(result)


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_is_not_followed(exporter, status):
    exporter["routes"]["/metrics"] = {
        "status": status,
        "headers": {"Location": exporter["url"] + "/stolen?key=secret"},
    }
    result = telemetry.scrape_source(source(exporter))
    assert result["status"] == "error"
    assert result["error"] == "redirect_rejected"
    assert [request[0] for request in exporter["requests"]] == ["/metrics"]
    assert "stolen" not in json.dumps(result)


def test_missing_environment_key_fails_before_network(exporter, monkeypatch):
    monkeypatch.delenv("F08_ABSENT_KEY", raising=False)
    result = telemetry.scrape_source(source(exporter, api_key_env="F08_ABSENT_KEY"))
    assert result["error"] == "missing_api_key"
    assert exporter["requests"] == []


@pytest.mark.parametrize(
    "url", ["file:///secret", "http://user:password@127.0.0.1:1/metrics", "definitely-not-a-url"]
)
def test_invalid_or_credential_url_is_rejected_without_echo(url):
    result = telemetry.scrape_source({"name": "bad", "url": url, "mappings": [mapping()]})
    assert result["error"] == "invalid_url"
    assert url not in json.dumps(result)


@pytest.mark.parametrize("no_length", [False, True])
def test_oversized_response_is_bounded(exporter, no_length):
    exporter["routes"]["/metrics"] = {"body": b"#" + b"a" * (2 * 1024 * 1024), "no_length": no_length}
    result = telemetry.scrape_source(source(exporter))
    assert result["error"] == "response_too_large"
    assert result["metrics"]["queue_waiting"]["value"] is None


def test_compression_is_not_accepted_for_unbounded_decompression(exporter):
    exporter["routes"]["/metrics"] = {"headers": {"Content-Encoding": "gzip"}, "body": b"not-gzip"}
    result = telemetry.scrape_source(source(exporter))
    assert result["error"] == "unsupported_encoding"
    assert exporter["requests"][0][1]["Accept-Encoding"] == "identity"


@pytest.mark.parametrize("body", [b'queue{key="server-secret"} malformed\n', b"\xff\xfe"])
def test_invalid_exposition_returns_safe_error(exporter, body):
    exporter["routes"]["/metrics"] = {"body": body}
    result = telemetry.scrape_source(source(exporter))
    assert result["error"] == "invalid_metrics"
    assert "server-secret" not in json.dumps(result)


def test_scrape_timeout_is_safe(exporter):
    exporter["routes"]["/metrics"] = {"delay": 0.2}
    result = telemetry.scrape_source(source(exporter), timeout_s=0.04)
    assert result["error"] == "timeout"


def test_slow_trickle_has_total_deadline(exporter):
    exporter["routes"]["/metrics"] = {"no_length": True, "chunks": [b"# data\n"] * 100, "chunk_delay": 0.015}
    before = time.monotonic()
    result = telemetry.scrape_source(source(exporter), timeout_s=0.07)
    assert result["error"] == "timeout"
    assert time.monotonic() - before < 0.5


def test_connection_failure_does_not_expose_url(exporter):
    exporter["routes"]["/metrics?token=private"] = {"disconnect": True}
    result = telemetry.scrape_source(source(exporter, "/metrics?token=private"), timeout_s=0.2)
    assert result["error"] == "network_error"
    assert "private" not in json.dumps(result)


def test_empty_source_mappings_use_defaults(exporter):
    exporter["routes"]["/metrics"] = {"body": b"vllm:num_requests_waiting 8\n"}
    result = telemetry.scrape_source(source(exporter, mappings=[]))
    assert result["status"] == "ok"
    assert result["metrics"]["queue_waiting"]["value"] == 8
    assert result["metrics"]["kv_cache_usage_ratio"]["status"] == "missing"


def wait_for_samples(collector, count, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        samples = collector.snapshot()
        if len(samples) >= count:
            return samples
        time.sleep(0.005)
    pytest.fail(f"collector did not produce {count} samples")


def test_collector_requires_start_and_persists_detached_snapshots(exporter, tmp_path):
    path = tmp_path / "run" / "telemetry.jsonl"
    collector = telemetry.TelemetryCollector({"interval_s": 60, "sources": [source(exporter)]}, path)
    assert collector.snapshot() == []
    assert not path.exists()
    assert exporter["requests"] == []
    collector.start()
    try:
        samples = wait_for_samples(collector, 1)
        collector.start()  # Idempotent: no duplicate sampling thread.
        samples[0]["metrics"]["queue_waiting"]["series"][0]["labels"]["device"] = "changed"
        assert collector.snapshot()[0]["metrics"]["queue_waiting"]["series"][0]["labels"] == {"device": "0"}
        assert [json.loads(line) for line in path.read_text().splitlines()] == collector.snapshot()
    finally:
        before = time.monotonic()
        collector.stop()
    assert time.monotonic() - before < 0.5  # Stop interrupts even a 60 second interval.
    collector.stop()
    assert len(exporter["requests"]) == 1
    with pytest.raises(RuntimeError, match="collector_stopped"):
        collector.start()


def test_collector_polls_only_configured_sources_and_stops(exporter, tmp_path):
    exporter["routes"]["/bad"] = {"status": 500}
    collector = telemetry.TelemetryCollector(
        {
            "interval_s": 0.02,
            "sources": [source(exporter, "/bad", name="broken"), source(exporter, "/good", name="healthy")],
        },
        tmp_path / "telemetry.jsonl",
    )
    collector.start()
    try:
        wait_for_samples(collector, 4)
    finally:
        collector.stop()
    samples = collector.snapshot()
    assert {s["source"] for s in samples} == {"broken", "healthy"}
    assert all(s["status"] == ("error" if s["source"] == "broken" else "ok") for s in samples)
    assert {request[0] for request in exporter["requests"]} == {"/bad", "/good"}
    count = len(exporter["requests"])
    time.sleep(0.08)
    assert len(exporter["requests"]) == count
    assert collector.snapshot() == samples


def test_stop_drains_inflight_scrape_and_skips_remaining_sources(exporter, tmp_path):
    entered, release = threading.Event(), threading.Event()
    exporter["routes"]["/first"] = {"entered": entered, "release": release}
    collector = telemetry.TelemetryCollector(
        {
            "interval_s": 0.01,
            "sources": [source(exporter, "/first"), source(exporter, "/must-not-start", name="second")],
        },
        tmp_path / "telemetry.jsonl",
    )
    collector.start()
    try:
        assert entered.wait(2)
        timer = threading.Timer(0.1, release.set)
        timer.start()
        collector.stop()
        timer.join()
    finally:
        release.set()
        collector.stop()
    assert [request[0] for request in exporter["requests"]] == ["/first"]
    assert len(collector.snapshot()) == 1


def test_collector_freezes_config_and_accepts_experiment_wrapper(exporter, tmp_path):
    config = {"telemetry": {"interval_s": 60, "sources": [source(exporter)]}}
    collector = telemetry.TelemetryCollector(config, tmp_path / "telemetry.jsonl")
    config["telemetry"]["sources"][0]["url"] = exporter["url"] + "/changed"
    config["telemetry"]["sources"][0]["mappings"][0]["labels"] = {"device": "not-here"}
    collector.start()
    try:
        samples = wait_for_samples(collector, 1)
    finally:
        collector.stop()
    assert samples[0]["metrics"]["queue_waiting"]["value"] == 2
    assert exporter["requests"][0][0] == "/metrics"


def test_jsonl_is_appended_not_overwritten(exporter, tmp_path):
    path = tmp_path / "telemetry.jsonl"
    all_samples = []
    for _ in range(2):
        collector = telemetry.TelemetryCollector({"interval_s": 60, "sources": [source(exporter)]}, path)
        collector.start()
        try:
            wait_for_samples(collector, 1)
        finally:
            collector.stop()
        all_samples.extend(collector.snapshot())
    assert len(all_samples) == 2
    assert [json.loads(line) for line in path.read_text().splitlines()] == all_samples


def test_empty_collector_has_no_side_effects(tmp_path):
    path = tmp_path / "not-created.jsonl"
    collector = telemetry.TelemetryCollector({"sources": []}, path)
    collector.start()
    collector.stop()
    collector.stop()
    assert collector.snapshot() == []
    assert not path.exists()


def test_stop_before_start_is_safe(exporter, tmp_path):
    collector = telemetry.TelemetryCollector({"sources": [source(exporter)]}, tmp_path / "not-created.jsonl")
    collector.stop()
    collector.stop()
    assert collector.snapshot() == []
    assert exporter["requests"] == []


def test_output_open_failure_is_safe_and_does_not_launch_requests(exporter, tmp_path):
    collector = telemetry.TelemetryCollector({"sources": [source(exporter)]}, tmp_path)
    with pytest.raises(OSError, match="^telemetry_output_unavailable$"):
        collector.start()
    collector.stop()
    assert exporter["requests"] == []


def counter_metric(values):
    text = "\n".join(f'hits_total{{device="{device}"}} {value}' for device, value in values.items())
    return telemetry.parse_metrics(text, [mapping("prefix_hits_total", "hits_total", kind="counter")])[
        "prefix_hits_total"
    ]


def test_counter_delta_uses_matching_series_without_changing_raw_values():
    previous, current = counter_metric({"0": 5, "1": 7}), counter_metric({"1": 9, "0": 6})
    saved = json.dumps([previous, current])
    assert telemetry.counter_delta(previous, current) == {
        "value": 3,
        "status": "available",
        "reason": None,
        "reset": False,
    }
    assert json.dumps([previous, current]) == saved


def test_per_device_counter_reset_cannot_be_hidden_by_another_device_increase():
    previous, current = counter_metric({"0": 50, "1": 2}), counter_metric({"0": 1, "1": 100})
    assert telemetry.counter_delta(previous, current) == {
        "value": None,
        "status": "missing",
        "reason": "counter_reset",
        "reset": True,
    }
    assert current["value"] == 101


def test_counter_delta_missing_and_label_churn_are_not_zero():
    previous = counter_metric({"0": 5})
    changed = telemetry.counter_delta(previous, counter_metric({"1": 8}))
    assert changed["value"] is None
    assert changed["reason"] == "series_changed"
    absent = telemetry.counter_delta(previous, counter_metric({}))
    assert absent["value"] is None
    assert absent["reason"] == "counter_unavailable"


def test_counter_delta_rejects_gauges():
    gauge = telemetry.parse_metrics("queue 2\n", [mapping()])["queue_waiting"]
    assert telemetry.counter_delta(gauge, gauge)["reason"] == "counter_unavailable"
