"""Worker contracts at the real EvalScope parser / replaceable HTTP boundary.

Unit doubles supply bytes and HTTP metadata only. Worker normalization, request
construction, admission, persistence and EvalScope response parsing remain real.
"""

import asyncio
import copy
import importlib.metadata
import json
import runpy
import sys
import threading
import time
import warnings
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from perfworkbench import evalscope_worker as worker
from perfworkbench.store import append_jsonl, read_jsonl, write_json


class MemoryContent:
    """Consumable response stream, including bounded reads across byte fragments."""

    def __init__(self, chunks):
        self.chunks = deque(chunks)

    async def iter_chunked(self, size):
        while self.chunks:
            chunk = self.chunks.popleft()
            if len(chunk) > size:
                self.chunks.appendleft(chunk[size:])
                chunk = chunk[:size]
            yield chunk


class MemoryResponse:
    def __init__(self, chunks, *, status=200, content_type="application/json"):
        self.content = MemoryContent(chunks)
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.reason = "fixture status"
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True


class MemorySession:
    def __init__(self, *responses, before_send=None):
        self.responses = deque(responses)
        self.sent = []
        self.before_send = before_send

    def post(self, **kwargs):
        if self.before_send:
            self.before_send()
        self.sent.append(copy.deepcopy(kwargs))
        assert self.responses, "unexpected extra request or retry"
        return self.responses.popleft()


def normalized(*, stream=False, responses=None, **changes):
    raw = SimpleNamespace(
        success=True,
        is_stream=stream,
        first_chunk_latency=0.1,
        prompt_tokens=12,
        completion_tokens=3,
        status_code=200,
        inter_chunk_latency=[0.02, 0.03],
        response_messages=responses if responses is not None else [completion(stream=stream)],
        error="provider-private-error",
        generated_text="answer",
    )
    for name, value in changes.items():
        setattr(raw, name, value)
    return worker.normalize_output(
        raw, {"request_id": "r", "phase": "measure"}, start=10, end=11, origin=9, started_at=1234
    )


def completion(*, stream=False, finish="stop", text="answer", usage=None):
    value = {
        "object": "chat.completion.chunk" if stream else "chat.completion",
        "choices": [
            {"index": 0, "delta" if stream else "message": {"content": text}, "finish_reason": finish}
        ],
    }
    if usage is not None:
        value["usage"] = usage
    return value


@pytest.mark.parametrize(
    "responses", [[], [None, "text", 7], [{"choices": []}], [{"choices": {"0": {}}}], [{"choices": [None]}]]
)
def test_empty_or_wrong_choices_are_protocol_failures(responses):
    result = normalized(responses=responses)
    assert result["status"] == "failed"
    assert result["error_kind"] == "protocol_error"
    assert result["output_text"] == ""
    assert result["ttft_ms"] is None and result["tpot_ms"] is None


@pytest.mark.parametrize("message", [None, "not-an-object", 7, ["not-a-message"]])
def test_nonstream_finish_reason_does_not_validate_a_malformed_message(message):
    result = normalized(responses=[{"choices": [{"message": message, "finish_reason": "stop"}]}])
    assert result["success"] is False, "finish_reason alone must not turn malformed content into success"
    assert result["error_kind"] == "protocol_error"


@pytest.mark.parametrize("reason", [[], {}, 123, True, "unknown-finish"])
def test_invalid_finish_reason_is_a_safe_failure(reason):
    result = normalized(responses=[completion(finish=reason)])
    assert result["success"] is False
    assert result["error_kind"] in {"protocol_error", "incomplete_response"}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("reason", ["length", "content_filter", "tool_calls", "function_call"])
def test_terminal_reasons_remain_completed_for_later_quality_evaluation(stream, reason):
    result = normalized(stream=stream, responses=[completion(stream=stream, finish=reason, text="")])
    assert result["success"] is True
    assert result["finish_reason"] == reason
    assert result["error_kind"] is None


