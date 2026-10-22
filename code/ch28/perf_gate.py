#!/usr/bin/env python3
"""A release gate: compare against a fixed baseline, not against last time.

28.1 is the whole argument: 性能退化的典型形态是持续的小幅累积，而每一次都在
噪声范围内。告警发现不了它，因为告警的阈值是按当前正常水平设的，而当前正常水平
自己在漂移。

Subcommands:

  run       check one result against a baseline: thresholds, assertions,
            quality, saturation. Offline once the numbers exist.
  baseline  promote a result to be the new baseline. Deliberately hard.
  drift     28.1's arithmetic: what a sequence of within-threshold regressions
            multiplies to. Offline.
  threshold 28.3's rule: a threshold must exceed the measured variation. It
            also prints what the threshold costs: the false-alarm rate per
            metric and across five, and the detection rate for a real
            regression, with one run and with three runs a side.
            Offline.

Four things this script refuses to do:

  It will not promote a baseline automatically. 28.3 says both cases that
  justify a new baseline need人工确认, so `promote` requires `--reason` and
  `--approver` and refuses on a failed result. 28.8 案例二 is what happens
  without this.

  It will not accept a threshold at or below the benchmark's own variation.
  28.3 案例一 is a gate with a 5% threshold on a 9% CV benchmark: it fired on
  noise until someone added a skip condition to CI.

  It will not pass a result that only compared latency. 28.4 names three silent
  regressions that latency cannot see, so a run without assertions, without a
  quality score when precision changed, or without a near-saturation datapoint
  comes back as `warn` at best.

  It will not compare against a baseline collected on a different environment
  fingerprint or workload hash. Two numbers from two environments are not a
  comparison.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

MODES = ("quick", "full", "release")

# 28.3 那张按指标分的阈值表。
DEFAULT_THRESHOLDS = {
    "p50_latency_ms": 0.05,
    "p95_latency_ms": 0.10,
    "throughput_tps": 0.05,
    "peak_memory_gib": 0.02,
}
# P99 只做观察，不做阻断（28.3）。
OBSERVE_ONLY = ("p99_latency_ms",)

# 越小越好的指标；其余按越大越好处理。
LOWER_IS_BETTER = ("p50_latency_ms", "p95_latency_ms", "p99_latency_ms",
                   "peak_memory_gib")

# 双向判的指标：它的波动极小，所以往哪边动超过阈值都是真实的变化。显存降两成
# 多半意味着精度或某个配置被悄悄改了（28.3、28.7 那份静默样例），只判变差那
# 一边会把这半个信号丢掉。
BIDIRECTIONAL = ("peak_memory_gib",)

# 28.4 的三类静默回归。
SILENT_KINDS = ("quality", "config", "saturation")

# 28.3 原则一：阈值设在两到三倍波动处。
# 下限不是「两倍 CV」：各跑 3 轮时它是第 7.3 节那条可识别线 2.27 × CV，
# 各跑 1 轮时是 1.96 × √2 × CV ≈ 2.77 × CV。两倍那个说法比两者都低，
# 会放过一档必然持续误报的阈值（28.3，Part 6 审阅 P1-15）。
IDENTIFICATION_LINE_3_RUNS = 2.7764 * math.sqrt(2 / 3)  # ≈ 2.27
IDENTIFICATION_LINE_1_RUN = 1.96 * math.sqrt(2)         # ≈ 2.77
THRESHOLD_MULTIPLE = (IDENTIFICATION_LINE_3_RUNS, 3.0)


class GateError(Exception):
    """An input that cannot support the verdict asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise GateError(message)


# --------------------------------------------------------------------------
# 28.1 漂移
# --------------------------------------------------------------------------

