#!/usr/bin/env python3
"""The whole-chain experiment: split the SLO, check the report, guard the result.

This is Part 5's last Demo, and it does the three things 25.3, 25.6 and 25.7 each
ask for.

  budget   split an end-to-end target across the layers, and refuse when the
           split is impossible instead of returning a plausible-looking one.
           Orchestration is budgeted per step, the model service per model
           call; given S and ρ it also checks that the queue fits (20.6).
           This is the subcommand worth running first, because 25.3's whole
           point is that a budget exposes an impossible goal before you start.
  run      check a whole-chain experiment report: nine-dimension scorecard,
           per-layer budget comparison, cross-layer effects, five boundaries.
  guard    run 25.7's regression assertions. Its exit code goes straight into
           a deployment pipeline.

`run` reuses Chapter 14's experiment discipline the way Chapter 19 does, so the
four verdicts and the "expectation written down beforehand" rule are the same
objects, not restatements.

Three hard checks, in the order 25.8 lists them:

  1. `layer_breakdown` must state the load level it was collected under. 25.2:
     a breakdown taken at idle is a different table, and optimising against it
     means optimising something that is not the bottleneck at peak.
  2. `cross_layer` may not be empty. A cross-layer experiment that recorded no
     effect on other layers did not look.
  3. `boundary` has five items, not Chapter 14's four. The fifth is the chain
     structure, because when the chain changes the conclusion does not hold.

And one rule none of the three can express: quality, task success and preemption
are vetoes, not votes (25.6). Six dimensions improving does not outrank one of
those three getting worse.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch14"))

# 第 14 章拥有共享的实验纪律；第 19 章也是这么引它的。
from prefill_experiment import VERDICTS  # noqa: E402

# 25.6 的十个维度，顺序就是表里的顺序。质量自己占一维：它是三项否决项之一，
# 藏在别的维度的子字段里时，读者按表取数会取不到（第 19 章那份记分卡同理）。
DIMENSIONS = ("end_to_end", "quality", "abandonment", "orchestration",
              "retrieval", "model_serving", "capacity", "governance",
              "routing", "cost")

# 25.6：其中三项是否决项。
VETO_DIMENSIONS = ("task_success_rate", "quality", "preemption_count")

# 25.8：比第 14 章多一项链路结构。
BOUNDARY_ITEMS = ("model", "load", "hardware", "config", "chain_structure")

# 25.3 的层级，顺序即预算表的顺序。
LAYERS = ("orchestration", "retrieval", "model_serving", "tools")

# 第 14 章那四种结论在全链路场景下各自意味着什么。标签本身由 ch14 拥有，
# 这里只补一句在这一章语境下的读法。
VERDICT_READING = {
    "符合预期": "改动生效且幅度对得上，可以进入下一项",
    "低于预期": "改动生效但幅度不够，先查预期是怎么估的，再决定要不要继续投入",
    "高于预期": "幅度超过预期，同样要查：多半是同时动了两件事，或者基线测错了",
    "在波动内不可分辨": "主指标测不出来，这是一个合法且诚实的结论；"
                        "收益若出现在别的维度，就写在那一维上，不要往主指标上凑",
}

# 25.7 的五条断言。前两条和最后一条是布尔判据，中间两个是阈值。
GUARD_RULES = ("prefix_cache_hit_rate", "prompt_order_fixed_first",
               "load_skew", "steps_p95", "attention_kernel_allowlisted")


class ExperimentError(Exception):
    """A report or a budget that cannot support the conclusion asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ExperimentError(message)


# --------------------------------------------------------------------------
# budget: 25.3
# --------------------------------------------------------------------------

def max_feasible_calls(model_serving_ms: float,
                       measured_call_ms: float) -> int:
    """能放进模型服务预算的最多模型调用次数：`floor(预算 / 单次纯计算)`。

    25.3: 5000 ms 的预算、480 ms 的单次纯计算，`5000 / 480 = 10.4`，所以连排队都
    不算，最多也只能放 10 次调用。
    """
    _require(model_serving_ms > 0, "模型服务预算必须为正")
    _require(measured_call_ms > 0, "实测单次纯计算必须为正")
    return math.floor(model_serving_ms / measured_call_ms)


def queue_ms(service_time_ms: float, rho: float) -> float:
    """20.6 的单服务台式子：W_q ≈ S × ρ/(1−ρ)。"""
    _require(service_time_ms > 0, "S 必须为正")
    _require(0 <= rho < 1, f"负载率 {rho} 不在 [0, 1) 内")
    return service_time_ms * rho / (1.0 - rho)


