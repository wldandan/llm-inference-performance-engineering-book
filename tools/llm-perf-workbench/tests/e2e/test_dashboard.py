"""Real Chrome + local HTTP API fixture. These are UI tests, not runner integration."""

import copy
import json
import mimetypes
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

STATIC = Path(__file__).resolve().parents[2] / "perfworkbench/static"
RUN_ID = "a" * 32
CANDIDATE_ID = "b" * 32
SPEC = {
    "name": "协议界面验证",
    "endpoint": {
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "fixture",
        "api_key_env": None,
        "context_length": None,
        "environment": {},
    },
    "dataset": [
        {
            "id": "s1",
            "messages": [{"role": "user", "content": "Hello"}],
            "category": "short",
            "max_tokens": None,
        }
    ],
    "load": {
        "mode": "concurrency",
        "concurrency": 1,
        "rate": 1,
        "count": 2,
        "warmup": 0,
        "repeats": 1,
        "scan": [],
        "mix": {},
        "seed": 42,
    },
    "generation": {"stream": True, "max_tokens": 8, "temperature": 0, "top_p": 1, "extra": {}},
    "goals": {
        "mode": "offline",
        "min_requests_per_s": None,
        "max_p95_e2e_ms": None,
        "max_p95_ttft_ms": None,
        "max_p95_tpot_ms": None,
        "min_quality_pass_rate": 1,
        "max_error_rate": 0,
        "deadline_s": None,
        "target_requests": None,
    },
    "quality": {
        "mode": "rules",
        "require_json": False,
        "json_fields": [],
        "required_text": [],
        "min_chars": 1,
        "reject_truncated": True,
    },
    "safety": {
        "max_requests": 1000,
        "max_concurrency": 64,
        "max_duration_s": 300,
        "request_timeout_s": 30,
        "max_output_tokens": 128000,
        "max_response_bytes": 2097152,
    },
    "telemetry": {"interval_s": 1, "sources": []},
    "cache_condition": "unknown",
    "tokenizer_path": None,
    "notes": "",
    "protocol_fixture": True,
}


def fixture_run(run_id=RUN_ID):
    return {
        "id": run_id,
        "created_at": "2026-09-21T00:00:00Z",
        "status": "completed",
        "spec": copy.deepcopy(SPEC),
        "profile": {"sample_count": 1},
        "parent_id": None,
        "error": None,
        "progress": {"completed": 2, "total": 2},
        "summary": {
            "sample_count": 2,
            "metrics": {
                "requests_per_s": 2,
                "goodput_per_s": 2,
                "error_rate": 0,
                "output_tokens_per_s": None,
                "duration_s": 1,
                "ttft_ms": {"count": 2, "p50": 10, "p95": 15, "p99": 16},
                "e2e_ms": {"count": 2, "p95": 500},
                "tpot_ms": None,
            },
            "groups": {"short": {"sent": 2, "requests_per_s": 2, "e2e_ms": {"p95": 500}}},
            "quality": {"pass": 2, "fail": 0, "unknown": 0, "coverage": 1, "pass_rate": 1},
            "goals": [{"name": "quality", "target": 1, "actual": 1, "status": "pass"}],
            "warnings": ["协议替身，不代表模型性能"],
            "definitions": {"tpot_ms": "均摊估计，不是 ITL"},
        },
        "records": [
            {
                "request_id": "r1",
                "sample_id": "s1",
                "category": "short",
                "phase": "measure",
                "status": "success",
                "success": True,
                "output_text": "LOCAL-ONLY-RESPONSE",
                "manual_label": None,
            }
        ],
        "telemetry": [
            {"source": "gpu", "status": "missing", "error": "exporter unavailable", "labels": {"device": "0"}}
        ],
        "diagnostics": [
            {
                "id": "d1",
                "title": "补充资源观测",
                "evidence": ["缺少 exporter"],
                "confidence": "low",
                "adjustment": "记录环境后复测",
                "risk": "额外实验消耗",
                "validation": "保持相同数据与质量规则",
                "status": "pending",
            }
        ],
    }


