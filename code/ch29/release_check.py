#!/usr/bin/env python3
"""The last gate before a release: nine items, and five seams between them.

29.1 says the value of a review is not re-auditing each document. Every document
can be correct on its own while the seams between them do not line up, and that
is what 29.8 案例一 is: Baseline 达标、门禁通过、容量核算说 8 张卡够用，上线当晚
过载，因为容量模型用的上下文长度和新版本的 prompt 模板对不上。

Subcommands:

  check    the nine-item checklist plus the five cross-checks. Offline.
  packet   the same thing rendered as the 29.6 review document. Offline.
  window   29.4's observation window: what to watch and for how long.

Three things this script refuses to do:

  It will not pass a release on the checklist alone. The nine items can all be
  green while a cross-check fails, and a cross-check failure is blocking.

  It will not accept a rollback plan without a measured duration. 29.3 says a
  plan that has never been rehearsed is discovered to be wrong exactly when it
  is needed, and the rehearsal's output is a number.

  It will not let 监控就绪 be a yes/no. 29.8 案例三 is a release where the answer
  was yes and the one metric that mattered did not exist, so the check lists the
  required metrics and reports which are missing.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# 29.2 那九项，顺序即正文顺序。
CHECKLIST = (
    ("slo", "SLO 定义清楚且可测"),
    ("baseline", "性能证据是在待发布的那套环境上量的"),
    ("capacity", "容量核算过，且和实际配置一致"),
    ("gate", "门禁通过，或有记录在案的豁免"),
    ("monitoring", "监控就绪"),
    ("traffic_policy", "流量治理配置齐全"),
    ("cold_start", "冷启动时间已知"),
    ("rollback", "回滚预案明确且演练过"),
    ("owner", "有人对结果负责"),
)

# 29.2：最容易被跳过的是第五和第八项。
OFTEN_SKIPPED = ("monitoring", "rollback")

# 21 章那五项治理配置。
TRAFFIC_POLICY_ITEMS = ("admission", "timeout", "cancellation", "retry",
                        "backpressure")

# 29.8 案例三那个教训：监控就绪不是一个是非题，要点名必须有哪些指标。
# 前六项是用户看得到的结果（规律三：只有有用的产出才算数），后四项是调度器
# 那一侧的原因。拒绝率单列，因为 29.2 那个 SLO 的口径不含被拒绝的请求：
# 只看 SLO 达成率，靠拒绝请求也能把它做得很好看。
RESULT_METRICS = ("ttft_p95", "itl_p95", "itl_distribution",
                  "error_rate", "rejection_rate", "slo_attainment")
# 命中率在原因里，不在「容易漏」里：29.4 的 2 小时窗口要看它的恢复曲线，
# 29.3 的回滚预案要用它算缓存恢复期，第 28 章案例三那次静默回退也是靠它
# 发现的（Part 6 审阅 P1-22）。
CAUSE_METRICS = ("running_ratio", "queue_length", "preemption_count",
                 "kv_usage", "prefix_cache_hit_rate")
REQUIRED_METRICS = RESULT_METRICS + CAUSE_METRICS

# 29.4 的观察窗口。
OBSERVATION_WINDOW = (
    ("10m", "错误率、P95 延迟、槽位占用率", "看的是有没有立刻崩"),
    ("2h", "缓存命中率的恢复曲线、抢占计数、显存占用", "看的是稳态下的资源状况"),
    ("24h", "跨越一个完整的日内波峰，看峰值表现", "这是唯一能验证容量核算的窗口"),
    ("7d", "成本、质量指标、长尾任务", "这些需要足够样本才看得出来"),
)

# 29.1 的五处接缝。
CROSS_CHECKS = (
    ("context_length", "容量模型的上下文长度", "当前 prompt 模板的实际长度"),
    ("batch", "门禁运行时的批量", "生产配置的批量"),
    ("framework_version", "性能证据的框架版本", "待发布镜像的框架版本"),
    ("instances", "容量模型的峰值与下限卡数", "扩缩容配置的实例数区间"),
    ("slo_threshold", "SLO 阈值", "门禁绝对阈值"),
)


class ReviewError(Exception):
    """An input that cannot support the verdict asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ReviewError(message)


# --------------------------------------------------------------------------
# 九项清单
# --------------------------------------------------------------------------

def check_monitoring(spec: dict | None) -> dict:
    """29.8 案例三：监控就绪不能是一个是非题。"""
    if spec is None:
        return {"ok": False, "missing": list(REQUIRED_METRICS),
                "detail": "没有提供监控清单"}
    available = set(spec.get("available_metrics") or [])
    missing = [m for m in REQUIRED_METRICS if m not in available]
    return {
        "ok": not missing, "missing": missing,
        "detail": ("全部就位" if not missing else
                   f"缺 {missing}。29.8 案例三就是缺了 itl_distribution，"
                   "出问题后加指标、发版、等数据花了两天"),
    }