@pytest.mark.parametrize("value", [True, False, -1, 3.5, "3", float("nan"), float("inf"), None])
def test_untrusted_usage_counts_remain_unknown(value):
    result = normalized(stream=True, prompt_tokens=value, completion_tokens=value)
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["tpot_ms"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("latency", [-0.1, float("nan"), float("inf"), 1.5])
def test_invalid_first_chunk_latency_does_not_create_impossible_timing(latency):
    result = normalized(stream=True, first_chunk_latency=latency)
    assert result["ttft_ms"] is None
    assert result["tpot_ms"] is None


def test_chunk_latency_filters_invalid_samples_and_keeps_valid_zero():
    result = normalized(stream=True, inter_chunk_latency=[0, -1, float("nan"), float("inf"), 0.125])
    assert result["inter_chunk_ms"] == [0, 125]


def test_transport_failure_dominates_a_previously_observed_finish():
    result = normalized(stream=True, success=False, status_code=None)
    assert result["error_kind"] == "transport_error"
    assert result["success"] is False
    assert result["ttft_ms"] is None
    assert result["inter_chunk_ms"] == []
    assert "provider-private-error" not in json.dumps(result)


def test_bounded_response_preserves_split_utf8_and_cached_reads():
    payload = json.dumps({"text": "中文"}, ensure_ascii=False).encode()
    raw = MemoryResponse([payload[:11], payload[11:12], payload[12:]])
    response = worker._BoundedResponse(raw, len(payload))

    async def scenario():
        assert await response.json() == {"text": "中文"}
        assert await response.text() == payload.decode()
        assert await response.json() == {"text": "中文"}
        assert response.status == 200

    asyncio.run(scenario())


@pytest.mark.parametrize("chunks,limit", [([b"123", b"45"], 4), ([b"\xe4\xb8\xad"], 2)])
def test_body_limit_counts_bytes_cumulatively(chunks, limit):
    response = worker._BoundedResponse(MemoryResponse(chunks), limit)
    with pytest.raises(ValueError, match="^response_size_limit$"):
        asyncio.run(response.text())


def test_body_limit_failure_cannot_be_bypassed_by_parser_fallback_read():
    response = worker._BoundedResponse(MemoryResponse([b"12345", b"{}"]), 4)

    async def scenario():
        with pytest.raises(ValueError, match="response_size_limit"):
            await response.json()
        with pytest.raises(ValueError, match="response_size_limit"):
            await response.text()

    asyncio.run(scenario())


def test_malformed_json_keeps_bounded_raw_text_available_for_upstream_fallback():
    response = worker._BoundedResponse(MemoryResponse([b'{"broken":']), 32)

    async def scenario():
        with pytest.raises(json.JSONDecodeError):
            await response.json()
        assert await response.text() == '{"broken":'

    asyncio.run(scenario())


def test_bounded_context_closes_after_parser_error_and_disables_redirects():
    raw = MemoryResponse([b"not-json"])
    session = MemorySession(raw)

    async def scenario():
        with pytest.raises(json.JSONDecodeError):
            async with worker.BoundedSession(session, 32).post(
                url="http://fixture.invalid", data="{}"
            ) as response:
                await response.json()

    asyncio.run(scenario())
    assert raw.closed
    assert session.sent[0]["allow_redirects"] is False


@pytest.fixture
def evalscope_boundary(monkeypatch):
    from evalscope.perf.arguments import Arguments
    from evalscope.perf.plugin.api.openai_api import OpenaiPlugin
    from evalscope.perf.plugin.registry import ApiRegistry
    from evalscope.perf.utils.benchmark_util import BenchmarkData
    from evalscope.perf.utils.body_meta import BODY_META_HEADERS, BODY_META_REQUEST_ID

    monkeypatch.setattr(ApiRegistry, "_registry", dict(ApiRegistry._registry))
    monkeypatch.delenv("PERFWORKBENCH_DEADLINE", raising=False)
    return SimpleNamespace(
        Arguments=Arguments,
        OpenaiPlugin=OpenaiPlugin,
        ApiRegistry=ApiRegistry,
        BenchmarkData=BenchmarkData,
        header_key=BODY_META_HEADERS,
        id_key=BODY_META_REQUEST_ID,
    )


@pytest.fixture
def plugin_factory(tmp_path, evalscope_boundary):
    def make(*, safety=None, api_key_env=None, phases=("warmup", "measure", "measure")):
        spec = {
            "endpoint": {
                "base_url": "http://fixture.invalid/v1",
                "model": "protocol-fixture",
                "api_key_env": api_key_env,
            },
            "safety": {
                "max_requests": 10,
                "max_output_tokens": 100,
                "max_concurrency": 2,
                "max_response_bytes": 1024,
                **(safety or {}),
            },
        }
        rows = [
            {
                "request_id": f"{index + 1:032x}",
                "sample_id": "same-sample",
                "category": "translation",
                "phase": phase,
                "body": {
                    "model": "protocol-fixture",
                    "messages": [{"role": "user", "content": "中文"}],
                    "stream": False,
                    "max_tokens": 4,
                    "temperature": 0.2,
                },
            }
            for index, phase in enumerate(phases)
        ]
        plugin_type = worker.register_workbench_plugin(tmp_path, spec, rows)
        plugin = plugin_type(evalscope_boundary.Arguments(model="fallback", max_tokens=99, stream=True))
        return SimpleNamespace(plugin=plugin, rows=rows, spec=spec, directory=tmp_path)

    return make


async def dispatch(harness, session, row, boundary):
    body = harness.plugin.build_request(
        {**copy.deepcopy(row["body"]), "_workbench_request_id": row["request_id"]}
    )
    headers = body.pop(boundary.header_key)
    body.pop(boundary.id_key)
    return await harness.plugin.process_request(
        session, "http://fixture.invalid/v1/chat/completions", headers, body
    )


def json_response(payload=None, *, status=200):
    if payload is None:
        payload = completion(usage={"prompt_tokens": 12, "completion_tokens": 3})
    return MemoryResponse([json.dumps(payload).encode()], status=status)


def test_build_request_preserves_per_sample_fields_and_separates_metadata(plugin_factory, evalscope_boundary):
    harness = plugin_factory()
    row = harness.rows[0]
    source = {**copy.deepcopy(row["body"]), "_workbench_request_id": row["request_id"]}
    original = copy.deepcopy(source)
    body = harness.plugin.build_request(source)
    assert source == original
    assert body["model"] == "protocol-fixture"
    assert body["max_tokens"] == 4  # Must survive the Arguments(max_tokens=99) default.
    assert body["stream"] is False
    assert body["temperature"] == 0.2
    assert "_workbench_request_id" not in body
    assert body[evalscope_boundary.id_key] == row["request_id"]
    assert body[evalscope_boundary.header_key]["X-Workbench-Request-ID"] == row["request_id"]
    assert "phase" not in body and "sample_id" not in body


def test_plugin_persists_phase_and_identity_before_send_when_dispatched_out_of_order(
    plugin_factory,
    evalscope_boundary,
):
    harness = plugin_factory()
    expected_order = [harness.rows[1], harness.rows[0]]

    def check_started_evidence():
        starts = read_jsonl(harness.directory / "starts.jsonl")
        assert starts[-1]["request_id"] == expected_order[len(session.sent)]["request_id"]

    session = MemorySession(json_response(), json_response(), before_send=check_started_evidence)

    async def scenario():
        for row in expected_order:
            assert (await dispatch(harness, session, row, evalscope_boundary)).success

    asyncio.run(scenario())
    records = read_jsonl(harness.directory / "records.jsonl")
    assert [(r["request_id"], r["sample_id"], r["phase"]) for r in records] == [
        (r["request_id"], "same-sample", r["phase"]) for r in expected_order
    ]
    assert [r["phase"] for r in records] == ["measure", "warmup"]
    assert all(r["input_tokens"] == 12 and r["output_tokens"] == 3 for r in records)
    assert all(r["end_s"] >= r["start_s"] for r in records)
    assert all("X-Workbench-Request-ID" not in request["headers"] for request in session.sent)
    assert [request["headers"]["X-Request-ID"] for request in session.sent] == [
        r["request_id"] for r in expected_order
    ]


def test_env_key_is_injected_but_echoes_never_survive_output_or_records(
    plugin_factory,
    evalscope_boundary,
    monkeypatch,
):
    secret = "worker-edge-secret-123"
    monkeypatch.setenv("WORKER_EDGE_KEY", secret)
    harness = plugin_factory(api_key_env="WORKER_EDGE_KEY")
    response = completion(text=f"before {secret} after", usage={"prompt_tokens": 12, "completion_tokens": 3})
    session = MemorySession(json_response(response))
    result = asyncio.run(dispatch(harness, session, harness.rows[0], evalscope_boundary))
    assert result.success
    assert session.sent[0]["headers"]["Authorization"] == f"Bearer {secret}"
    assert result.generated_text == "before [REDACTED] after"
    assert secret not in json.dumps(result.response_messages)
    record = read_jsonl(harness.directory / "records.jsonl")[0]
    assert record["output_text"] == "before [REDACTED] after"
    assert all(secret not in path.read_text() for path in harness.directory.iterdir() if path.is_file())
    assert secret not in json.dumps(harness.spec)


def test_missing_env_key_fails_before_registration_or_evidence(plugin_factory, monkeypatch, tmp_path):
    monkeypatch.delenv("WORKER_EDGE_MISSING_KEY", raising=False)
    with pytest.raises(ValueError, match="environment variable is missing"):
        plugin_factory(api_key_env="WORKER_EDGE_MISSING_KEY")
    assert not (tmp_path / "starts.jsonl").exists()
    assert not (tmp_path / "records.jsonl").exists()


@pytest.mark.parametrize("status", [307, 401, 503])
def test_plugin_http_failure_is_safe_and_never_retries(plugin_factory, evalscope_boundary, status):
    harness = plugin_factory()
    session = MemorySession(json_response({"error": "private-provider-body"}, status=status))
    result = asyncio.run(dispatch(harness, session, harness.rows[0], evalscope_boundary))
    record = read_jsonl(harness.directory / "records.jsonl")[0]
    assert not result.success
    assert result.error == record["error_kind"] == "http_error"
    assert record["http_status"] == status
    assert len(session.sent) == 1
    assert session.sent[0]["allow_redirects"] is False
    assert "private-provider-body" not in json.dumps(record)
    assert "private-provider-body" not in result.error


@pytest.mark.parametrize(
    "kind", ["cancelled", "deadline_exceeded", "request_budget_exceeded", "token_budget_exceeded"]
)
def test_admission_failure_records_reason_and_never_claims_a_sent_request(
    plugin_factory,
    evalscope_boundary,
    monkeypatch,
    tmp_path,
    kind,
):
    safety = {"max_requests": 0} if kind == "request_budget_exceeded" else {}
    if kind == "token_budget_exceeded":
        safety["max_output_tokens"] = 3
    if kind == "cancelled":
        (tmp_path / "STOP").touch()
    if kind == "deadline_exceeded":
        monkeypatch.setenv("PERFWORKBENCH_DEADLINE", "0")
    harness = plugin_factory(safety=safety)
    session = MemorySession()
    result = asyncio.run(dispatch(harness, session, harness.rows[0], evalscope_boundary))
    record = read_jsonl(tmp_path / "records.jsonl")[0]
    assert result.success is False
    assert result.error == record["error_kind"] == kind
    assert record["status"] == "client_rejected"
    assert record["phase"] == "warmup"
    assert record["request_id"] == harness.rows[0]["request_id"]
    assert record["http_status"] is None
    assert record["input_tokens"] is None and record["output_tokens"] is None
    assert record["e2e_ms"] is None and record["ttft_ms"] is None
    assert record["start_s"] == record["end_s"]
    assert session.sent == []
    assert not (tmp_path / "starts.jsonl").exists()


def test_failed_http_request_still_spends_reserved_tokens(plugin_factory, evalscope_boundary):
    harness = plugin_factory(safety={"max_output_tokens": 4})
    session = MemorySession(json_response({"error": "upstream failed"}, status=503))

    async def scenario():
        first = await dispatch(harness, session, harness.rows[0], evalscope_boundary)
        second = await dispatch(harness, session, harness.rows[1], evalscope_boundary)
        assert not first.success
        assert second.error == "token_budget_exceeded"

    asyncio.run(scenario())
    assert len(session.sent) == 1
    records = read_jsonl(harness.directory / "records.jsonl")
    assert [r["status"] for r in records] == ["failed", "client_rejected"]


def test_saturated_admission_is_immediate_and_capacity_returns_after_completion(
    plugin_factory, evalscope_boundary
):
    harness = plugin_factory(safety={"max_concurrency": 1})

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        class HeldResponse(MemoryResponse):
            async def __aenter__(self):
                entered.set()
                await release.wait()
                return self

        held = HeldResponse([json.dumps(completion()).encode()])
        session = MemorySession(held, json_response())
        active = asyncio.create_task(dispatch(harness, session, harness.rows[0], evalscope_boundary))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            rejected = await asyncio.wait_for(
                dispatch(harness, session, harness.rows[1], evalscope_boundary), 1
            )
            assert rejected.error == "client_rejected"
            assert len(session.sent) == 1
        finally:
            release.set()
            await active
        assert (await dispatch(harness, session, harness.rows[2], evalscope_boundary)).success
        assert len(session.sent) == 2

    asyncio.run(scenario())
    records = read_jsonl(harness.directory / "records.jsonl")
    assert [r["status"] for r in records] == ["client_rejected", "success", "success"]
    assert len(read_jsonl(harness.directory / "starts.jsonl")) == 2


@pytest.mark.parametrize("kind", ["malformed_json", "empty_choices", "oversize", "sse_without_finish"])
def test_real_upstream_parser_failures_produce_terminal_worker_records(
    plugin_factory,
    evalscope_boundary,
    kind,
):
    harness = plugin_factory(safety={"max_response_bytes": 180})
    if kind == "malformed_json":
        raw = MemoryResponse([b"{invalid"])
    elif kind == "empty_choices":
        raw = json_response({"choices": [], "usage": {"prompt_tokens": 8, "completion_tokens": 0}})
    elif kind == "oversize":
        raw = MemoryResponse([b"x" * 181])
    else:
        event = completion(stream=True, finish=None)
        raw = MemoryResponse(
            [b"data: " + json.dumps(event).encode() + b"\n\ndata: [DONE]\n\n"],
            content_type="text/event-stream",
        )
    result = asyncio.run(dispatch(harness, MemorySession(raw), harness.rows[0], evalscope_boundary))
    record = read_jsonl(harness.directory / "records.jsonl")[0]
    assert record["success"] is result.success is False
    assert result.error == record["error_kind"]
    assert record["e2e_ms"] >= 0
    assert result.query_latency >= 0
    assert raw.closed


def test_adapter_replaces_stale_upstream_completion_time(plugin_factory, evalscope_boundary, monkeypatch):
    harness = plugin_factory()

    async def upstream_boundary(self, session, url, headers, body):
        return evalscope_boundary.BenchmarkData(
            success=True, response_messages=[completion()], completed_time=-1, query_latency=-1
        )

    monkeypatch.setattr(evalscope_boundary.OpenaiPlugin, "process_request", upstream_boundary)
    result = asyncio.run(dispatch(harness, None, harness.rows[0], evalscope_boundary))
    record = read_jsonl(harness.directory / "records.jsonl")[0]
    assert result.success
    assert result.completed_time > 0
    assert result.query_latency == pytest.approx(record["e2e_ms"] / 1000)
    assert record["end_s"] >= record["start_s"]


def prepare_run(directory, mode="concurrency", timeout_s=1.2):
    from perfworkbench.config import ExperimentSpec
    from perfworkbench.dataset import materialize_requests

    spec = ExperimentSpec.model_validate(
        {
            "name": "worker-unit-boundary",
            "endpoint": {
                "base_url": "http://fixture.invalid/v1/chat/completions",
                "model": "protocol-fixture",
            },
            "dataset": [{"id": "one", "messages": [{"role": "user", "content": "中文"}], "max_tokens": 4}],
            "load": {"count": 2, "warmup": 1, "mode": mode, "concurrency": 2, "rate": 7},
            "generation": {"stream": False, "max_tokens": 8},
            "safety": {"request_timeout_s": timeout_s},
            "protocol_fixture": True,
        }
    ).model_dump(mode="json")
    rows = materialize_requests(spec)
    write_json(directory / "run.json", {"spec": spec})
    for row in rows:
        append_jsonl(directory / "requests.jsonl", row)
    return spec, rows


@pytest.mark.parametrize("mode", ["concurrency", "rate"])
@pytest.mark.parametrize("timeout_s", [0.05, 1.2])
def test_worker_builds_safe_engine_arguments_and_persists_actual_adapter_results(
    tmp_path,
    monkeypatch,
    evalscope_boundary,
    mode,
    timeout_s,
):
    import evalscope.perf.main as engine

    spec, rows = prepare_run(tmp_path, mode, timeout_s)
    captured = []

    def benchmark_boundary(args):
        captured.append(copy.deepcopy(args))
        assert (tmp_path / "worker-started.json").is_file()
        assert not (tmp_path / "worker-finished.json").exists()
        inputs = read_jsonl(Path(args["dataset_path"]))
        plugin = evalscope_boundary.ApiRegistry.get_class(args["api"])(evalscope_boundary.Arguments(**args))
        session = MemorySession(*(json_response() for _ in inputs))

        async def scenario():
            for row in inputs:
                body = plugin.build_request(row)
                headers = body.pop(evalscope_boundary.header_key)
                body.pop(evalscope_boundary.id_key)
                result = await plugin.process_request(session, args["url"], headers, body)
                assert result.success

        asyncio.run(scenario())

    monkeypatch.setattr(engine, "run_perf_benchmark", benchmark_boundary)
    worker.run_worker(tmp_path)
    assert len(captured) == 1
    args = captured[0]
    assert args["url"] == "http://fixture.invalid/v1/chat/completions"
    assert args["no_test_connection"] is True and args["debug"] is False
    assert args["number"] == 2 and args["warmup_num"] == 1
    assert args["open_loop"] is (mode == "rate")
    assert args["parallel"] == (2 if mode == "concurrency" else 0)
    assert args["rate"] == (-1 if mode == "concurrency" else 7)
    # EvalScope's arguments may round up for compatibility; the adapter's outer
    # timeout must enforce the exact configured limit (tested with a stalled I/O).
    assert all(args[key] >= timeout_s for key in ("connect_timeout", "read_timeout", "total_timeout"))
    inputs = read_jsonl(tmp_path / "evalscope-input.jsonl")
    assert [row["_workbench_request_id"] for row in inputs] == [row["request_id"] for row in rows]
    assert all(row["max_tokens"] == 4 for row in inputs)
    records = read_jsonl(tmp_path / "records.jsonl")
    assert [row["phase"] for row in records] == ["warmup", "measure", "measure"]
    assert all(row["success"] for row in records)
    assert json.loads((tmp_path / "worker-finished.json").read_text())["records"] == 3
    assert json.loads((tmp_path / "run.json").read_text())["spec"] == spec


@pytest.mark.parametrize("failure", ["wrong_version", "missing_package", "benchmark_exception"])
def test_worker_entrypoint_records_package_and_engine_failures_without_private_details(
    tmp_path,
    monkeypatch,
    evalscope_boundary,
    failure,
    capsys,
):
    import evalscope.perf.main as engine

    prepare_run(tmp_path)
    private = "private-package-detail-https://user:secret@provider.invalid"
    if failure == "benchmark_exception":

        def broken_benchmark(args):
            raise RuntimeError(private)

        monkeypatch.setattr(engine, "run_perf_benchmark", broken_benchmark)
    else:
        real_version = importlib.metadata.version

        def version(name):
            if name != "evalscope":
                return real_version(name)
            if failure == "missing_package":
                raise importlib.metadata.PackageNotFoundError(private)
            return "0.0.0"

        monkeypatch.setattr(importlib.metadata, "version", version)
    monkeypatch.setattr(sys, "argv", [str(Path(worker.__file__)), str(tmp_path)])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)
        with pytest.raises(SystemExit) as stopped:
            runpy.run_module("perfworkbench.evalscope_worker", run_name="__main__")
    assert stopped.value.code == 1
    error = json.loads((tmp_path / "worker-error.json").read_text())
    assert error["kind"] == ("PackageNotFoundError" if failure == "missing_package" else "RuntimeError")
    assert error["message"] and private not in json.dumps(error)
    assert not (tmp_path / "worker-finished.json").exists()
    assert read_jsonl(tmp_path / "records.jsonl") == []
    captured = capsys.readouterr()
    assert private not in captured.out + captured.err


