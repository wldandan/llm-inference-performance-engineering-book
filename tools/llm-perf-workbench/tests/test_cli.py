import importlib
import json

import pytest


def cli():
    try:
        return importlib.import_module("perfworkbench.cli")
    except ModuleNotFoundError:
        pytest.fail("F01-F14 CLI entry point missing", pytrace=False)


def test_cli_help_lists_user_workflows(capsys):
    with pytest.raises(SystemExit) as exc:
        cli().main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    for name in ("serve", "profile", "preflight", "run", "compare", "retest", "report", "label", "cancel"):
        assert name in text


def test_cli_validate_and_profile_jsonl(tmp_path, capsys):
    sample = {"id": "s", "messages": [{"role": "user", "content": "文章"}]}
    dataset = tmp_path / "data.jsonl"
    dataset.write_text(json.dumps(sample))
    assert cli().main(["profile", str(dataset)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["sample_count"] == 1 and result["input_tokens"] is None


def test_cli_invalid_input_is_actionable_without_traceback(tmp_path, capsys):
    config = tmp_path / "bad.json"
    config.write_text('{"api_key":"secret"}')
    assert cli().main(["validate", str(config)]) == 2
    text = capsys.readouterr().err
    assert "secret" not in text and "Traceback" not in text


def test_cli_init_produces_runnable_protocol_example(tmp_path, capsys):
    path = tmp_path / "example.json"
    assert cli().main(["init", "--output", str(path)]) == 0
    spec = json.loads(path.read_text())
    assert spec["protocol_fixture"] is True
    assert spec["endpoint"]["base_url"].startswith("http://127.0.0.1:")
    assert cli().main(["validate", str(path)]) == 0


def test_cli_refuses_public_web_bind():
    with pytest.raises(SystemExit):
        cli().main(["serve", "--host", "0.0.0.0"])


def test_cli_list_empty_workspace(tmp_path, capsys):
    assert cli().main(["--root", str(tmp_path), "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_demo_endpoint_is_explicit_fixture_and_generates_valid_json():
    import threading

    import httpx

    try:
        demo = importlib.import_module("perfworkbench.demo")
    except ModuleNotFoundError:
        pytest.fail("Local protocol demo missing", pytrace=False)
    server = demo.create_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1"
        assert httpx.get(base + "/models", trust_env=False).json()["data"][0]["id"] == "protocol-fixture"
        response = httpx.post(
            base + "/chat/completions",
            json={
                "model": "protocol-fixture",
                "messages": [{"role": "user", "content": "test"}],
                "stream": False,
            },
            trust_env=False,
        ).json()
        assert response["choices"][0]["finish_reason"] == "stop"
        assert "协议" in response["choices"][0]["message"]["content"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_cli_compare_label_report_and_declared_retest(tmp_path, capsys):
    from perfworkbench.analysis import analyze
    from perfworkbench.config import ExperimentSpec
    from perfworkbench.store import RunStore, append_jsonl

    store = RunStore(tmp_path)
    runs = []
    for concurrency, duration in ((1, 2), (2, 1)):
        spec = ExperimentSpec.model_validate(
            {
                "endpoint": {"base_url": "http://localhost/v1", "model": "m"},
                "dataset": [{"id": "s", "messages": [{"role": "user", "content": "test"}]}],
                "load": {"count": 2, "concurrency": concurrency},
            }
        ).model_dump(mode="json")
        run = store.create(spec)
        records = [
            {
                "request_id": f"r{i}",
                "sample_id": "s",
                "category": "default",
                "phase": "measure",
                "start_s": 0,
                "end_s": duration,
                "status": "success",
                "success": True,
                "is_stream": False,
                "input_tokens": 32,
                "output_tokens": 8,
                "e2e_ms": duration * 1000,
                "output_text": "answer",
                "finish_reason": "stop",
            }
            for i in range(2)
        ]
        for row in records:
            append_jsonl(store.run_dir(run["id"]) / "records.jsonl", row)
        store.update(run["id"], status="completed", summary=analyze(records, spec))
        runs.append(run)
    args = ["--root", str(tmp_path)]
    assert cli().main([*args, "show", runs[0]["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
    assert cli().main([*args, "compare", *[r["id"] for r in runs]]) == 0
    assert not json.loads(capsys.readouterr().out)["comparable"]
    assert (
        cli().main([*args, "retest", runs[0]["id"], runs[1]["id"], "--allow-change", "load.concurrency"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "effective"
    assert store.get(runs[1]["id"])["retest"]["baseline_id"] == runs[0]["id"]
    assert store.get(runs[1]["id"])["retest"]["status"] == "effective"
    assert store.get(runs[1]["id"])["retest"]["candidate_id"] == runs[1]["id"]
    labels = tmp_path / "labels.json"
    labels.write_text('{"r0":"pass"}')
    assert cli().main([*args, "label", runs[0]["id"], str(labels)]) == 0
    assert json.loads(capsys.readouterr().out)["records"][0]["manual_label"] == "pass"
    assert cli().main([*args, "report", runs[0]["id"], "--format", "json"]) == 0
    assert "output_text" not in capsys.readouterr().out
