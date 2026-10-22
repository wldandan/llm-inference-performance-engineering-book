#!/usr/bin/env python3
"""Choose a serving form, then check what the router did to Prefix Cache.

Two halves, matching the two halves of the chapter.

  decide      22.2's four criteria, in 22.2's priority order. Costs are computed
              and reported, but they are not the first criterion and the output
              says so: 22.1's whole point is that 自建's real advantages are not
              cost. Offline.
  route-eval  22.4's trade-off, as two numbers that move in opposite
              directions: cache hit rate and load skew. The routing-term table
              is offline arithmetic (13.3's formula: a session prefix reused k
              times over N round-robin replicas); measuring the real hit rate
              needs several instances.

Three things this script refuses to do:

  It will not recommend 自托管 or 专用部署 without `--team-capacity`. 22.2 calls
  that criterion the most often underestimated one, and a recommendation that
  silently skips it is the failure mode the chapter is warning about.

  It will not report a routing result without `worst_instance`. 22.5 says
  aggregate metrics hide single-instance problems, so the aggregate alone is not
  an acceptable report.

  It will not let a cache hit rate exceed the cacheable share. That share is the
  ceiling (13.3), and a measured number above it means the measurement is wrong,
  not that the cache beat physics.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

SECONDS_PER_MONTH = 86400 * 30

# 22.2's priority order. The list is the algorithm.
CRITERIA = ("hard_constraints", "traffic_shape", "latency", "team_capacity")

# 22.2 一、三条硬约束，任何一条成立就直接走自托管，不用再算成本。
HARD_CONSTRAINTS = {
    "data_residency": "数据不能出域",
    "custom_weights": "必须用微调后的模型",
    "specific_hardware": "必须跑在特定硬件上",
}

FORMS = ("共享 API", "专用部署", "自托管")

# 22.4 的三种路由形态。
STRATEGIES = ("round-robin", "prefix-hash", "prefix-hash-with-overflow")

# 22.4 的经验界：0.3 以下感觉不到，0.5 以上最慢的那个实例开始决定整体 P99。
# 两条都只在平均负载率不高时成立，见 hottest_instance_load。
SKEW_UNNOTICEABLE = 0.3
SKEW_P99_DOMINATED = 0.5

# 22.2 第二条判据写成脚本时的那条线：峰谷比到这里就推荐共享 API。它是本书的
# 经验界，不是算出来的，代表的是 22.1 那三项不进月成本的投入。已经在养别的
# 自建服务的团队，那三项的边际成本低，应该把它调高。
API_PEAK_TROUGH = 5.0


class ChoiceError(Exception):
    """An input that cannot support the decision asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ChoiceError(message)


# --------------------------------------------------------------------------
# decide
# --------------------------------------------------------------------------

def monthly_api_cost(mean_qps: float, tokens_per_request: float,
                     price_per_1k: float) -> float:
    """按 token 计价的月成本。"""
    _require(mean_qps >= 0, "mean_qps 不能为负")
    _require(tokens_per_request > 0, "tokens_per_request 必须为正")
    tokens = mean_qps * SECONDS_PER_MONTH * tokens_per_request
    return tokens / 1000.0 * price_per_1k


def monthly_selfhost_cost(peak_qps: float, capacity_per_gpu: float,
                          gpu_monthly: float) -> tuple[float, int]:
    """按峰值容量配置的月成本，以及要几张卡。

    22.1 的第一项：API 按实际用量计费，自建按卡的存在计费。所以这里用的是
    peak_qps，不是均值。
    """
    _require(capacity_per_gpu > 0, "capacity_per_gpu 必须为正")
    gpus = math.ceil(peak_qps / capacity_per_gpu) if peak_qps > 0 else 0
    return gpus * gpu_monthly, gpus


def breakeven_mean_qps(selfhost_monthly: float, tokens_per_request: float,
                       price_per_1k: float) -> float:
    """两者成本相等的平均 QPS，按当前这套峰值配置算。

    固定峰值配置是一个明确的简化：真实的自建成本会随峰值跳档，所以这个数只在
    当前档位附近有意义，输出里会写明。
    """
    per_qps = (SECONDS_PER_MONTH * tokens_per_request / 1000.0 * price_per_1k)
    _require(per_qps > 0, "单位 QPS 的月 API 成本为 0，无法求平衡点")
    return selfhost_monthly / per_qps