@pytest.mark.parametrize(
    "base",
    [
        "http://fixture.invalid/v1",
        "http://fixture.invalid/v1/",
        "http://fixture.invalid/v1/chat/completions/",
    ],
)
def test_endpoint_url_does_not_duplicate_chat_suffix(base):
    assert worker.endpoint_url(base, "models") == "http://fixture.invalid/v1/models"
    assert worker.endpoint_url(base, "chat/completions") == "http://fixture.invalid/v1/chat/completions"


def test_scrub_preserves_nonstrings_and_recurses_without_mutating_source():
    source = {
        "nested": ["prefix needle suffix", {"text": "needle", "tokens": 3}],
        "unknown": None,
        "ok": True,
    }
    original = copy.deepcopy(source)
    redacted = worker._scrub(source, "needle")
    assert redacted == {
        "nested": ["prefix [REDACTED] suffix", {"text": "[REDACTED]", "tokens": 3}],
        "unknown": None,
        "ok": True,
    }
    assert source == original


def test_scrub_redacts_nested_dictionary_keys_as_well_as_values():
    source = {"prefix secret-key": [{"nested-secret-key": "secret-key"}], "count": 3}
    original = copy.deepcopy(source)
    redacted = worker._scrub(source, "secret-key")
    assert redacted == {"prefix [REDACTED]": [{"nested-[REDACTED]": "[REDACTED]"}], "count": 3}
    assert "secret-key" not in json.dumps(redacted)
    assert source == original


