"""Local observation UI against protocol fixtures; never invoke a real model."""

import copy
import json

import pytest
from playwright.sync_api import expect
from test_dashboard import SPEC, expand_editor_options, fixture_run
from test_dashboard import api_fixture as api_fixture  # noqa: PLC0414
from test_dashboard import browser_page as browser_page  # noqa: PLC0414

pytestmark = pytest.mark.e2e
STAMP = 1790000000
SYSTEM = {
    "host_memory_total_bytes": 16 * 1024**3,
    "host_memory_available_bytes": 512 * 1024**2,
    "host_swap_used_bytes": 0,
    "host_swap_total_bytes": 2 * 1024**3,
}
OLLAMA = {"model_memory_bytes": 3 * 1024**3, "model_context_tokens": 8192}
REASONS = [
    "model_not_loaded",
    "field_unavailable",
    "invalid_value",
    "invalid_response",
    "ambiguous_model",
    "http_401",
    "http_404",
    "http_500",
    "missing_api_key",
    "timeout",
    "network_error",
    "system_unavailable",
    "redirect_rejected",
    "response_too_large",
    "unsupported_encoding",
]
EXPORTERS = [
    {
        "name": "device",
        "url": "http://127.0.0.1:9400/metrics",
        "api_key_env": None,
        "mappings": [{"key": "device_memory_used_bytes", "metric": "gpu_memory", "kind": "gauge"}],
    }
]


def frame(kind="local_system", timestamp=STAMP, reason=None):
    values = SYSTEM if kind == "local_system" else OLLAMA
    return {
        "timestamp": timestamp,
        "source": kind.replace("_", "-"),
        "source_kind": kind,
        "status": "error" if reason else "ok",
        **({"error": reason} if reason else {}),
        "metrics": {
            key: {
                "value": None if reason else value,
                "unit": "tokens" if key.endswith("tokens") else "bytes",
                "kind": "gauge",
                "status": "missing" if reason else "available",
                "reason": reason,
                "series": [],
            }
            for key, value in values.items()
        },
    }


def local_run(frames=(), enabled=True, status="running"):
    run = fixture_run()
    run["spec"]["telemetry"]["local"] = {"enabled": enabled}
    run["telemetry"] = list(frames)
    run["status"] = status
    return run


def open_result(page, api_fixture, run):
    url, state = api_fixture
    state["runs"] = [run]
    page.goto(url)
    page.get_by_role("button", name="查看实验", exact=True).click()
    return state


