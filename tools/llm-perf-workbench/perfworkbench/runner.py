"""Own the EvalScope process lifecycle, plan budgets, evidence and explicit cancellation."""

import asyncio
import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from .config import Endpoint, ExperimentSpec
from .dataset import build_plan, materialize_requests, profile_dataset
from .store import JsonlCounter, RunStore, append_jsonl, read_jsonl

TERMINAL = {"completed", "failed", "cancelled", "timed_out", "interrupted"}


def finalize_interrupted(directory, spec, status):
    """Reconcile locally observed starts without inventing successful responses."""
    rows = read_jsonl(directory / "records.jsonl")
    seen = {row["request_id"] for row in rows}
    for start in read_jsonl(directory / "starts.jsonl"):
        if start["request_id"] in seen:
            continue
        anchor = start.get("monotonic_start")
        elapsed = max(0, time.monotonic() - anchor) if anchor is not None else None
        append_jsonl(
            directory / "records.jsonl",
            {
                **start,
                "end_s": start["start_s"] + (elapsed or 0),
                "status": "interrupted",
                "success": False,
                "http_status": None,
                "error_kind": status,
                "is_stream": spec.get("generation", {}).get("stream", False),
                "e2e_ms": elapsed * 1000 if elapsed is not None else None,
                "input_tokens": None,
                "output_tokens": None,
                "ttft_ms": None,
                "tpot_ms": None,
                "inter_chunk_ms": [],
                "output_text": "",
                "finish_reason": None,
            },
        )
    return read_jsonl(directory / "records.jsonl")


def refresh_analysis(store, run_id):
    from .analysis import analyze, diagnose

    run = store.get(run_id)
    summary = analyze(run["records"], run["spec"], run["telemetry"], status=run["status"])
    diagnostics = diagnose(summary, run["spec"], run["telemetry"])
    return store.update(run_id, summary=summary, diagnostics=diagnostics)


