"""EvalScope extension and guarded worker. No pickle deserialization."""

import asyncio
import json
import logging
import math
import os
import signal
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from .store import append_jsonl, read_jsonl, write_json


def _token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def normalize_output(output, meta, *, start, end, origin, started_at):
    stream = bool(output.is_stream)
    parts, finish, has_choices, malformed = [], None, False, False
    for response in output.response_messages:
        if not isinstance(response, dict):
            continue
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            continue
        first = choices[0]
        content = first.get("delta" if stream else "message")
        if (
            not isinstance(content, dict)
            or (content.get("content") is not None and not isinstance(content["content"], str))
            or (not stream and not {"content", "tool_calls", "function_call", "refusal"} & content.keys())
        ):
            malformed = True
            continue
        has_choices = True
        if isinstance(content.get("content"), str):
            parts.append(content["content"])
        if isinstance(first.get("finish_reason"), str) and first["finish_reason"] in {
            "stop",
            "length",
            "content_filter",
            "tool_calls",
            "function_call",
        }:
            finish = first["finish_reason"]
    success = bool(output.success) and has_choices and not malformed and finish is not None
    error_kind = None
    if not output.success:
        error_kind = "http_error" if output.status_code else "transport_error"
    elif not has_choices or malformed:
        error_kind = "protocol_error"
    elif finish is None:
        error_kind = "incomplete_response"
    elapsed = max(0.0, (end - start) * 1000)
    first_latency = output.first_chunk_latency
    ttft = (
        first_latency * 1000
        if stream
        and success
        and isinstance(first_latency, (float, int))
        and 0 < first_latency <= elapsed / 1000
        else None
    )
    tokens = _token_count(output.completion_tokens)
    tpot = (
        max(0, elapsed - ttft) / (tokens - 1)
        if ttft is not None and tokens is not None and tokens > 1
        else None
    )
    return {
        **meta,
        "started_at": started_at,
        "start_s": start - origin,
        "end_s": end - origin,
        "status": "success" if success else "failed",
        "success": success,
        "http_status": (output.status_code or 200) if output.success else output.status_code,
        "error_kind": error_kind,
        "is_stream": stream,
        "input_tokens": _token_count(output.prompt_tokens),
        "output_tokens": tokens,
        "e2e_ms": elapsed,
        "ttft_ms": ttft,
        "tpot_ms": tpot,
        "inter_chunk_ms": [t * 1000 for t in output.inter_chunk_latency if math.isfinite(t) and t >= 0]
        if stream and success
        else [],
        "output_text": "".join(parts),
        "finish_reason": finish,
        "manual_label": None,
    }


class AdmissionBudget:
    """Call reserve/release on one event loop without awaiting between checks."""

    def __init__(self, max_requests, max_tokens, max_active):
        self.max_requests, self.max_tokens, self.max_active = max_requests, max_tokens, max_active
        self.requests = self.tokens = self.active = 0

    def reserve(self, tokens):
        if self.active >= self.max_active:
            return "client_rejected"
        if self.requests >= self.max_requests:
            return "request_budget_exceeded"
        if self.tokens + tokens > self.max_tokens:
            return "token_budget_exceeded"
        self.requests += 1
        self.tokens += tokens
        self.active += 1
        return None

    def release(self):
        self.active = max(0, self.active - 1)


class _BoundedContent:
    def __init__(self, content, limit, close=None):
        self.content, self.limit = content, limit
        self.received = 0
        self.exceeded = False
        self.close = close

    async def iter_any(self):
        if self.exceeded:
            raise ValueError("response_size_limit")
        async for chunk in self.content.iter_chunked(min(self.limit + 1, 65536)):
            self.received += len(chunk)
            if self.received > self.limit:
                self.exceeded = True
                if self.close:
                    self.close()
                raise ValueError("response_size_limit")
            yield chunk