def check_traffic_policy(cfg: dict | None) -> dict:
    if cfg is None:
        return {"ok": False, "missing": list(TRAFFIC_POLICY_ITEMS),
                "detail": "没有提供治理配置"}
    missing = [k for k in TRAFFIC_POLICY_ITEMS if not cfg.get(k)]
    admission_off = not (cfg.get("admission") or {}).get("enabled", False) \
        if isinstance(cfg.get("admission"), dict) else False
    return {
        "ok": not missing and not admission_off,
        "missing": missing,
        "detail": ("五项齐全" if not missing and not admission_off else
                   ("准入没开启：它是突发流量唯一的防线" if admission_off
                    else f"缺 {missing}")),
    }


def check_rollback(plan: dict | None) -> dict:
    """29.3：没演练过的预案在真正需要时才会发现不对。"""
    if plan is None:
        return {"ok": False, "detail": "没有提供回滚预案"}
    problems = []
    if not plan.get("trigger_conditions"):
        problems.append("没写触发条件")
    if not plan.get("steps"):
        problems.append("没写执行步骤：29.6 那份模板里它和触发条件并列")
    if plan.get("rehearsed_duration_min") is None:
        problems.append("没有演练量出来的耗时：演练的目标就是量出这个数")
    if plan.get("irreversible") is None:
        problems.append("没列不可回滚项（数据迁移、外部副作用）")
    if plan.get("cache_warmup_min") is None:
        problems.append("没写回滚后的缓存恢复期，29.8 案例二就栽在这里")
    return {"ok": not problems, "problems": problems,
            "detail": "完整" if not problems else "；".join(problems)}


def run_checklist(docs: dict) -> dict:
    items = {}
    for key, label in CHECKLIST:
        if key == "monitoring":
            r = check_monitoring(docs.get("monitoring"))
        elif key == "traffic_policy":
            r = check_traffic_policy(docs.get("traffic_policy"))
        elif key == "rollback":
            r = check_rollback(docs.get("rollback"))
        elif key == "gate":
            g = docs.get("gate")
            ok = bool(g) and (g.get("verdict") == "pass" or g.get("waiver"))
            r = {"ok": ok,
                 "detail": ("通过" if g and g.get("verdict") == "pass" else
                            (f"豁免：{g['waiver']}" if g and g.get("waiver")
                             else "门禁未通过且无豁免记录"))}
        elif key == "cold_start":
            c = docs.get("cold_start_s")
            r = {"ok": c is not None,
                 "detail": (f"{c} 秒" if c is not None else
                            "冷启动时间未知：27.5 说它决定了弹性能做什么")}
        elif key == "owner":
            o = docs.get("owner")
            r = {"ok": bool(o), "detail": o or "没有指定责任人"}
        else:
            v = docs.get(key)
            r = {"ok": bool(v), "detail": "已提供" if v else "缺失"}
        r["label"] = label
        r["often_skipped"] = key in OFTEN_SKIPPED
        items[key] = r
    missing = [k for k, v in items.items() if not v["ok"]]
    return {"items": items, "missing": missing,
            "skipped_among_the_easy_ones": [k for k in missing
                                            if k in OFTEN_SKIPPED]}


# --------------------------------------------------------------------------
# 五处接缝
# --------------------------------------------------------------------------

def context_length_consequence(modeled: float, actual: float,
                               output_tokens: float = 0.0,
                               instances: int | None = None,
                               binding: str | None = None) -> dict:
    """把“上下文对不上”换算成“并发少多少、卡要加几张”。

    第 16 章那张容量表里，单卡并发上限反比于平均总长度：KV 预算是固定的，
    每条请求占的 KV 和它的总长度成正比。所以模型用 12000 而实际是 16000 时，
    并发上限要按两边的总长度之比折算，而不是“差不多”。

    这个“要几张卡”的换算只在显存先满时成立。容量模型是吞吐先满时（第 26 章
    的主例），显存一侧多出来的卡仍然不是约束，真正要重算的是 Prefill 占时：
    输入变长，单卡输出吞吐下降。这时只报显存一侧的比例，并要求重跑第 26 章。
    """
    _require(modeled > 0 and actual > 0, "上下文长度必须是正数")
    left = modeled + output_tokens
    right = actual + output_tokens
    ratio = left / right
    out = {
        "modeled_total_tokens": left,
        "actual_total_tokens": right,
        "concurrency_ratio": round(ratio, 4),
        "concurrency_drop": round(1 - ratio, 4),
    }
    out["binding_constraint"] = binding
    if instances and binding != "throughput":
        need = math.ceil(instances / ratio)
        out["instances_in_model"] = instances
        out["instances_needed"] = need
        out["reading"] = (
            f"并发上限折算为原来的 {ratio:.0%}，容量模型算出的 {instances} 张"
            f"实际要 {need} 张。这就是 29.8 案例一上线当晚过载的量"
            + ("。" if binding == "memory" else
               "。前提是显存先满；容量模型没写哪个约束先满，先补上这一项"))
    elif binding == "throughput":
        out["reading"] = (
            f"显存一侧的并发上限折算为原来的 {ratio:.0%}，但容量模型是吞吐先满，"
            "显存多出来的卡仍不是约束。输入变长会抬高 Prefill 占时、压低单卡输出"
            "吞吐，要用第 26 章的模型按新的输入长度重算卡数")
    else:
        out["reading"] = f"并发上限折算为原来的 {ratio:.0%}"
    return out