@pytest.fixture
def api_fixture():
    state = {"runs": [], "calls": [], "error": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload, status=200, mime="application/json"):
            body = (
                json.dumps(payload, ensure_ascii=False).encode()
                if mime == "application/json"
                else payload.encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/plans/"):
                return self.reply(
                    {
                        "variable": "concurrency",
                        "comparable": True,
                        "eligible_points": [],
                        "best_point": None,
                        "points": [
                            {"value": 1, "requests_per_s": 5, "goodput_per_s": 5, "repeats": 1},
                            {"value": 2, "requests_per_s": 8, "goodput_per_s": 8, "repeats": 1},
                        ],
                        "warnings": ["协议替身仅展示曲线，不推荐容量；检查发压器实际发出速率。"],
                    }
                )
            if self.path == "/api/example":
                return self.reply(SPEC)
            if self.path == "/api/runs":
                return self.reply(state["runs"])
            if self.path.startswith("/api/runs/") and "/report" in self.path:
                return self.reply("Sanitized report", mime="text/plain")
            if self.path.startswith("/api/runs/"):
                run = next((r for r in state["runs"] if r["id"] == self.path.split("/")[3]), None)
                return self.reply(run or {}, 200 if run else 404)
            name = {"/": "index.html", "/static/app.js": "app.js", "/static/style.css": "style.css"}.get(
                self.path
            )
            if name and (STATIC / name).exists():
                return self.reply((STATIC / name).read_text(), mime=mimetypes.guess_type(name)[0])
            return self.reply("T4 UI is not implemented", 404, "text/plain")

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            state["calls"].append((self.path, payload, self.headers.get("X-Workbench-Action")))
            if state["error"]:
                return self.reply(state["error"], 422, "text/plain")
            if self.path == "/api/profile":
                return self.reply(
                    {
                        "sample_count": len(payload["dataset"]),
                        "fingerprint": "fixture-fingerprint",
                        "tokens": None,
                    }
                )
            if self.path == "/api/preflight":
                return self.reply(
                    {"models": ["fixture"], "sync": {"status": "ok"}, "stream": {"status": "ok"}}
                )
            if self.path == "/api/runs":
                run = fixture_run()
                run["spec"] = payload
                run["status"] = "running"
                state["runs"] = [run]
                return self.reply({"plan_id": RUN_ID, "run_ids": [RUN_ID]}, 202)
            if self.path.endswith("/cancel"):
                state["runs"][0]["status"] = "cancelled"
                return self.reply({"status": "cancelled"})
            if self.path.endswith("/labels"):
                return self.reply(state["runs"][0])
            if self.path == "/api/compare":
                return self.reply(
                    {
                        "comparable": False,
                        "reasons": ["协议替身不能证明模型性能"],
                        "candidates": [],
                        "best_run_id": None,
                        "differences": {"model": ["fixture", "fixture-2"]},
                    }
                )
            if self.path == "/api/retest":
                return self.reply(
                    {"status": "insufficient_evidence", "reasons": ["协议替身不能证明优化"], "change": None}
                )
            return self.reply("not found", 404, "text/plain")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def browser_page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page.set_default_timeout(4000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        browser.close()
        assert errors == [], errors


def open_editor(page, url):
    page.goto(url)
    page.get_by_role("button", name="新建实验", exact=True).first.click()
    page.get_by_role("button", name="载入起始配置", exact=True).click()
    expect(page.get_by_label("实验名称", exact=True)).to_have_value(SPEC["name"])


@pytest.mark.e2e
def test_initial_empty_state_and_mobile_keyboard(browser_page, api_fixture):
    page = browser_page
    url, state = api_fixture
    page.goto(url)
    expect(page.get_by_role("heading", name="每一次优化，都留下证据。")).to_be_visible()
    expect(page.get_by_text("还没有实验记录", exact=True)).to_be_visible()
    assert state["calls"] == []
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="跳到主要内容")).to_be_focused()


@pytest.mark.e2e
def test_jsonl_import_profile_and_explicit_capped_preflight(browser_page, api_fixture):
    page = browser_page
    url, state = api_fixture
    open_editor(page, url)
    page.get_by_label("导入 JSONL 数据集").set_input_files(
        {
            "name": "samples.jsonl",
            "mimeType": "application/jsonl",
            "buffer": b'{"id":"imported","messages":[{"role":"user","content":"test"}],"category":"qa"}\n',
        }
    )
    page.get_by_role("button", name="生成数据画像", exact=True).click()
    expect(page.get_by_text("fixture-fingerprint", exact=False)).to_be_visible()
    assert state["calls"][-1][1]["dataset"][0]["id"] == "imported"
    page.get_by_role("button", name="服务预检", exact=True).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("2 次生成")
    expect(dialog).to_contain_text("16")
    assert not any(c[0] == "/api/preflight" for c in state["calls"])
    dialog.get_by_role("button", name="确认预检", exact=True).click()
    expect(page.locator("#preflight-result")).to_contain_text("fixture")
    assert state["calls"][-1][2] == "local"


