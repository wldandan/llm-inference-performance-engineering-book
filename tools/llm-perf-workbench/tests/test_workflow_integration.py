"""Real local workflow integration; fixed protocol data is never model evidence.

No manager, store, analysis, transport, or web route is mocked. Only the model
and exporter are localhost HTTP fixtures. All generated runs keep fixture=True.
"""

import copy
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from perfworkbench.cli import main
from perfworkbench.dataset import load_jsonl
from perfworkbench.demo import create_server, example_spec
from perfworkbench.runner import ExperimentManager
from perfworkbench.store import RunStore
from perfworkbench.web import create_app

pytestmark = pytest.mark.integration

ACTION = {"X-Workbench-Action": "local", "Origin": "http://testserver"}
KEY_ENV = "WORKFLOW_INTEGRATION_API_KEY"
FAKE_KEY = "workflow-only-not-a-real-credential"
PRIVATE_PROMPT = "WORKFLOW_PRIVATE_PROMPT"
PRIVATE_OUTPUT = "WORKFLOW_PRIVATE_OUTPUT<script>fixture_only()</script>"
PRIVATE_ERROR = "WORKFLOW_PRIVATE_ERROR"
OUTPUT = json.dumps({"answer": PRIVATE_OUTPUT, "ok": True})


class WorkflowHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _reply(self, payload, status=200, content_type="application/json"):
        body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        if self.headers.get("Authorization") == "Bearer " + FAKE_KEY:
            return True
        self._reply({"error": PRIVATE_ERROR}, 401)
        return False

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/v1/models":
            self._reply({"data": [{"id": "protocol-fixture", "max_model_len": 4096}]})
        elif self.path == "/metrics":
            with self.server.evidence_lock:
                self.server.metric_reads += 1
                counter = self.server.metric_reads
            self._reply(
                'queue{device="0"} 1\nqueue{device="1"} 2\n'
                'utilization{device="0"} 60\nutilization{device="1"} 80\n'
                "kv_usage 0.9\n"
                f"preemptions_total {counter}\n",
                content_type="text/plain; version=0.0.4",
            )
        elif self.path == "/denied-metrics":
            self._reply({"error": PRIVATE_ERROR + FAKE_KEY}, 503)
        else:
            self._reply({"error": "not found"}, 404)

    def do_POST(self):
        if not self._authorized():
            return
        if self.path != "/v1/chat/completions":
            self._reply({"error": "not found"}, 404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with self.server.evidence_lock:
            self.server.sends.append({"body": body, "headers": dict(self.headers)})
        usage = {"prompt_tokens": 32, "completion_tokens": 8, "total_tokens": 40}
        if not body.get("stream"):
            self._reply(
                {
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": OUTPUT},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": usage,
                }
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            midpoint = len(OUTPUT) // 2
            for piece in (OUTPUT[:midpoint], OUTPUT[midpoint:]):
                time.sleep(0.015)
                event = {
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
                }
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
            for event in (
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                {"choices": [], "usage": usage},
            ):
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True


@contextmanager
def serving(server):
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive(), "Local fixture server did not stop"


def imported_samples():
    rows = [
        {
            "id": f"sample-{i}",
            "category": category,
            "messages": [{"role": "user", "content": f"{PRIVATE_PROMPT}: {category}"}],
        }
        for i, category in enumerate(("small", "large"))
    ]
    return load_jsonl("\n".join(json.dumps(row) for row in rows))


@pytest.fixture(scope="module")
def workflow(tmp_path_factory):
    root = tmp_path_factory.mktemp("workflow-integration") / "runs"
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkflowHandler)
    server.sends, server.metric_reads = [], 0
    server.evidence_lock = threading.Lock()
    base = f"http://127.0.0.1:{server.server_port}"
    spec = {
        "name": "Local workflow protocol verification only",
        "protocol_fixture": True,
        "endpoint": {"base_url": base + "/v1", "model": "protocol-fixture", "api_key_env": KEY_ENV},
        "dataset": imported_samples(),
        "load": {"count": 2, "warmup": 1, "scan": [1, 2], "repeats": 2, "mix": {"small": 1, "large": 1}},
        "generation": {"max_tokens": 16},
        "quality": {"mode": "manual"},
        "safety": {
            "max_requests": 12,
            "max_output_tokens": 192,
            "max_concurrency": 2,
            "max_duration_s": 120,
            "request_timeout_s": 3,
        },
        "telemetry": {
            "interval_s": 0.1,
            "sources": [
                {
                    "name": "fixture-exporter",
                    "url": base + "/metrics",
                    "api_key_env": KEY_ENV,
                    "mappings": [
                        {"key": "queue_waiting", "metric": "queue", "aggregation": "sum"},
                        {
                            "key": "device_utilization_ratio",
                            "metric": "utilization",
                            "scale": 0.01,
                            "aggregation": "mean",
                        },
                        {"key": "kv_cache_usage_ratio", "metric": "kv_usage"},
                        {"key": "preemptions_total", "metric": "preemptions_total", "kind": "counter"},
                        {"key": "device_memory_used_bytes", "metric": "absent_memory"},
                    ],
                },
                {
                    "name": "unavailable-exporter",
                    "url": base + "/denied-metrics",
                    "api_key_env": KEY_ENV,
                    "mappings": [{"key": "queue_waiting", "metric": "queue"}],
                },
            ],
        },
    }
    # Only a synthetic credential is injected; no business logic is replaced.
    with pytest.MonkeyPatch.context() as environment, serving(server):
        environment.setenv(KEY_ENV, FAKE_KEY)
        with TestClient(create_app(root)) as client:
            assert isinstance(client.app.state.manager, ExperimentManager)
            yield {"client": client, "root": root, "server": server, "spec": spec, "base": base}


def post(client, route, payload, expected=200):
    response = client.post(route, json=payload, headers=ACTION)
    assert response.status_code == expected, response.text
    return response.json()


def detail(client, run_id):
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def completed_plan(workflow):
    client, server = workflow["client"], workflow["server"]
    before = len(server.sends)
    plan = post(client, "/api/runs", workflow["spec"], expected=202)
    runs = client.app.state.manager.wait(plan["plan_id"], timeout=120)
    assert len(runs) == 4
    assert all(run["status"] == "completed" for run in runs), [
        (run["id"], run["status"], run["error"]) for run in runs
    ]
    assert len(server.sends) - before == 12, "Unexpected implicit preflight/retry or dropped request"
    return plan


def label_all(client, run_id, state="pass"):
    rows = detail(client, run_id)["records"]
    labels = {row["request_id"]: state for row in rows if row["phase"] == "measure"}
    return post(client, f"/api/runs/{run_id}/labels", labels)


def test_jsonl_import_and_web_profile_are_consistent_without_sends(workflow, tmp_path, capsys):
    client, server = workflow["client"], workflow["server"]
    before = len(server.sends)
    samples = imported_samples()
    profile = post(client, "/api/profile", {"dataset": samples})
    assert profile["sample_count"] == 2
    assert profile["categories"] == {"small": 1, "large": 1}
    assert profile["input_tokens"] is None
    assert len(profile["version"]) == 64
    path = tmp_path / "samples.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in samples), encoding="utf-8")
    assert main(["profile", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == profile["version"]
    assert len(server.sends) == before
    with pytest.raises(ValueError, match="unique"):
        load_jsonl("\n".join(json.dumps(samples[0]) for _ in range(2)))
    assert (
        client.post("/api/profile", json={"dataset": [samples[0], samples[0]]}, headers=ACTION).status_code
        == 422
    )


def test_preflight_through_real_web_manager_has_exact_separate_budget(workflow):
    server = workflow["server"]
    before = len(server.sends)
    result = post(workflow["client"], "/api/preflight", workflow["spec"]["endpoint"])
    sends = server.sends[before:]
    assert result["ready"] is True
    assert result["context_length"] == 4096 and result["context_source"] == "models_endpoint"
    assert result["generation_budget"] == {"max_requests": 2, "max_output_tokens": 16}
    assert len(sends) == 2
    assert {item["body"]["stream"] for item in sends} == {False, True}
    assert all(item["body"]["max_tokens"] == 8 for item in sends)
    assert all(row["success"] for row in result["checks"])


def test_complete_plan_retains_per_request_and_telemetry_evidence(workflow, completed_plan):
    client = workflow["client"]
    ids = completed_plan["run_ids"]
    for run_id, concurrency in zip(ids, (1, 1, 2, 2), strict=True):
        run = detail(client, run_id)
        assert run["parent_id"] == completed_plan["plan_id"]
        assert run["spec"]["load"]["concurrency"] == concurrency
        assert len(run["records"]) == 3 and run["summary"]["sample_count"] == 2
        assert sum(row["phase"] == "warmup" for row in run["records"]) == 1
        assert all(row["success"] and row["output_tokens"] == 8 for row in run["records"])
        assert set(run["summary"]["groups"]) == {"small", "large"}
        assert run["summary"]["metrics"]["input_tokens_per_s"] > 0
        healthy = [sample for sample in run["telemetry"] if sample["source"] == "fixture-exporter"]
        unavailable = [sample for sample in run["telemetry"] if sample["source"] == "unavailable-exporter"]
        assert healthy and unavailable
        metrics = healthy[0]["metrics"]
        assert metrics["queue_waiting"]["value"] == 3
        assert metrics["device_utilization_ratio"]["value"] == pytest.approx(0.7)
        assert {s["labels"]["device"] for s in metrics["device_utilization_ratio"]["series"]} == {"0", "1"}
        assert metrics["device_memory_used_bytes"]["value"] is None
        assert metrics["device_memory_used_bytes"]["reason"] == "metric_not_found"
        assert all(sample["status"] == "error" and sample["error"] == "http_503" for sample in unavailable)
        assert all(sample["metrics"]["queue_waiting"]["value"] is None for sample in unavailable)
    sends = [item for item in workflow["server"].sends if "X-Request-ID" in item["headers"]]
    assert len({item["headers"]["X-Request-ID"] for item in sends}) == 12
    assert all(not any(key.startswith("_workbench") for key in item["body"]) for item in sends)
    assert all(item["headers"]["Authorization"] == "Bearer " + FAKE_KEY for item in sends)
    listing = client.get("/api/runs").json()
    assert set(ids).issubset({run["id"] for run in listing})
    # The collector must have stopped when manager.wait() returns.
    before = workflow["server"].metric_reads
    threading.Event().wait(0.25)
    assert workflow["server"].metric_reads == before


def test_manual_labels_refresh_quality_and_survive_reopen(workflow, completed_plan):
    client, run_id = workflow["client"], completed_plan["run_ids"][0]
    label_all(client, run_id, "unknown")
    unknown = detail(client, run_id)
    assert unknown["summary"]["quality"]["coverage"] == 0
    assert unknown["summary"]["quality"]["unknown"] == 2
    samples = [row for row in unknown["records"] if row["phase"] == "measure"]
    partially_labeled = post(client, f"/api/runs/{run_id}/labels", {samples[0]["request_id"]: "pass"})
    assert partially_labeled["summary"]["quality"]["coverage"] == 0.5
    labeled = label_all(client, run_id)
    assert labeled["summary"]["quality"]["pass"] == 2
    assert labeled["summary"]["quality"]["coverage"] == 1
    assert labeled["summary"]["metrics"]["goodput_per_s"] > 0
    reopened = RunStore(workflow["root"]).get(run_id)
    assert reopened["summary"] == labeled["summary"]
    assert [r["manual_label"] for r in reopened["records"] if r["phase"] == "measure"] == ["pass", "pass"]
    invalid = client.post(f"/api/runs/{run_id}/labels", json={"foreign-request-id": "pass"}, headers=ACTION)
    assert invalid.status_code == 422
    assert detail(client, run_id)["summary"] == labeled["summary"]


def test_comparison_aligns_real_snapshots_and_never_ranks_fixture(workflow, completed_plan):
    client = workflow["client"]
    first, repeated, changed, _ = completed_plan["run_ids"]
    for run_id in (first, repeated, changed):
        label_all(client, run_id)
    comparison = post(client, "/api/compare", {"ids": [first, repeated]})
    assert comparison["comparable"] is True
    assert comparison["best_run_id"] is None
    assert all(not candidate["eligible"] for candidate in comparison["candidates"])
    assert all(
        any("fixture" in reason.lower() for reason in candidate["reasons"])
        for candidate in comparison["candidates"]
    )
    changed_load = post(client, "/api/compare", {"ids": [first, changed]})
    assert changed_load["comparable"] is False
    assert any(item["field"] == "load.concurrency" for item in changed_load["differences"])


def test_declared_change_retest_persists_without_mutating_evidence(workflow, completed_plan):
    client = workflow["client"]
    baseline, _, candidate, _ = completed_plan["run_ids"]
    before = label_all(client, baseline)
    after = label_all(client, candidate)
    criterion = {
        "metric": "requests_per_s",
        "direction": "increase",
        "min_relative_change": 0.1,
        "change": {"field": "load.concurrency", "before": 1, "after": 2},
    }
    result = post(
        client, "/api/retest", {"baseline_id": baseline, "candidate_id": candidate, "criterion": criterion}
    )
    assert result["status"] == "insufficient_evidence"
    assert any("fixture" in reason.lower() for reason in result["reasons"])
    assert not any("not aligned" in reason or "declaration" in reason.lower() for reason in result["reasons"])
    assert result["before"] == before["summary"]["metrics"]["requests_per_s"]
    assert result["after"] == after["summary"]["metrics"]["requests_per_s"]
    persisted = RunStore(workflow["root"]).get(candidate)
    assert persisted["retest"] == result
    assert persisted["retest"]["criterion"] == criterion
    assert persisted["spec"] == after["spec"] and persisted["records"] == after["records"]
    assert detail(client, baseline)["spec"] == before["spec"]


@pytest.mark.parametrize("fmt", ["json", "markdown", "html"])
def test_shareable_report_omits_private_data_but_retains_metrics(workflow, completed_plan, fmt):
    client, run_id = workflow["client"], completed_plan["run_ids"][0]
    run = label_all(client, run_id)
    assert PRIVATE_PROMPT in json.dumps(run["spec"]) and PRIVATE_OUTPUT in run["records"][0]["output_text"]
    response = client.get(f"/api/runs/{run_id}/report", params={"format": fmt})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    for private in (PRIVATE_PROMPT, PRIVATE_OUTPUT, PRIVATE_ERROR, FAKE_KEY, KEY_ENV, workflow["base"]):
        assert private not in response.text
    assert "<script>" not in response.text
    if fmt == "json":
        report = response.json()
        assert "records" not in report
        assert report["summary"]["metrics"]["succeeded"] == 2
        assert report["spec"]["protocol_fixture"] is True
        assert report["profile"]["version"] == run["profile"]["version"]
    elif fmt == "html":
        assert "<html" in response.text.lower()
        assert "sandbox" in response.headers["content-security-policy"]


def test_scan_summary_groups_repeats_without_claiming_model_capacity(workflow, completed_plan):
    client = workflow["client"]
    for run_id in completed_plan["run_ids"]:
        label_all(client, run_id)
    response = client.get(f"/api/plans/{completed_plan['plan_id']}/summary")
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["variable"] == "concurrency" and summary["comparable"] is True
    assert [point["value"] for point in summary["points"]] == [1, 2]
    assert all(point["repeats"] == 2 for point in summary["points"])
    assert {run_id for point in summary["points"] for run_id in point["run_ids"]} == set(
        completed_plan["run_ids"]
    )
    assert summary["best_point"] is None and summary["eligible_points"] == []
    for point in summary["points"]:
        actual = [
            detail(client, run_id)["summary"]["metrics"]["requests_per_s"] for run_id in point["run_ids"]
        ]
        assert point["requests_per_s"] == pytest.approx(sum(actual) / len(actual))
        assert point["reasons"] and not point["eligible"]


def test_cli_consumes_real_web_runs_and_refreshes_persisted_labels(
    workflow, completed_plan, tmp_path, capsys
):
    ids = completed_plan["run_ids"]
    args = ["--root", str(workflow["root"])]
    assert main([*args, "show", ids[1]]) == 0
    run = json.loads(capsys.readouterr().out)
    assert run["status"] == "completed"
    labels = {row["request_id"]: "pass" for row in run["records"] if row["phase"] == "measure"}
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(labels), encoding="utf-8")
    assert main([*args, "label", ids[1], str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["quality"]["coverage"] == 1
    assert main([*args, "compare", ids[0], ids[1]]) == 0
    assert json.loads(capsys.readouterr().out)["best_run_id"] is None
    assert main([*args, "retest", ids[0], ids[2], "--allow-change", "load.concurrency"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "insufficient_evidence"
    assert RunStore(workflow["root"]).get(ids[2])["retest"]["baseline_id"] == ids[0]
    report = tmp_path / "report.json"
    assert main([*args, "report", ids[1], "--format", "json", "--output", str(report)]) == 0
    assert json.loads(report.read_text())["summary"]["metrics"]["succeeded"] == 2
    assert PRIVATE_PROMPT not in report.read_text() and FAKE_KEY not in report.read_text()


def test_security_and_invalid_budget_reject_before_real_dispatch(workflow):
    client, server = workflow["client"], workflow["server"]
    before = len(server.sends)
    assert client.post("/api/preflight", json=workflow["spec"]["endpoint"]).status_code == 403
    assert (
        client.post(
            "/api/preflight",
            json=workflow["spec"]["endpoint"],
            headers={**ACTION, "Origin": "https://foreign.example"},
        ).status_code
        == 403
    )
    assert client.get("/api/runs", headers={"Host": "foreign.example"}).status_code == 400
    unsafe = copy.deepcopy(workflow["spec"])
    unsafe["safety"]["max_requests"] = 11
    assert client.post("/api/runs", json=unsafe, headers=ACTION).status_code == 422
    unsafe["safety"]["max_requests"] = 12
    unsafe["safety"]["max_output_tokens"] = 191
    assert client.post("/api/runs", json=unsafe, headers=ACTION).status_code == 422
    assert client.get("/api/runs/" + "a" * 32 + "/report").status_code == 404
    assert len(server.sends) == before


def test_shipped_demo_runs_real_manager_with_nonstream_and_default_telemetry(tmp_path):
    with serving(create_server(0)) as server:
        base = f"http://127.0.0.1:{server.server_port}"
        spec = example_spec()
        spec["endpoint"]["base_url"] = base + "/v1"
        spec["telemetry"]["sources"][0]["url"] = base + "/metrics"
        spec["load"]["count"] = 2
        spec["generation"]["stream"] = False
        manager = ExperimentManager(tmp_path / "demo-runs")
        try:
            preflight = manager.preflight(spec["endpoint"])
            assert preflight["ready"] and len(preflight["checks"]) == 2
            plan = manager.submit(spec)
            (run,) = manager.wait(plan["plan_id"], timeout=60)
            assert run["status"] == "completed"
            assert run["spec"]["protocol_fixture"] is True
            assert all("协议" in row["output_text"] for row in run["records"])
            assert all(row["ttft_ms"] is None and row["tpot_ms"] is None for row in run["records"])
            assert run["summary"]["quality"]["pass"] == 2
            assert run["telemetry"][0]["metrics"]["kv_cache_usage_ratio"]["value"] == 0.2
            assert run["summary"]["warnings"]
        finally:
            manager.close()
