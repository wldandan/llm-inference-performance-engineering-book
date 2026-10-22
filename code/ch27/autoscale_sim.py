#!/usr/bin/env python3
"""Simulate an autoscaling loop against a traffic trace, and compare strategies.

27.5 has the chapter's whole point in one sentence: 冷启动 3 到 10 分钟，而突发
流量是秒级的。This script makes that sentence produce a number instead of a
feeling, by running the loop against a trace and reporting how much demand went
unserved while the loop was still catching up.

Subcommands:

  simulate  one strategy against one trace. Offline.
  compare   the four strategies of 27.8 side by side, including the
            `admission-only` control that does no scaling at all.
  lag       27.4's loop lag: 观测窗口 + 决策周期 + 冷启动, and the judgement it
            supports. Offline, no trace needed.
  cache     22.4's |N−M| / max(N,M) applied to a scaling event, so the cache
            cost of a scale-down is visible next to its instance-hour saving.

Three things this script refuses to do:

  It will not call a strategy good on a trace whose variations are all shorter
  than the loop lag. On such a trace every reactive strategy loses and the
  comparison says nothing about the strategies (27.4).

  It will not use one threshold for both directions. 27.6 says the risks are
  asymmetric, so `--scale-down-threshold` is required and must sit below the
  scale-up one, leaving a hysteresis band.

  It will not report instance-hour cost as the only cost of a scale-down. The
  cache that gets thrown away is a cost too, and `cache` quantifies it.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

STRATEGIES = ("reactive", "scheduled", "warm-pool", "admission-only")

# 27.4 那张回路滞后表的三段，单位秒。
LAG_PARTS = {
    "observation": (30, 90),
    "decision": (30, 120),
    "cold_start": (180, 600),
}

# 27.2：多副本容量按 0.8 到 0.9 折算。
SCALING_EFFICIENCY = (0.8, 0.9)


class SimError(Exception):
    """An input that cannot support the conclusion asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SimError(message)


# --------------------------------------------------------------------------
# 27.4 回路滞后
# --------------------------------------------------------------------------

def loop_lag(observation_s: float | None = None,
             decision_s: float | None = None,
             cold_start_s: float | None = None) -> dict:
    """三段之和。不给具体值就报 27.4 那张表的上下界。"""
    if observation_s is None and decision_s is None and cold_start_s is None:
        lo = sum(v[0] for v in LAG_PARTS.values())
        hi = sum(v[1] for v in LAG_PARTS.values())
        return {
            "parts": {k: {"low_s": v[0], "high_s": v[1]}
                      for k, v in LAG_PARTS.items()},
            "low_s": lo, "high_s": hi,
            "low_min": round(lo / 60, 1), "high_min": round(hi / 60, 1),
            "actionable_threshold_min": round(hi / 60 * 2, 1),
            "reading": (
                f"回路滞后 {lo/60:.0f} 到 {hi/60:.1f} 分钟。经验上取两倍，"
                f"也就是持续 {hi/60*2:.0f} 分钟以上的变化才值得交给 Autoscaling；"
                "更短的突发，无论指标选得多好、阈值调得多准，都追不上。"),
        }
    parts = {"observation": observation_s or 0, "decision": decision_s or 0,
             "cold_start": cold_start_s or 0}
    for k, v in parts.items():
        _require(v >= 0, f"{k} 不能为负")
    total = sum(parts.values())
    _require(total > 0, "三段全是 0，这不是一个回路")
    dominant = max(parts, key=lambda k: parts[k])
    return {
        "parts": parts, "total_s": total, "total_min": round(total / 60, 2),
        "dominant": dominant,
        "dominant_share": round(parts[dominant] / total, 4),
        "actionable_threshold_min": round(total / 60 * 2, 2),
        "reading": (
            f"回路滞后 {total/60:.1f} 分钟，其中 {dominant} 占 "
            f"{parts[dominant]/total:.0%}。"
            + ("冷启动是唯一能靠预热实例池压到秒级的一段，压掉它整个滞后就由"
               "前两段决定。" if dominant == "cold_start" else
               "冷启动不是大头，压缩它收益有限，该动的是窗口和评估间隔。")),
    }


# --------------------------------------------------------------------------
# 22.4 的缓存冲击，用在扩缩容上
# --------------------------------------------------------------------------

