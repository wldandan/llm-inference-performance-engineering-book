"""HTTP boundary tests. Manager is a route double, not execution integration."""

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "a" * 32
CANDIDATE_ID = "b" * 32
ACTION = {"X-Workbench-Action": "local"}


def test_web_entrypoint_exists():
    assert (ROOT / "perfworkbench/web.py").is_file(), "T4 web entry point is not implemented"


class RouteStore:
    def __init__(self):
        self.runs = {}

    def list(self):
        return list(self.runs.values())

    def get(self, run_id):
        if run_id not in self.runs:
            raise FileNotFoundError(run_id)
        return self.runs[run_id]

    def label(self, run_id, labels):
        run = self.get(run_id)
        for record in run.get("records", []):
            if record["request_id"] in labels:
                record["manual_label"] = labels[record["request_id"]]
        return run

    def update(self, run_id, **fields):
        self.get(run_id).update(fields)
        return self.get(run_id)


class RouteManager:
    def __init__(self):
        self.store = RouteStore()
        self.submissions = []
        self.preflights = []
        self.closed = False
        self.busy = False

    def submit(self, spec):
        if self.busy:
            raise RuntimeError("An experiment is already running")
        self.submissions.append(spec)
        return {"plan_id": RUN_ID, "run_ids": [RUN_ID]}

    def preflight(self, endpoint):
        self.preflights.append(endpoint)
        return {"models": ["local-model"], "stream": {"status": "ok"}}

    def cancel(self, run_id):
        self.store.get(run_id)
        return {"status": "cancelling", "id": run_id}

    def close(self):
        self.closed = True


@pytest.fixture
def web():
    assert (ROOT / "perfworkbench/web.py").is_file(), "T4 web entry point is not implemented"
    return importlib.import_module("perfworkbench.web")


@pytest.fixture
def manager():
    return RouteManager()


@pytest.fixture
def client(web, manager, monkeypatch, tmp_path):
    monkeypatch.setattr(web, "_create_manager", lambda root: manager)
    with TestClient(web.create_app(tmp_path)) as client:
        yield client
    assert manager.closed


def test_empty_history_and_local_assets(client):
    assert client.get("/api/runs").json() == []
    page = client.get("/")
    assert page.status_code == 200
    assert 'lang="zh-CN"' in page.text
    for asset, mime in [("app.js", "javascript"), ("style.css", "text/css")]:
        response = client.get("/static/" + asset)
        assert response.status_code == 200
        assert mime in response.headers["content-type"]
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/", "/api/runs", "/api/example", "/static/app.js"])
def test_host_guard_covers_reads(client, path):
    assert client.get(path, headers={"Host": "attacker.example"}).status_code == 400


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Workbench-Action": "no"},
        {**ACTION, "Origin": "https://evil.example"},
        {**ACTION, "Origin": "null"},
        {**ACTION, "Origin": "http://testserver:9999"},
        {**ACTION, "Origin": "http://testserver.evil.example"},
    ],
)
def test_mutation_guard_before_dispatch(client, manager, headers):
    response = client.post("/api/preflight", json={}, headers=headers)
    assert response.status_code == 403
    assert manager.preflights == []