@pytest.mark.e2e
def test_form_advanced_json_sweep_submit_and_cancel(browser_page, api_fixture):
    page = browser_page
    url, state = api_fixture
    open_editor(page, url)
    page.get_by_label("模型名称", exact=True).fill("my-local-model")
    page.get_by_label("扫描点（逗号分隔）").fill("1, 2")
    page.get_by_role("button", name="展开高级 JSON").click()
    editor = page.get_by_label("完整实验 JSON")
    spec = json.loads(editor.input_value())
    assert spec["endpoint"]["model"] == "my-local-model"
    assert spec["load"]["scan"] == [1, 2]
    spec["telemetry"]["sources"] = [
        {"name": "device", "url": "http://127.0.0.1:9090/metrics", "mappings": []}
    ]
    spec["goals"]["max_p95_e2e_ms"] = 2500
    editor.fill(json.dumps(spec))
    page.get_by_role("button", name="应用 JSON", exact=True).click()
    page.get_by_role("button", name="启动实验计划", exact=True).click()
    expect(page.get_by_role("heading", name=SPEC["name"], exact=True)).to_be_visible()
    payload = next(c[1] for c in state["calls"] if c[0] == "/api/runs")
    assert payload["telemetry"]["sources"][0]["name"] == "device"
    assert payload["goals"]["max_p95_e2e_ms"] == 2500
    assert not any(c[0] == "/api/preflight" for c in state["calls"])
    page.get_by_role("button", name="停止实验计划", exact=True).click()
    expect(page.locator("#detail-status")).to_contain_text("已取消")


@pytest.mark.e2e
def test_detail_unknown_units_categories_raw_opt_in_labels_and_retest(browser_page, api_fixture):
    page = browser_page
    url, state = api_fixture
    state["runs"] = [fixture_run(), fixture_run(CANDIDATE_ID)]
    page.goto(url)
    page.get_by_role("button", name="查看实验", exact=True).first.click()
    expect(page.locator("#metrics")).to_contain_text("req/s")
    expect(page.locator("#metrics")).to_contain_text("未知")
    expect(page.locator("#category-table")).to_contain_text("short")
    expect(page.locator("#reliability")).to_contain_text("协议替身")
    expect(page.get_by_text("LOCAL-ONLY-RESPONSE", exact=False)).to_have_count(0)
    page.get_by_label("仅在本机查看响应原文").check()
    expect(page.get_by_text("LOCAL-ONLY-RESPONSE", exact=False)).to_be_visible()
    page.get_by_label("仅在本机查看响应原文").uncheck()
    expect(page.get_by_text("LOCAL-ONLY-RESPONSE", exact=False)).to_have_count(0)
    page.get_by_label("导入人工质量标签").set_input_files(
        {"name": "labels.json", "mimeType": "application/json", "buffer": b'{"r1":"pass"}'}
    )
    expect(page.locator("#labels-feedback")).to_contain_text("已更新")
    expect(page.locator("#telemetry")).to_contain_text("exporter unavailable")
    expect(page.locator("#recommendations")).to_contain_text("补充资源观测")
    assert page.get_by_role("link", name="下载 JSON").get_attribute("href").endswith("report?format=json")
    page.get_by_label("复测候选实验").select_option(CANDIDATE_ID)
    page.get_by_role("button", name="评估关联复测", exact=True).click()
    expect(page.locator("#retest-result")).to_contain_text("证据不足")
    call = next(c for c in state["calls"] if c[0] == "/api/retest")
    assert call[1]["baseline_id"] == RUN_ID
    assert call[1]["candidate_id"] == CANDIDATE_ID
    page.get_by_role("combobox", name="判定指标", exact=True).select_option(label="E2E P95 时延 ms")
    page.get_by_label("期望方向").select_option("decrease")
    page.get_by_role("button", name="评估关联复测", exact=True).click()
    expect(page.locator("#retest-result")).to_contain_text("e2e_ms.p95")
    page.get_by_label("允许的单一变更").select_option("load.concurrency")
    page.get_by_label("变更前的值").fill("1")
    page.get_by_label("变更后的值").fill("2")
    page.get_by_role("button", name="评估关联复测", exact=True).click()
    expect(page.locator("#retest-result")).to_contain_text("load.concurrency")
    assert state["calls"][-1][1]["criterion"]["change"] == {
        "field": "load.concurrency",
        "before": 1,
        "after": 2,
    }


@pytest.mark.e2e
def test_compare_conditions_and_no_false_winner(browser_page, api_fixture):
    page = browser_page
    url, state = api_fixture
    state["runs"] = [fixture_run(), fixture_run(CANDIDATE_ID)]
    page.goto(url)
    page.get_by_role("button", name="结果比较", exact=True).click()
    page.locator("#compare-candidates input[type=checkbox]").nth(0).check()
    page.locator("#compare-candidates input[type=checkbox]").nth(1).check()
    page.get_by_role("button", name="比较所选实验", exact=True).click()
    expect(page.locator("#compare-result")).to_contain_text("协议替身不能证明模型性能")
    expect(page.locator("#compare-result")).to_contain_text("无可推荐胜出实验")