@pytest.mark.parametrize("width", [390, 1440])
def test_local_opt_in_help_and_default_are_inert(browser_page, api_fixture, width):
    page = browser_page
    url, state = api_fixture
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(url)
    page.locator('nav [data-view="editor"]').click()
    checkbox = page.locator('[name="telemetry.local.enabled"]')
    expect(checkbox).to_have_count(1)
    expect(checkbox).not_to_be_visible()
    expand_editor_options(page)
    expect(page.get_by_role("checkbox", name="采集本机 Ollama 与内存", exact=True)).to_be_visible()
    expect(checkbox).not_to_be_checked()
    expect(page.locator("#run-settings-summary")).to_contain_text("本地采集：关闭")
    assert json.loads(page.locator("#spec-json").input_value())["telemetry"]["local"] == {"enabled": False}
    page.get_by_role("button", name="采集本机 Ollama 与内存说明", exact=True).click()
    tip = page.get_by_role("tooltip")
    for phrase in ["后端主机", "确认", "隧道", "GET", "不额外生成", "GPU", "KV", "macOS", "Linux"]:
        expect(tip).to_contain_text(phrase)
    box = tip.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    expect(checkbox).not_to_be_checked()
    page.keyboard.press("Escape")
    expect(tip).to_be_hidden()
    checkbox.check()
    expect(page.locator("#run-settings-summary")).to_contain_text("本地采集：开启")
    assert json.loads(page.locator("#spec-json").input_value())["telemetry"]["local"]["enabled"] is True
    checkbox.uncheck()
    assert state["calls"] == []
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("source,enabled", [("file", True), ("json", False), ("old", None)])
def test_local_config_round_trip_preserves_exporters(browser_page, api_fixture, source, enabled):
    page = browser_page
    url, state = api_fixture
    page.goto(url)
    page.locator('nav [data-view="editor"]').click()
    expand_editor_options(page)
    checkbox = page.locator('[name="telemetry.local.enabled"]')
    expect(checkbox).to_have_count(1)
    checkbox.check()  # Importing an older spec must turn this back off.
    spec = copy.deepcopy(SPEC)
    spec["telemetry"]["sources"] = EXPORTERS
    if enabled is not None:
        spec["telemetry"]["local"] = {"enabled": enabled}
    page.get_by_role("button", name="展开高级 JSON", exact=True).click()
    if source == "json":
        page.locator("#spec-json").fill(json.dumps(spec))
        page.get_by_role("button", name="应用 JSON", exact=True).click()
    else:
        page.locator("#config-file").set_input_files(
            {"name": "local.json", "mimeType": "application/json", "buffer": json.dumps(spec).encode()}
        )
        expect(page.locator("#editor-feedback")).to_contain_text("配置已导入")
    assert checkbox.is_checked() is bool(enabled)
    assert json.loads(page.locator("#spec-json").input_value()) == spec
    expect(page.locator("#run-settings-summary")).to_contain_text(
        "本地采集：开启" if enabled else "本地采集：关闭"
    )
    page.get_by_role("button", name="收起高级 JSON", exact=True).click()
    page.get_by_role("button", name="展开高级 JSON", exact=True).click()
    assert json.loads(page.locator("#spec-json").input_value()) == spec
    assert state["calls"] == []
    page.get_by_role("button", name="启动实验计划", exact=True).click()
    expect(page.locator("#view-detail")).to_be_visible()
    assert len(state["calls"]) == 1
    assert state["calls"][0][0] == "/api/runs"
    assert state["calls"][0][1] == spec


@pytest.mark.parametrize(
    "enabled,status,mode,expected",
    [
        (False, "running", "empty", "未启用"),
        (True, "running", "empty", "等待首样本"),
        (True, "running", "all", "可用"),
        (True, "running", "partial", "部分缺失"),
        (True, "running", "system_only", "部分缺失"),
        (True, "running", "failure", "失败"),
        (True, "completed", "all", "已停止"),
        (True, "cancelled", "partial", "已停止"),
        (True, "failed", "empty", "已停止"),
        (True, "interrupted", "failure", "已停止"),
    ],
)
def test_local_summary_states(browser_page, api_fixture, enabled, status, mode, expected):
    frames = [] if mode == "empty" else [frame(), frame("local_ollama")]
    if mode in ("partial", "failure"):
        frames[-1] = frame("local_ollama", reason="model_not_loaded")
    if mode == "failure":
        frames[0] = frame(reason="system_unavailable")
    if mode == "system_only":
        frames.pop()
    state = open_result(browser_page, api_fixture, local_run(frames, enabled, status))
    expect(browser_page.locator("#local-telemetry-status")).to_contain_text(expected)
    if mode == "system_only":
        expect(browser_page.locator("#local-telemetry-summary")).to_contain_text("等待首样本")
    if status == "cancelled":
        expect(browser_page.locator("#local-telemetry-status")).to_contain_text("部分缺失")
    assert state["calls"] == []