def max_rho(queue_allowance_ms: float, service_time_ms: float) -> float:
    """排队预算 q 允许的最高负载率：ρ/(1−ρ) ≤ q/S，即 ρ ≤ q/(S + q)。"""
    _require(service_time_ms > 0, "S 必须为正")
    if queue_allowance_ms <= 0:
        return 0.0
    return queue_allowance_ms / (service_time_ms + queue_allowance_ms)


def build_budget(*, total_ms: float, steps_p95: int,
                 per_step_orchestration_ms: float,
                 retrieval_ms: float, tools_ms: float,
                 model_serving_ms: float,
                 measured_call_compute_ms: float,
                 model_calls_p95: int | None = None,
                 service_time_ms: float | None = None,
                 rho: float | None = None) -> dict:
    """25.3 那张表，外加它自己的可行性判断。

    编排层按步数算，模型服务按模型调用次数算：34 步里只有约 7 次是模型调用，
    其余是编排层串行执行的工具调用。没给调用次数时按每步一次调用算。

    The infeasibility checks come first and raise. 25.3 says the contradiction
    must be resolved before any work starts, not discovered halfway through, and
    a function that returns a plausible-looking allocation is the thing that
    lets it be discovered halfway through. Two checks, in order: the pure compute
    must fit in the per-call budget, and, given S and ρ, so must the queue.
    """
    _require(total_ms > 0, "总预算必须为正")
    _require(steps_p95 >= 1, "步数至少 1")
    calls = model_calls_p95 if model_calls_p95 is not None else steps_p95
    _require(calls >= 1, "模型调用次数至少 1")
    orchestration_ms = steps_p95 * per_step_orchestration_ms
    allocated = (orchestration_ms + retrieval_ms + model_serving_ms + tools_ms)
    _require(allocated <= total_ms,
             f"各层之和 {round(allocated)} ms 已经超过总预算 {round(total_ms)} ms，"
             "这份分配不成立")
    per_call = model_serving_ms / calls
    limit = max_feasible_calls(model_serving_ms, measured_call_compute_ms)
    _require(per_call >= measured_call_compute_ms,
             f"模型服务 {round(model_serving_ms)} ms 分给 {calls} 次调用，"
             f"每次只有 {round(per_call)} ms，而当前单次调用的纯计算就要 "
             f"{round(measured_call_compute_ms)} ms。这说明两件事之一："
             f"要么调用次数还得再降（这份预算下最多 {limit} 次），"
             "要么这个 SLO 定错了。这个矛盾必须在动手之前解决")
    allowance = per_call - measured_call_compute_ms
    queue_part: dict = {}
    if service_time_ms is not None:
        ceiling_rho = max_rho(allowance, service_time_ms)
        queue_part = {"service_time_ms": service_time_ms,
                      "rho_max": round(ceiling_rho, 4)}
        if rho is not None:
            q = queue_ms(service_time_ms, rho)
            queue_part.update({"rho": rho, "queue_per_call_ms": round(q, 1)})
            _require(q <= allowance,
                     f"每次调用 {round(per_call)} ms，扣掉纯计算 "
                     f"{round(measured_call_compute_ms)} ms，留给排队的只有 "
                     f"{round(allowance)} ms；负载率 {rho} 时按 20.6 每次排队约 "
                     f"{round(q)} ms（S = {service_time_ms} ms）。"
                     f"要么把负载率守在 {round(ceiling_rho, 2)} 以下（准入、容量、"
                     "减少调用），要么这个 SLO 定错了。这个矛盾必须在动手之前解决")
    unallocated = total_ms - allocated
    result = {
        "total_ms": total_ms,
        "steps_p95": steps_p95,
        "model_calls_p95": calls,
        "layers": {
            "orchestration": {
                "ms": orchestration_ms,
                "basis": (f"步数 P95 = {steps_p95}，"
                          f"每步编排开销 {round(per_step_orchestration_ms)} ms")},
            "retrieval": {"ms": retrieval_ms, "basis": "含重排"},
            "model_serving": {
                "ms": model_serving_ms,
                "basis": (f"含排队，按 {calls} 次模型调用计，"
                          f"每次 {round(per_call)} ms")},
            "tools": {"ms": tools_ms, "basis": "代码执行设超时"},
        },
        "unallocated_ms": unallocated,
        "unallocated_basis": (
            "余量是整条链路共用的一份，不在纸面上分给某一层，"
            "理由和 5.9 那份预算表一样"),
        "per_call_model_serving_ms": round(per_call, 3),
        "measured_call_compute_ms": measured_call_compute_ms,
        "queue_allowance_per_call_ms": round(allowance, 3),
        "max_feasible_calls": limit,
        "feasible": True,
        "acceptance": ("这张表是一条 P95 那类任务的时间怎么分；验收只看整条链路的 "
                       "P95 任务完成时间，不拿各层自己的 P95 相加（第 5 章）"),
    }
    result.update(queue_part)
    return result


