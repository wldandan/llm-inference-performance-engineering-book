#!/usr/bin/env python3
"""Run one controlled Prefill experiment and write a report that can be wrong.

Two things are enforced rather than suggested:

* `expectation` must exist before the run. The script records when it was
  written; an expectation supplied after the fact is refused (14.1).
* `changed` may name exactly one item. Two changes and it refuses to run,
  because the result would not be attributable to either (14.2, 14.4).

`verdict` keeps a fourth value beside 符合 / 低于 / 高于: 在波动内不可分辨.
That is a legitimate, honest conclusion, and the script will not let it be
rewritten as a small improvement (14.7).

Needs a real vLLM service to collect data. The report builder and the checker
below run without one, which is what the tests and the synthetic sample use.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch11"))
sys.path.insert(0, str(HERE.parent / "ch07"))
from prefill_model import (  # noqa: E402
    ModelError,
    crossover_tokens,
    load_config,
)
from run_baseline import line_factor  # noqa: E402

BLOCKS = (
    "expectation",
    "fixed",
    "changed",
    "results",
    "guardrails",
    "verdict",
    "boundary",
)

EXPECTATION_FIELDS = ("direction", "magnitude", "unchanged", "null_criterion")
FIXED_BLOCKS = ("workload", "protocol", "environment")
BOUNDARY_FIELDS = ("model", "workload", "hardware", "config")

VERDICTS = ("符合预期", "低于预期", "高于预期", "在波动内不可分辨")
INDISTINGUISHABLE = "在波动内不可分辨"


class ExperimentError(ValueError):
    """Raised when an experiment report could not support a conclusion."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentError(message)


def coefficient_of_variation(values: list[float]) -> float:
    """Sample standard deviation over the mean (7.3, n-1 convention)."""
    _require(len(values) >= 3, "至少需要三轮数据才能谈波动（7.3）")
    mean = statistics.fmean(values)
    _require(mean > 0, "延迟均值必须为正")
    return statistics.stdev(values) / mean


def detectable_difference(values: list[float], runs_per_group: int | None = None) -> float:
    """The book's one criterion for 'can this experiment tell?' (7.3).

    t x sqrt(2/n) x CV for two groups of n runs each; about 2.3 x CV for three
    against three. Not the range: the range is an observation, this is the
    judgement derived from the CV, and the same line Chapters 10, 14, 19 and
    28 use.
    """
    n = runs_per_group or len(values)
    return line_factor(n) * coefficient_of_variation(values)


def validate_expectation(doc: object) -> None:
    _require(isinstance(doc, dict), "expectation must be an object")
    assert isinstance(doc, dict)
    for field in EXPECTATION_FIELDS:
        value = doc.get(field)
        _require(
            value not in (None, "", [], {}),
            f"expectation.{field} is required：少了它这次实验就没有被推翻的可能（14.1）",
        )
    written_at = doc.get("written_at")
    _require(
        isinstance(written_at, str) and written_at.strip() != "",
        "expectation.written_at is required：事后补写的预期不被接受（14.1）",
    )
    magnitude = doc["magnitude"]
    _require(
        isinstance(magnitude, dict) and magnitude,
        "expectation.magnitude 必须是对象，且每一项要能和实测对上",
    )
    for key, item in magnitude.items():
        _require(
            isinstance(item, dict) and "expected_pct" in item and "basis" in item,
            f"expectation.magnitude.{key} 必须给 expected_pct 和 basis："
            "幅度的每个数都要有出处，不能是感觉（14.1）",
        )


