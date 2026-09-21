"""Release-blocking review cases; external HTTP remains a local protocol fixture."""

import asyncio
import fcntl
import json
import logging
import os
import subprocess
import sys
import threading

import pytest
from test_integration import endpoint as endpoint_fixture
from test_integration import make_spec, run_one

from perfworkbench import evalscope_worker as worker
from perfworkbench import runner
from perfworkbench.store import append_jsonl, read_jsonl

endpoint = endpoint_fixture


def test_secret_dictionary_keys_are_redacted():
    value = {"echo-secret": {"nested-secret": "secret"}}
    assert "secret" not in json.dumps(worker._scrub(value, "secret"))


def test_upstream_logging_filter_removes_secret_values_and_exception_details():
    assert hasattr(worker, "redact_upstream_logs"), "Upstream diagnostics must not persist injected keys"
    logger = logging.getLogger("evalscope")
    messages = []

    class Recorder(logging.Handler):
        def emit(self, record):
            messages.append(self.format(record))

    handler = Recorder()
    logger.addHandler(handler)
    try:
        with worker.redact_upstream_logs("credential-canary"):
            try:
                raise ValueError("header credential-canary")
            except ValueError:
                logger.exception("echo %s", "credential-canary")
        assert messages and "credential-canary" not in messages[0]
        assert "REDACTED" in messages[0]
    finally:
        logger.removeHandler(handler)


def test_preflight_cannot_bypass_other_process_workspace_lock(tmp_path):
    manager = runner.ExperimentManager(tmp_path)
    fd = os.open(tmp_path / "manager.lock", os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(ValueError, match="(process|active|workspace)"):
            manager.preflight({"base_url": "http://127.0.0.1:1/v1", "model": "m"})
    finally:
        os.close(fd)
        manager.close()


def test_preflight_reserves_same_manager_before_sending(tmp_path, monkeypatch):
    manager = runner.ExperimentManager(tmp_path)
    entered, release = threading.Event(), threading.Event()

    async def held_http(endpoint):
        entered.set()
        await asyncio.to_thread(release.wait, 3)
        return {"ready": True}

    monkeypatch.setattr(worker, "probe_endpoint", held_http)
    thread = threading.Thread(
        target=manager.preflight, args=({"base_url": "http://127.0.0.1:1/v1", "model": "m"},)
    )
    thread.start()
    try:
        assert entered.wait(2)
        with pytest.raises(ValueError, match="active"):
            manager.submit(make_spec("http://127.0.0.1:1/v1"))
        assert manager.store.list() == []
    finally:
        release.set()
        thread.join(4)
        manager.close()


def test_interruption_uses_monotonic_not_adjusted_wall_clock(tmp_path, monkeypatch):
    append_jsonl(
        tmp_path / "starts.jsonl",
        {"request_id": "r", "start_s": 2, "started_at": 1234, "monotonic_start": 100},
    )
    monkeypatch.setattr(runner.time, "time", lambda: 99999999)
    monkeypatch.setattr(runner.time, "monotonic", lambda: 100.5)
    assert hasattr(runner, "finalize_interrupted"), "Missing monotonic reconciliation"
    runner.finalize_interrupted(tmp_path, {"generation": {"stream": True}}, "cancelled")
    row = read_jsonl(tmp_path / "records.jsonl")[0]
    assert row["e2e_ms"] == 500
    assert row["end_s"] == 2.5


def test_dead_parent_watchdog_terminates_only_own_worker():
    assert hasattr(worker, "start_parent_watchdog"), "Orphan workers must not keep sending"
    code = "import os,time; from perfworkbench.evalscope_worker import start_parent_watchdog; start_parent_watchdog(os.getppid()+100000); time.sleep(3)"
    result = subprocess.run([sys.executable, "-c", code], timeout=5, capture_output=True, check=False)
    assert result.returncode < 0


def test_worker_environment_tracks_parent_pid(tmp_path):
    manager = runner.ExperimentManager(tmp_path)
    try:
        environment = manager._environment({"endpoint": {}}, {"deadline": 123})
        assert environment.get("PERFWORKBENCH_PARENT_PID") == str(os.getpid())
    finally:
        manager.close()


def test_manifest_only_progress_does_not_reread_request_outputs(tmp_path, monkeypatch):
    manager = runner.ExperimentManager(tmp_path)
    run = manager.store.create({"name": "progress"})

    def forbidden_read(*args):
        pytest.fail("Progress updates must not re-read growing request evidence")

    monkeypatch.setattr(manager.store, "records", forbidden_read)
    updated = manager.store.update(run["id"], include_evidence=False, progress={"done": 1})
    assert updated["progress"] == {"done": 1}
    assert "records" not in updated
    manager.close()


def test_progress_counter_reads_new_complete_lines_only(tmp_path):
    from perfworkbench import store

    assert hasattr(store, "JsonlCounter"), "Need incremental progress without O(N²) file reads"
    path = tmp_path / "records.jsonl"
    cursor = store.JsonlCounter(path)
    assert cursor.count() == 0
    path.write_bytes(b'{"id":1}\n{"id":')
    assert cursor.count() == 1
    assert cursor.count() == 1
    with path.open("ab") as output:
        output.write(b"2}\n")
    assert cursor.count() == 2


def test_failed_plan_creation_releases_workspace_lock(tmp_path, monkeypatch):
    manager = runner.ExperimentManager(tmp_path)

    def broken_store(*args):
        raise OSError("disk full")

    monkeypatch.setattr(manager.store, "create", broken_store)
    with pytest.raises(OSError, match="disk full"):
        manager.submit(make_spec("http://127.0.0.1:1/v1"))
    fd = os.open(tmp_path / "manager.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)
        manager.close()


@pytest.mark.integration
def test_usage_missing_does_not_stop_remaining_requests(tmp_path, endpoint):
    url, server = endpoint
    run = run_one(tmp_path, make_spec(url, ["NOUSAGE", "article"], load={"concurrency": 1}))
    assert run["status"] == "completed", run["error"]
    assert len(server.observed) == 2
    rows = {row["sample_id"]: row for row in run["records"]}
    assert rows["s0"]["success"] and rows["s0"]["output_tokens"] is None
    assert rows["s1"]["success"] and rows["s1"]["output_tokens"] == 8


@pytest.mark.integration
def test_fractional_request_timeout_is_not_rounded_up(tmp_path, endpoint):
    url, server = endpoint
    run = run_one(tmp_path, make_spec(url, ["SLOW"], safety={"request_timeout_s": 0.05}))
    assert run["status"] == "completed", run["error"]
    assert len(server.observed) == 1
    row = run["records"][0]
    assert not row["success"]
    assert 20 <= row["e2e_ms"] < 350
