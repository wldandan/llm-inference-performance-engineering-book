"""Measured load curves; no interpolation or unmeasured capacity claims."""

import copy
import math
from collections import defaultdict


def _number(value):
    return (
        value
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
        else None
    )


def _mean(values):
    return sum(values) / len(values) if values and all(_number(x) is not None for x in values) else None


def _conditions(run, variable):
    spec = copy.deepcopy(run.get("spec") or {})
    for key in ("name", "notes"):
        spec.pop(key, None)
    spec.get("load", {}).pop(variable, None)
    return spec


def summarize_sweep(runs):
    warnings, grouped, points = [], defaultdict(list), []
    mode = runs[0].get("spec", {}).get("load", {}).get("mode") if runs else None
    variable = "rate" if mode == "rate" else "concurrency"
    comparable = bool(runs) and all(
        _conditions(run, variable) == _conditions(runs[0], variable) for run in runs
    )
    if not comparable:
        warnings.append("配置未对齐或没有数据，不能视为单变量负载扫描。")
    for run in runs:
        point = _number(run.get("spec", {}).get("load", {}).get(variable))
        if point is None:
            warnings.append("扫描点缺失，无法判断容量。")
            continue
        grouped[point].append(run)
    for value in sorted(grouped):
        batch = grouped[value]
        eligible, reasons = comparable, []
        for run in batch:
            spec, summary = run.get("spec", {}), run.get("summary") or {}
            metrics, quality = summary.get("metrics", {}), summary.get("quality", {})
            if (
                run.get("status") != "completed"
                or not summary.get("sample_count")
                or summary.get("sample_count") != spec.get("load", {}).get("count")
            ):
                reasons.append("实验尚未完整完成。")
            if spec.get("protocol_fixture"):
                reasons.append("协议示例不能证明模型容量。")
            if quality.get("coverage") != 1 or (_number(quality.get("pass_rate")) or 0) < spec.get(
                "goals", {}
            ).get("min_quality_pass_rate", 1):
                reasons.append("质量覆盖或通过率未达标。")
            if any(goal.get("status") != "pass" for goal in summary.get("goals", [])):
                reasons.append("存在失败或未知的目标约束。")
            if metrics.get("client_rejected") or metrics.get("interrupted"):
                reasons.append("存在客户端拒绝或中断，负载没有完整执行。")
            if _number(metrics.get("goodput_per_s")) is None:
                reasons.append("有效吞吐缺少可用证据。")
            if variable == "rate":
                sent_rate = _number(metrics.get("actual_sent_per_s"))
                if sent_rate is None or sent_rate < value * 0.9:
                    warning = f"到达速率 {value} 的实际发送速率缺失或低于目标的 90%；检查发压端和样本量，不能直接归因于模型。"
                    reasons.append(warning)
                    warnings.append(warning)
        eligible = eligible and not reasons
        measures = [run.get("summary", {}).get("metrics", {}) for run in batch]
        points.append(
            {
                "value": value,
                "run_ids": [run["id"] for run in batch],
                "repeats": len(batch),
                "requests_per_s": _mean([m.get("requests_per_s") for m in measures]),
                "goodput_per_s": _mean([m.get("goodput_per_s") for m in measures]),
                "p95_e2e_ms": _mean([m.get("e2e_ms", {}).get("p95") for m in measures]),
                "error_rate": _mean([m.get("error_rate") for m in measures]),
                "eligible": eligible,
                "reasons": list(dict.fromkeys(reasons)),
            }
        )
    qualifying = [point for point in points if point["eligible"]]
    best = max(qualifying, key=lambda point: point["goodput_per_s"], default=None)
    return {
        "variable": variable,
        "comparable": comparable,
        "points": points,
        "eligible_points": [point["value"] for point in qualifying],
        "best_point": best["value"] if best else None,
        "warnings": list(dict.fromkeys(warnings))
        + ["只比较已测点；重复实验的数值为算术均值，不合并成新的 P95，也不推断点间容量。"],
    }
