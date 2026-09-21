import pytest

from perfworkbench.runner import ExperimentManager
from perfworkbench.store import RunStore


def test_new_manager_recovers_orphan_running_run(tmp_path):
    store = RunStore(tmp_path)
    run = store.create({"name": "orphan"})
    store.update(run["id"], status="running")
    manager = ExperimentManager(tmp_path)
    try:
        assert manager.store.get(run["id"])["status"] == "interrupted"
    finally:
        manager.close()


def test_cancel_from_another_manager_marks_whole_plan(tmp_path):
    store = RunStore(tmp_path)
    plan_id = "a" * 32
    first = store.create({"name": "a"}, parent_id=plan_id)
    second = store.create({"name": "b"}, parent_id=plan_id)
    manager = ExperimentManager(tmp_path)
    try:
        result = manager.cancel(first["id"])
        assert result["plan_id"] == plan_id
        assert (store.run_dir(first["id"]) / "STOP").exists()
        assert (store.run_dir(second["id"]) / "STOP").exists()
    finally:
        manager.close()


def test_preflight_does_not_contaminate_active_experiment(tmp_path):
    manager = ExperimentManager(tmp_path)
    # State sentinel: no external service needed to reject this invalid transition.
    manager._active = "busy"
    with pytest.raises(ValueError, match="active"):
        manager.preflight({"base_url": "http://127.0.0.1:1/v1", "model": "m"})
    manager._active = None
    manager.close()