@pytest.mark.e2e
def test_invalid_json_and_api_errors_are_text_not_html(browser_page, api_fixture):
    page = browser_page
    url, state = api_fixture
    open_editor(page, url)
    page.get_by_role("button", name="展开高级 JSON").click()
    page.get_by_label("完整实验 JSON").fill('{"name":')
    page.get_by_role("button", name="应用 JSON", exact=True).click()
    expect(page.locator("#editor-error")).to_contain_text("JSON")
    page.get_by_label("完整实验 JSON").fill(json.dumps(SPEC))
    page.get_by_role("button", name="应用 JSON", exact=True).click()
    state["error"] = '<img src=x onerror="window.injected=true"> Invalid model'
    page.get_by_role("button", name="启动实验计划", exact=True).click()
    expect(page.locator("#editor-error")).to_contain_text("<img")
    assert page.evaluate("window.injected === undefined")
    assert page.locator("#editor-error img").count() == 0


@pytest.mark.e2e
def test_late_analysis_refresh_and_timeout_status(browser_page, api_fixture):
    page = browser_page
    url, state = api_fixture
    run = fixture_run()
    run["summary"] = None
    run["status"] = "completed"
    state["runs"] = [run]
    page.goto(url)
    page.get_by_role("button", name="查看实验", exact=True).click()
    expect(page.locator("#metrics")).to_contain_text("未知")
    run["summary"] = fixture_run()["summary"]
    expect(page.locator("#category-table")).to_contain_text("short", timeout=8000)
    run["status"] = "timed_out"
    page.get_by_role("button", name="刷新结果", exact=True).click()
    expect(page.locator("#detail-status")).to_have_text("已超时")


@pytest.mark.e2e
def test_sweep_curve_table_retains_fixture_and_generator_warnings(browser_page, api_fixture):
    page = browser_page
    url, state = api_fixture
    run = fixture_run()
    run["parent_id"] = "d" * 32
    state["runs"] = [run]
    page.goto(url)
    page.get_by_role("button", name="查看实验", exact=True).click()
    page.get_by_role("button", name="扫描曲线", exact=True).click()
    expect(page.locator("#sweep-table")).to_contain_text("req/s")
    expect(page.locator("#sweep-table tbody tr")).to_have_count(2)
    expect(page.locator("#sweep-assessment")).to_contain_text("无可推荐最佳点")
    expect(page.locator("#sweep-warnings")).to_contain_text("发压器")
    expect(page.locator("#sweep-chart")).to_be_visible()