def decide(*, workload: dict, peak_qps: float, trough_qps: float,
           api_price_per_1k: float, gpu_monthly: float,
           capacity_per_gpu: float, slo_ttft_ms: float | None = None,
           constraints: dict | None = None,
           team_capacity: str | None = None,
           api_peak_trough: float = API_PEAK_TROUGH) -> dict:
    constraints = constraints or {}
    _require(peak_qps > 0, "peak_qps 必须为正")
    _require(trough_qps >= 0, "trough_qps 不能为负")
    mean_qps = workload.get("mean_qps")
    if mean_qps is None:
        mean_qps = (peak_qps + trough_qps) / 2.0
        mean_source = "由峰谷取中点估的，不是量出来的"
    else:
        mean_source = "来自 workload 描述"
    tokens_per_request = workload.get("tokens_per_request")
    _require(tokens_per_request is not None,
             "workload 里没有 tokens_per_request：没有它 API 成本算不出来，"
             "而这正是第 6 章那份负载描述该提供的字段")

    fired = [{"key": k, "why": HARD_CONSTRAINTS[k]}
             for k in HARD_CONSTRAINTS if constraints.get(k)]
    unknown = [k for k in constraints if k not in HARD_CONSTRAINTS]
    _require(not unknown, f"不认识的约束：{unknown}；"
                          f"22.2 只列了三条硬约束 {list(HARD_CONSTRAINTS)}")

    api_monthly = monthly_api_cost(mean_qps, tokens_per_request,
                                   api_price_per_1k)
    selfhost_monthly, gpus = monthly_selfhost_cost(
        peak_qps, capacity_per_gpu, gpu_monthly)
    utilization = (mean_qps / (gpus * capacity_per_gpu)) if gpus else 0.0
    ratio = (peak_qps / trough_qps) if trough_qps > 0 else float("inf")
    breakeven = breakeven_mean_qps(selfhost_monthly, tokens_per_request,
                                   api_price_per_1k)
    # 盈亏平衡负载率：平均负载率到这里，按卡钱算自建和 API 打平。
    breakeven_util = (breakeven / (gpus * capacity_per_gpu)) if gpus else 0.0

    reasons: list[str] = []
    if fired:
        form = "自托管"
        reasons.append(f"硬约束成立（{'、'.join(c['why'] for c in fired)}），"
                       "按 22.2 的第一条直接走自托管，成本不参与这个决定")
        cost_decides = False
    else:
        cost_decides = True
        # 22.2 二、流量的形状。波动大、有明显波谷的走 API。
        if ratio >= api_peak_trough:
            form = "共享 API"
            reasons.append(
                f"峰谷比 {round(ratio, 2)}，过了 {api_peak_trough} 这条线："
                f"自建要按峰值配 {gpus} 张卡和一支团队，22.1 那三项不进月成本的投入"
                "（工程、可用性、模型迭代）在这种只在峰值时段用满的形状下最不划算。"
                f"这条线是经验界，已经在养别的自建服务的团队可以用 --api-peak-trough 调高")
        else:
            form = "专用部署"
            reasons.append(f"峰谷比 {round(ratio, 2)}，流量平稳，"
                           "独占资源的延迟稳定性可以拿到")
        # 22.2 三、延迟要求。共享 API 的 P99 受邻居影响。
        if slo_ttft_ms is not None and slo_ttft_ms <= 1500 and form == "共享 API":
            form = "专用部署"
            reasons.append(f"TTFT SLO 卡在 {slo_ttft_ms} ms："
                           "共享 API 的 P99 受其他租户影响，这个档位拿不到保障，"
                           "所以形状虽然偏 API，延迟这一条把它推回专用部署")

    # 22.2 四、团队能不能养。这一条最常被低估，所以它是一道闸，不是一句建议。
    if form in ("自托管", "专用部署"):
        _require(team_capacity is not None,
                 f"结论是{form}，但没有填 --team-capacity："
                 "22.2 把“团队能不能养”列为第四条判据并说它最常被低估，"
                 "没有这一项的结论不能出")
        if team_capacity == "no":
            reasons.append("团队填的是养不起：没有持续投入的自建服务通常比 API "
                           "更慢也更不稳定。硬约束成立时这是一个必须先解决的前置条件，"
                           "硬约束不成立时应该退回共享 API")
            if not fired:
                form = "共享 API"

    if cost_decides:
        cheaper = "自托管" if selfhost_monthly < api_monthly else "共享 API"
        reasons.append(f"按卡钱算{cheaper}更便宜"
                       f"（API {round(api_monthly)} vs 自建 {round(selfhost_monthly)}）："
                       f"平均负载率过 {round(breakeven_util * 100, 1)}% 自建就和 API 打平，"
                       f"这份负载是 {round(utilization * 100, 1)}%。"
                       "但 22.1 说过成本通常不是自建的真正优势，所以它排在判据之后")

    return {
        "hard_constraints": fired,
        "peak_qps": peak_qps,
        "trough_qps": trough_qps,
        "mean_qps": round(mean_qps, 4),
        "mean_qps_source": mean_source,
        "peak_trough_ratio": (round(ratio, 4) if ratio != float("inf")
                              else "无穷（波谷为 0）"),
        "gpus_for_peak": gpus,
        "utilization": round(utilization, 4),
        "api_monthly": round(api_monthly, 2),
        "selfhost_monthly": round(selfhost_monthly, 2),
        "breakeven_qps": round(breakeven, 4),
        "breakeven_utilization": round(breakeven_util, 4),
        "api_peak_trough": api_peak_trough,
        "breakeven_note": ("按当前这套峰值配置算的；峰值一涨卡数跳档，"
                           "这个数会跟着跳，所以它只在当前档位附近有意义"),
        "cost_is_decisive": cost_decides,
        "recommendation": form,
        "reasons": reasons,
        "revisit_when": [
            "流量涨到现在的十倍，或峰谷比变化超过一倍",
            "换模型，因为容量和 tokens_per_request 都会变",
            "合规要求变化，三条硬约束里任何一条的状态改变",
            "团队投入变化，第四条判据的答案改变",
        ],
    }