class _BoundedResponse:
    def __init__(self, response, limit):
        self.response = response
        self.content = _BoundedContent(response.content, limit, getattr(response, "close", None))
        self._raw = None

    def __getattr__(self, name):
        return getattr(self.response, name)

    async def text(self):
        if self._raw is None:
            self._raw = b"".join([chunk async for chunk in self.content.iter_any()])
        return self._raw.decode("utf-8")

    async def json(self):
        return json.loads(await self.text())


class _BoundedContext:
    def __init__(self, context, limit):
        self.context, self.limit = context, limit

    async def __aenter__(self):
        return _BoundedResponse(await self.context.__aenter__(), self.limit)

    async def __aexit__(self, *args):
        return await self.context.__aexit__(*args)


class BoundedSession:
    """Restrict upstream HTTP redirects/body size without replacing its SSE parser."""

    def __init__(self, session, limit):
        self.session, self.limit = session, limit

    def post(self, **kwargs):
        return _BoundedContext(self.session.post(**kwargs, allow_redirects=False), self.limit)


def endpoint_url(base_url, path):
    base = base_url.rstrip("/")
    base = base.removesuffix("/chat/completions")
    return base + "/" + path


def _scrub(value, secret):
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, list):
        return [_scrub(item, secret) for item in value]
    if isinstance(value, dict):
        return {_scrub(key, secret): _scrub(item, secret) for key, item in value.items()}
    return value


@contextmanager
def redact_upstream_logs(secret):
    """Filter provider tracebacks before EvalScope's handlers persist them."""
    logger = logging.getLogger("evalscope")

    def redact(record):
        record.msg = _scrub(record.getMessage(), secret)
        record.args = ()
        if record.exc_info:
            record.exc_text = _scrub("".join(traceback.format_exception(*record.exc_info)), secret)
            record.exc_info = None
        if record.exc_text:
            record.exc_text = _scrub(record.exc_text, secret)
        if record.stack_info:
            record.stack_info = _scrub(record.stack_info, secret)
        return True

    if secret:
        logger.addFilter(redact)
    try:
        yield
    finally:
        if secret:
            logger.removeFilter(redact)


def register_workbench_plugin(directory, spec, requests):
    from evalscope.perf.plugin.api.openai_api import OpenaiPlugin
    from evalscope.perf.plugin.registry import register_api
    from evalscope.perf.utils.benchmark_util import BenchmarkData
    from evalscope.perf.utils.body_meta import BODY_META_HEADERS, BODY_META_REQUEST_ID

    origin = time.perf_counter()
    deadline = float(os.environ.get("PERFWORKBENCH_DEADLINE", "inf"))
    metadata = {
        row["request_id"]: {key: row[key] for key in ("request_id", "sample_id", "category", "phase")}
        for row in requests
    }
    safety = spec["safety"]
    budget = AdmissionBudget(safety["max_requests"], safety["max_output_tokens"], safety["max_concurrency"])
    key_name = spec["endpoint"].get("api_key_env")
    secret = os.environ.get(key_name, "") if key_name else ""
    if key_name and not secret:
        raise ValueError("Configured API key environment variable is missing")

    @register_api("workbench_openai")
    class WorkbenchPlugin(OpenaiPlugin):
        def build_request(self, messages, param=None):
            row = dict(messages)
            request_id = row.pop("_workbench_request_id")
            body = super().build_request(row, param)
            body[BODY_META_REQUEST_ID] = request_id
            body[BODY_META_HEADERS] = {"X-Workbench-Request-ID": request_id, "X-Request-ID": request_id}
            return body

        async def process_request(self, client_session, url, headers, body):
            request_id = headers.get("X-Workbench-Request-ID")
            meta = metadata[request_id]
            start, wall = time.perf_counter(), time.time()
            reason = "cancelled" if (directory / "STOP").exists() else None
            if time.monotonic() >= deadline:
                reason = "deadline_exceeded"
            reason = reason or budget.reserve(body["max_tokens"])
            if reason:
                record = {
                    **meta,
                    "started_at": wall,
                    "start_s": start - origin,
                    "end_s": start - origin,
                    "status": "client_rejected",
                    "success": False,
                    "error_kind": reason,
                    "is_stream": body.get("stream", False),
                    "input_tokens": None,
                    "output_tokens": None,
                    "ttft_ms": None,
                    "tpot_ms": None,
                    "e2e_ms": None,
                    "inter_chunk_ms": [],
                    "output_text": "",
                    "finish_reason": None,
                    "http_status": None,
                }
                append_jsonl(directory / "records.jsonl", record)
                return BenchmarkData(success=False, error=reason, start_time=start, completed_time=start)
            append_jsonl(
                directory / "starts.jsonl",
                {**meta, "started_at": wall, "start_s": start - origin, "monotonic_start": time.monotonic()},
            )
            headers = {k: v for k, v in headers.items() if k != "X-Workbench-Request-ID"}
            if secret:
                headers["Authorization"] = "Bearer " + secret
            try:
                try:
                    async with asyncio.timeout(safety.get("request_timeout_s", 30)):
                        with redact_upstream_logs(secret):
                            output = await super().process_request(
                                BoundedSession(client_session, safety["max_response_bytes"]),
                                url,
                                headers,
                                body,
                            )
                except TimeoutError:
                    output = BenchmarkData(success=False, is_stream=body.get("stream", False))
                end = time.perf_counter()
                record = normalize_output(output, meta, start=start, end=end, origin=origin, started_at=wall)
                record = _scrub(record, secret)
                append_jsonl(directory / "records.jsonl", record)
                # Correct false-success cases before upstream aggregates/serializes its own diagnostics.
                output.success = record["success"]
                output.completed_time = end
                output.query_latency = end - start
                output.error = record["error_kind"] or ""
                output.response_messages = _scrub(output.response_messages, secret)
                output.generated_text = _scrub(output.generated_text, secret)
                # Upstream's numeric-only accumulator cannot represent unknown usage.
                # Zero-fill its PRIVATE diagnostics only, after persisting canonical nulls.
                # Workbench analysis/reports never consume upstream aggregates.
                output.prompt_tokens = record["input_tokens"] or 0
                output.completion_tokens = record["output_tokens"] or 0
                return output
            finally:
                budget.release()

    return WorkbenchPlugin