def validate_report(doc: object) -> None:
    _require(isinstance(doc, dict), "experiment report must be an object")
    assert isinstance(doc, dict)
    for block in BLOCKS:
        _require(block in doc, f"missing required block: {block}")

    validate_expectation(doc["expectation"])

    fixed = doc["fixed"]
    _require(isinstance(fixed, dict), "fixed must be an object")
    for block in FIXED_BLOCKS:
        _require(
            isinstance(fixed.get(block), dict) and fixed[block],
            f"fixed.{block} is required：这三组必须原样不动才能相减（14.2）",
        )
    env = fixed["environment"]
    for field in ("model_revision", "framework_version", "gpu", "driver"):
        _require(
            field in env,
            f"fixed.environment.{field} is required：交给同事要能重跑（7.6）",
        )
    protocol = fixed["protocol"]
    for field in ("warmup", "repeats", "window", "percentile_algorithm",
                  "stdev_convention", "temperature", "prefix_cache"):
        _require(
            field in protocol,
            f"fixed.protocol.{field} is required（14.2）",
        )
    _require(
        protocol["temperature"] == 0,
        "fixed.protocol.temperature 必须为 0：否则输出长度每次不同，会污染 E2E 和吞吐（14.2）",
    )
    _require(
        protocol["prefix_cache"] in ("off", "on-and-recorded"),
        "fixed.protocol.prefix_cache 只能是 off 或 on-and-recorded："
        "不能一次开一次关（14.2）",
    )

    changed = doc["changed"]
    _require(isinstance(changed, dict), "changed must be an object")
    _require(
        len(changed) == 1,
        f"changed 只允许出现一项，现在有 {len(changed)} 项："
        "同时改两项，结果好了也不知道是谁的功劳（14.2）",
    )

    results = doc["results"]
    _require(isinstance(results, dict), "results must be an object")
    for arm in ("baseline", "variant"):
        runs = results.get(arm)
        _require(
            isinstance(runs, list) and len(runs) >= 3,
            f"results.{arm} 至少要三轮：一次运行给不出结论（7.3）",
        )
        for value in runs:
            _require(
                isinstance(value, (int, float)) and value > 0,
                f"results.{arm} 里的每一轮都必须是正数",
            )

    guardrails = doc["guardrails"]
    _require(
        isinstance(guardrails, dict) and guardrails,
        "guardrails 不是可选项：只报主指标是不诚实的（5 章、14.4）",
    )

    boundary = doc["boundary"]
    _require(isinstance(boundary, dict), "boundary must be an object")
    for field in BOUNDARY_FIELDS:
        value = boundary.get(field)
        _require(
            value not in (None, "", [], {}),
            f"boundary.{field} is required：没有边界说明的收益数字会被当成普适结论（14.6）",
        )

    verdict = doc["verdict"]
    _require(isinstance(verdict, dict), "verdict must be an object")
    label = verdict.get("label")
    _require(label in VERDICTS, f"verdict.label 必须是 {VERDICTS} 之一")
    if label == INDISTINGUISHABLE:
        text = json.dumps(verdict, ensure_ascii=False)
        for phrase in ("小幅有效", "小幅提升", "略有改善", "有小幅"):
            _require(
                phrase not in text,
                f"verdict 标为“{INDISTINGUISHABLE}”却又写了“{phrase}”："
                "这是在用噪声支撑结论（14.7）",
            )


def judge(
    baseline: list[float], variant: list[float], expected_pct: float
) -> dict:
    """Two steps, one line (14.5).

    Step 1: is |observed| beyond the line? If not, the experiment cannot tell.
    Step 2: is |observed - expected| beyond the same line? Inside it the result
    matches; outside it, the sign says lower or higher than expected.
    Means, not medians, because the CV and the line are built on means (7.3).
    """
    base_mean = statistics.fmean(baseline)
    var_mean = statistics.fmean(variant)
    observed = (base_mean - var_mean) / base_mean
    line = detectable_difference(baseline)
    gap = observed - expected_pct

    if abs(observed) < line:
        label = INDISTINGUISHABLE
        reading = (
            f"改善 {observed * 100:.1f}% 小于可识别线 {line * 100:.1f}%，"
            "当前精度区分不出来。先降低波动，或者接受这个结论"
        )
    elif abs(gap) < line:
        label = "符合预期"
        reading = (
            f"改善 {observed * 100:.1f}%，预期 {expected_pct * 100:.1f}%，"
            f"相差 {abs(gap) * 100:.1f} 个百分点，在可识别线 {line * 100:.1f}% 以内"
        )
    elif gap > 0:
        label = "高于预期"
        reading = (
            f"改善 {observed * 100:.1f}%，比预期的 {expected_pct * 100:.1f}% 高出 "
            f"{gap * 100:.1f} 个百分点，超过可识别线。按 14.5 的顺序排查，"
            "高于预期同样要找原因，常见的是预期的依据本身错了"
        )
    else:
        label = "低于预期"
        reading = (
            f"改善 {observed * 100:.1f}%，比预期的 {expected_pct * 100:.1f}% 低 "
            f"{-gap * 100:.1f} 个百分点，超过可识别线。按 14.5 的顺序排查："
            "先查变量泄漏，再查前提条件，最后才怀疑预期"
        )
    return {
        "label": label,
        "baseline_mean": round(base_mean, 2),
        "variant_mean": round(var_mean, 2),
        "observed_pct": round(observed, 4),
        "expected_pct": round(expected_pct, 4),
        "gap_pct": round(gap, 4),
        "detectable_difference": round(line, 4),
        "coefficient_of_variation": round(coefficient_of_variation(baseline), 4),
        "reading": reading,
    }