def drift(steps: list[float], threshold: float | None = None) -> dict:
    """一串每次都在阈值内的退化，乘起来是多少。

    28.1: 每一项单独看都在噪声范围内，但它们是乘起来的。
    """
    _require(bool(steps), "至少要给一次退化")
    for s in steps:
        _require(-1 < s, f"退化幅度 {s} 不合法")
    total = 1.0
    rows = []
    for i, s in enumerate(steps, 1):
        total *= (1 + s)
        rows.append({"step": i, "regression": s,
                     "cumulative": round(total, 4),
                     "within_threshold": (None if threshold is None
                                          else s <= threshold)})
    out = {
        "steps": rows,
        "cumulative": round(total, 4),
        "mean_step": round(sum(steps) / len(steps), 4),
        "reading": (f"{len(steps)} 次退化累积成 {total:.2f} 倍，"
                    f"平均每次 {sum(steps)/len(steps):.1%}"),
    }
    if threshold is not None:
        over = [r["step"] for r in rows if not r["within_threshold"]]
        out["threshold"] = threshold
        out["steps_over_threshold"] = over
        out["all_within_threshold"] = not over
        if over:
            out["reading"] += (f"。注意第 {over} 次超过了 {threshold:.0%} 的阈值，"
                               "它们会被门禁拦住，不属于“每一次都在噪声范围内”那类")
        else:
            out["reading"] += (f"，而且每一次都在 {threshold:.0%} 的阈值以内，"
                               "门禁一次都不会响")
    return out


def steps_to_double(step: float) -> float:
    """每次退化 step，多少次翻倍。"""
    _require(0 < step < 1, f"每次退化 {step} 要在 (0, 1) 内")
    return math.log(2) / math.log(1 + step)


# --------------------------------------------------------------------------
# 28.3 阈值
# --------------------------------------------------------------------------

def _normal_sf(z: float) -> float:
    """标准正态分布的上尾概率。"""
    return 0.5 * math.erfc(z / math.sqrt(2))


def gate_error_rates(cv: float, threshold: float, *, runs: int = 1,
                     metrics: int = 5, regression: float | None = None) -> dict:
    """28.3：一个阈值的误报率和检出率。

    候选和基线各跑 runs 轮取均值，两边的差值的波动约 CV × √(2/runs)。没有回归时
    差值越过阈值的概率就是单个指标的误报率；metrics 个指标一起判、各自独立时，
    至少一个误报的概率是 1 − (1 − p)^metrics。真实回归为 regression 时，差值越过
    阈值的概率就是检出率。
    """
    _require(0 < cv < 1 and 0 < threshold < 1, "变异系数和阈值都要在 (0, 1) 内")
    _require(runs >= 1 and metrics >= 1, "轮数和指标数至少是 1")
    sd = cv * math.sqrt(2 / runs)
    false_alarm = _normal_sf(threshold / sd)
    regression = threshold if regression is None else regression
    detection = _normal_sf((threshold - regression) / sd)
    return {
        "runs": runs,
        "difference_sd": round(sd, 4),
        "false_alarm_per_metric": round(false_alarm, 4),
        "false_alarm_any_of": round(1 - (1 - false_alarm) ** metrics, 4),
        "metrics": metrics,
        "regression": regression,
        "detection": round(detection, 4),
    }


