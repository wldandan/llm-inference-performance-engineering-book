#!/usr/bin/env python3
"""Build a task-level profile of an Agent service, and find the tail's waste.

24.1's whole argument is that every per-call metric can be green while the task
is unacceptable. So this script reports nothing per call: every number it gives
is per task.

Three subcommands, all offline once the traces exist:

  profile   the ten fields 24.7 lists, from a JSONL of task traces.
  tail      the tasks above a percentile, their step sequences, and the waste
            patterns in them. 24.7 calls this the most useful tool in the
            chapter, and it is: one pattern fixed improves many tasks.
  step-slo  24.2's p^N arithmetic in both directions, and 24.6's warning about
            when it does not apply.

Four things this script refuses to do:

  It will not report tool time without per-tool spans. 24.4: without them, tool
  waiting does not exist in your monitoring, and you only see "the task is slow".

  It will not silently normalise away unaccounted time. If the spans do not add
  up to the task duration, the remainder is reported as its own field, the way
  ch05 reports unallocated budget. A share that sums to 1 by construction hides
  exactly the gap worth looking at.

  It will not apply p^N to an agent that retries. 24.2 says so itself and 24.6
  gives the replacement: define 达标 as "task finished inside the deadline", not
  as a product over steps.

  It will not estimate cumulative tokens from a step count and an average. That
  is the mistake 案例二 is about. The trapezoid needs the first and last step.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

# 24.7 fixes the profile's field names.
PROFILE_FIELDS = ("task_count", "steps", "model_calls", "duration",
                  "llm_time_share", "tool_time_share", "context_growth",
                  "cumulative_tokens", "prefix_hit_rate", "abandon_rate",
                  "step_limit_rate", "unaccounted_time_share")

# 24.2's table: 单步 P95 达标时，任务级达标率随步数的衰减。
STEP_SLO_ROWS = (5, 8, 15, 35)

# tail 找的三种浪费模式，就是 24.7 列的那三种。
WASTE_PATTERNS = ("repeated_tool", "oscillation", "same_resource")

# 一个模式要算数的最小长度。连续两次调同一个工具是正常的，四次就不是。
REPEAT_THRESHOLD = 4
OSCILLATION_THRESHOLD = 4
SAME_RESOURCE_THRESHOLD = 4


class ProfileError(Exception):
    """A trace set that cannot support the reading asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ProfileError(message)


# --------------------------------------------------------------------------
# 24.2 / 24.6: the step SLO arithmetic
# --------------------------------------------------------------------------

def task_pass_rate(step_pass_rate: float, steps: int) -> float:
    """p^N. 24.2: 每一步都要成功、各步独立时，任务成功率是 p 的 N 次方。"""
    _require(0 < step_pass_rate <= 1,
             f"单步达标率 {step_pass_rate} 要在 (0, 1] 内")
    _require(steps >= 1, "步数至少 1")
    return step_pass_rate ** steps


def required_step_pass_rate(task_target: float, steps: int) -> float:
    """p = target^(1/N). 24.2 的反推：15 步做到 95% 需要单步 99.66%。"""
    _require(0 < task_target <= 1, f"任务级目标 {task_target} 要在 (0, 1] 内")
    _require(steps >= 1, "步数至少 1")
    return task_target ** (1.0 / steps)


def step_slo_table(step_pass_rate: float = 0.95,
                   step_counts=STEP_SLO_ROWS) -> list[dict]:
    return [{"steps": n,
             "task_pass_rate": round(task_pass_rate(step_pass_rate, n), 6),
             "percent": round(task_pass_rate(step_pass_rate, n) * 100)}
            for n in step_counts]