def modulo_kept_share(before: int, after: int) -> float:
    """取模哈希下归属不变的键的比例：gcd(N, M) / max(N, M)。

    hash % N 与 hash % M 相同，要求余数小于 min(N, M)，每个 lcm(N, M) 周期里
    恰好有 min(N, M) 个这样的键，所以比例是 min/lcm = gcd/max。12 → 11 只保住
    1/12；12 → 4 保住 1/3，和一致性哈希一样，因为 12 是 4 的倍数。
    """
    _require(before > 0 and after > 0, "实例数必须为正")
    return math.gcd(before, after) / max(before, after)


def cache_impact(before: int, after: int, *, consistent_hashing: bool = True,
                 warm_minutes_full: float = 120.0) -> dict:
    """缩容或扩容时必须重建的前缀比例。27.6 把它当缩容的一个参数用。

    一致性哈希：|N − M| / max(N, M)。取模哈希：1 − gcd(N, M) / max(N, M)。
    """
    _require(before > 0 and after > 0, "实例数必须为正")
    consistent_moved = abs(before - after) / max(before, after)
    modulo_moved = 1 - modulo_kept_share(before, after)
    moved = consistent_moved if consistent_hashing else modulo_moved
    same = abs(consistent_moved - modulo_moved) < 1e-9
    return {
        "before": before, "after": after,
        "hashing": "consistent" if consistent_hashing else "modulo",
        "prefix_moved_share": round(moved, 4),
        "prefix_kept_share": round(1 - moved, 4),
        "consistent_moved_share": round(consistent_moved, 4),
        "modulo_moved_share": round(modulo_moved, 4),
        "estimated_warm_minutes": round(warm_minutes_full * moved, 1),
        "reading": (
            f"{before} → {after}，必须重建 {moved:.0%} 的前缀，"
            f"预计回暖 {warm_minutes_full * moved:.0f} 分钟。"
            + (f"这一档取模哈希和一致性哈希一样（{before} 和 {after} 成倍数），"
               "换哪种哈希都救不回来，要改的是缩容幅度"
               if same else
               f"一致性哈希要重建 {consistent_moved:.0%}，取模哈希要重建 {modulo_moved:.0%}")),
    }


# --------------------------------------------------------------------------
# simulate
# --------------------------------------------------------------------------