def start_parent_watchdog(parent_pid):
    """Stop this isolated worker if its controller disappears, including during imports."""
    stopped = threading.Event()

    def watch():
        while not stopped.wait(0.1):
            if os.getppid() != parent_pid:
                os.kill(os.getpid(), signal.SIGTERM)
                return

    threading.Thread(target=watch, daemon=True, name="workbench-parent-watch").start()
    return stopped


def run_worker(directory):
    import importlib.metadata

    from evalscope.perf.main import run_perf_benchmark

    from .config import ExperimentSpec

    if importlib.metadata.version("evalscope") != "1.12.0":
        raise RuntimeError("This adapter requires tested EvalScope 1.12.0")
    spec = ExperimentSpec.model_validate(json.loads((directory / "run.json").read_text())["spec"]).model_dump(
        mode="json"
    )
    requests = read_jsonl(directory / "requests.jsonl")
    register_workbench_plugin(directory, spec, requests)
    input_path = directory / "evalscope-input.jsonl"
    for row in requests:
        append_jsonl(input_path, {**row["body"], "_workbench_request_id": row["request_id"]})
    load, safety = spec["load"], spec["safety"]
    # EvalScope Arguments accepts integer seconds only. The plugin's outer
    # asyncio.timeout enforces the user's exact fractional deadline.
    timeout = max(1, math.ceil(safety["request_timeout_s"]))
    args = {
        "model": spec["endpoint"]["model"],
        "api": "workbench_openai",
        "url": endpoint_url(spec["endpoint"]["base_url"], "chat/completions"),
        "dataset": "line_by_line",
        "dataset_path": str(input_path),
        "number": load["count"],
        "warmup_num": load["warmup"],
        "parallel": load["concurrency"] if load["mode"] == "concurrency" else 0,
        "open_loop": load["mode"] == "rate",
        "rate": load["rate"] if load["mode"] == "rate" else -1,
        "outputs_dir": str(directory / "upstream"),
        "name": "evalscope",
        "no_timestamp": True,
        "no_test_connection": True,
        "stream": spec["generation"]["stream"],
        "max_tokens": spec["generation"]["max_tokens"],
        "connect_timeout": timeout,
        "read_timeout": timeout,
        "total_timeout": timeout,
        "seed": load["seed"],
        "debug": False,
    }
    write_json(
        directory / "worker-started.json",
        {"pid": os.getpid(), "evalscope": "1.12.0", "started_at": time.time()},
    )
    run_perf_benchmark(args)
    write_json(
        directory / "worker-finished.json",
        {"finished_at": time.time(), "records": len(read_jsonl(directory / "records.jsonl"))},
    )