@pytest.mark.parametrize("timeout_s", [0.03, 0.12])
def test_fractional_deadline_ends_stalled_io_records_failure_and_preserves_budget(
    plugin_factory,
    evalscope_boundary,
    timeout_s,
):
    harness = plugin_factory(
        safety={"request_timeout_s": timeout_s, "max_concurrency": 1, "max_output_tokens": 8}
    )

    async def scenario():
        entered = asyncio.Event()

        class StalledResponse(MemoryResponse):
            async def __aenter__(self):
                entered.set()
                await asyncio.Event().wait()
                return self

        session = MemorySession(StalledResponse([]), json_response())
        before = time.monotonic()
        result = await asyncio.wait_for(dispatch(harness, session, harness.rows[0], evalscope_boundary), 0.6)
        elapsed = time.monotonic() - before
        assert entered.is_set()
        assert timeout_s * 0.8 <= elapsed < 0.5
        assert result.success is False and result.error
        # Timeout releases concurrency, while spent token reservations survive.
        assert (await dispatch(harness, session, harness.rows[1], evalscope_boundary)).success
        rejected = await dispatch(harness, session, harness.rows[2], evalscope_boundary)
        assert rejected.error == "token_budget_exceeded"
        assert len(session.sent) == 2

    asyncio.run(scenario())
    records = read_jsonl(harness.directory / "records.jsonl")
    assert [row["status"] for row in records] == ["failed", "success", "client_rejected"]
    assert timeout_s * 800 <= records[0]["e2e_ms"] < 500
    assert records[0]["output_tokens"] is None
    assert len(read_jsonl(harness.directory / "starts.jsonl")) == 2