@pytest.mark.parametrize("width", [390, 1440])
def test_local_units_scope_history_and_exporter_coexist(browser_page, api_fixture, tmp_path, width):
    page = browser_page
    page.set_viewport_size({"width": width, "height": 1000})
    run = local_run([frame(), frame("local_ollama")])
    exporter = {
        "timestamp": STAMP,
        "source": "gpu-exporter",
        "status": "ok",
        "metrics": {
            "device_memory_used_bytes": {"value": 5 * 1024**3, "unit": "bytes", "status": "available"},
            "kv_cache_usage_ratio": {"value": 0.25, "unit": "ratio", "status": "available"},
        },
    }
    run["telemetry"].append(exporter)
    open_result(page, api_fixture, run)
    latest = page.locator("#local-telemetry-summary")
    expect(latest).to_be_visible()
    for phrase in [
        "16 GiB",
        "512 MiB",
        "0 MiB",
        "2 GiB",
        "3 GiB",
        "8,192 tokens",
        "size_vram",
        "配置上下文",
        "非使用量",
        "本地 GPU / KV：未提供",
        "后端主机",
    ]:
        expect(latest).to_contain_text(phrase)
    assert "NVIDIA 显存使用" not in latest.inner_text()
    assert "不等于设备" in latest.inner_text()
    exporter_view = page.locator("#exporter-telemetry")
    expect(exporter_view).to_be_visible()
    expect(exporter_view).to_contain_text("device_memory_used_bytes")
    expect(exporter_view).to_contain_text("kv_cache_usage_ratio")
    expect(exporter_view).to_contain_text("0.25")
    expect(page.locator("#local-telemetry-history")).not_to_have_attribute("open", "")
    expect(page.locator("#telemetry-raw")).not_to_be_visible()
    page.locator("#local-telemetry-history > summary").click()
    table = page.locator("#local-telemetry-table")
    expect(table.locator("thead")).to_contain_text("采样时间")
    expect(table.locator("thead")).to_contain_text("来源")
    expect(table.locator("thead")).to_contain_text("指标")
    expect(table.locator("thead")).to_contain_text("值 / 状态")
    expect(table.locator("tbody tr")).to_have_count(6)
    expect(table).to_contain_text("local-system")
    expect(table).to_contain_text("local-ollama")
    expect(table.locator("time").first).to_have_attribute("datetime", "2026-09-21T14:13:20.000Z")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator("#local-telemetry-summary").scroll_into_view_if_needed()
    screenshot = tmp_path / f"local-telemetry-{width}.png"
    page.screenshot(path=str(screenshot), full_page=True)
    print(f"Screenshot: {screenshot}")
    page.locator("#telemetry-raw-details > summary").click()
    assert json.loads(page.locator("#telemetry-raw").inner_text()) == run["telemetry"]


@pytest.mark.parametrize("missing", ["error", "metric", "omitted"])
def test_latest_frame_replaces_stale_values_per_source(browser_page, api_fixture, missing):
    page = browser_page
    run = local_run([frame(), frame("local_ollama")])
    open_result(page, api_fixture, run)
    summary = page.locator("#local-telemetry-summary")
    expect(summary).to_contain_text("3 GiB")
    newer = frame("local_ollama", STAMP + 5, "timeout" if missing == "error" else None)
    if missing == "metric":
        newer["metrics"]["model_memory_bytes"].update(
            value=None, status="missing", reason="field_unavailable"
        )
    if missing == "omitted":
        newer["metrics"].pop("model_memory_bytes")
    # API rows retain JSONL append order, including the most recent incomplete frame.
    run["telemetry"].append(newer)
    page.get_by_role("button", name="刷新结果", exact=True).click()
    expect(summary).to_contain_text("null")
    expect(summary).to_contain_text("timeout" if missing == "error" else "field_unavailable")
    expect(summary).not_to_contain_text("3 GiB")
    expect(summary).to_contain_text("16 GiB")
    expect(page.locator("#local-telemetry-status")).to_contain_text("部分缺失")
    if missing == "error":
        expect(summary).not_to_contain_text("8,192 tokens")
    else:
        expect(summary).to_contain_text("8,192 tokens")