# --------------------------------------------------------------------------
# guard: 25.7
# --------------------------------------------------------------------------

def cacheable_share_from_calls(calls: int) -> float:
    """1 − 2/调用次数：追加式上下文里可复用前缀的占比。

    25.7 的推导：每次调用里全新的只是上一次之后新增的那一段，把各次的全新部分
    加起来正好是最后一次调用的输入；累计输入按 24.3 那个梯形式子约是
    `调用次数 × 末次输入 / 2`。两者相除，全新部分约占 `2 / 调用次数`。
    """
    _require(calls >= 2, "至少两次调用才有可复用的前缀")
    return 1.0 - 2.0 / calls


def hit_rate_ceiling(cacheable_share: float, route_hit: float) -> float:
    """13.3 四刀式子里剩下的两刀在一个任务内部都接近 1，所以天花板是这两项之积。"""
    _require(0 <= cacheable_share <= 1, "可缓存占比要在 [0, 1] 内")
    _require(0 < route_hit <= 1, "路由命中要在 (0, 1] 内")
    return cacheable_share * route_hit


def guard(rules: dict) -> dict:
    """25.7 的五条断言。每条都要带 `basis`，没有依据的门禁半年后没人敢改。"""
    missing = [r for r in GUARD_RULES if r not in rules]
    _require(not missing, f"缺断言：{missing}；25.7 那五条一条都不能少")
    results = []
    for name in GUARD_RULES:
        rule = rules[name]
        _require("basis" in rule and rule["basis"],
                 f"断言 {name} 没有写 basis："
                 "25.7 要求每条断言后面都写清阈值是从哪里来的，"
                 "否则半年后没人敢改它，也没人敢相信它")
        _require("actual" in rule, f"断言 {name} 没有实测值")
        actual = rule["actual"]
        if isinstance(actual, bool):
            passed = actual
            detail = "布尔判据"
        else:
            threshold = rule.get("threshold")
            _require(threshold is not None,
                     f"断言 {name} 是数值判据但没有阈值")
            direction = rule.get("direction", "min")
            _require(direction in ("min", "max"),
                     f"断言 {name} 的 direction 只能是 min 或 max")
            # 闭区间：阈值本身是设计点，不是越线。25.7 那条「步数 P95 ≤ 10」
            # 的预算正是按 10 步给的，P95 正好等于 10 不该判红。
            passed = (actual >= threshold if direction == "min"
                      else actual <= threshold)
            detail = (f"实测 {actual}，要求"
                      f"{'不低于' if direction == 'min' else '不超过'} {threshold}")
        results.append({"rule": name, "passed": passed, "detail": detail,
                        "basis": rule["basis"]})
    failed = [r["rule"] for r in results if not r["passed"]]
    return {
        "rules": results,
        "failed": failed,
        "passed": not failed,
        "reading": ("五条断言全部通过" if not failed
                    else f"以下断言未通过：{failed}。部署应当中止"),
    }


def ceiling_check(*, calls: int, route_hit: float,
                  threshold: float) -> dict:
    """25.7 那条命中率断言的依据，算出来而不是写上去。"""
    cacheable = cacheable_share_from_calls(calls)
    ceiling = hit_rate_ceiling(cacheable, route_hit)
    # 门槛贴着天花板和超过天花板是同一回事：断言必然长期红着。用一个小的余量界
    # 判，否则 0.80 × 0.9 的浮点尾数会让“门槛正好等于天花板”被判成够得着。
    headroom = ceiling - threshold
    reachable = headroom > 1e-9
    return {
        "calls": calls,
        "cacheable_share": round(cacheable, 4),
        "route_hit": route_hit,
        "ceiling": round(ceiling, 4),
        "threshold": threshold,
        "headroom": round(headroom, 4),
        "reachable": reachable,
        "reading": (
            f"{calls} 次调用的追加式上下文里可缓存占比约 "
            f"{round(cacheable * 100, 1)}%，前缀亲和后的路由命中 {route_hit}，"
            f"天花板 {round(ceiling * 100, 1)}%，门槛 "
            f"{round(threshold * 100, 1)}% 留 "
            f"{round((ceiling - threshold) * 100, 1)} 个点的余量"
            if reachable else
            f"天花板只有 {round(ceiling * 100, 1)}%，低于门槛 "
            f"{round(threshold * 100, 1)}%：这条断言必然长期红着，"
            "先把门槛降到天花板以下，或者提高可缓存占比"),
    }