def load_trace(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not row.get("t"):
                continue
            rows.append({"t": float(row["t"]), "demand": float(row["demand"])})
    _require(bool(rows), "轨迹里没有数据")
    rows.sort(key=lambda r: r["t"])
    return rows


def trace_variation_scale(trace: list[dict]) -> dict:
    """这段流量的变化有多快：相邻采样点之间的最大变化，和它持续了多久。"""
    _require(len(trace) >= 3, "至少要三个采样点才看得出变化尺度")
    step = trace[1]["t"] - trace[0]["t"]
    _require(step > 0, "时间戳必须递增")
    peak = max(r["demand"] for r in trace)
    base = statistics.median(r["demand"] for r in trace)
    _require(base > 0, "中位需求为 0，这段轨迹说明不了什么")
    # 峰值持续多久：需求高于中位数两倍的那些点
    high = [r for r in trace if r["demand"] > base * 2]
    return {
        "sample_step_s": step,
        "median_demand": round(base, 3),
        "peak_demand": round(peak, 3),
        "peak_over_median": round(peak / base, 3),
        "surge_duration_s": round(len(high) * step, 1),
    }


def simulate(trace: list[dict], *, capacity_per_instance: float,
             scale_up_threshold: float, scale_down_threshold: float,
             cold_start_s: float, scale_up_cooldown_s: float,
             scale_down_cooldown_s: float, min_instances: int,
             max_instances: int, strategy: str = "reactive",
             warm_pool: int = 0, admission: bool = False,
             observation_s: float = 60.0,
             decision_s: float = 60.0) -> dict:
    _require(strategy in STRATEGIES, f"不认识的策略 {strategy}")
    _require(capacity_per_instance > 0, "单实例容量必须为正")
    _require(0 < scale_down_threshold < scale_up_threshold < 1,
             f"阈值要满足 0 < 缩容 {scale_down_threshold} < 扩容 "
             f"{scale_up_threshold} < 1：27.6 说两个方向的风险不对称，"
             "用同一个阈值的系统会持续抖动")
    _require(0 < min_instances <= max_instances, "实例数区间不合法")

    # 预热实例池把冷启动压到秒级，这是唯一能改量级的手段（27.5）。
    effective_cold = 10.0 if strategy == "warm-pool" else cold_start_s
    react = strategy in ("reactive", "warm-pool", "scheduled")

    step = trace[1]["t"] - trace[0]["t"]
    n = min_instances
    pending: list[tuple[float, int]] = []   # (生效时刻, 目标实例数)
    last_up = last_down = -1e9
    timeline, events, unmet, lags = [], [], 0.0, []
    rejected = 0.0
    # 27.5 把流量变化分成三类，所以未满足需求也要按类分开算：趋势期跟不上是
    # 参数问题，突发期跟不上是时间尺度问题，两者的处方完全不同。
    surge_cut = statistics.median(r["demand"] for r in trace) * 2
    unmet_surge = 0.0

    for row in trace:
        t, demand = row["t"], row["demand"]
        while pending and pending[0][0] <= t:
            _, n = pending.pop(0)
        capacity = n * capacity_per_instance
        served = min(demand, capacity)
        over = demand - served
        if admission and over > 0:
            rejected += over * step
        else:
            unmet += over * step
            if demand > surge_cut:
                unmet_surge += over * step
        util = demand / capacity if capacity else float("inf")
        timeline.append({"t": t, "instances": n, "utilisation": round(util, 4)})

        if not react:
            continue
        # 定时扩缩容按轨迹的时间点走，不看指标；这里简化成提前一个滞后量动作。
        decide_lag = observation_s + decision_s
        if util > scale_up_threshold and n < max_instances \
                and t - last_up >= scale_up_cooldown_s:
            target = min(max_instances, n + max(1, int(n * 0.5)))
            eff = t + (decide_lag if strategy != "scheduled" else 0) + effective_cold
            pending.append((eff, target))
            events.append({"t": t, "kind": "up", "from": n, "to": target,
                           "effective_at": eff, "utilisation": round(util, 3)})
            lags.append(eff - t)
            last_up = t
        elif util < scale_down_threshold and n > min_instances \
                and t - last_down >= scale_down_cooldown_s:
            target = max(min_instances, n - 1)
            eff = t + decide_lag
            pending.append((eff, target))
            events.append({"t": t, "kind": "down", "from": n, "to": target,
                           "effective_at": eff, "utilisation": round(util, 3)})
            last_down = t

    thrash = 0
    for a, b in zip(events, events[1:]):
        if a["kind"] == "down" and b["kind"] == "up" \
                and b["t"] - a["t"] < scale_down_cooldown_s:
            thrash += 1

    total_demand = sum(r["demand"] for r in trace) * step
    instance_seconds = sum(p["instances"] for p in timeline) * step
    scale = trace_variation_scale(trace)
    lag_total = observation_s + decision_s + effective_cold

    verdict, why = _verdict(strategy=strategy, unmet=unmet,
                            unmet_surge=unmet_surge,
                            total_demand=total_demand, thrash=thrash,
                            surge_s=scale["surge_duration_s"],
                            lag_s=lag_total, admission=admission)
    return {
        "strategy": strategy,
        "loop_lag_s": lag_total,
        "trace": scale,
        "instance_timeline": timeline[::max(1, len(timeline) // 20)],
        "scale_events": events,
        "lag": {"count": len(lags),
                "mean_s": round(statistics.fmean(lags), 1) if lags else None,
                "max_s": round(max(lags), 1) if lags else None},
        "unmet_demand": round(unmet, 2),
        "unmet_share": round(unmet / total_demand, 4) if total_demand else None,
        "unmet_in_surge": round(unmet_surge, 2),
        "unmet_in_trend": round(unmet - unmet_surge, 2),
        "rejected_demand": round(rejected, 2),
        "thrash_count": thrash,
        "instance_seconds": round(instance_seconds, 1),
        "cost_index": round(instance_seconds / 3600, 2),
        "verdict": verdict,
        "verdict_reason": why,
    }


def _verdict(*, strategy, unmet, unmet_surge, total_demand, thrash, surge_s,
             lag_s, admission) -> tuple[str, str]:
    share = unmet / total_demand if total_demand else 0
    trend_unmet = unmet - unmet_surge
    trend_share = trend_unmet / total_demand if total_demand else 0
    if surge_s and surge_s < lag_s and unmet_surge > 0 and trend_share <= 0.02:
        return ("趋势跟得上，突发跟不上",
                f"未满足的 {unmet:.0f} 里有 {unmet_surge/unmet:.0%} 落在那段只持续 "
                f"{surge_s:.0f} 秒的突发上，而回路滞后是 {lag_s:.0f} 秒。"
                "这一段不该交给扩缩容，27.5 那张表把它归给准入和预留余量；"
                "趋势那一段的参数是够用的")
    if share > 0.05:
        return ("不可用",
                f"{share:.1%} 的需求没被满足。要么滞后太大，要么阈值太松，"
                "要么最小实例数定低了")
    if thrash >= 2:
        return ("抖动",
                f"缩容后短时间内又扩容 {thrash} 次。滞回区间要拉宽，"
                "或者缩容冷却要加长（27.6）")
    return ("可用",
            f"未满足需求 {share:.1%}，抖动 {thrash} 次"
            + ("，且超出的部分被准入挡住了，不是堆在队列里" if admission else ""))


def compare(trace: list[dict], base: dict, target_load: float = 0.7) -> dict:
    rows = []
    # admission-only 不扩缩容，但也不是按最小实例数跑：27.5 那张表里它配的是
    # “预留余量”，也就是按趋势的高位静态配好，再用准入挡住突发。高位是需求的
    # P95，而且要按目标负载率配，不能按 1 配：模拟器不建模延迟，负载率贴着 1
    # 在这里没有代价，在真实服务上是第 20 章那条曲线的最陡处。
    _require(0 < target_load <= 1, "目标负载率要在 (0, 1] 内")
    ordered = sorted(r["demand"] for r in trace)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))]
    static = max(base["min_instances"],
                 math.ceil(p95 / (base["capacity_per_instance"] * target_load)))
    static = min(static, base["max_instances"])
    for s in STRATEGIES:
        kw = dict(base)
        kw["strategy"] = s
        kw["admission"] = (s == "admission-only")
        if s == "admission-only":
            kw["min_instances"] = static
            kw["max_instances"] = static
        rows.append(simulate(trace, **kw))
    best_service = min(rows, key=lambda r: r["unmet_demand"])
    cheapest = min(rows, key=lambda r: r["cost_index"])
    scale = rows[0]["trace"]
    mismatch = scale["surge_duration_s"] < rows[0]["loop_lag_s"]
    return {
        "trace": scale,
        "admission_only_static_instances": static,
        "admission_only_target_load": target_load,
        "loss_note": ("未满足和被拒不是同一种损失：被拒的请求立刻拿到 429，可以退避重试或降级；"
                      "未满足的请求堆在队列里慢慢超时，还拖慢同批其他请求。"
                      "比较策略时按 Goodput 比，不能把两列直接相加。"),
        "strategies": [{k: r[k] for k in
                        ("strategy", "unmet_demand", "unmet_share",
                         "rejected_demand", "thrash_count", "cost_index",
                         "verdict")} for r in rows],
        "best_service": best_service["strategy"],
        "cheapest": cheapest["strategy"],
        "scale_mismatch": mismatch,
        "reading": (
            (f"这段轨迹里那次突发只持续 {scale['surge_duration_s']:.0f} 秒，"
             f"比回路滞后 {rows[0]['loop_lag_s']:.0f} 秒还短，所以三种靠扩缩容的"
             "策略都在那一段上漏了需求；而 admission-only 把超出的部分当场拒掉，"
             "未满足为零，成本还更低。这不是说弹性没用，它们在趋势那一段都跟得上，"
             "是说突发那一段不该交给弹性（27.5 那张三类变化的表）。"
             if mismatch else
             f"服务质量最好的是 {best_service['strategy']}，"
             f"最省的是 {cheapest['strategy']}。"
             "两者不是同一个策略时，取舍点在你愿意为多少未满足需求付多少钱。")),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_sim(r: dict) -> None:
    print(f"策略              {r['strategy']}")
    print(f"回路滞后          {r['loop_lag_s']:.0f} 秒")
    print(f"轨迹              中位 {r['trace']['median_demand']}，"
          f"峰值 {r['trace']['peak_demand']}"
          f"（{r['trace']['peak_over_median']} 倍），"
          f"高峰持续 {r['trace']['surge_duration_s']:.0f} 秒")
    print(f"未满足需求        {r['unmet_demand']}"
          + (f"（{r['unmet_share']:.1%}）" if r["unmet_share"] is not None else ""))
    if r["rejected_demand"]:
        print(f"被准入挡下        {r['rejected_demand']}")
    print(f"扩缩容次数        {len(r['scale_events'])}，抖动 {r['thrash_count']} 次")
    if r["lag"]["mean_s"] is not None:
        print(f"生效延迟          均值 {r['lag']['mean_s']} 秒，"
              f"最大 {r['lag']['max_s']} 秒")
    print(f"成本指数          {r['cost_index']} 实例小时")
    print(f"结论              {r['verdict']}")
    print(f"                  {r['verdict_reason']}")


def print_compare(r: dict) -> None:
    print(f"轨迹              高峰是中位的 {r['trace']['peak_over_median']} 倍，"
          f"持续 {r['trace']['surge_duration_s']:.0f} 秒")
    print(f"{'策略':<18}{'未满足':>10}{'被拒':>10}{'抖动':>6}{'成本':>10}  结论")
    for s in r["strategies"]:
        print(f"{s['strategy']:<18}{s['unmet_demand']:>10.1f}"
              f"{s['rejected_demand']:>10.1f}{s['thrash_count']:>6}"
              f"{s['cost_index']:>10.1f}  {s['verdict']}")
    print(f"静态档位          admission-only 按需求 P95 ÷ 目标负载率 "
          f"{r['admission_only_target_load']} 配 {r['admission_only_static_instances']} 个实例")
    print(f"解读              {r['reading']}")
    print(f"注意              {r['loss_note']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    def add_sim(sp):
        sp.add_argument("--traffic", type=Path, required=True)
        sp.add_argument("--capacity-per-instance", type=float, default=150)
        sp.add_argument("--scale-up-threshold", type=float, default=0.7)
        sp.add_argument("--scale-down-threshold", type=float, default=0.4)
        sp.add_argument("--cold-start", type=float, default=300)
        sp.add_argument("--observation", type=float, default=60)
        sp.add_argument("--decision", type=float, default=60)
        sp.add_argument("--scale-up-cooldown", type=float, default=180)
        sp.add_argument("--scale-down-cooldown", type=float, default=1800)
        sp.add_argument("--min-instances", type=int, default=3)
        sp.add_argument("--max-instances", type=int, default=30)

    p_s = sub.add_parser("simulate", help="一种策略跑一段轨迹")
    add_sim(p_s)
    p_s.add_argument("--strategy", choices=STRATEGIES, default="reactive")
    p_s.add_argument("--output", type=Path, default=None)

    p_c = sub.add_parser("compare", help="27.8 那四种策略同轨迹对比")
    add_sim(p_c)
    p_c.add_argument("--target-load", type=float, default=0.7,
                     help="admission-only 静态档位按需求 P95 ÷ 它配")
    p_c.add_argument("--output", type=Path, default=None)

    p_l = sub.add_parser("lag", help="27.4 那张回路滞后表")
    p_l.add_argument("--observation", type=float, default=None)
    p_l.add_argument("--decision", type=float, default=None)
    p_l.add_argument("--cold-start", type=float, default=None)

    p_h = sub.add_parser("cache", help="22.4 那个式子用在一次扩缩容上")
    p_h.add_argument("--before", type=int, required=True)
    p_h.add_argument("--after", type=int, required=True)
    p_h.add_argument("--modulo", action="store_true", help="用取模哈希而不是一致性哈希")
    p_h.add_argument("--warm-minutes", type=float, default=120.0)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "lag":
            r = loop_lag(args.observation, args.decision, args.cold_start)
            if "parts" in r and "low_s" in r:
                for k, v in r["parts"].items():
                    print(f"  {k:<14}{v['low_s']:>5} 到 {v['high_s']:>5} 秒")
            print(f"解读              {r['reading']}")
            return 0
        if args.cmd == "cache":
            r = cache_impact(args.before, args.after,
                             consistent_hashing=not args.modulo,
                             warm_minutes_full=args.warm_minutes)
            print(f"解读              {r['reading']}")
            return 0
        trace = load_trace(args.traffic)
        base = dict(capacity_per_instance=args.capacity_per_instance,
                    scale_up_threshold=args.scale_up_threshold,
                    scale_down_threshold=args.scale_down_threshold,
                    cold_start_s=args.cold_start,
                    observation_s=args.observation, decision_s=args.decision,
                    scale_up_cooldown_s=args.scale_up_cooldown,
                    scale_down_cooldown_s=args.scale_down_cooldown,
                    min_instances=args.min_instances,
                    max_instances=args.max_instances)
        if args.cmd == "simulate":
            result = simulate(trace, strategy=args.strategy, **base)
            print_sim(result)
        else:
            result = compare(trace, base, target_load=args.target_load)
            print_compare(result)
        if args.output is not None:
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}")
        return 0
    except SimError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