def threshold_advice(cv: float, multiple: float = 3.0) -> dict:
    """阈值必须大于实测波动，经验做法是两到三倍；同时报误报率和检出率。"""
    _require(0 < cv < 1, f"变异系数 {cv} 要在 (0, 1) 内")
    lo, hi = THRESHOLD_MULTIPLE
    # 建议值取整到百分位，误报率和检出率都按这个取整后的阈值算，免得报出来的
    # 数和真正写进配置的阈值对不上。
    recommended = round(cv * multiple + 1e-9, 2)
    single = gate_error_rates(cv, recommended, runs=1)
    triple = gate_error_rates(cv, recommended, runs=3, regression=0.10)
    # 第 7.3 节那条可识别线：两边各跑 3 轮时是 t(0.975, 4) × √(2/3) × CV ≈ 2.27 × CV。
    line3 = IDENTIFICATION_LINE_3_RUNS * cv
    line1 = IDENTIFICATION_LINE_1_RUN * cv
    return {
        "cv": cv,
        "min_usable": round(cv * lo, 4),
        "recommended": round(recommended, 4),
        "identification_line_3_runs": round(line3, 4),
        "min_usable_1_run": round(line1, 4),
        "single_run": single,
        "three_runs": triple,
        "reading": (
            f"变异系数 {cv:.1%}，建议 {recommended:.0%}。下限随轮数变："
            f"两边各 3 轮时是第 7.3 节那条可识别线 {line3:.1%}，"
            f"各 1 轮时是 {line1:.1%}。"
            f"单轮对单轮时差值的波动约 {single['difference_sd']:.1%}，"
            f"每个指标误报约 {single['false_alarm_per_metric']:.1%}，"
            f"{single['metrics']} 个指标一起判约 {single['false_alarm_any_of']:.0%}；"
            f"真实 {recommended:.0%} 的回归只有 {single['detection']:.0%} 被拦住。"
            f"两边各跑 3 轮时，10% 回归的检出率约 {triple['detection']:.0%}。"
            "设在波动以内的门禁会持续误报，两周后大家开始点重试，"
            "一个月后有人在 CI 里加跳过条件（28.8 案例一）。"),
    }


def check_threshold_sanity(thresholds: dict, cv: dict) -> list[str]:
    """把阈值和实测波动逐项对一遍，返回不合格的那些。"""
    bad = []
    for metric, th in thresholds.items():
        c = cv.get(metric)
        if c is None:
            continue
        if th <= c * THRESHOLD_MULTIPLE[0]:
            bad.append(f"{metric}：阈值 {th:.1%} 低于可识别线 "
                       f"{c * THRESHOLD_MULTIPLE[0]:.1%}"
                       f"（变异系数 {c:.1%}，两边各 3 轮）")
    return bad


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def _fingerprint(doc: dict, name: str) -> dict:
    fp = doc.get("environment")
    _require(isinstance(fp, dict) and fp, f"{name} 没有 environment 指纹")
    for field in ("framework_version", "model", "gpu", "workload_hash"):
        _require(fp.get(field), f"{name} 的 environment 缺 {field}")
    return fp


def compare_environments(result: dict, baseline: dict) -> None:
    """28.2 条件二分两类：钉死的和被测的。

    model / gpu / workload_hash 是钉死的那一类，不同就没有可比性。
    framework_version 是被测的那一类：框架升级正是门禁要拦的候选变更之一
    （28.1），把它也要求一致，门禁就没东西可比了。它记录在指纹里，
    不参与这条判断。
    """
    a = _fingerprint(result, "本次结果")
    b = _fingerprint(baseline, "基线")
    diff = [k for k in ("model", "gpu", "workload_hash") if a.get(k) != b.get(k)]
    _require(not diff,
             f"本次结果和基线在 {diff} 上不一致：两个环境下的两个数字不构成对比。"
             "换了这几项要重建基线，不是接着比")


def evaluate_metrics(metrics: dict, baseline_metrics: dict,
                     thresholds: dict) -> dict:
    rows = []
    for name, value in metrics.items():
        base = baseline_metrics.get(name)
        if base in (None, 0):
            continue
        change = value / base - 1
        worse = change if name in LOWER_IS_BETTER else -change
        th = thresholds.get(name)
        observe = name in OBSERVE_ONLY or th is None
        two_sided = name in BIDIRECTIONAL
        moved = abs(change) if two_sided else worse
        row = {
            "metric": name, "value": value, "baseline": base,
            "change": round(change, 4),
            "worse_by": round(worse, 4),
            "threshold": th,
            "two_sided": two_sided,
            "blocking": bool(th) and not observe and moved > th,
            "observe_only": observe,
        }
        if two_sided and row["blocking"] and worse <= th:
            row["why"] = ("降幅超过阈值：这一项几乎不波动，往哪边动都是真实的"
                          "变化，多半是某个配置悄悄改了（28.3）")
        rows.append(row)
    failed = [r["metric"] for r in rows if r["blocking"]]
    return {"rows": rows, "failed": failed}