def boundary_from_config(config: dict) -> str:
    """14.6 wants the crossover in the report, so it is filled in from the config."""
    return (
        f"{config.get('name', 'unnamed')}："
        f"{config['layers']} 层、hidden {config['hidden_size']}、"
        f"KV 头 {config['num_key_value_heads']}、"
        f"GEMM 与 Attention 的交叉点 {crossover_tokens(config)} token。"
        f"换模型后交叉点会移动，本次结论需要重验"
    )


def build_report(
    *,
    expectation: dict,
    workload: dict,
    protocol: dict,
    environment: dict,
    changed: dict,
    baseline: list[float],
    variant: list[float],
    guardrails: dict,
    boundary: dict,
    config: dict | None = None,
    primary_metric: str = "ttft_p50_ms",
) -> dict:
    validate_expectation(expectation)
    _require(
        primary_metric in expectation["magnitude"],
        f"expectation.magnitude 里没有主指标 {primary_metric}",
    )
    expected_pct = expectation["magnitude"][primary_metric]["expected_pct"]
    boundary = dict(boundary)
    if config is not None:
        boundary.setdefault("model", boundary_from_config(config))
    report = {
        "expectation": expectation,
        "fixed": {
            "workload": workload,
            "protocol": protocol,
            "environment": environment,
        },
        "changed": changed,
        "results": {
            "primary_metric": primary_metric,
            "baseline": baseline,
            "variant": variant,
        },
        "guardrails": guardrails,
        "verdict": judge(baseline, variant, expected_pct),
        "boundary": boundary,
    }
    validate_report(report)
    return report


def print_summary(report: dict) -> None:
    v = report["verdict"]
    changed = next(iter(report["changed"].items()))
    print(f"改动      {changed[0]} = {changed[1]}")
    print(f"主指标    {report['results']['primary_metric']}")
    print(f"Baseline  {report['results']['baseline']}  均值 {v['baseline_mean']}")
    print(f"Variant   {report['results']['variant']}  均值 {v['variant_mean']}")
    print(f"可识别线  {v['detectable_difference'] * 100:.1f}%"
          f"  （t × √(2/n) × CV，CV = {v['coefficient_of_variation'] * 100:.1f}%）")
    print(f"预期      {v['expected_pct'] * 100:.1f}%  实测 {v['observed_pct'] * 100:.1f}%"
          f"  相差 {v['gap_pct'] * 100:+.1f} 个百分点")
    print(f"结论      {v['label']}")
    print(f"解读      {v['reading']}")
    for name, value in report["guardrails"].items():
        print(f"护栏      {name}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=None,
                        help="已有的实验报告，检查它是否自洽")
    parser.add_argument("--model-config", type=Path, default=None,
                        help="第 11 章那份共享配置，用来自动填 boundary.model")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.report is None:
        print(
            "本章 Demo 需要真实 vLLM 服务采集数据。"
            "用 --report 检查一份已有报告，"
            "例如 content/ch14/evidence/prefill-experiment-sample.json"
        )
        return 2

    doc = json.loads(args.report.read_text(encoding="utf-8"))
    rounds = doc.get("rounds")
    reports = rounds if isinstance(rounds, list) else [doc]
    try:
        if args.model_config is not None:
            load_config(json.loads(args.model_config.read_text(encoding="utf-8")))
        for i, one in enumerate(reports, start=1):
            validate_report(one)
            if len(reports) > 1:
                print(f"--- 第 {i} 轮 ---")
            print_summary(one)
    except (ExperimentError, ModelError) as exc:
        print(f"REJECTED: {exc}")
        return 1

    print(f"\nOK: {len(reports)} 轮报告全部自洽")
    if args.output is not None:
        args.output.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