def cross_check(docs: dict) -> dict:
    cap = docs.get("capacity") or {}
    runtime = docs.get("runtime") or {}
    gate = docs.get("gate") or {}
    base = docs.get("baseline") or {}
    slo = docs.get("slo") or {}
    autoscale = docs.get("autoscale") or {}

    pairs = {
        "context_length": (cap.get("context_tokens"),
                           runtime.get("prompt_template_tokens")),
        "batch": (gate.get("batch"), runtime.get("batch")),
        "framework_version": (base.get("framework_version"),
                              runtime.get("framework_version")),
        "instances": ((cap.get("instances"), cap.get("floor_instances"))
                      if cap.get("instances") is not None else None,
                      (autoscale.get("max_instances"), autoscale.get("min_instances"))
                      if autoscale.get("max_instances") is not None else None),
        "slo_threshold": (slo.get("ttft_p95_ms"),
                          gate.get("absolute_ttft_p95_ms")),
    }
    rows = []
    for key, left_label, right_label in CROSS_CHECKS:
        a, b = pairs[key]
        if key == "instances" and a is not None and b is not None:
            # 实例数不是相等关系：最大实例数要扛得住峰值卡数，最小实例数要不低于
            # 下限卡数。要求最小实例数等于峰值卡数，等于说波谷永远缩不下来。
            (peak, floor), (hi, lo) = a, b
            if None in (peak, floor, hi, lo):
                status, note = "无法核对", "峰值、下限、最大、最小四个数至少缺一个"
            elif hi >= peak and lo >= floor:
                status, note = "一致", ""
            else:
                bad = []
                if hi < peak:
                    bad.append(f"最大实例数 {hi} 低于峰值卡数 {peak}")
                if lo < floor:
                    bad.append(f"最小实例数 {lo} 低于下限卡数 {floor}")
                status, note = "不一致", "；".join(bad)
        elif a is None or b is None:
            status, note = "无法核对", "两边至少有一个没提供"
        elif a == b:
            status, note = "一致", ""
        else:
            status, note = "不一致", f"{a} 对 {b}"
        row = {"key": key, "left": left_label, "right": right_label,
               "left_value": a, "right_value": b,
               "status": status, "note": note}
        if key == "context_length" and status == "不一致":
            row["consequence"] = context_length_consequence(
                a, b, cap.get("output_tokens") or 0.0, cap.get("instances"),
                cap.get("binding_constraint"))
        rows.append(row)
    mismatched = [r["key"] for r in rows if r["status"] == "不一致"]
    unknown = [r["key"] for r in rows if r["status"] == "无法核对"]
    return {"rows": rows, "mismatched": mismatched, "unknown": unknown}


def review(docs: dict) -> dict:
    _require(isinstance(docs, dict) and docs, "没有提供任何材料")
    cl = run_checklist(docs)
    cc = cross_check(docs)
    blocking = list(cl["missing"]) + [f"seam:{k}" for k in cc["mismatched"]]
    if blocking:
        verdict = "不通过"
        why = ("清单缺项：" + "、".join(cl["missing"]) if cl["missing"] else "")
        if cc["mismatched"]:
            why += ("；" if why else "") + "接缝对不上：" + "、".join(cc["mismatched"])
    elif cc["unknown"]:
        verdict = "有条件通过"
        why = f"有 {len(cc['unknown'])} 处接缝无法核对：{cc['unknown']}"
    else:
        verdict = "通过"
        why = "九项齐全，五处接缝一致"
    return {
        "checklist": cl, "cross_check": cc,
        "verdict": verdict, "reason": why,
        "note": ("29.1 说评审的价值不在重审每一份材料，而在交叉检查那些接缝："
                 "九项全绿而接缝对不上，仍然不通过。"),
    }