# --------------------------------------------------------------------------
# run: 25.6 / 25.8
# --------------------------------------------------------------------------

def check_layer_breakdown(block: object) -> dict:
    _require(isinstance(block, dict), "layer_breakdown 缺失或格式不对")
    load = block.get("collected_under_load")
    _require(load is not None,
             "layer_breakdown 没有标注采集时的负载水平："
             "25.2 说过分解要在压测下做，空闲时排队为零，"
             "那张表会完全是另一个样子，然后你会去优化一个在高峰期"
             "根本不是瓶颈的环节")
    _require(load not in ("idle", "空闲"),
             "layer_breakdown 是空闲状态下采集的，不可用于决策（25.2）")
    shares = block.get("shares")
    _require(isinstance(shares, dict) and shares, "layer_breakdown 没有 shares")
    missing = [l for l in LAYERS if l not in shares]
    _require(not missing, f"layer_breakdown 缺这几层：{missing}")
    total = sum(shares.values())
    _require(abs(total - 1.0) <= 0.02,
             f"各层占比之和是 {round(total, 4)}，不等于 1："
             "要么有一层漏了，要么某一段的时间被算了两遍")
    ranked = sorted(shares, key=lambda k: shares[k], reverse=True)
    return {"collected_under_load": load, "shares": shares,
            "largest_layer": ranked[0],
            "largest_share": shares[ranked[0]]}


def check_scorecard(block: object) -> dict:
    _require(isinstance(block, dict), "scorecard 缺失或格式不对")
    missing = [d for d in DIMENSIONS if d not in block]
    _require(not missing,
             f"十维记分卡缺这几维：{missing}。"
             "25.6 说少任何一项都对应着前面某个案例里犯过的错")
    vetoes = {}
    for name in VETO_DIMENSIONS:
        found = None
        for dim in block.values():
            if isinstance(dim, dict) and name in dim:
                found = dim[name]
                break
        _require(found is not None,
                 f"记分卡里找不到否决项 {name}："
                 "25.6 那三项任何一项恶化都不能算成功，所以它们不能缺")
        vetoes[name] = found
    breached = [name for name, value in vetoes.items()
                if value.get("worsened")]
    improved = [d for d, block_ in block.items()
                if isinstance(block_, dict) and block_.get("improved")]
    return {
        "dimensions": list(block),
        "vetoes": vetoes,
        "vetoes_breached": breached,
        "dimensions_improved": improved,
        "veto_holds": not breached,
        "reading": (
            f"{len(improved)} 个维度改善，否决项未越线" if not breached else
            f"{len(improved)} 个维度改善，但 {breached} 恶化了。"
            "记分卡不是投票：否决项任何一项恶化都不能算成功"),
    }


def _check_layers_add_up(budget_check: dict, breakdown: dict,
                         end_to_end: dict) -> None:
    """各层实测之和要等于端到端 P95，占比也要和实测对得上。

    两张表量的是同一条链路：一份按层给毫秒数，一份按层给占比。对不上时
    不是四舍五入的事，是某一层漏了、某一段算了两遍，或者两张表来自不同
    的两轮——那样后面每一步推理都站在两组数上（25.8）。
    """
    actuals = {layer: row.get("actual_ms") for layer, row in
               budget_check.items() if row.get("actual_ms") is not None}
    if len(actuals) < len(LAYERS):
        return
    total = sum(actuals.values())
    p95 = end_to_end.get("p95_task_ms")
    if p95:
        _require(abs(total - p95) <= 0.1 * p95,
                 f"各层实测加起来 {round(total)} ms，端到端 P95 是 {p95} ms，差超过一成：要么有一层漏了，要么某一段的时间被算了两遍")
    shares = breakdown["shares"]
    for layer, actual in actuals.items():
        if layer not in shares:
            continue
        implied = actual / total
        _require(abs(implied - shares[layer]) <= 0.03,
                 f"{layer} 这一层：实测占 {round(implied * 100, 1)}%，layer_breakdown 写的是 {round(shares[layer] * 100, 1)}%，两张表对不上")