class ProbeSession(MemorySession):
    def __init__(self, model_response, *responses):
        super().__init__(*responses)
        self.model_response = model_response
        self.got = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def get(self, url, **kwargs):
        self.got.append({"url": url, **kwargs})
        return self.model_response


def streaming_response():
    event = completion(stream=True)
    usage = {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}}
    return MemoryResponse(
        [
            b"data: " + json.dumps(event).encode() + b"\n\n",
            b"data: " + json.dumps(usage).encode() + b"\n\ndata: [DONE]\n\n",
        ],
        content_type="text/event-stream",
    )


@pytest.mark.parametrize(
    "models",
    [
        {"data": [{"id": "protocol-fixture", "max_model_len": 4096}]},
        {"data": []},
    ],
)
def test_probe_uses_two_bounded_generations_and_reports_context_provenance(
    monkeypatch,
    evalscope_boundary,
    models,
):
    import aiohttp

    session = ProbeSession(json_response(models), json_response(), streaming_response())
    options = []

    def session_boundary(**kwargs):
        options.append(kwargs)
        return session

    monkeypatch.setattr(aiohttp, "ClientSession", session_boundary)
    monkeypatch.setenv("WORKER_EDGE_PROBE_KEY", "probe-secret")
    result = asyncio.run(
        worker.probe_endpoint(
            {
                "base_url": "http://fixture.invalid/v1",
                "model": "protocol-fixture",
                "api_key_env": "WORKER_EDGE_PROBE_KEY",
                "context_length": 2048,
            }
        )
    )
    assert result["ready"] is True
    assert result["model_list_status"] == "available"
    expected_context = 4096 if models["data"] else 2048
    assert result["context_length"] == expected_context
    assert result["context_source"] == ("models_endpoint" if models["data"] else "user_declared")
    assert [row["requested_stream"] for row in result["checks"]] == [False, True]
    assert all("output_text" not in row for row in result["checks"])
    assert options[0]["trust_env"] is False
    assert options[0]["timeout"].total == 10
    assert len(session.got) == 1 and session.got[0]["allow_redirects"] is False
    bodies = [json.loads(request["data"]) for request in session.sent]
    assert len(bodies) == 2 and all(body["max_tokens"] == 8 for body in bodies)
    assert bodies[1]["stream_options"] == {"include_usage": True}
    assert all(request["headers"]["Authorization"] == "Bearer probe-secret" for request in session.sent)
    assert "probe-secret" not in json.dumps(result)


