"""Loopback-only HTTP boundary for the local experiment workbench."""

import json
import math
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

MAX_BODY_BYTES = 2 * 1024 * 1024
STATIC = Path(__file__).with_name("static")
SAFE_ID = re.compile(r"^[a-f0-9]{32}$")
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'self'; object-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
}


def _create_manager(root):
    # Keep worker/backend imports out of static asset import and module discovery.
    from .runner import ExperimentManager

    return ExperimentManager(root)


def _authority(value, scheme):
    parts = urlsplit(f"{scheme}://{value}")
    if parts.username or parts.password or parts.path or parts.query or parts.fragment:
        raise ValueError("invalid authority")
    if parts.hostname not in {"localhost", "127.0.0.1", "testserver"}:
        raise ValueError("non-local host")
    return parts.hostname, parts.port or (443 if scheme == "https" else 80)


class LocalBoundary:
    """Check authority and bound the actual body, including chunked requests."""

    def __init__(self, app):
        self.app = app

    async def _dispatch(self, scope, receive, send):
        started = False

        async def track_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track_send)
        except Exception:  # noqa: BLE001 - the HTTP boundary must not log sensitive exception values.
            # Do not let the server log an exception that could contain a secret.
            if not started:
                await PlainTextResponse(
                    "本地服务暂时无法完成操作，请检查服务状态后重试。错误原文未回显。", 500
                )(scope, receive, send)
            else:
                raise RuntimeError("Local response delivery failed") from None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secure_send(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    (key.lower().encode(), value.encode())
                    for key, value in SECURITY_HEADERS.items()
                    if key.lower().encode() not in existing
                ]
            await send(message)

        async def reject(status, text):
            await PlainTextResponse(text, status_code=status)(scope, receive, secure_send)

        headers = {}
        for key, value in scope["headers"]:
            name = key.decode("latin1").lower()
            if name in headers and name in {"host", "origin", "content-length", "x-workbench-action"}:
                return await reject(400, "请求头重复，请重新发送。")
            headers[name] = value.decode("latin1")
        scheme = scope.get("scheme", "http")
        try:
            authority = _authority(headers.get("host", ""), scheme)
        except ValueError:
            return await reject(400, "仅允许 localhost 或 127.0.0.1 本地访问。")
        if "origin" in headers:
            try:
                origin = urlsplit(headers["origin"])
                if (
                    origin.scheme != scheme
                    or origin.path
                    or origin.query
                    or origin.fragment
                    or _authority(origin.netloc, origin.scheme) != authority
                ):
                    raise ValueError("foreign origin")
            except ValueError:
                return await reject(403, "拒绝跨来源请求，请从本地工作台操作。")
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            if headers.get("x-workbench-action") != "local":
                return await reject(403, "操作需要 X-Workbench-Action: local。")
            try:
                length = int(headers.get("content-length", "0"))
                if length < 0:
                    raise ValueError("negative length")
            except ValueError:
                return await reject(400, "Content-Length 无效。")
            if length > MAX_BODY_BYTES:
                return await reject(413, "请求超过 2 MiB 上限，请缩小数据集或配置。")
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_BODY_BYTES:
                    return await reject(413, "请求超过 2 MiB 上限，请缩小数据集或配置。")
                if not message.get("more_body", False):
                    break
            consumed = False

            async def bounded_receive():
                nonlocal consumed
                if consumed:
                    return await receive()
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            return await self._dispatch(scope, bounded_receive, secure_send)
        return await self._dispatch(scope, receive, secure_send)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("non-finite number")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("overflow number")
    return result


async def _payload(request):
    try:
        data = json.loads(
            await request.body(),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
            parse_float=_finite_float,
        )
    except json.JSONDecodeError as exc:
        raise HTTPException(
            422, f"JSON 解析失败：第 {exc.lineno} 行，第 {exc.colno} 列；检查引号、逗号与括号。"
        ) from None
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, "JSON 无效：请使用 UTF-8，禁止重复键、非有限数值与过深嵌套。") from None
    if not isinstance(data, dict):
        raise HTTPException(422, "JSON 顶层必须是对象，请检查 {}。")
    return data


def _id(value):
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise HTTPException(422, "实验 ID 必须是本机生成的十六进制标识，不接受文件路径。")
    return value


def _fields(data, allowed, required=()):
    if set(data) - set(allowed) or set(required) - set(data):
        raise HTTPException(422, "字段不符合接口契约，请检查必填字段与多余字段。")