async def probe_endpoint(endpoint):
    import aiohttp
    from evalscope.perf.arguments import Arguments
    from evalscope.perf.plugin.api.openai_api import OpenaiPlugin

    key_name = endpoint.get("api_key_env")
    secret = os.environ.get(key_name, "") if key_name else ""
    if key_name and not secret:
        raise ValueError("Configured API key environment variable is missing")
    headers = {"Authorization": "Bearer " + secret} if secret else {}
    result = {
        "ready": False,
        "model_list": [],
        "model_list_status": "unavailable",
        "checks": [],
        "context_length": endpoint.get("context_length"),
        "context_source": "user_declared" if endpoint.get("context_length") else "unknown",
        "generation_budget": {"max_requests": 2, "max_output_tokens": 16},
        "environment": endpoint.get("environment", {}),
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10), trust_env=False) as session:
        try:
            async with session.get(
                endpoint_url(endpoint["base_url"], "models"), headers=headers, allow_redirects=False
            ) as response:
                if response.status == 200:
                    data = await _BoundedResponse(response, 1024 * 1024).json()
                    rows = data.get("data") if isinstance(data, dict) else None
                    if not isinstance(rows, list):
                        raise ValueError("Invalid model list")
                    result["model_list"] = [
                        row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)
                    ]
                    result["model_list_status"] = "available"
                    for row in rows:
                        if (
                            isinstance(row, dict)
                            and row.get("id") == endpoint["model"]
                            and _token_count(row.get("max_model_len"))
                        ):
                            result["context_length"] = row["max_model_len"]
                            result["context_source"] = "models_endpoint"
        except (TimeoutError, aiohttp.ClientError, ValueError, TypeError):
            result["model_list_status"] = "unavailable"
        plugin = OpenaiPlugin(
            Arguments(model=endpoint["model"], url=endpoint_url(endpoint["base_url"], "chat/completions"))
        )
        for stream in (False, True):
            body = {
                "model": endpoint["model"],
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "stream": stream,
                "max_tokens": 8,
            }
            if stream:
                body["stream_options"] = {"include_usage": True}
            start, wall = time.perf_counter(), time.time()
            with redact_upstream_logs(secret):
                output = await plugin.process_request(
                    BoundedSession(session, 1024 * 1024),
                    endpoint_url(endpoint["base_url"], "chat/completions"),
                    headers,
                    body,
                )
            record = normalize_output(
                output, {}, start=start, end=time.perf_counter(), origin=start, started_at=wall
            )
            record.pop("output_text", None)
            result["checks"].append({"requested_stream": stream, **record})
    result["ready"] = all(row["success"] for row in result["checks"])
    return _scrub(result, secret)


if __name__ == "__main__":
    watchdog = (
        start_parent_watchdog(int(os.environ["PERFWORKBENCH_PARENT_PID"]))
        if "PERFWORKBENCH_PARENT_PID" in os.environ
        else None
    )
    try:
        run_worker(Path(sys.argv[1]).resolve())
    except Exception as exc:  # noqa: BLE001 - redact at the isolated process boundary.
        # Do not persist exception bodies: providers may echo credentials or inputs.
        write_json(
            Path(sys.argv[1]) / "worker-error.json",
            {
                "kind": type(exc).__name__,
                "message": "Worker failed; inspect local run configuration and safe process log.",
            },
        )
        raise SystemExit(1) from None
    finally:
        if watchdog:
            watchdog.set()