@pytest.mark.parametrize("kind", ["local_system", "local_ollama"])
@pytest.mark.parametrize("clock_delta", [-5, 0], ids=["clock-rollback", "same-timestamp"])
def test_latest_failure_uses_append_order_despite_clock(browser_page, api_fixture, kind, clock_delta):
    page = browser_page
    run = local_run([frame(), frame("local_ollama")])
    state = open_result(page, api_fixture, run)
    source = page.locator(".local-source").filter(has_text=kind.replace("_", "-"))
    stale_value = "16 GiB" if kind == "local_system" else "3 GiB"
    reason = "system_unavailable" if kind == "local_system" else "timeout"
    expect(source).to_contain_text(stale_value)

    # A later JSONL row remains current even when the wall clock moves backwards.
    run["telemetry"].append(frame(kind, STAMP + clock_delta, reason))
    other_kind = "local_ollama" if kind == "local_system" else "local_system"
    run["telemetry"].append(frame(other_kind))
    page.get_by_role("button", name="刷新结果", exact=True).click()
    expect(source).to_contain_text("null")
    expect(source).to_contain_text(reason)
    expect(source).not_to_contain_text(stale_value)
    expect(source.locator("h4")).to_contain_text("失败")
    expect(source.locator("time")).to_have_attribute(
        "datetime", "2026-09-21T14:13:15.000Z" if clock_delta == -5 else "2026-09-21T14:13:20.000Z"
    )
    other_source = page.locator(".local-source").filter(has_text=other_kind.replace("_", "-"))
    expect(other_source).to_contain_text("3 GiB" if kind == "local_system" else "16 GiB")
    expect(page.locator("#local-telemetry-status")).to_contain_text("部分缺失")

    # Presentation order in the historical table must not select the summary frame.
    page.locator("#local-telemetry-history > summary").click()
    table = page.locator("#local-telemetry-table")
    expect(table.locator("time").first).to_have_attribute("datetime", "2026-09-21T14:13:20.000Z")
    expect(table).to_contain_text(reason)
    page.locator("#telemetry-raw-details > summary").click()
    assert json.loads(page.locator("#telemetry-raw").inner_text()) == run["telemetry"]
    assert state["calls"] == []


def test_local_history_is_bounded_and_raw_keeps_all_frames(browser_page, api_fixture):
    page = browser_page
    frames = [frame("local_ollama", STAMP + index) for index in range(125)]
    frames[0]["metrics"]["model_context_tokens"]["value"] = 123456
    frames[-1]["metrics"]["model_context_tokens"]["value"] = 0
    open_result(page, api_fixture, local_run(frames))
    expect(page.locator("#local-telemetry-status")).to_contain_text("部分缺失")
    expect(page.locator("#local-telemetry-summary")).to_contain_text("0 tokens")
    page.locator("#local-telemetry-history > summary").click()
    table = page.locator("#local-telemetry-table")
    expect(table.locator("tbody tr")).to_have_count(200)
    expect(page.locator("#local-telemetry-count")).to_contain_text("最近 200 条")
    expect(page.locator("#local-telemetry-count")).to_contain_text("共 250 条")
    expect(table).not_to_contain_text("123,456")
    expect(table.locator("tbody tr").first).to_contain_text("2026-09-21T14:15:24.000Z")
    page.locator("#telemetry-raw-details > summary").click()
    assert json.loads(page.locator("#telemetry-raw").inner_text()) == frames


def test_reason_codes_and_untrusted_strings_are_rendered_as_text(browser_page, api_fixture):
    page = browser_page
    frames = [frame("local_ollama", STAMP + i, reason) for i, reason in enumerate(REASONS)]
    attack = '<img src=x onerror="window.injected=true">'
    frames.append(frame("local_system", STAMP + 100, attack))
    frames[-1]["source"] = attack
    frames[-1]["metrics"]["host_memory_total_bytes"]["reason"] = attack
    open_result(page, api_fixture, local_run(frames))
    expect(page.locator("#local-telemetry-status")).to_contain_text("失败")
    page.locator("#local-telemetry-history > summary").click()
    table = page.locator("#local-telemetry-table")
    for reason in REASONS:
        expect(table).to_contain_text(reason)
    expect(table).to_contain_text("null")
    expect(table).to_contain_text(attack)
    assert page.locator("#telemetry img").count() == 0
    assert page.evaluate("window.injected === undefined")


def test_old_run_keeps_exporter_and_raw_observations(browser_page, api_fixture):
    page = browser_page
    run = fixture_run()
    open_result(page, api_fixture, run)
    expect(page.locator("#local-telemetry-status")).to_contain_text("未启用")
    expect(page.locator("#exporter-telemetry")).to_contain_text("exporter unavailable")
    page.locator("#telemetry-raw-details > summary").click()
    assert json.loads(page.locator("#telemetry-raw").inner_text()) == run["telemetry"]
