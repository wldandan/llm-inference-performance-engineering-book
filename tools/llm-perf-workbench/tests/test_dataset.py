import importlib
import json
from collections import Counter

import pytest


def modules():
    try:
        return importlib.import_module("perfworkbench.dataset"), importlib.import_module(
            "perfworkbench.config"
        )
    except ModuleNotFoundError:
        pytest.fail("F03/F04 dataset implementation is missing", pytrace=False)


def samples():
    return [
        {
            "id": f"s{i}",
            "category": category,
            "messages": [{"role": "system", "content": "共享前缀"}, {"role": "user", "content": f"文章{i}"}],
        }
        for i, category in enumerate(["small", "large"])
    ]


def spec(**load):
    dataset, cfg = modules()
    return dataset, cfg.ExperimentSpec.model_validate(
        {"endpoint": {"base_url": "http://localhost/v1", "model": "m"}, "dataset": samples(), "load": load}
    ).model_dump(mode="json")


def test_jsonl_validates_lines_and_blank_lines():
    ds, _ = modules()
    text = "\n".join(json.dumps(row) for row in samples())
    assert len(ds.load_jsonl("\n" + text)) == 2
    with pytest.raises(ValueError, match="line 2"):
        ds.load_jsonl(json.dumps(samples()[0]) + "\n{bad}")
    with pytest.raises(ValueError):
        ds.load_jsonl("\n")


def test_profile_preserves_char_not_token_and_version():
    ds, _ = modules()
    rows = samples()
    first = ds.profile_dataset(rows)
    assert first["sample_count"] == 2
    assert first["input_tokens"] is None
    assert first["token_count_source"] == "unavailable"
    assert first["shared_prefix_chars"] > 0
    rows[0]["messages"][1]["content"] += "变更"
    assert ds.profile_dataset(rows)["version"] != first["version"]


def test_mix_exact_reproducible_and_requests_independent():
    ds, raw = spec(count=10, mix={"small": 0.7, "large": 0.3}, seed=7)
    requests = ds.materialize_requests(raw)
    assert Counter(x["category"] for x in requests) == {"small": 7, "large": 3}
    assert [x["sample_id"] for x in requests] == [x["sample_id"] for x in ds.materialize_requests(raw)]
    assert len({x["request_id"] for x in requests}) == 10
    assert all(len(x["body"]["messages"]) == 2 for x in requests)


def test_warmup_not_silently_counted_as_measurement():
    ds, raw = spec(count=3, warmup=2)
    reqs = ds.materialize_requests(raw)
    assert [x["phase"] for x in reqs] == ["warmup", "warmup", "measure", "measure", "measure"]


def test_scan_changes_one_variable_and_preserves_original():
    ds, raw = spec(count=3, scan=[1, 2], repeats=2)
    plans = ds.build_plan(raw)
    assert len(plans) == 4
    assert [p["load"]["concurrency"] for p in plans] == [1, 1, 2, 2]
    assert all(p["load"]["repeats"] == 1 and p["load"]["scan"] == [] for p in plans)
    assert raw["load"]["scan"] == [1, 2]


def test_rate_scan_retains_concurrency_admission_cap():
    ds, raw = spec(mode="rate", count=3, rate=1, scan=[0.5, 2])
    plans = ds.build_plan(raw)
    assert [p["load"]["rate"] for p in plans] == [0.5, 2]
    assert plans[0]["safety"]["max_concurrency"] == raw["safety"]["max_concurrency"]


def test_prompt_params_and_fingerprint_do_not_mutate_source():
    ds, raw = spec(count=2)
    raw["dataset"][0]["max_tokens"] = 32
    reqs = ds.materialize_requests(raw)
    assert {x["body"]["max_tokens"] for x in reqs} == {32, 128}
    assert all(x["body"]["model"] == "m" for x in reqs)
    assert "model" not in raw["dataset"][0]