@pytest.mark.parametrize("model_response", ["malformed_json", "http_401", "wrong_shape"])
def test_probe_model_list_failure_keeps_generation_evidence_and_unknown_context(
    monkeypatch,
    evalscope_boundary,
    model_response,
):
    import aiohttp

    raw = (
        MemoryResponse([b"invalid-json"])
        if model_response == "malformed_json"
        else (
            json_response({"error": "private-model-list-error"}, status=401)
            if model_response == "http_401"
            else json_response({"data": None})
        )
    )
    session = ProbeSession(raw, json_response(), streaming_response())
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: session)
    result = asyncio.run(
        worker.probe_endpoint({"base_url": "http://fixture.invalid/v1", "model": "protocol-fixture"})
    )
    assert result["model_list_status"] == "unavailable"
    assert result["context_length"] is None
    assert result["context_source"] == "unknown"
    assert len(result["checks"]) == 2
    assert "private-model-list-error" not in json.dumps(result)


def test_probe_with_missing_key_does_not_open_a_session(monkeypatch, evalscope_boundary):
    import aiohttp

    monkeypatch.delenv("WORKER_EDGE_ABSENT_PROBE_KEY", raising=False)

    def forbidden_session(**kwargs):
        pytest.fail("preflight must reject missing credentials before opening a session")

    monkeypatch.setattr(aiohttp, "ClientSession", forbidden_session)
    with pytest.raises(ValueError, match="environment variable is missing"):
        asyncio.run(
            worker.probe_endpoint(
                {
                    "base_url": "http://fixture.invalid/v1",
                    "model": "m",
                    "api_key_env": "WORKER_EDGE_ABSENT_PROBE_KEY",
                }
            )
        )