class ExperimentManager:
    def __init__(self, root):
        self.store = RunStore(root)
        self._lock = threading.RLock()
        self._plans = {}
        self._active = None
        self._preflight_active = False
        self._recover_orphans()

    def _recover_orphans(self):
        fd = os.open(self.store.root / "manager.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return  # A live manager owns the workspace; never steal its state.
            for run in self.store.list():
                if run["status"] not in TERMINAL:
                    directory = self.store.run_dir(run["id"])
                    (directory / "STOP").touch(mode=0o600)
                    finalize_interrupted(directory, run["spec"], "controller_exited")
                    self.store.update(
                        run["id"],
                        status="interrupted",
                        error="Previous controller exited; retained evidence, no automatic replay",
                    )
        finally:
            os.close(fd)

    def preflight(self, endpoint):
        from .evalscope_worker import probe_endpoint

        value = Endpoint.model_validate(endpoint).model_dump(mode="json")
        with self._lock:
            if self._active or self._preflight_active:
                raise ValueError("Cannot preflight while an experiment or preflight is active")
            fd = os.open(self.store.root / "manager.lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                raise ValueError("Another process owns this experiment workspace") from None
            self._preflight_active = True
        try:
            return asyncio.run(probe_endpoint(value))
        finally:
            with self._lock:
                self._preflight_active = False
                os.close(fd)

    def submit(self, spec):
        raw = ExperimentSpec.model_validate(spec).model_dump(mode="json")
        profile = profile_dataset(raw["dataset"], raw["tokenizer_path"])
        if profile["input_tokens"] and raw["endpoint"]["context_length"]:
            maximum = profile["input_tokens"]["max"] + max(
                row["max_tokens"] or raw["generation"]["max_tokens"] for row in raw["dataset"]
            )
            if maximum > raw["endpoint"]["context_length"]:
                raise ValueError("Input plus output reservation exceeds declared context length")
        plans = build_plan(raw)
        key = raw["endpoint"].get("api_key_env")
        if key and not os.environ.get(key):
            raise ValueError("Configured API key environment variable is missing")
        with self._lock:
            if self._active is not None or self._preflight_active:
                raise ValueError("Another experiment plan is active; finish or cancel it first")
            lock_path = self.store.root / "manager.lock"
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                raise ValueError("Another process owns this experiment workspace") from None
            plan_id = uuid.uuid4().hex
            try:
                runs = [self.store.create(child, profile, plan_id) for child in plans]
            except BaseException:
                os.close(fd)
                raise
            state = {
                "plan_id": plan_id,
                "run_ids": [r["id"] for r in runs],
                "stop": threading.Event(),
                "done": threading.Event(),
                "fd": fd,
                "spec": raw,
                "process": None,
                "deadline": time.monotonic() + raw["safety"]["max_duration_s"],
            }
            self._plans[plan_id] = state
            self._active = plan_id
            thread = threading.Thread(target=self._execute, args=(state,), daemon=True, name="workbench-plan")
            state["thread"] = thread
            thread.start()
            return {"plan_id": plan_id, "run_ids": state["run_ids"]}

    def _environment(self, spec, state):
        allowed = ("PATH", "HOME", "TMPDIR", "LANG", "SSL_CERT_FILE")
        env = {key: os.environ[key] for key in allowed if key in os.environ}
        for name in [spec["endpoint"].get("api_key_env")]:
            if name and name in os.environ:
                env[name] = os.environ[name]
        env.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "TOKENIZERS_PARALLELISM": "false",
                "DO_NOT_TRACK": "1",
                "NO_PROXY": "*",
                "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                "PERFWORKBENCH_PARENT_PID": str(os.getpid()),
                "PERFWORKBENCH_DEADLINE": str(state["deadline"]),
            }
        )
        if "COVERAGE_PROCESS_START" in os.environ:
            env["COVERAGE_PROCESS_START"] = os.environ["COVERAGE_PROCESS_START"]
        return env

    @staticmethod
    def _terminate(process):
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        except ProcessLookupError:
            pass

    def _execute(self, state):
        try:
            for run_id in state["run_ids"]:
                if state["stop"].is_set() or time.monotonic() >= state["deadline"]:
                    status = "cancelled" if state["stop"].is_set() else "timed_out"
                    self.store.update(run_id, status=status, error="Plan stopped before this point started")
                    refresh_analysis(self.store, run_id)
                    continue
                self._execute_one(run_id, state)
        except Exception as exc:  # noqa: BLE001 - retain terminal state without provider error bodies.
            for run_id in state["run_ids"]:
                if self.store.get(run_id)["status"] not in TERMINAL:
                    self.store.update(
                        run_id, status="failed", error=f"Experiment controller failed ({type(exc).__name__})"
                    )
        finally:
            self._terminate(state.get("process"))
            with self._lock:
                self._active = None
                fcntl.flock(state["fd"], fcntl.LOCK_UN)
                os.close(state["fd"])
                state["done"].set()

    def _execute_one(self, run_id, state):
        from .telemetry import TelemetryCollector

        run = self.store.get(run_id)
        spec = run["spec"]
        directory = self.store.run_dir(run_id)
        requests = materialize_requests(spec)
        for record in requests:
            append_jsonl(directory / "requests.jsonl", record)
        collector = TelemetryCollector(spec, directory / "telemetry.jsonl")
        collector.start()
        process = None
        try:
            self.store.update(run_id, status="running")
            log_fd = os.open(directory / "process.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(log_fd, "w") as log:
                command = [sys.executable, "-m", "perfworkbench.evalscope_worker", str(directory)]
                process = subprocess.Popen(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=self._environment(spec, state),
                    cwd=directory,
                    start_new_session=True,
                )
                state["process"] = process
                counter = JsonlCounter(directory / "records.jsonl")
                last_done = -1
                while process.poll() is None:
                    if (directory / "STOP").exists():
                        state["stop"].set()
                    if state["stop"].is_set() or time.monotonic() >= state["deadline"]:
                        (directory / "STOP").touch(mode=0o600)
                        self._terminate(process)
                        break
                    done = counter.count()
                    if done != last_done:
                        self.store.update(
                            run_id, include_evidence=False, progress={"done": done, "total": len(requests)}
                        )
                        last_done = done
                    state["stop"].wait(0.1)
            if state["stop"].is_set():
                status = "cancelled"
            elif time.monotonic() >= state["deadline"]:
                status = "timed_out"
            elif process.returncode or not (directory / "worker-finished.json").exists():
                status = "failed"
            else:
                status = "completed"
            rows = finalize_interrupted(directory, spec, status)
            if status == "completed" and len(rows) != len(requests):
                status = "failed"
            self.store.update(
                run_id,
                status=status,
                error=None if status == "completed" else f"Run {status}; partial evidence retained",
                progress={"done": len(rows), "total": len(requests)},
            )
        finally:
            self._terminate(process)
            collector.stop()
            state["process"] = None
        refresh_analysis(self.store, run_id)

    def _plan(self, identifier):
        if identifier in self._plans:
            return self._plans[identifier]
        for plan in self._plans.values():
            if identifier in plan["run_ids"]:
                return plan
        raise ValueError("No active/local plan with this id")

    def cancel(self, identifier):
        with self._lock:
            try:
                plan = self._plan(identifier)
            except ValueError:
                runs = self.store.list()
                selected = next(
                    (r for r in runs if r["id"] == identifier or r.get("parent_id") == identifier), None
                )
                if selected is None:
                    raise ValueError("Unknown experiment or plan") from None
                parent = selected.get("parent_id") or selected["id"]
                for run in runs:
                    if run["id"] == selected["id"] or run.get("parent_id") == parent:
                        (self.store.run_dir(run["id"]) / "STOP").touch(mode=0o600)
                return {"plan_id": parent, "status": "stop_requested"}
            plan["stop"].set()
            for run_id in plan["run_ids"]:
                (self.store.run_dir(run_id) / "STOP").touch(mode=0o600)
            return {
                "plan_id": plan["plan_id"],
                "status": "stopping" if not plan["done"].is_set() else "stopped",
            }

    def wait(self, plan_id, timeout=None):
        plan = self._plan(plan_id)
        if not plan["done"].wait(timeout):
            raise TimeoutError("Experiment remains active")
        return [self.store.get(run_id) for run_id in plan["run_ids"]]

    def close(self):
        with self._lock:
            active = self._active
        if active:
            self.cancel(active)
            self._plans[active]["done"].wait(10)