# --------------------------------------------------------------------------
# route-eval
# --------------------------------------------------------------------------

def load_skew(counts: list[float]) -> float:
    """各实例请求数的样本标准差除以均值，与第 7 章那个变异系数同一套口径。

    22.4: 完全均衡是 0；四个实例里有一个接了全部流量是 2.0。
    """
    _require(bool(counts), "没有实例请求数")
    _require(all(c >= 0 for c in counts), "请求数不能为负")
    mean = sum(counts) / len(counts)
    _require(mean > 0, "所有实例的请求数都是 0，不均衡度无从计算")
    if len(counts) == 1:
        return 0.0
    return statistics.stdev(counts) / mean


def hottest_instance_load(mean_rho: float, skew: float, instances: int) -> float:
    """22.4：最热那个实例的负载率最坏是 ρ̄ × (1 + skew × (N − 1)/√N)。

    最坏情况是全部偏差都压在一个实例上；skew 用样本标准差口径。N = 4、ρ̄ = 0.7、
    skew = 0.3 时约 1.0，所以“0.3 以下感觉不到”只在负载不高时成立。
    """
    _require(instances >= 1, "实例数至少 1")
    _require(mean_rho >= 0 and skew >= 0, "负载率和不均衡度不能为负")
    if instances == 1:
        return mean_rho
    return mean_rho * (1 + skew * (instances - 1) / math.sqrt(instances))


def upgrade_load(rho: float, instances: int) -> float:
    """22.5：滚动升级时摘掉一个实例，其余 N − 1 个的负载率是 ρ × N/(N − 1)。"""
    _require(instances >= 2, "至少两个实例才谈得上滚动升级")
    return rho * instances / (instances - 1)


def routing_term(replicas: int, reuse: int) -> float:
    """13.3 的路由项：一个前缀被复用 k 次、随机落在 N 个副本上时命中的比例。

    每个被碰到的副本都要先付一次首次写入，所以是 1 − N(1 − (1 − 1/N)^k)/k。
    假设每个副本的缓存都装得下；装不下时更低，往 1/N 掉。与
    code/ch13/prefill_optimization_check.py 的同名函数是同一个式子。
    """
    _require(replicas >= 1 and reuse >= 1, "副本数和复用次数至少是 1")
    touched = replicas * (1 - (1 - 1 / replicas) ** reuse)
    return 1 - touched / reuse