def check_run(result: dict, baseline: dict, thresholds: dict | None = None,
              mode: str = "full") -> dict:
    _require(mode in MODES, f"--mode 只能是 {list(MODES)}")
    compare_environments(result, baseline)
    thresholds = thresholds or dict(DEFAULT_THRESHOLDS)

    cv = result.get("variation", {})
    bad_thresholds = check_threshold_sanity(thresholds, cv)
    _require(not bad_thresholds,
             "阈值设在了实测波动以内，门禁会持续误报：" + "；".join(bad_thresholds)
             + "。先把波动压下去，再定阈值（28.3 原则一）")

    metrics = evaluate_metrics(result.get("metrics", {}),
                               baseline.get("metrics", {}), thresholds)

    # 28.4 三类静默回归
    silent = {}
    assertions = result.get("assertions") or []
    silent["config"] = {
        "present": bool(assertions),
        "failed": [a["name"] for a in assertions if not a.get("passed")],
    }
    changed = result.get("changed") or []
    touches_precision = any(
        k in str(changed) for k in ("quant", "dtype", "精度", "int8", "fp8"))
    quality = result.get("quality")
    silent["quality"] = {
        "required": touches_precision,
        "present": quality is not None,
        "breached": bool(quality and quality.get("score") is not None
                         and quality.get("floor") is not None
                         and quality["score"] < quality["floor"]),
    }
    saturation = result.get("saturation")
    silent["saturation"] = {"present": saturation is not None}

    blocking = list(metrics["failed"])
    reasons = [f"{m} 超阈值" for m in metrics["failed"]]
    if silent["config"]["failed"]:
        blocking.append("assertions")
        reasons.append(f"断言未通过：{silent['config']['failed']}")
    if silent["quality"]["required"] and not silent["quality"]["present"]:
        blocking.append("quality")
        reasons.append("这次改动动了精度却没有质量数据（28.4 第一类）")
    if silent["quality"]["breached"]:
        blocking.append("quality")
        reasons.append("质量越过底线")

    warnings = []
    if not silent["config"]["present"]:
        warnings.append("没有断言检查，28.4 第二类静默回归发现不了")
    if mode == "release" and not silent["saturation"]["present"]:
        warnings.append("release 档没有接近饱和的压力档位，28.4 第三类发现不了")

    if blocking:
        verdict, code = "fail", 1
    elif warnings:
        verdict, code = "warn", 2
    else:
        verdict, code = "pass", 0

    return {
        "mode": mode,
        "environment": result["environment"],
        "metrics": metrics["rows"],
        "threshold_failed": metrics["failed"],
        "assertions": assertions,
        "silent_regression_checks": silent,
        "verdict": verdict,
        "exit_code": code,
        "blocking_reason": "；".join(reasons) if reasons else None,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# baseline promote
# --------------------------------------------------------------------------

def promote(result_check: dict, *, reason: str | None, approver: str | None,
            kind: str | None) -> dict:
    """28.3：基线只在两种情况下更新，两种都要人工确认。"""
    _require(bool(reason), "promote 必须给 --reason：说明这次为什么该换基线")
    _require(bool(approver), "promote 必须给 --approver：基线更新要有人签字")
    _require(kind in ("improvement", "accepted_regression"),
             "--kind 只能是 improvement 或 accepted_regression："
             "28.3 说基线只在这两种情况下更新")
    _require(result_check["verdict"] != "fail",
             f"这次结果判的是 {result_check['verdict']}，不能提升为基线。"
             "通过即更新基线正是 28.8 案例二那条路")
    return {
        "promoted": True, "reason": reason, "approver": approver, "kind": kind,
        "from_verdict": result_check["verdict"],
        "note": ("基线换了之后，之前所有和旧基线比出来的结论都不能直接沿用。"
                 "28.1 那条纪律是和固定基准比，换基准要留记录。"),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_run(r: dict) -> None:
    print(f"档位              {r['mode']}")
    for row in r["metrics"]:
        mark = "  阻断" if row["blocking"] else ("  仅观察" if row["observe_only"] else "")
        th = "—" if row["threshold"] is None else f"{row['threshold']:.0%}"
        print(f"  {row['metric']:<20}{row['value']:>10}  基线 {row['baseline']:<10}"
              f"变化 {row['change']:+.1%}  阈值 {th}{mark}")
    s = r["silent_regression_checks"]
    print(f"断言              {'有' if s['config']['present'] else '无'}"
          + (f"，未通过 {s['config']['failed']}" if s["config"]["failed"] else ""))
    print(f"质量              需要 {s['quality']['required']}，"
          f"有 {s['quality']['present']}，越界 {s['quality']['breached']}")
    print(f"饱和档位          {'有' if s['saturation']['present'] else '无'}")
    print(f"结论              {r['verdict']}（退出码 {r['exit_code']}）")
    if r["blocking_reason"]:
        print(f"阻断原因          {r['blocking_reason']}")
    for w in r["warnings"]:
        print(f"警告              {w}")


def print_drift(r: dict) -> None:
    for row in r["steps"]:
        mark = ""
        if row["within_threshold"] is False:
            mark = "  超阈值"
        print(f"  第 {row['step']:>2} 次  {row['regression']:+.1%}"
              f"   累计 {row['cumulative']:.3f} 倍{mark}")
    print(f"解读              {r['reading']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_r = sub.add_parser("run", help="一次门禁检查")
    p_r.add_argument("--result", type=Path, required=True)
    p_r.add_argument("--baseline", type=Path, required=True)
    p_r.add_argument("--thresholds", type=Path, default=None)
    p_r.add_argument("--mode", choices=MODES, default="full")
    p_r.add_argument("--output", type=Path, default=None)

    p_b = sub.add_parser("promote", help="把一次结果提升为新基线")
    p_b.add_argument("--result", type=Path, required=True)
    p_b.add_argument("--baseline", type=Path, required=True)
    p_b.add_argument("--reason", default=None)
    p_b.add_argument("--approver", default=None)
    p_b.add_argument("--kind", default=None,
                     choices=("improvement", "accepted_regression"))

    p_d = sub.add_parser("drift", help="28.1 那串小退化乘起来是多少")
    p_d.add_argument("--steps", required=True,
                     help="逗号分隔的退化幅度，例如 0.05,0.04,0.06,0.05,0.04")
    p_d.add_argument("--threshold", type=float, default=None)

    p_t = sub.add_parser("threshold", help="28.3 原则一：阈值要大于实测波动")
    p_t.add_argument("--cv", type=float, required=True)
    p_t.add_argument("--multiple", type=float, default=3.0)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "drift":
            steps = [float(x) for x in args.steps.split(",")]
            print_drift(drift(steps, args.threshold))
            return 0
        if args.cmd == "threshold":
            r = threshold_advice(args.cv, args.multiple)
            print(f"解读              {r['reading']}")
            return 0
        result = json.loads(args.result.read_text(encoding="utf-8"))
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        thresholds = (json.loads(args.thresholds.read_text(encoding="utf-8"))
                      if getattr(args, "thresholds", None) else None)
        check = check_run(result, baseline, thresholds,
                          getattr(args, "mode", "full"))
        if args.cmd == "run":
            print_run(check)
            if args.output is not None:
                args.output.write_text(
                    json.dumps(check, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
            return check["exit_code"]
        r = promote(check, reason=args.reason, approver=args.approver,
                    kind=args.kind)
        print(f"已提升为基线      {r['kind']}，批准人 {r['approver']}")
        print(f"理由              {r['reason']}")
        print(f"注意              {r['note']}")
        return 0
    except GateError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