def step_slo(step_pass_rate: float, steps: int, task_target: float | None,
             retries_enabled: bool = False) -> dict:
    # 24.2 自己说了这条估算有两处会偏，其中带重试那一处足以让乘法模型失效。
    _require(not retries_enabled,
             "这个 Agent 开了重试，不能用 p 的 N 次方来估任务级达标率："
             "带重试的 Agent 可以多花两三步换一次成功，任务整体仍然达标。"
             "按 24.6 的做法，达标要定成“任务在时限内完成”的比例，"
             "用 profile 的 duration 分布和目标时限算，不是按步累乘")
    table = step_slo_table(step_pass_rate)
    result = {
        "step_pass_rate": step_pass_rate,
        "table": table,
        "at_steps": steps,
        "task_pass_rate": round(task_pass_rate(step_pass_rate, steps), 6),
        "reading": (
            f"单步 {round(step_pass_rate * 100, 2)}% 达标，{steps} 步任务的"
            f"任务级达标率约 "
            f"{round(task_pass_rate(step_pass_rate, steps) * 100)}%。"
            "用户投诉的是任务，而看板上绿着的是单步。"),
        "caveats": [
            "p 的 N 次方算的是“每一步都成功”的比例，对工具调用成功率是准的；"
            "对延迟，用户关心的是任务总时长，要直接测它的分布，不是按步累乘。",
            "各步并不真的独立。正相关让“每一步都达标”的比例比式子更高"
            "（8 步、单步 95%、相关系数 0.3 时约 73%，不是 66%），"
            "变重的是任务总时长的尾巴：几步一起慢，总时长的 P95 就被拉长。",
            "带重试的 Agent 不适用这条式子，见 24.6。",
        ],
    }
    if task_target is not None:
        need = required_step_pass_rate(task_target, steps)
        result["task_target"] = task_target
        result["required_step_pass_rate"] = round(need, 6)
        result["required_reading"] = (
            f"要让 {steps} 步任务的任务级达标率做到 "
            f"{round(task_target * 100, 2)}%，单步需要 "
            f"{round(need * 100, 2)}%。把单步从 "
            f"{round(step_pass_rate * 100, 2)}% 抬到 {round(need * 100, 2)}% "
            "通常比砍掉一半步数难得多。")
        half = max(1, steps // 2)
        result["halved_steps"] = half
        result["halved_task_pass_rate"] = round(
            task_pass_rate(step_pass_rate, half), 6)
    return result


# --------------------------------------------------------------------------
# 24.3: cumulative tokens
# --------------------------------------------------------------------------

def trapezoid_tokens(steps: int, first_step_tokens: float,
                     last_step_tokens: float) -> float:
    """步数 × (首步 + 末步) / 2。24.3 那个梯形式子。"""
    _require(steps >= 1, "步数至少 1")
    _require(first_step_tokens > 0 and last_step_tokens > 0,
             "首步和末步的 token 数必须为正")
    return steps * (first_step_tokens + last_step_tokens) / 2.0


def cumulative_tokens(per_step_inputs: list[float]) -> dict:
    """Exact sum plus the trapezoid estimate, and how far apart they are.

    Both are reported because 24.3 uses both: the exact sum is the bill, and the
    trapezoid is what you can compute from two numbers when you do not have the
    whole sequence.
    """
    _require(len(per_step_inputs) >= 2,
             "至少要两步才能算累计输入的形状：一步的任务没有累积")
    exact = sum(per_step_inputs)
    estimate = trapezoid_tokens(len(per_step_inputs), per_step_inputs[0],
                                per_step_inputs[-1])
    naive = len(per_step_inputs) * statistics.fmean(per_step_inputs[:1])
    return {
        "steps": len(per_step_inputs),
        "first_step": per_step_inputs[0],
        "last_step": per_step_inputs[-1],
        "exact": round(exact, 2),
        "trapezoid_estimate": round(estimate, 2),
        "estimate_error_share": round((estimate - exact) / exact, 6),
        "naive_first_step_times_steps": round(naive, 2),
        "naive_understates_by": round(exact / naive, 4) if naive else None,
        "note": ("梯形估算在增长量完全均匀时精确，增长量越到后面越大时略微偏高。"
                 "把首步乘以步数（最后一列）是案例二那个错法，它会低估好几倍。"),
    }


# --------------------------------------------------------------------------
# profile
# --------------------------------------------------------------------------

def _validate_task(task: dict, index: int) -> None:
    _require(task.get("task_id") is not None, f"第 {index} 个任务没有 task_id")
    steps = task.get("steps")
    _require(isinstance(steps, list) and steps,
             f"任务 {task.get('task_id')} 没有 steps")
    _require(task.get("duration_ms") is not None,
             f"任务 {task['task_id']} 没有 duration_ms")
    for j, step in enumerate(steps):
        for field in ("llm_ms", "input_tokens", "output_tokens"):
            _require(step.get(field) is not None,
                     f"任务 {task['task_id']} 第 {j} 步缺 {field}："
                     "纯工具步（24.1 那种只调工具、不调模型的一步）"
                     "把 llm_ms 写 0，不要省掉这个字段")
        tools = step.get("tools")
        _require(tools is not None,
                 f"任务 {task['task_id']} 第 {j} 步没有 tools 字段："
                 "24.4 说过没有按工具拆开的 Span，工具等待这块时间在监控里"
                 "是不存在的，你只会看到“任务很慢”。一步没有调工具就写空列表")
        for tool in tools:
            for field in ("name", "ms"):
                _require(tool.get(field) is not None,
                         f"任务 {task['task_id']} 第 {j} 步的某个工具缺 {field}")


def percentiles(values: list[float]) -> dict:
    """Nearest-rank percentiles, plus the max.

    24.2 says the distribution matters more than the mean, so the mean is
    reported alongside but never alone.
    """
    _require(bool(values), "没有数据")
    ordered = sorted(values)

    def at(q: float):
        idx = min(len(ordered) - 1,
                  max(0, int(round(q * (len(ordered) - 1)))))
        return ordered[idx]

    return {"p50": at(0.50), "p90": at(0.90), "p95": at(0.95),
            "p99": at(0.99), "max": ordered[-1],
            "mean": round(statistics.fmean(ordered), 3)}


def build_profile(tasks: list[dict]) -> dict:
    _require(bool(tasks), "没有任何任务追踪")
    for i, task in enumerate(tasks):
        _validate_task(task, i)

    step_counts = [len(t["steps"]) for t in tasks]
    # 步数不等于模型调用次数：纯工具步不打到模型服务上（24.1）。第 26 章做
    # 容量规划时代进容量链的是后者的均值，所以它要单独报一项（24.7）。
    model_call_counts = [
        float(sum(1 for s in t["steps"] if (s["llm_ms"] or 0) > 0))
        for t in tasks]
    durations = [t["duration_ms"] for t in tasks]

    llm_ms = sum(s["llm_ms"] for t in tasks for s in t["steps"])
    tool_ms_by_name: Counter = Counter()
    for task in tasks:
        for step in task["steps"]:
            for tool in step["tools"]:
                tool_ms_by_name[tool["name"]] += tool["ms"]
    tool_ms = sum(tool_ms_by_name.values())
    total_ms = sum(durations)
    # 24.4 那块时间必须自己成一列。让占比凑成 1 会正好盖掉值得看的那个缺口。
    unaccounted = total_ms - llm_ms - tool_ms

    growth = []
    for task in tasks:
        inputs = [s["input_tokens"] for s in task["steps"]]
        if len(inputs) >= 2:
            growth.append(cumulative_tokens(inputs))
    _require(bool(growth),
             "所有任务都只有一步：这批数据看不出上下文累积，"
             "而那是这一章的第二主张")

    hits = [s["prefix_hit_rate"] for t in tasks for s in t["steps"]
            if s.get("prefix_hit_rate") is not None]
    abandoned = [t for t in tasks if t.get("abandoned")]
    limited = [t for t in tasks if t.get("hit_step_limit")]

    # 样本少于 20 个时 P95 就是最大值，这时它不是一个分位数，是那一个任务。
    # 把这句话写进输出，比让读者以为自己看到了一个分位数要好。
    warning = None
    if len(tasks) < 20:
        warning = (f"只有 {len(tasks)} 个任务，P95 落在最大值上，"
                   "它反映的是那一个任务而不是一个分布。"
                   "要让 P95 有意义，至少需要二十个任务。")

    return {
        "task_count": len(tasks),
        "percentile_warning": warning,
        "steps": percentiles([float(n) for n in step_counts]),
        "model_calls": percentiles(model_call_counts),
        "model_calls_note": (
            "第 26 章代进容量链的是这一项的均值，不是步数：纯工具步不打到"
            "模型服务上（24.1、25.5）。"),
        "duration": percentiles([float(d) for d in durations]),
        "llm_time_share": round(llm_ms / total_ms, 4),
        "tool_time_share": round(tool_ms / total_ms, 4),
        "tool_time_by_name": {k: round(v / total_ms, 4)
                              for k, v in tool_ms_by_name.most_common()},
        "unaccounted_time_share": round(unaccounted / total_ms, 4),
        "unaccounted_note": (
            "编排层开销、串行等待和追踪没覆盖到的部分都落在这里。"
            "它不被摊进上面两项，因为让占比凑成 1 会盖掉这个缺口。"),
        "context_growth": [
            {"task_id": t["task_id"],
             "per_step_input_tokens": [s["input_tokens"] for s in t["steps"]]}
            for t in tasks],
        "cumulative_tokens": {
            "per_task": [dict(g, task_id=t["task_id"])
                         for g, t in zip(growth, tasks)],
            "total_exact": round(sum(g["exact"] for g in growth), 2),
            "total_trapezoid": round(
                sum(g["trapezoid_estimate"] for g in growth), 2),
        },
        "prefix_hit_rate": (round(statistics.fmean(hits), 4) if hits else None),
        "abandon_rate": round(len(abandoned) / len(tasks), 4),
        "abandon_mean_step": (
            round(statistics.fmean(t["abandoned_at_step"] for t in abandoned), 3)
            if abandoned and all(t.get("abandoned_at_step") is not None
                                 for t in abandoned) else None),
        "step_limit_rate": round(len(limited) / len(tasks), 4),
        "reading": (
            f"{len(tasks)} 个任务，步数 P50 {int(percentiles([float(n) for n in step_counts])['p50'])}、"
            f"P95 {int(percentiles([float(n) for n in step_counts])['p95'])}。"
            "用户体验由 P95 那一档决定，不是 P50。"),
    }


# --------------------------------------------------------------------------
# tail
# --------------------------------------------------------------------------

def _tool_sequence(task: dict) -> list[str]:
    seq = []
    for step in task["steps"]:
        for tool in step["tools"]:
            seq.append(tool["name"])
    return seq


def _resource_sequence(task: dict) -> list[str]:
    seq = []
    for step in task["steps"]:
        for tool in step["tools"]:
            if tool.get("resource"):
                seq.append(tool["resource"])
    return seq


def find_waste(task: dict) -> list[dict]:
    """24.7's three patterns, each as a run-length check on the step sequence."""
    found = []
    tools = _tool_sequence(task)

    # 一、同一个工具被连续调用多次。
    run, start = 1, 0
    for i in range(1, len(tools) + 1):
        if i < len(tools) and tools[i] == tools[i - 1]:
            run += 1
            continue
        if run >= REPEAT_THRESHOLD:
            found.append({
                "pattern": "repeated_tool",
                "tool": tools[start],
                "length": run,
                "at_step": start,
                "why": (f"{tools[start]} 被连续调用 {run} 次。"
                        "常见原因是工具粒度太细，一件事要调好几次；"
                        "把工具改成一次返回完整内容，步数直接降一个数量级"),
            })
        run, start = 1, i

    # 二、在两个状态之间来回。
    for i in range(len(tools) - OSCILLATION_THRESHOLD + 1):
        window = tools[i:i + OSCILLATION_THRESHOLD]
        if (len(set(window)) == 2 and window[0] == window[2]
                and window[1] == window[3] and window[0] != window[1]):
            found.append({
                "pattern": "oscillation",
                "tools": [window[0], window[1]],
                "length": OSCILLATION_THRESHOLD,
                "at_step": i,
                "why": (f"在 {window[0]} 和 {window[1]} 之间来回。"
                        "通常是错误信息不够清楚，Agent 拿不到足够的信息决定下一步，"
                        "提升错误信息的清晰度是一种性能优化"),
            })
            break

    # 三、大量步骤花在同一份资源上。
    resources = _resource_sequence(task)
    for name, count in Counter(resources).most_common(1):
        if count >= SAME_RESOURCE_THRESHOLD:
            found.append({
                "pattern": "same_resource",
                "resource": name,
                "length": count,
                "why": (f"{count} 次工具调用都指向 {name}。"
                        "同一份长文档被反复解析，每一次的返回内容都会留在上下文里"
                        "被后面每一步重复付费"),
            })
    return found


def tail(tasks: list[dict], percentile: float = 0.95,
         by: str = "steps") -> dict:
    _require(bool(tasks), "没有任何任务追踪")
    for i, task in enumerate(tasks):
        _validate_task(task, i)
    _require(by in ("steps", "duration"), "只能按 steps 或 duration 取长尾")

    def key(t: dict) -> float:
        return float(len(t["steps"]) if by == "steps" else t["duration_ms"])

    values = sorted(key(t) for t in tasks)
    idx = min(len(values) - 1,
              max(0, int(round(percentile * (len(values) - 1)))))
    threshold = values[idx]
    picked = [t for t in tasks if key(t) >= threshold]

    rows = []
    pattern_counts: Counter = Counter()
    # 按判据降序排，最该先看的排在最前。
    for task in sorted(picked, key=key, reverse=True):
        waste = find_waste(task)
        # 数的是「出现在几个任务里」，所以同一个任务里检出两次只算一次。
        # 按检出次数累加会让一个任务里重复两段的模式被判成「共享」（24.7）。
        for pattern in {w["pattern"] for w in waste}:
            pattern_counts[pattern] += 1
        rows.append({
            "task_id": task["task_id"],
            "type": task.get("type"),
            "steps": len(task["steps"]),
            "duration_ms": task["duration_ms"],
            "tool_sequence": _tool_sequence(task),
            "cumulative_input_tokens": sum(s["input_tokens"]
                                           for s in task["steps"]),
            "waste": waste,
        })
    shared = [p for p, c in pattern_counts.items() if c >= 2]
    return {
        "by": by,
        "percentile": percentile,
        "threshold": threshold,
        "tasks_in_tail": len(picked),
        "tasks_total": len(tasks),
        "tail_tasks": rows,
        "pattern_counts": dict(pattern_counts),
        "shared_patterns": shared,
        "reading": (
            (f"长尾里有 {len(shared)} 种模式出现在两个以上的任务里"
             f"（{shared}）：修掉一个模式能同时改善很多任务，"
             "这是从长尾下手的全部理由。")
            if shared else
            (f"长尾里只有 {len(picked)} 个任务，判不出模式是否共享："
             "把 --percentile 调低再看一遍（24.7）。")
            if len(picked) < 2 else
            "长尾里没有重复出现的浪费模式，这些任务大概确实复杂，"
            "该看的是能不能拆成并行子任务（24.5）。"),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_traces(path: Path) -> list[dict]:
    tasks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        tasks.append(json.loads(line))
    return tasks


def print_profile(r: dict) -> None:
    print(f"任务数            {r['task_count']}")
    if r.get("percentile_warning"):
        print(f"                  {r['percentile_warning']}")
    s, d = r["steps"], r["duration"]
    print(f"步数              P50 {int(s['p50'])}  P90 {int(s['p90'])}  "
          f"P95 {int(s['p95'])}  P99 {int(s['p99'])}  max {int(s['max'])}"
          f"  均值 {s['mean']}")
    m = r["model_calls"]
    print(f"模型调用次数      均值 {m['mean']}  P50 {int(m['p50'])}  "
          f"P95 {int(m['p95'])}")
    print(f"                  {r['model_calls_note']}")
    print(f"任务时长          P50 {int(d['p50'])}  P95 {int(d['p95'])}  "
          f"max {int(d['max'])} ms")
    print(f"LLM 占比          {round(r['llm_time_share'] * 100, 1)}%")
    print(f"工具占比          {round(r['tool_time_share'] * 100, 1)}%")
    for name, share in r["tool_time_by_name"].items():
        print(f"  {name:<16}{round(share * 100, 1)}%")
    print(f"未归属占比        {round(r['unaccounted_time_share'] * 100, 1)}%")
    print(f"                  {r['unaccounted_note']}")
    ct = r["cumulative_tokens"]
    print(f"累计输入          精确 {ct['total_exact']}，"
          f"梯形估 {ct['total_trapezoid']}")
    print(f"Prefix 命中率     {r['prefix_hit_rate']}")
    print(f"放弃率            {round(r['abandon_rate'] * 100, 1)}%"
          + (f"，平均在第 {r['abandon_mean_step']} 步"
             if r["abandon_mean_step"] is not None else ""))
    print(f"步数超限率        {round(r['step_limit_rate'] * 100, 1)}%")
    print(f"解读              {r['reading']}")


def print_tail(r: dict) -> None:
    print(f"长尾判据          按 {r['by']}，P"
          f"{round(r['percentile'] * 100)} = {r['threshold']}")
    print(f"落在长尾          {r['tasks_in_tail']} / {r['tasks_total']}")
    for row in r["tail_tasks"]:
        print(f"  {row['task_id']}  {row['steps']} 步  "
              f"{row['duration_ms']} ms  累计输入 "
              f"{row['cumulative_input_tokens']} token")
        print(f"    工具序列  {' → '.join(row['tool_sequence'])}")
        for w in row["waste"]:
            print(f"    浪费模式  {w['pattern']}（{w['length']}）：{w['why']}")
    print(f"模式统计          {r['pattern_counts']}")
    print(f"解读              {r['reading']}")


def print_step_slo(r: dict) -> None:
    print(f"单步达标率        {round(r['step_pass_rate'] * 100, 2)}%")
    for row in r["table"]:
        print(f"  N = {row['steps']:<5}{r['step_pass_rate']}^{row['steps']}"
              f" ≈ {row['percent']}%")
    print(f"解读              {r['reading']}")
    if "required_step_pass_rate" in r:
        print(f"反推              {r['required_reading']}")
        print(f"砍一半步数        {r['halved_steps']} 步时任务级达标率 "
              f"{round(r['halved_task_pass_rate'] * 100, 1)}%")
    print("边界")
    for c in r["caveats"]:
        print(f"  - {c}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_p = sub.add_parser("profile", help="24.7 那十个字段")
    p_p.add_argument("--traces", type=Path, required=True)
    p_p.add_argument("--output", type=Path, default=None)

    p_t = sub.add_parser("tail", help="长尾任务与浪费模式")
    p_t.add_argument("--traces", type=Path, required=True)
    p_t.add_argument("--percentile", type=float, default=0.95)
    p_t.add_argument("--by", choices=("steps", "duration"), default="steps")
    p_t.add_argument("--output", type=Path, default=None)

    p_s = sub.add_parser("step-slo", help="24.2 那张表，以及它的反推")
    p_s.add_argument("--step-pass-rate", type=float, default=0.95)
    p_s.add_argument("--steps", type=int, default=15)
    p_s.add_argument("--task-target", type=float, default=None)
    p_s.add_argument("--retries-enabled", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "step-slo":
            result = step_slo(args.step_pass_rate, args.steps,
                              args.task_target, args.retries_enabled)
            print_step_slo(result)
            return 0
        tasks = load_traces(args.traces)
        if args.cmd == "profile":
            result = build_profile(tasks)
            print_profile(result)
        else:
            result = tail(tasks, args.percentile, args.by)
            print_tail(result)
        if args.output is not None:
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}")
        return 0
    except ProfileError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