def check_report(doc: dict) -> dict:
    _require(doc.get("expectation"),
             "报告里没有 expectation：第 14 章那条纪律要求预期必须事前写下，"
             "事后补的预期没有判别力")
    breakdown = check_layer_breakdown(doc.get("layer_breakdown"))
    scorecard = check_scorecard(doc.get("scorecard"))

    cross = doc.get("cross_layer")
    _require(isinstance(cross, list) and cross,
             "cross_layer 为空：跨层实验必须记录对其他层指标的影响，"
             "一项都没记的实验是没有看")

    boundary = doc.get("boundary") or {}
    missing = [b for b in BOUNDARY_ITEMS if not boundary.get(b)]
    _require(not missing,
             f"boundary 缺这几项：{missing}。这里比第 14 章多一项 "
             "chain_structure，因为链路变了结论就不成立")

    budget_check = doc.get("budget_check")
    _require(isinstance(budget_check, dict) and budget_check,
             "报告里没有 budget_check：各层实际耗时要和预算逐层对照")
    _check_layers_add_up(budget_check, breakdown,
                         doc.get("scorecard", {}).get("end_to_end", {}))
    overruns = [layer for layer, row in budget_check.items()
                if row.get("actual_ms") is not None
                and row.get("budget_ms") is not None
                and row["actual_ms"] > row["budget_ms"]]

    verdict = doc.get("verdict") or {}
    label = verdict.get("label")
    _require(label in VERDICTS,
             f"结论 {label!r} 不在第 14 章那四种里：{list(VERDICTS)}")
    claimed_pass = bool(verdict.get("passed"))
    # 否决项越线时报告不能写通过，这是记分卡存在的理由。
    _require(not (claimed_pass and scorecard["vetoes_breached"]),
             f"报告写着通过，而否决项 {scorecard['vetoes_breached']} 恶化了："
             "六个维度改善抵不过一个否决项越线（25.6）")

    reading = VERDICT_READING[label]
    baseline = (doc["expectation"] or {}).get("baseline_ms")
    after = (doc.get("scorecard", {}).get("end_to_end", {})
             .get("p95_task_ms"))
    if label == "低于预期" and baseline and after and after > baseline:
        # 「幅度不够」读的是改善不足，这一轮是主指标反向，两件事不能同一句话。
        reading = ("改动让主指标变差了，不是幅度不够：先把这一轮回滚，"
                   "再拆成单项重做（25.4 那条一次只改一项）")

    return {
        "variant": doc.get("variant"),
        "expectation": doc["expectation"],
        "layer_breakdown": breakdown,
        "budget_check": budget_check,
        "budget_overruns": overruns,
        "scorecard": scorecard,
        "cross_layer": cross,
        "verdict": {"label": label, "reading": reading,
                    "passed": claimed_pass},
        "boundary": boundary,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_budget(r: dict) -> None:
    print(f"总预算            {round(r['total_ms'])} ms")
    for name in LAYERS:
        row = r["layers"][name]
        print(f"  {name:<16}{round(row['ms']):>6} ms   {row['basis']}")
    print(f"  {'未分配余量':<14}{round(r['unallocated_ms']):>6} ms   "
          f"{r['unallocated_basis']}")
    print(f"每次模型调用      {r['per_call_model_serving_ms']} ms"
          f"（实测纯计算 {r['measured_call_compute_ms']} ms，"
          f"留给排队 {r['queue_allowance_per_call_ms']} ms）")
    if "rho_max" in r:
        print(f"负载率上限        {r['rho_max']}"
              f"（S = {r['service_time_ms']} ms，按 20.6 反推）")
    if "queue_per_call_ms" in r:
        print(f"负载率 {r['rho']} 时      每次排队约 {r['queue_per_call_ms']} ms")
    print(f"这份预算下最多    {r['max_feasible_calls']} 次调用（只算纯计算）")
    print(f"验收              {r['acceptance']}")


def print_run(r: dict) -> None:
    bd = r["layer_breakdown"]
    print(f"变体              {r['variant']}")
    print(f"分解采集于        {bd['collected_under_load']}")
    print(f"最大的一层        {bd['largest_layer']}"
          f"（{round(bd['largest_share'] * 100, 1)}%）")
    print("预算对照")
    for layer, row in r["budget_check"].items():
        mark = "  超支" if layer in r["budget_overruns"] else ""
        print(f"  {layer:<16}实际 {row.get('actual_ms')} / "
              f"预算 {row.get('budget_ms')}{mark}")
    sc = r["scorecard"]
    print(f"记分卡            {len(sc['dimensions'])} 维，"
          f"{len(sc['dimensions_improved'])} 维改善")
    print(f"否决项            {'未越线' if sc['veto_holds'] else sc['vetoes_breached']}")
    print(f"                  {sc['reading']}")
    print(f"跨层影响          {len(r['cross_layer'])} 项")
    for item in r["cross_layer"]:
        print(f"  - {item}")
    print(f"结论              {r['verdict']['label']}"
          f"  {'通过' if r['verdict']['passed'] else '失败'}")
    print(f"                  {r['verdict']['reading']}")
    print(f"边界              {list(r['boundary'])}")


def print_guard(r: dict) -> None:
    for row in r["rules"]:
        mark = "通过" if row["passed"] else "未通过"
        print(f"  [{mark}] {row['rule']}：{row['detail']}")
        print(f"          依据：{row['basis']}")
    print(f"结论              {r['reading']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_b = sub.add_parser("budget", help="25.3 那件事：拆预算并在不可行时报错")
    p_b.add_argument("--slo", type=float, required=True)
    p_b.add_argument("--steps-p95", type=int, required=True,
                     help="编排层按它算")
    p_b.add_argument("--model-calls-p95", type=int, default=None,
                     help="模型服务按它算；不给则按每步一次调用")
    p_b.add_argument("--service-time-ms", type=float, default=None,
                     help="模型服务的 S（20.6），给了就反推负载率上限")
    p_b.add_argument("--rho", type=float, default=None,
                     help="当前负载率；给了就检查排队放不放得下")
    p_b.add_argument("--per-step-orchestration-ms", type=float, default=50.0)
    p_b.add_argument("--retrieval-ms", type=float, default=1200.0)
    p_b.add_argument("--model-serving-ms", type=float, default=5000.0)
    p_b.add_argument("--tools-ms", type=float, default=1000.0)
    p_b.add_argument("--measured-call-compute-ms", type=float, default=480.0)
    p_b.add_argument("--output", type=Path, default=None)

    p_r = sub.add_parser("run", help="检查一份全链路实验报告")
    p_r.add_argument("--report", type=Path, required=True)
    p_r.add_argument("--output", type=Path, default=None)

    p_g = sub.add_parser("guard", help="25.7 那五条断言，退出码可接进 CI")
    p_g.add_argument("--config", type=Path, required=True)
    p_g.add_argument("--output", type=Path, default=None)

    p_c = sub.add_parser("ceiling", help="命中率断言的依据：算出天花板")
    p_c.add_argument("--calls", type=int, required=True,
                     help="P95 任务的模型调用次数")
    p_c.add_argument("--route-hit", type=float, default=0.9)
    p_c.add_argument("--threshold", type=float, default=0.55)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "budget":
            result = build_budget(
                total_ms=args.slo, steps_p95=args.steps_p95,
                per_step_orchestration_ms=args.per_step_orchestration_ms,
                retrieval_ms=args.retrieval_ms, tools_ms=args.tools_ms,
                model_serving_ms=args.model_serving_ms,
                measured_call_compute_ms=args.measured_call_compute_ms,
                model_calls_p95=args.model_calls_p95,
                service_time_ms=args.service_time_ms, rho=args.rho)
            print_budget(result)
        elif args.cmd == "run":
            doc = json.loads(args.report.read_text(encoding="utf-8"))
            result = check_report(doc)
            print_run(result)
        elif args.cmd == "guard":
            rules = json.loads(args.config.read_text(encoding="utf-8"))
            result = guard(rules.get("rules", rules))
            print_guard(result)
            if args.output is not None:
                args.output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
            return 0 if result["passed"] else 1
        else:
            result = ceiling_check(calls=args.calls, route_hit=args.route_hit,
                                  threshold=args.threshold)
            print(f"解读              {result['reading']}")
            return 0 if result["reachable"] else 1
        if args.output is not None:
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}")
        return 0
    except ExperimentError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