@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"prompt_tokens": 12, "completion_tokens": "3"},
        {"prompt_tokens": 12, "completion_tokens": True},
        {"prompt_tokens": 12, "completion_tokens": -1},
        {"prompt_tokens": 12, "completion_tokens": 3.5},
        {"prompt_tokens": 12, "completion_tokens": float("inf")},
    ],
    ids=["missing", "string", "boolean", "negative", "fractional", "infinite"],
)
def test_unknown_usage_cannot_crash_or_pollute_evalscope_accumulation(
    plugin_factory,
    evalscope_boundary,
    usage,
):
    from evalscope.perf.utils.benchmark_util import MetricsAccumulator

    harness = plugin_factory()
    session = MemorySession(json_response(completion(usage=usage)))
    result = asyncio.run(dispatch(harness, session, harness.rows[1], evalscope_boundary))
    record = read_jsonl(harness.directory / "records.jsonl")[0]
    assert record["output_tokens"] is None
    assert record["tpot_ms"] is None
    # This is the real downstream operation performed by EvalScope after the
    # adapter returns. A safe canonical record alone does not protect this call.
    metrics = MetricsAccumulator()
    metrics.update(result, harness.plugin)
    assert metrics.n_total == 1
    assert metrics.total_completion_tokens == 0, "invalid/unknown usage must not enter upstream totals"
    assert read_jsonl(harness.directory / "records.jsonl")[0]["output_tokens"] is None