def observation_window() -> list[dict]:
    return [{"window": w, "watch": what, "why": why}
            for w, what, why in OBSERVATION_WINDOW]


# --------------------------------------------------------------------------
# 评审材料
# --------------------------------------------------------------------------

def packet(docs: dict, result: dict) -> str:
    lines = ["# 上线评审材料", "",
             f"结论：**{result['verdict']}**　{result['reason']}", ""]

    # 29.6 那份模板是六块。前两块不在九项清单里，而变更说明和风险清单正是
    # 它说最有价值、也最容易被省掉的部分，所以缺了要显式写出来。
    change = docs.get("change") or {}
    lines += ["## 一、变更说明", ""]
    for field, label in (("what", "改了什么"), ("why", "为什么"),
                         ("scope", "影响范围")):
        value = change.get(field)
        lines.append(f"- {label}：" + (value if value else "**未记录**"))
    lines += ["", "## 二、九项清单", ""]
    for key, label in CHECKLIST:
        r = result["checklist"]["items"][key]
        mark = "通过" if r["ok"] else "**缺项**"
        lines.append(f"- {label}：{mark}　{r['detail']}")
    lines += ["", "## 三、五处接缝", ""]
    for row in result["cross_check"]["rows"]:
        tail = f"　{row['note']}" if row["note"] else ""
        lines.append(f"- {row['left']} 对 {row['right']}："
                     f"{row['status']}{tail}")
        if row.get("consequence"):
            lines.append(f"  - {row['consequence']['reading']}")
    lines += ["", "## 四、风险清单", ""]
    risks = docs.get("risks")
    if not risks:
        lines.append("- **未记录**：29.6 说这一块里“未覆盖的场景”最有价值，也最容易被省掉")
    else:
        for risk in risks:
            state = "已验证" if risk.get("verified") else "**未验证**"
            lines.append(f"- {risk.get('risk', '未命名风险')}：{state}"
                         f"　缓解：{risk.get('mitigation') or '**未记录**'}")
    lines += ["", "## 五、观察窗口", ""]
    for w in observation_window():
        lines.append(f"- 前 {w['window']}：{w['watch']}　{w['why']}")
    lines += ["", "## 六、回滚与责任人", ""]
    rb = docs.get("rollback") or {}
    # 29.6：缺的东西要显式标出来，不能因为字段存在而渲染成一个 None。
    dur = rb.get("rehearsed_duration_min")
    warm = rb.get("cache_warmup_min")
    irr = rb.get("irreversible")
    lines.append("- 演练耗时：" +
                 (f"{dur} 分钟" if dur is not None else "**未演练**"))
    lines.append("- 缓存恢复期：" +
                 (f"{warm} 分钟" if warm is not None else "**未记录**"))
    lines.append("- 不可回滚项：" +
                 ("、".join(irr) if irr else
                  ("无" if irr == [] else "**未列出**")))
    lines += [f"- 责任人：{docs.get('owner', '未指定')}", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_review(r: dict) -> None:
    print("九项清单")
    for key, label in CHECKLIST:
        item = r["checklist"]["items"][key]
        mark = " ok " if item["ok"] else "缺项"
        print(f"  [{mark}] {label}　{item['detail']}")
    print("五处接缝")
    for row in r["cross_check"]["rows"]:
        tail = f"　{row['note']}" if row["note"] else ""
        print(f"  [{row['status']}] {row['left']} 对 {row['right']}{tail}")
        if row.get("consequence"):
            print(f"           {row['consequence']['reading']}")
    print(f"结论              {r['verdict']}")
    print(f"                  {r['reason']}")
    print(f"                  {r['note']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    for name, helptext in (("check", "九项清单加五处接缝"),
                           ("packet", "渲染成 29.6 那份评审材料")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--docs", type=Path, required=True,
                        help="一份把所有材料汇在一起的 JSON")
        sp.add_argument("--output", type=Path, default=None)

    sub.add_parser("window", help="29.4 那四档观察窗口")

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "window":
            for w in observation_window():
                print(f"  前 {w['window']:<5}{w['watch']}")
                print(f"          {w['why']}")
            return 0
        docs = json.loads(args.docs.read_text(encoding="utf-8"))
        result = review(docs)
        if args.cmd == "check":
            print_review(result)
            if args.output is not None:
                args.output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
        else:
            text = packet(docs, result)
            print(text)
            if args.output is not None:
                args.output.write_text(text, encoding="utf-8")
        return 0 if result["verdict"] == "通过" else 1
    except ReviewError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
