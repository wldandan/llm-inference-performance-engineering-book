"""Real EvalScope + local protocol fixture, never a model performance benchmark."""

import importlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


class EndpointFixture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_payload(self, value, status=200):
        payload = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/v1/models":
            self.send_payload({"data": [{"id": "protocol-fixture", "max_model_len": 4096}]})
        elif self.path == "/metrics":
            body = b'vllm:num_requests_waiting 2\nvllm:kv_cache_usage_perc 0.75\nnpu_busy{device="0"} 60\n'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.observed.append({"body": body, "headers": dict(self.headers), "time": time.monotonic()})
        prompt = body["messages"][-1]["content"]
        try:
            if "FAIL" in prompt:
                time.sleep(0.03)
                self.send_payload({"error": "Upstream raw private error"}, 503)
                return
            if "REDIRECT" in prompt:
                self.send_response(307)
                self.send_header("Location", "/v1/chat/completions")
                self.end_headers()
                return
            if "SLOW" in prompt:
                time.sleep(0.5)
            if "MALFORMED" in prompt:
                self.send_payload({"not_choices": "invalid protocol"})
                return
            usage = {"prompt_tokens": 32, "completion_tokens": 8, "total_tokens": 40}
            finish = "length" if "TRUNCATED" in prompt else "stop"
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                for part in ("文章", "摘要", "完成"):
                    time.sleep(0.005)
                    event = {
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}],
                    }
                    self.wfile.write(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode())
                    self.wfile.flush()
                if "NOFINISH" not in prompt:
                    event = {
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                    }
                    self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                    if "NOUSAGE" not in prompt:
                        self.wfile.write(
                            ("data: " + json.dumps({"choices": [], "usage": usage}) + "\n\n").encode()
                        )
                    self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.close_connection = True
            else:
                self.send_payload(
                    {
                        "object": "chat.completion",
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "文章摘要完成"},
                                "finish_reason": finish,
                            }
                        ],
                        "usage": usage,
                    }
                )
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def endpoint():
    server = ThreadingHTTPServer(("127.0.0.1", 0), EndpointFixture)
    server.daemon_threads = True
    server.observed = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", server
    server.shutdown()
    server.server_close()
    thread.join(2)


def manager_type():
    try:
        return importlib.import_module("perfworkbench.runner").ExperimentManager
    except ModuleNotFoundError:
        pytest.fail("F05/F06 runner is missing", pytrace=False)


def make_spec(url, prompts=None, **changes):
    prompts = prompts or ["文章"]
    raw = {
        "name": "protocol-only",
        "endpoint": {"base_url": url, "model": "protocol-fixture"},
        "dataset": [
            {
                "id": f"s{i}",
                "category": "small" if i % 2 == 0 else "large",
                "messages": [{"role": "user", "content": p}],
            }
            for i, p in enumerate(prompts)
        ],
        "load": {"count": len(prompts), "concurrency": 2},
        "generation": {"max_tokens": 16},
        "safety": {"max_duration_s": 60, "request_timeout_s": 2},
        "protocol_fixture": True,
        "quality": {"required_text": ["摘要"]},
    }
    for key, value in changes.items():
        raw.setdefault(key, {}).update(value)
    return raw


def run_one(tmp_path, spec):
    manager = manager_type()(tmp_path)
    try:
        plan = manager.submit(spec)
        runs = manager.wait(plan["plan_id"], timeout=60)
        assert len(runs) == 1
        return runs[0]
    finally:
        manager.close()


def test_real_evalscope_stream_and_nonstream_usage(tmp_path, endpoint):
    url, server = endpoint
    for stream in (True, False):
        run = run_one(
            tmp_path / str(stream), make_spec(url, ["文章一", "文章二"], generation={"stream": stream})
        )
        assert run["status"] == "completed", run.get("error")
        assert len(run["records"]) == 2
        assert all(r["success"] and r["output_tokens"] == 8 for r in run["records"])
        assert all((r["ttft_ms"] is not None) == stream for r in run["records"])
        assert run["summary"]["metrics"]["input_tokens_per_s"] > 0
    assert len(server.observed) == 4  # no hidden connection test or retries


def test_real_evalscope_protocol_failure_and_http_failure(tmp_path, endpoint):
    url, _ = endpoint
    run = run_one(tmp_path, make_spec(url, ["文章", "NOFINISH", "MALFORMED", "FAIL", "TRUNCATED"]))
    rows = {r["sample_id"]: r for r in run["records"]}
    assert run["status"] == "completed", run.get("error")
    assert rows["s1"]["error_kind"] == "incomplete_response"
    assert rows["s2"]["error_kind"] == "protocol_error"
    assert rows["s3"]["http_status"] == 503 and not rows["s3"]["success"]
    assert rows["s4"]["finish_reason"] == "length"
    assert run["summary"]["quality"]["fail"] >= 1