def read_skew(skew: float) -> str:
    if skew <= SKEW_UNNOTICEABLE:
        return f"{round(skew, 4)}，在 0.3 以下，感觉不到"
    if skew < SKEW_P99_DOMINATED:
        return f"{round(skew, 4)}，在 0.3 到 0.5 之间，开始能看出来但还不决定 P99"
    return (f"{round(skew, 4)}，到了 0.5 以上，"
            "最慢的那个实例会开始决定整体 P99")


def hit_rate_ceiling(cacheable_share: float, instances: int, strategy: str,
                     overflow_share: float = 0.1) -> float:
    """命中率不可能超过的那条线，按 22.4 的三种形态取值。

    可缓存占比本身是硬天花板。轮询不另设天花板：全体共享的前缀轮询下照样命中，
    会话级前缀掉多少取决于复用次数和缓存装不装得下（见 routing_term），所以
    1/N 不是一条可以用来拒绝报告的线。带溢出时，溢出出去的那部分只有落回原实例
    （概率 1/N）才可能命中。
    """
    _require(0 <= cacheable_share <= 1,
             f"可缓存占比 {cacheable_share} 不在 [0, 1] 内")
    _require(instances >= 1, "实例数至少 1")
    _require(strategy in STRATEGIES,
             f"不认识的路由策略 {strategy}，22.4 只列了 {list(STRATEGIES)}")
    _require(0 <= overflow_share < 1, "溢出比例要在 [0, 1) 内")
    if strategy in ("round-robin", "prefix-hash"):
        route = 1.0
    else:
        route = 1.0 - overflow_share * (1.0 - 1.0 / instances)
    return cacheable_share * route


def scaling_table(cacheable_share: float, instance_counts=(1, 4, 8),
                  reuse_counts=(2, 10, 100)) -> list[dict]:
    """22.4 那张表：会话级前缀被轮询打散时，路由项随副本数掉下去。

    每行给出各复用次数下的路由项，以及乘上可缓存占比之后的命中率上限。全体共享
    的前缀复用次数极大，路由项接近 1，不在这张表里受伤。
    """
    rows = []
    for n in instance_counts:
        terms = {k: round(routing_term(n, k), 6) for k in reuse_counts}
        rows.append({
            "instances": n,
            "routing_term": terms,
            "hit_rate_upper": {k: round(cacheable_share * t, 6)
                               for k, t in terms.items()},
        })
    return rows


def evaluate_strategy(name: str, per_instance: list[dict],
                      cacheable_share: float,
                      p95_ttft: float | None = None,
                      overflow_share: float = 0.1) -> dict:
    """One strategy's row: hit rate, skew, aggregate and worst instance.

    22.7 单列 worst_instance 是刻意的，所以这里缺它就报错，不给一个只有聚合值
    的结果。
    """
    _require(name in STRATEGIES, f"不认识的路由策略 {name}")
    _require(bool(per_instance), f"{name} 没有任何实例数据")
    for i, inst in enumerate(per_instance):
        for field in ("requests", "cache_hit_rate", "p95_ttft"):
            _require(inst.get(field) is not None,
                     f"{name} 第 {i} 个实例缺 {field}："
                     "22.5 说聚合指标会掩盖单实例问题，所以每个实例都要报全")
        _require(inst["cache_hit_rate"] <= cacheable_share + 1e-9,
                 f"{name} 第 {i} 个实例的命中率 {inst['cache_hit_rate']} "
                 f"超过了可缓存占比 {cacheable_share}：那是天花板，"
                 "超过说明量错了，不是缓存赢了物理")

    counts = [inst["requests"] for inst in per_instance]
    total = sum(counts)
    _require(total > 0, f"{name} 的请求总数是 0")
    # 命中率按请求数加权，不是各实例简单平均：轻载实例的高命中率不该和满载实例
    # 的低命中率等权，那会让打散的策略看起来比实际好。
    weighted = sum(inst["cache_hit_rate"] * inst["requests"]
                   for inst in per_instance) / total
    worst = max(per_instance, key=lambda inst: inst["p95_ttft"])
    skew = load_skew(counts)
    ceiling = hit_rate_ceiling(cacheable_share, len(per_instance), name,
                               overflow_share)
    # 加权命中率超过天花板，说明声明的溢出比例和实际跑出来的不是一回事。这一条
    # 比单实例那条更容易被踩到，因为溢出比例是配置，不是量出来的。
    _require(weighted <= ceiling + 1e-6,
             f"{name} 的加权命中率 {round(weighted, 4)} 超过天花板 "
             f"{round(ceiling, 4)}：声明的溢出比例 {overflow_share} "
             "和实际不符，先把这个数对上再谈取舍")
    return {
        "strategy": name,
        "instances": len(per_instance),
        "cache_hit_rate": round(weighted, 6),
        "cache_hit_rate_ceiling": round(ceiling, 6),
        "load_skew": round(skew, 6),
        "load_skew_reading": read_skew(skew),
        "p95_ttft": p95_ttft,
        "worst_instance": {
            "index": per_instance.index(worst),
            "p95_ttft": worst["p95_ttft"],
            "requests": worst["requests"],
            "cache_hit_rate": worst["cache_hit_rate"],
        },
        "aggregate_hides": (
            None if p95_ttft is None else
            round(worst["p95_ttft"] - p95_ttft, 4)),
    }