def create_app(root) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.manager = await run_in_threadpool(_create_manager, root)
        try:
            yield
        finally:
            await run_in_threadpool(app.state.manager.close)

    app = FastAPI(
        title="LLM 推理性能工作台", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(LocalBoundary)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code, headers=SECURITY_HEADERS)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        issues = []
        for error in exc.errors()[:12]:
            # Never include Pydantic's input/context: these can contain credentials or prompts.
            location = ".".join(str(part) for part in error["loc"])[:160] or "experiment"
            issues.append(f"{location}: {error['msg']}")
        return PlainTextResponse("配置校验失败：\n" + "\n".join(issues), 422, headers=SECURITY_HEADERS)

    @app.exception_handler(FileNotFoundError)
    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return PlainTextResponse("未找到该实验或请求记录，请刷新列表。", 404, headers=SECURITY_HEADERS)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        if str(exc) in {
            "Another experiment plan is active; finish or cancel it first",
            "Another process owns this experiment workspace",
        }:
            return PlainTextResponse(
                "已有实验计划运行，请等待完成或停止后重试。", 409, headers=SECURITY_HEADERS
            )
        if str(exc) == "No active/local plan with this id":
            return PlainTextResponse(
                "未找到可取消的本地实验计划，请刷新列表。", 404, headers=SECURITY_HEADERS
            )
        return PlainTextResponse(
            "输入校验失败，请检查数据集 ID、标签、指标与本地 tokenizer 配置。", 422, headers=SECURITY_HEADERS
        )

    @app.exception_handler(RuntimeError)
    async def conflict(request, exc):
        return PlainTextResponse(
            "当前操作不可执行：可能已有实验计划运行，请刷新状态后重试。", 409, headers=SECURITY_HEADERS
        )

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return PlainTextResponse(
            "本地服务暂时无法完成操作，请检查服务状态后重试。错误原文未回显。", 500, headers=SECURITY_HEADERS
        )

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/static/{name}")
    def asset(name: str):
        if name not in {"app.js", "style.css"}:
            raise HTTPException(404, "资源不存在。")
        return FileResponse(
            STATIC / name, media_type="text/javascript" if name.endswith(".js") else "text/css"
        )

    @app.get("/api/example")
    def example():
        from .config import ExperimentSpec

        return ExperimentSpec.model_validate(
            {
                "name": "baseline",
                "endpoint": {"base_url": "http://127.0.0.1:8000/v1", "model": "my-model"},
                "dataset": [
                    {"id": "sample-1", "messages": [{"role": "user", "content": "请简要介绍你的能力。"}]}
                ],
            }
        ).model_dump(mode="json")

    @app.get("/api/runs")
    def runs(request: Request):
        return request.app.state.manager.store.list()

    @app.get("/api/runs/{run_id}")
    def detail(run_id: str, request: Request):
        return request.app.state.manager.store.get(_id(run_id))

    @app.get("/api/plans/{plan_id}/summary")
    def plan_summary(plan_id: str, request: Request):
        from .sweep import summarize_sweep

        identifier = _id(plan_id)
        store = request.app.state.manager.store
        children = [store.get(row["id"]) for row in store.list() if row.get("parent_id") == identifier]
        if not children:
            raise HTTPException(404, "未找到此计划的实验记录，请刷新列表。")
        # The store uses null until analysis lands; the reducer consumes dict summaries.
        snapshots = [{**run, "summary": run.get("summary") or {}} for run in children]
        return summarize_sweep(snapshots)

    @app.post("/api/runs", status_code=202)
    async def submit(request: Request):
        from .config import ExperimentSpec

        spec = ExperimentSpec.model_validate(await _payload(request)).model_dump(mode="json")
        return await run_in_threadpool(request.app.state.manager.submit, spec)

    @app.post("/api/preflight")
    async def preflight(request: Request):
        from .config import Endpoint

        endpoint = Endpoint.model_validate(await _payload(request)).model_dump(mode="json")
        return await run_in_threadpool(request.app.state.manager.preflight, endpoint)

    @app.post("/api/profile")
    async def profile(request: Request):
        from .config import Sample
        from .dataset import profile_dataset

        data = await _payload(request)
        _fields(data, {"dataset", "tokenizer_path"}, {"dataset"})
        rows = TypeAdapter(list[Sample]).validate_python(data["dataset"])
        if not 1 <= len(rows) <= 10000 or len({row.id for row in rows}) != len(rows):
            raise HTTPException(422, "数据集需要 1—10000 条样本，且每条 id 唯一。")
        tokenizer_path = data.get("tokenizer_path")
        if tokenizer_path is not None and (not isinstance(tokenizer_path, str) or len(tokenizer_path) > 4096):
            raise HTTPException(422, "tokenizer_path 必须是本地目录字符串或 null。")
        return await run_in_threadpool(
            profile_dataset, [row.model_dump(mode="json") for row in rows], tokenizer_path
        )

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str, request: Request):
        return await run_in_threadpool(request.app.state.manager.cancel, _id(run_id))

    @app.post("/api/runs/{run_id}/labels")
    async def labels(run_id: str, request: Request):
        from .runner import refresh_analysis

        labels = await _payload(request)
        if (
            not labels
            or len(labels) > 10000
            or any(
                not key or len(key) > 128 or value not in ("pass", "fail", "unknown")
                for key, value in labels.items()
            )
        ):
            raise HTTPException(422, "标签必须为 {request_id: pass|fail|unknown}，且非空。")
        store = request.app.state.manager.store
        run = await run_in_threadpool(store.get, _id(run_id))
        if run["status"] not in {"completed", "failed", "cancelled", "interrupted", "timed_out"}:
            raise HTTPException(409, "实验结束后才能导入质量标签。")
        if set(labels) - {row["request_id"] for row in run.get("records", [])}:
            raise HTTPException(422, "标签包含不属于本次实验的 request_id。")
        await run_in_threadpool(store.label, run_id, labels)
        return await run_in_threadpool(refresh_analysis, store, run_id)

    @app.post("/api/compare")
    async def compare(request: Request):
        from .analysis import compare_runs

        data = await _payload(request)
        _fields(data, {"ids"}, {"ids"})
        ids = data["ids"]
        if not isinstance(ids, list) or not 2 <= len(ids) <= 32:
            raise HTTPException(422, "请选择 2—32 个不同的实验。")
        ids = [_id(value) for value in ids]
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "不能重复选择同一实验。")
        store = request.app.state.manager.store
        selected = [await run_in_threadpool(store.get, value) for value in ids]
        return await run_in_threadpool(compare_runs, selected)

    @app.post("/api/retest")
    async def retest(request: Request):
        from .analysis import evaluate_retest

        data = await _payload(request)
        _fields(
            data, {"baseline_id", "candidate_id", "criterion"}, {"baseline_id", "candidate_id", "criterion"}
        )
        baseline_id, candidate_id = _id(data["baseline_id"]), _id(data["candidate_id"])
        criterion = data["criterion"]
        if baseline_id == candidate_id or not isinstance(criterion, dict):
            raise HTTPException(422, "请选择不同的基线与复测实验，并提供判定标准。")
        _fields(criterion, {"metric", "direction", "min_relative_change", "change"}, {"metric", "direction"})
        if "change" in criterion:
            declaration = criterion["change"]
            if not isinstance(declaration, dict):
                raise HTTPException(422, "单变量变更必须是 {field, before, after} 对象。")
            _fields(declaration, {"field", "before", "after"}, {"field", "before", "after"})
            if declaration["field"] not in ("load.concurrency", "load.rate"):
                raise HTTPException(422, "仅允许声明 load.concurrency 或 load.rate 的单一变更。")
            for value in (declaration["before"], declaration["after"]):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value <= 0
                    or (declaration["field"] == "load.concurrency" and not float(value).is_integer())
                ):
                    raise HTTPException(422, "变更前后值必须为正数；并发数必须为整数。")
        change = criterion.get("min_relative_change", 0)
        allowed_metrics = {
            "requests_per_s",
            "goodput_per_s",
            "input_tokens_per_s",
            "output_tokens_per_s",
            "error_rate",
        }
        allowed_metrics.update(
            f"{metric}.{percentile}"
            for metric in ("e2e_ms", "ttft_ms", "tpot_ms", "inter_chunk_ms")
            for percentile in ("mean", "p50", "p95", "p99")
        )
        if (
            not isinstance(criterion["metric"], str)
            or criterion["metric"] not in allowed_metrics
            or criterion["direction"] not in ("increase", "decrease")
            or isinstance(change, bool)
            or not isinstance(change, (int, float))
            or not math.isfinite(change)
            or change < 0
        ):
            raise HTTPException(422, "复测指标、方向或最小相对变化无效；相对变化用非负比例。")
        store = request.app.state.manager.store
        baseline = await run_in_threadpool(store.get, baseline_id)
        candidate = await run_in_threadpool(store.get, candidate_id)
        result = await run_in_threadpool(evaluate_retest, baseline, candidate, criterion)
        association = {
            **result,
            "baseline_id": baseline_id,
            "candidate_id": candidate_id,
            "criterion": criterion,
        }
        await run_in_threadpool(store.update, candidate_id, retest=association)
        return association

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str, request: Request, format: str = "markdown"):
        from .report import export_report

        if format not in {"markdown", "json", "html"}:
            raise HTTPException(422, "报告格式只能是 markdown、json 或 html。")
        run = request.app.state.manager.store.get(_id(run_id))
        extension, mime = {
            "markdown": ("md", "text/markdown"),
            "json": ("json", "application/json"),
            "html": ("html", "text/html"),
        }[format]
        headers = {
            "Content-Disposition": f'attachment; filename="experiment-{run_id}.{extension}"',
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        }
        return Response(export_report(run, fmt=format), media_type=mime, headers=headers)

    return app
