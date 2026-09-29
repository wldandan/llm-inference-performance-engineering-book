"""The ordinary editor hides the reproducibility knob without losing its value."""

import copy
import json

import pytest
from playwright.sync_api import expect
from test_dashboard import SPEC, expand_editor_options
from test_dashboard import api_fixture as api_fixture  # noqa: PLC0414 -- re-export pytest fixture
from test_dashboard import browser_page as browser_page  # noqa: PLC0414 -- re-export pytest fixture


@pytest.mark.e2e
@pytest.mark.parametrize(("source", "seed"), [("default", 42), ("file", 73), ("json", 0), ("missing", 42)])
def test_hidden_seed_keeps_default_and_explicit_values(browser_page, api_fixture, source, seed):
    page = browser_page
    url, state = api_fixture
    page.set_viewport_size({"width": 390 if source == "json" else 1440, "height": 1000})
    page.goto(url)
    page.locator('nav [data-view="editor"]').click()
    expand_editor_options(page)
    expect(page.get_by_label("随机种子", exact=True)).not_to_be_visible()
    expect(page.get_by_role("button", name="随机种子说明", exact=True)).to_have_count(0)
    page.get_by_label("模型名称", exact=True).fill("fixture")
    page.get_by_role("button", name="展开高级 JSON", exact=True).click()
    if source != "default":
        spec = copy.deepcopy(SPEC)
        spec["load"]["seed"] = seed
        if source == "missing":
            del spec["load"]["seed"]
        if source == "json":
            page.locator("#spec-json").fill(json.dumps(spec))
            page.get_by_role("button", name="应用 JSON", exact=True).click()
        else:
            page.locator("#config-file").set_input_files(
                {"name": "seed.json", "mimeType": "application/json", "buffer": json.dumps(spec).encode()}
            )
            expect(page.locator("#editor-feedback")).to_contain_text("配置已导入")
    # Presets and ordinary field edits must not reset a seed supplied through JSON.
    page.locator('[data-preset="quick"]').click()
    page.get_by_label("实验名称", exact=True).fill("seed-check")
    assert json.loads(page.locator("#spec-json").input_value())["load"]["seed"] == seed
    assert state["calls"] == []
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="启动实验计划", exact=True).click()
    expect(page.locator("#view-detail")).to_be_visible()
    calls = state["calls"]
    assert len(calls) == 1 and calls[0][0] == "/api/runs"
    assert calls[0][1]["load"]["seed"] == seed
    assert type(calls[0][1]["load"]["seed"]) is int