def route_eval(report: dict) -> dict:
    cacheable = report.get("cacheable_share")
    _require(cacheable is not None,
             "报告里没有 cacheable_share：22.4 说取舍点取决于可缓存比例，"
             "没有它这份评估读不出该往哪边走")
    rows = []
    for name in STRATEGIES:
        block = (report.get("strategies") or {}).get(name)
        if block is None:
            continue
        rows.append(evaluate_strategy(
            name, block["per_instance"], cacheable, block.get("p95_ttft"),
            block.get("overflow_share", 0.1)))
    _require(len(rows) >= 2,
             "至少要两种策略才谈得上取舍，一种策略的数只是一个现状")

    best_hit = max(rows, key=lambda r: r["cache_hit_rate"])
    best_skew = min(rows, key=lambda r: r["load_skew"])
    conflict = best_hit["strategy"] != best_skew["strategy"]
    # 22.4 说第三种形态才是实际可用的那个。这里把“实际可用”写成一条判据：
    # 在不均衡度还感觉不到的那些策略里，取命中率最高的。
    acceptable = [r for r in rows if r["load_skew"] <= SKEW_UNNOTICEABLE]
    practical = (max(acceptable, key=lambda r: r["cache_hit_rate"])
                 if acceptable else None)
    result = {
        "cacheable_share": cacheable,
        "scaling_table": scaling_table(cacheable),
        "strategies": rows,
        "best_hit_rate": best_hit["strategy"],
        "best_balance": best_skew["strategy"],
        "conflict": conflict,
        "practical": practical["strategy"] if practical else None,
        "reading": (
            f"命中率最高的是 {best_hit['strategy']}"
            f"（{round(best_hit['cache_hit_rate'] * 100, 1)}%），"
            f"最均衡的是 {best_skew['strategy']}"
            f"（不均衡度 {round(best_skew['load_skew'], 3)}）。"
            + ("两者不是同一个策略，这就是 22.4 那个取舍，"
               "溢出阈值就是在这两个数之间定位置。"
               if conflict else
               "两者是同一个策略，这种情况下不必取舍，直接用它。")),
    }
    if practical is not None:
        result["practical_reading"] = (
            f"不均衡度在 0.3 以内的策略里，命中率最高的是 {practical['strategy']}"
            f"（{round(practical['cache_hit_rate'] * 100, 1)}%，"
            f"不均衡度 {round(practical['load_skew'], 3)}）。")
    else:
        result["practical_reading"] = (
            "没有一种策略把不均衡度压在 0.3 以内：要么加溢出，要么这条链路的"
            "可缓存占比不足以支撑前缀亲和。")
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_decide(r: dict) -> None:
    print(f"硬约束            {[c['why'] for c in r['hard_constraints']] or '无'}")
    print(f"峰谷比            {r['peak_trough_ratio']}")
    print(f"峰值需要          {r['gpus_for_peak']} 张卡，"
          f"平均负载率 {round(r['utilization'] * 100, 1)}%")
    print(f"API 月成本        {r['api_monthly']}")
    print(f"自建月成本        {r['selfhost_monthly']}")
    print(f"平衡点            平均 {r['breakeven_qps']} QPS，"
          f"即平均负载率 {round(r['breakeven_utilization'] * 100, 1)}%")
    print(f"                  {r['breakeven_note']}")
    print(f"建议形态          {r['recommendation']}")
    for reason in r["reasons"]:
        print(f"  - {reason}")
    print("什么时候重新评估")
    for item in r["revisit_when"]:
        print(f"  - {item}")