@pytest.fixture
def worker_http_endpoint():
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            observed.append(self.path)
            self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/redirect":
                self.send_response(307)
                self.send_header("Location", "/redirect-target")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path == "/oversize":
                payload = json.dumps(completion(text="x" * 4096)).encode()
            elif self.path == "/bad-json":
                payload = b'{"broken":'
            else:
                payload = json.dumps(
                    completion(text="中文结果", usage={"prompt_tokens": 12, "completion_tokens": 3}),
                    ensure_ascii=False,
                ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                for start in range(0, len(payload), 7):
                    self.wfile.write(payload[start : start + 7])
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", observed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.integration
@pytest.mark.parametrize(
    "path,success", [("/oversize", False), ("/bad-json", False), ("/redirect", False), ("/utf8", True)]
)
def test_worker_adapter_over_real_http_preserves_limits_and_completion(
    plugin_factory,
    evalscope_boundary,
    worker_http_endpoint,
    path,
    success,
):
    import aiohttp

    harness = plugin_factory(safety={"max_response_bytes": 512})
    base, observed = worker_http_endpoint
    row = harness.rows[1]
    body = harness.plugin.build_request({**row["body"], "_workbench_request_id": row["request_id"]})
    headers = body.pop(evalscope_boundary.header_key)
    body.pop(evalscope_boundary.id_key)

    async def scenario():
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2), trust_env=False) as session:
            return await harness.plugin.process_request(session, base + path, headers, body)

    result = asyncio.run(scenario())
    record = read_jsonl(harness.directory / "records.jsonl")[0]
    assert result.success is record["success"] is success
    assert observed == [path]
    assert record["request_id"] == row["request_id"] and record["phase"] == "measure"
    if success:
        assert record["output_text"] == "中文结果"
        assert record["output_tokens"] == 3
    else:
        assert record["status"] == "failed"
        assert record["error_kind"] and result.error == record["error_kind"]
    if path == "/redirect":
        assert record["http_status"] == 307
