"""A complete FastAPI/runner workflow against a local protocol fixture, never a real model."""

import threading
import time
from http.server import ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from test_integration import EndpointFixture, make_spec

from perfworkbench.web import create_app

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("ps_status", [200, 503])
def test_local_resources_persist_through_real_experiment_and_http_query(tmp_path, ps_status):
    class Handler(EndpointFixture):
        def do_GET(self):
            if self.path == "/api/ps":
                self.server.ps_reads += 1
                return self.send_payload(
                    {"models": [{"name": "protocol-fixture", "size_vram": 1024, "context_length": 4096}]},
                    ps_status,
                )
            return super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.observed, server.ps_reads = [], 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with TestClient(create_app(tmp_path)) as client:
            value = make_spec(f"http://127.0.0.1:{server.server_port}/v1")
            value["telemetry"] = {"local": {"enabled": True}, "interval_s": 0.1}
            response = client.post("/api/runs", json=value, headers={"X-Workbench-Action": "local"})
            assert response.status_code == 202
            plan = response.json()
            client.app.state.manager.wait(plan["plan_id"], timeout=45)
            run_id = plan["run_ids"][0]
            run = client.get(f"/api/runs/{run_id}").json()
            assert run["status"] == "completed"
            assert len(server.observed) == 1  # Only the explicitly requested generation.
            assert server.ps_reads > 0
            assert {f["source_kind"] for f in run["telemetry"]} == {"local_system", "local_ollama"}
            model_frame = next(f for f in run["telemetry"] if f["source_kind"] == "local_ollama")
            assert model_frame["metrics"]["model_memory_bytes"]["value"] == (
                1024 if ps_status == 200 else None
            )
            reads = server.ps_reads
            time.sleep(0.2)
            assert server.ps_reads == reads
            assert client.get(f"/api/runs/{run_id}").json()["telemetry"] == run["telemetry"]
            assert client.get(f"/api/runs/{run_id}/report?format=json").status_code == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
