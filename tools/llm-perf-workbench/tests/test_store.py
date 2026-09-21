import importlib
import json
import stat

import pytest


def storage():
    try:
        return importlib.import_module("perfworkbench.store")
    except ModuleNotFoundError:
        pytest.fail("F05 store is not implemented", pytrace=False)


def test_private_atomic_snapshots_and_no_overwrite(tmp_path):
    store = storage().RunStore(tmp_path / "private")
    spec = {"name": "a"}
    first = store.create(spec)
    other = store.create(spec)
    spec["name"] = "edited"
    assert first["id"] != other["id"]
    assert store.get(first["id"])["spec"]["name"] == "a"
    assert stat.S_IMODE(store.run_dir(first["id"]).stat().st_mode) == 0o700
    assert len(store.list()) == 2
    store.update(first["id"], status="running", progress={"done": 1})
    assert store.get(first["id"])["status"] == "running"


@pytest.mark.parametrize("run_id", ["../secret", "/etc/passwd", "x", "a" * 33])
def test_run_id_is_not_a_path(tmp_path, run_id):
    with pytest.raises(ValueError):
        storage().RunStore(tmp_path).get(run_id)


def test_unknown_label_is_rejected_and_record_content_preserved(tmp_path):
    mod = storage()
    store = mod.RunStore(tmp_path)
    run = store.create({"name": "one"})
    mod.append_jsonl(store.run_dir(run["id"]) / "records.jsonl", {"request_id": "r1", "output_text": "内容"})
    with pytest.raises(ValueError):
        store.label(run["id"], {"unknown": "pass"})
    with pytest.raises(ValueError):
        store.label(run["id"], {"r1": "maybe"})
    store.label(run["id"], {"r1": "pass"})
    assert store.records(run["id"])[0]["manual_label"] == "pass"
    assert store.records(run["id"])[0]["output_text"] == "内容"


def test_jsonl_trailing_partial_crash_line_is_ignored_not_executed(tmp_path):
    mod = storage()
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"request_id": "ok"}) + '\n{"partial":', encoding="utf-8")
    assert mod.read_jsonl(path) == [{"request_id": "ok"}]


def test_reserved_fields_cannot_be_overwritten(tmp_path):
    store = storage().RunStore(tmp_path)
    run = store.create({"name": "one"})
    with pytest.raises(ValueError):
        store.update(run["id"], spec={"name": "replacement"})