def print_route_eval(r: dict) -> None:
    print(f"可缓存占比        {r['cacheable_share']}")
    print("会话级前缀被轮询打散时的路由项（缓存装得下时；装不下更低）")
    for row in r["scaling_table"]:
        cells = "  ".join(f"k={k} {round(v * 100, 1)}%"
                          for k, v in row["routing_term"].items())
        print(f"  {row['instances']} 个实例  {cells}")
    print("各策略实测")
    for row in r["strategies"]:
        print(f"  {row['strategy']}")
        print(f"    命中率        {round(row['cache_hit_rate'] * 100, 1)}%"
              f"（天花板 {round(row['cache_hit_rate_ceiling'] * 100, 1)}%）")
        print(f"    不均衡度      {row['load_skew_reading']}")
        print(f"    整体 P95 TTFT {row['p95_ttft']}")
        print(f"    最差实例      #{row['worst_instance']['index']}，"
              f"P95 {row['worst_instance']['p95_ttft']}"
              + (f"，聚合掩盖了 {row['aggregate_hides']} ms"
                 if row["aggregate_hides"] is not None else ""))
    print(f"解读              {r['reading']}")
    print(f"实际可用形态      {r['practical'] or '无'}")
    print(f"                  {r['practical_reading']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_d = sub.add_parser("decide", help="22.2 那四条判据，按优先级排")
    p_d.add_argument("--workload", type=Path, required=True)
    p_d.add_argument("--peak-qps", type=float, required=True)
    p_d.add_argument("--trough-qps", type=float, required=True)
    p_d.add_argument("--data-residency", choices=("required", "not-required"),
                     default="not-required")
    p_d.add_argument("--custom-weights", action="store_true")
    p_d.add_argument("--specific-hardware", action="store_true")
    p_d.add_argument("--slo-ttft", type=float, default=None)
    p_d.add_argument("--api-price", type=float, required=True,
                     help="每千 token 的价格")
    p_d.add_argument("--gpu-monthly", type=float, required=True)
    p_d.add_argument("--capacity-per-gpu", type=float, required=True)
    p_d.add_argument("--team-capacity", choices=("yes", "no"), default=None,
                     help="22.2 第四条判据；结论是自建时必填")
    p_d.add_argument("--api-peak-trough", type=float, default=API_PEAK_TROUGH,
                     help="峰谷比到这里推荐共享 API；经验界，默认 5")
    p_d.add_argument("--output", type=Path, default=None)

    p_r = sub.add_parser("route-eval", help="22.4 那个取舍：命中率与不均衡度")
    p_r.add_argument("--report", type=Path, required=True)
    p_r.add_argument("--output", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "decide":
            workload = json.loads(args.workload.read_text(encoding="utf-8"))
            result = decide(
                workload=workload, peak_qps=args.peak_qps,
                trough_qps=args.trough_qps, api_price_per_1k=args.api_price,
                gpu_monthly=args.gpu_monthly,
                capacity_per_gpu=args.capacity_per_gpu,
                slo_ttft_ms=args.slo_ttft,
                constraints={
                    "data_residency": args.data_residency == "required",
                    "custom_weights": args.custom_weights,
                    "specific_hardware": args.specific_hardware,
                },
                team_capacity=args.team_capacity,
                api_peak_trough=args.api_peak_trough)
            print_decide(result)
        else:
            report = json.loads(args.report.read_text(encoding="utf-8"))
            result = route_eval(report)
            print_route_eval(result)
        if args.output is not None:
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}")
        return 0
    except ChoiceError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