def test_foreign_origin_read_is_rejected(client):
    response = client.get("/api/runs", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_example_is_starter_only(client, manager):
    spec = client.get("/api/example").json()
    assert spec["endpoint"]["base_url"].startswith("http://127.0.0.1")
    assert spec["dataset"]
    assert spec["safety"]["max_requests"] > 0
    assert not manager.submissions and not manager.preflights


def test_submit_uses_validated_contract_and_does_not_preflight(client, manager):
    spec = client.get("/api/example").json()
    response = client.post("/api/runs", json=spec, headers={**ACTION, "Origin": "http://testserver"})
    assert response.status_code == 202, response.text
    assert response.json() == {"plan_id": RUN_ID, "run_ids": [RUN_ID]}
    assert manager.submissions[0]["load"]["repeats"] == spec["load"]["repeats"]
    assert not manager.preflights


def test_invalid_spec_is_actionable_without_echoing_input(client, manager):
    spec = client.get("/api/example").json()
    spec["load"]["count"] = "do-not-echo-this-private-content"
    response = client.post("/api/runs", json=spec, headers=ACTION)
    assert response.status_code == 422
    assert "count" in response.text
    assert "do-not-echo" not in response.text
    assert not manager.submissions


@pytest.mark.parametrize("body", ['{"endpoint":', "[]", "null", '{"x":NaN}', '{"x":1,"x":2}'])
def test_invalid_json_is_actionable_text(client, body):
    response = client.post("/api/runs", content=body, headers=ACTION)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text


def test_body_is_bounded_with_and_without_declared_length(client, web):
    too_large = b" " * (web.MAX_BODY_BYTES + 1)
    for data in (too_large, iter([too_large[:1000], too_large[1000:]])):
        response = client.post("/api/runs", content=data, headers=ACTION)
        assert response.status_code == 413


def test_preflight_and_profile_are_explicit_actions(client, manager):
    spec = client.get("/api/example").json()
    response = client.post("/api/preflight", json=spec["endpoint"], headers=ACTION)
    assert response.status_code == 200, response.text
    assert manager.preflights[0]["model"] == spec["endpoint"]["model"]
    profile = client.post("/api/profile", json={"dataset": spec["dataset"]}, headers=ACTION)
    assert profile.status_code == 200, profile.text
    assert isinstance(profile.json(), dict) and profile.json()


def test_busy_manager_and_unexpected_failure_are_safe(client, manager, monkeypatch):
    manager.busy = True
    spec = client.get("/api/example").json()
    assert client.post("/api/runs", json=spec, headers=ACTION).status_code == 409

    def explode():
        raise OSError("private-token-and-private-path")

    monkeypatch.setattr(manager.store, "list", explode)
    response = client.get("/api/runs")
    assert response.status_code == 500
    assert "private-token" not in response.text


@pytest.mark.parametrize("run_id", ["not-a-run", "..", "a%2fb", "a%5cb"])
def test_ids_never_become_paths(client, run_id):
    assert client.get(f"/api/runs/{run_id}/report").status_code in (404, 422)


def test_missing_run_and_unsupported_export(client):
    assert client.get(f"/api/runs/{RUN_ID}").status_code == 404
    assert client.post(f"/api/runs/{RUN_ID}/cancel", json={}, headers=ACTION).status_code == 404
    assert client.get(f"/api/runs/{RUN_ID}/report?format=pickle").status_code == 422


def test_run_details_cancel_and_redacted_exports(client, manager):
    spec = client.get("/api/example").json()
    manager.store.runs[RUN_ID] = {
        "id": RUN_ID,
        "status": "completed",
        "created_at": "2026-09-21T00:00:00Z",
        "spec": spec,
        "summary": {},
        "profile": {},
        "parent_id": None,
        "diagnostics": [],
        "error": None,
        "telemetry": [],
        "progress": {},
        "records": [{"request_id": "r1", "output_text": "private-output-marker"}],
    }
    assert client.get(f"/api/runs/{RUN_ID}").json()["id"] == RUN_ID
    assert client.post(f"/api/runs/{RUN_ID}/cancel", json={}, headers=ACTION).status_code == 200
    for fmt in ["json", "markdown", "html"]:
        response = client.get(f"/api/runs/{RUN_ID}/report?format={fmt}")
        assert response.status_code == 200, response.text
        assert "private-output-marker" not in response.text
        assert "attachment" in response.headers["content-disposition"]
        if fmt == "html":
            assert "sandbox" in response.headers["content-security-policy"]


def test_compare_retest_and_labels_validation(client):
    for path, payload in [
        ("/api/compare", {"ids": ["../../etc/passwd"]}),
        ("/api/compare", {"ids": []}),
        ("/api/retest", {"baseline_id": RUN_ID, "candidate_id": RUN_ID, "criterion": {}}),
        (f"/api/runs/{RUN_ID}/labels", {"r1": "maybe"}),
    ]:
        assert client.post(path, json=payload, headers=ACTION).status_code == 422


def test_actual_manager_conflict_and_missing_plan_messages(client, manager, monkeypatch):
    def busy(spec):
        raise ValueError("Another experiment plan is active; finish or cancel it first")

    monkeypatch.setattr(manager, "submit", busy)
    response = client.post("/api/runs", json=client.get("/api/example").json(), headers=ACTION)
    assert response.status_code == 409

    def missing_plan(identifier):
        raise ValueError("No active/local plan with this id")

    monkeypatch.setattr(manager, "cancel", missing_plan)
    assert client.post(f"/api/runs/{RUN_ID}/cancel", json={}, headers=ACTION).status_code == 404


def test_retest_latency_percentile_and_persistent_association(client, manager):
    spec = client.get("/api/example").json()
    for identifier in (RUN_ID, CANDIDATE_ID):
        manager.store.runs[identifier] = {
            "id": identifier,
            "spec": spec,
            "status": "completed",
            "summary": {},
            "parent_id": "c" * 32,
            "records": [],
        }
    payload = {
        "baseline_id": RUN_ID,
        "candidate_id": CANDIDATE_ID,
        "criterion": {"metric": "e2e_ms.p95", "direction": "decrease", "min_relative_change": 0.1},
    }
    result = client.post("/api/retest", json=payload, headers=ACTION)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "insufficient_evidence"
    candidate = client.get(f"/api/runs/{CANDIDATE_ID}").json()
    assert candidate["parent_id"] == "c" * 32  # Plan association must remain intact.
    assert candidate["retest"]["baseline_id"] == RUN_ID
    assert candidate["retest"]["criterion"]["metric"] == "e2e_ms.p95"


def test_label_refresh_accepts_timeout_and_rejects_foreign_request(client, manager):
    spec = client.get("/api/example").json()
    manager.store.runs[RUN_ID] = {
        "id": RUN_ID,
        "spec": spec,
        "status": "timed_out",
        "summary": {},
        "telemetry": [],
        "records": [{"request_id": "r1", "status": "interrupted"}],
    }
    response = client.post(f"/api/runs/{RUN_ID}/labels", json={"r1": "unknown"}, headers=ACTION)
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["quality"]["unknown"] >= 0
    response = client.post(f"/api/runs/{RUN_ID}/labels", json={"foreign": "pass"}, headers=ACTION)
    assert response.status_code == 422


def test_404_errors_are_plain_text_and_unsafe_report_ids_reject_before_store(client):
    for path in ["/api/missing", "/static/missing", f"/api/runs/{'a' * 16}"]:
        response = client.get(path)
        assert response.status_code in {404, 422}
        assert response.headers["content-type"].startswith("text/plain")


def test_overflow_number_rejected_as_invalid_json(client):
    response = client.post("/api/runs", content='{"name":1e999}', headers=ACTION)
    assert response.status_code == 422
    assert "JSON" in response.text


def test_retest_accepts_exact_declared_load_change_and_rejects_others(client, manager):
    spec = client.get("/api/example").json()
    for identifier in (RUN_ID, CANDIDATE_ID):
        manager.store.runs[identifier] = {
            "id": identifier,
            "spec": spec,
            "status": "completed",
            "summary": {},
        }
    payload = {
        "baseline_id": RUN_ID,
        "candidate_id": CANDIDATE_ID,
        "criterion": {
            "metric": "requests_per_s",
            "direction": "increase",
            "min_relative_change": 0.1,
            "change": {"field": "load.concurrency", "before": 1, "after": 2},
        },
    }
    response = client.post("/api/retest", json=payload, headers=ACTION)
    assert response.status_code == 200, response.text
    assert response.json()["criterion"]["change"]["field"] == "load.concurrency"
    assert manager.store.get(CANDIDATE_ID)["retest"]["criterion"]["change"]["after"] == 2
    for declaration in [
        {"field": "endpoint.model", "before": 1, "after": 2},
        {"field": "load.concurrency", "before": 1, "after": 1.5},
        {"field": "load.rate", "before": 1, "after": -1},
        {"field": "load.rate", "before": True, "after": 2},
        "invalid",
    ]:
        payload["criterion"]["change"] = declaration
        assert client.post("/api/retest", json=payload, headers=ACTION).status_code == 422


def test_plan_summary_collects_only_matching_children_and_never_ranks_fixture(client, manager):
    plan_id = "d" * 32
    for index, identifier in enumerate((RUN_ID, CANDIDATE_ID)):
        spec = client.get("/api/example").json()
        spec["protocol_fixture"] = True
        spec["load"]["concurrency"] = index + 1
        manager.store.runs[identifier] = {
            "id": identifier,
            "parent_id": plan_id,
            "status": "completed",
            "spec": spec,
            "summary": {
                "sample_count": 10,
                "quality": {"coverage": 1, "pass_rate": 1},
                "goals": [{"status": "pass"}],
                "metrics": {
                    "requests_per_s": 5 + index,
                    "goodput_per_s": 5 + index,
                    "failed": 0,
                    "interrupted": 0,
                    "client_rejected": 0,
                },
            },
        }
    manager.store.runs["e" * 32] = {"id": "e" * 32, "parent_id": "f" * 32}
    response = client.get(f"/api/plans/{plan_id}/summary")
    assert response.status_code == 200, response.text
    assert len(response.json()["points"]) == 2
    assert response.json()["best_point"] is None
    assert response.json()["warnings"]
    assert client.get(f"/api/plans/{'f' * 32}/summary").status_code == 200
    assert client.get(f"/api/plans/{'c' * 32}/summary").status_code == 404
    assert client.get("/api/plans/not-a-path/summary").status_code == 422


def test_running_plan_summary_keeps_unknown_evidence(client, manager):
    manager.store.runs[RUN_ID] = {
        "id": RUN_ID,
        "parent_id": CANDIDATE_ID,
        "status": "running",
        "spec": client.get("/api/example").json(),
        "summary": None,
    }
    response = client.get(f"/api/plans/{CANDIDATE_ID}/summary")
    assert response.status_code == 200, response.text
    assert response.json()["best_point"] is None
    assert response.json()["eligible_points"] == []
    assert response.json()["points"][0]["requests_per_s"] is None


def test_profile_is_independent_of_generation_budget(client):
    samples = client.get("/api/example").json()["dataset"]
    samples[0]["max_tokens"] = 200000
    response = client.post("/api/profile", json={"dataset": samples}, headers=ACTION)
    assert response.status_code == 200, response.text
    assert response.json()["sample_count"] == 1


def test_retest_wrong_direction_type_returns_validation_error(client):
    payload = {
        "baseline_id": RUN_ID,
        "candidate_id": CANDIDATE_ID,
        "criterion": {"metric": "requests_per_s", "direction": []},
    }
    response = client.post("/api/retest", json=payload, headers=ACTION)
    assert response.status_code == 422