def test_rate_scan_and_warmups_run_actual_engine(tmp_path, endpoint):
    url, server = endpoint
    manager = manager_type()(tmp_path)
    try:
        plan = manager.submit(make_spec(url, load={"mode": "rate", "scan": [5, 10], "count": 2, "warmup": 1}))
        runs = manager.wait(plan["plan_id"], 60)
        assert len(runs) == 2 and all(r["status"] == "completed" for r in runs)
        assert len(server.observed) == 6
        assert all(sum(x["phase"] == "measure" for x in r["records"]) == 2 for r in runs)
        assert [r["spec"]["load"]["rate"] for r in runs] == [5, 10]
    finally:
        manager.close()


def test_preflight_has_separate_bounded_generation_and_context_evidence(tmp_path, endpoint):
    url, server = endpoint
    manager = manager_type()(tmp_path)
    try:
        check = manager.preflight({"base_url": url, "model": "protocol-fixture"})
        assert check["ready"] is True
        assert check["context_length"] == 4096
        assert len(server.observed) == 2
        assert all(r["body"]["max_tokens"] == 8 for r in server.observed)
    finally:
        manager.close()


def test_cancel_marks_inflight_and_stops_future_dispatch(tmp_path, endpoint):
    url, server = endpoint
    manager = manager_type()(tmp_path)
    try:
        plan = manager.submit(make_spec(url, ["SLOW"], load={"count": 80, "scan": [2, 3]}))
        limit = time.monotonic() + 20
        while len(server.observed) < 1 and time.monotonic() < limit:
            time.sleep(0.05)
        assert server.observed, "worker never dispatched"
        manager.cancel(plan["plan_id"])
        runs = manager.wait(plan["plan_id"], 10)
        sent = len(server.observed)
        time.sleep(0.2)
        assert len(server.observed) == sent
        assert all(r["status"] == "cancelled" for r in runs)
        assert any(r["status"] == "interrupted" for r in runs[0]["records"])
        assert len(runs[1]["records"]) == 0
    finally:
        manager.close()


def test_credentials_not_saved_and_redirects_not_followed(tmp_path, endpoint, monkeypatch):
    url, server = endpoint
    monkeypatch.setenv("WORKBENCH_TEST_KEY", "sensitive-test-credential")
    run = run_one(
        tmp_path, make_spec(url, ["REDIRECT", "文章"], endpoint={"api_key_env": "WORKBENCH_TEST_KEY"})
    )
    assert len(server.observed) == 2
    assert server.observed[0]["headers"].get("Authorization") == "Bearer sensitive-test-credential"
    assert any(r["http_status"] == 307 for r in run["records"])
    for path in Path(tmp_path).rglob("*"):
        if path.is_file():
            assert b"sensitive-test-credential" not in path.read_bytes(), path


def test_arrival_rate_cap_rejects_not_delays(tmp_path, endpoint):
    url, server = endpoint
    run = run_one(
        tmp_path,
        make_spec(
            url,
            ["SLOW"],
            load={"mode": "rate", "rate": 1000, "count": 8, "concurrency": 1},
            safety={"max_concurrency": 1},
        ),
    )
    assert run["status"] == "completed"
    assert len(server.observed) < 8
    assert any(r["status"] == "client_rejected" for r in run["records"])


def test_deadline_covers_worker_startup_and_remaining_scan(tmp_path, endpoint):
    url, server = endpoint
    run = run_one(tmp_path, make_spec(url, ["SLOW"], safety={"max_duration_s": 0.01}))
    assert run["status"] == "timed_out"
    assert not server.observed


def test_cli_runs_real_evalscope_and_exports_report(tmp_path, endpoint, capsys):
    try:
        from perfworkbench.cli import main
    except ModuleNotFoundError:
        pytest.fail("CLI workflow missing", pytrace=False)
    url, server = endpoint
    config = tmp_path / "spec.json"
    config.write_text(json.dumps(make_spec(url)))
    root = tmp_path / "runs"
    assert main(["--root", str(root), "run", str(config)]) == 0
    results = json.loads(capsys.readouterr().out)
    run_id = results["run_ids"][0]
    report = tmp_path / "report.html"
    assert main(["--root", str(root), "report", run_id, "--format", "html", "--output", str(report)]) == 0
    assert "<html" in report.read_text().lower()
    assert len(server.observed) == 1