@pytest.fixture
def real_workbench(tmp_path):
    """Real FastAPI + ExperimentManager + EvalScope, talking to a protocol-only server."""
    import uvicorn

    from perfworkbench.web import create_app

    observed = []

    class ProtocolHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            payload = json.dumps({"data": [{"id": "browser-protocol-fixture"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observed.append(data)
            usage = {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
            if data.get("stream"):
                events = [
                    {
                        "object": "chat.completion.chunk",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": "BROWSER-PROTOCOL-OUTPUT"},
                                "finish_reason": None,
                            }
                        ],
                    },
                    {
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    },
                    {"choices": [], "usage": usage},
                ]
                payload = (
                    "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
                ).encode()
                mime = "text/event-stream"
            else:
                payload = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "BROWSER-PROTOCOL-OUTPUT"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": usage,
                    }
                ).encode()
                mime = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    endpoint = ThreadingHTTPServer(("127.0.0.1", 0), ProtocolHandler)
    endpoint_thread = threading.Thread(target=endpoint.serve_forever, daemon=True)
    endpoint_thread.start()
    app = create_app(tmp_path / "runs")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "Real workbench server did not start"
    try:
        yield address, f"http://127.0.0.1:{endpoint.server_port}/v1", app, observed
    finally:
        server.should_exit = True
        thread.join(12)
        sock.close()
        endpoint.shutdown()
        endpoint.server_close()
        endpoint_thread.join(2)


@pytest.mark.e2e
@pytest.mark.integration
def test_real_manager_browser_preflight_run_labels_and_sanitized_download(browser_page, real_workbench):
    page = browser_page
    address, endpoint, app, observed = real_workbench
    page.goto(address)
    page.get_by_role("button", name="新建实验", exact=True).first.click()
    page.get_by_role("button", name="载入起始配置", exact=True).click()
    expect(page.get_by_label("实验名称", exact=True)).to_have_value("baseline")
    page.get_by_label("实验名称", exact=True).fill("真实执行链路·协议验证")
    page.get_by_label("模型名称", exact=True).fill("browser-protocol-fixture")
    page.get_by_label("OpenAI 兼容服务地址").fill(endpoint)
    page.get_by_label("每点测量请求数").fill("2")
    page.get_by_label("每请求最大输出（tokens）").fill("8")
    page.get_by_label("计划总时限（s）").fill("60")
    page.get_by_label("协议替身实验（不代表模型性能）").check()
    page.get_by_label("质量模式").select_option("manual")
    page.get_by_role("button", name="生成数据画像", exact=True).click()
    expect(page.locator("#profile-result")).to_contain_text('"sample_count": 1')
    assert observed == []
    page.get_by_role("button", name="服务预检", exact=True).click()
    page.get_by_role("button", name="确认预检", exact=True).click()
    expect(page.locator("#preflight-result")).to_contain_text("browser-protocol-fixture", timeout=15000)
    assert len(observed) == 2 and all(data["max_tokens"] <= 8 for data in observed)
    page.get_by_role("button", name="启动实验计划", exact=True).click()
    expect(page.get_by_role("heading", name="真实执行链路·协议验证")).to_be_visible()
    expect(page.locator("#detail-status")).to_have_text("已完成", timeout=60000)
    expect(page.locator("#category-table")).to_contain_text("default", timeout=10000)
    assert len(observed) == 4  # Explicit preflight (2) + measured requests (2), no hidden sends.
    run = app.state.manager.store.list()[0]
    records = app.state.manager.store.records(run["id"])
    assert len(records) == 2 and all(record["success"] for record in records)
    expect(page.locator("#quality")).to_contain_text("未知 2")
    labels = {record["request_id"]: "pass" for record in records}
    page.get_by_label("导入人工质量标签").set_input_files(
        {"name": "labels.json", "mimeType": "application/json", "buffer": json.dumps(labels).encode()}
    )
    expect(page.locator("#labels-feedback")).to_contain_text("已更新")
    expect(page.locator("#quality")).to_contain_text("通过 2")
    expect(page.get_by_text("BROWSER-PROTOCOL-OUTPUT", exact=False)).to_have_count(0)
    page.get_by_label("仅在本机查看响应原文").check()
    expect(page.locator("#raw-responses")).to_contain_text("BROWSER-PROTOCOL-OUTPUT")
    with page.expect_download() as download_info:
        page.get_by_role("link", name="下载 JSON", exact=True).click()
    report = Path(download_info.value.path()).read_text()
    assert "BROWSER-PROTOCOL-OUTPUT" not in report
    assert endpoint not in report
    assert json.loads(report)["id"] == run["id"]


@pytest.mark.e2e
@pytest.mark.integration
def test_real_manager_browser_cancel_sweep_and_inspect_plan(browser_page, real_workbench):
    page = browser_page
    address, endpoint, app, observed = real_workbench
    page.goto(address)
    page.get_by_role("button", name="新建实验", exact=True).first.click()
    page.get_by_role("button", name="载入起始配置", exact=True).click()
    expect(page.get_by_label("实验名称", exact=True)).to_have_value("baseline")
    page.get_by_label("OpenAI 兼容服务地址").fill(endpoint)
    page.get_by_label("每点测量请求数").fill("4")
    page.get_by_label("每请求最大输出（tokens）").fill("8")
    page.get_by_label("扫描点（逗号分隔）").fill("1, 2")
    page.get_by_label("协议替身实验（不代表模型性能）").check()
    page.get_by_role("button", name="启动实验计划", exact=True).click()
    page.get_by_role("button", name="扫描曲线", exact=True).click()
    expect(page.locator("#sweep-table tbody tr")).to_have_count(2)
    expect(page.locator("#sweep-assessment")).to_contain_text("无可推荐最佳点")
    page.get_by_role("button", name="停止实验计划", exact=True).click()
    expect(page.locator("#detail-status")).to_have_text("已取消", timeout=15000)
    plan_id = app.state.manager.store.list()[0]["parent_id"]
    runs = app.state.manager.wait(plan_id, timeout=15)
    assert len(runs) == 2 and all(run["status"] == "cancelled" for run in runs)
    assert len(observed) <= 4  # Remaining point never dispatches; no implicit preflight.
    page.get_by_role("button", name="扫描曲线", exact=True).click()
    expect(page.locator("#sweep-assessment")).to_contain_text("无可推荐最佳点")
