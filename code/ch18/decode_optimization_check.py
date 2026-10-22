#!/usr/bin/env python3
"""Decide which of the three non-precision Decode optimizations applies here,
and refuse to guess the one number that decides Speculative Decoding.

The chapter's three techniques answer different bottleneck shapes, so the
script's first job is to name the shape (18.1), and only then to judge each
technique against it. Four things it does on purpose:

  - Speculative Decoding gets NO benefit estimate without a measured
    acceptance report. That number is a business-content property and does not
    transfer between services (18.7, 18.8 case two), so an industry average
    would be worse than silence.
  - The gain formula is `a ÷ (1 + k × c)` (18.3) and the script reports the
    break-even line `a > 1 + k × c` alongside it, because below that line
    Speculative Decoding is a net loss, not a small gain. `a` is the mean
    accepted length per round (1 to k+1); engines usually report the
    per-position acceptance rate α instead, and a = (1 − α^(k+1)) ÷ (1 − α)
    converts one into the other.
  - At high batch the formula's premise fails rather than the formula. The
    denominator's 1 means "verification is nearly free", which stops being true
    once compute is busy (18.8 case one), so the script says the premise is
    gone instead of quietly reporting a number.
  - The CUDA Graph model-size threshold is DERIVED, not hardcoded: it is the
    parameter count at which the per-step launch overhead falls below 1% of the
    bandwidth floor. So it moves when the bandwidth does.

Only the Python standard library. No GPU.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

GIB = 1024 ** 3
KIB = 1024

# 18.7's bands, the same ones 15.5 uses to read a measurement against the floor.
RATIO_BANDWIDTH_BOUND = 1.3
RATIO_SCHEDULER_BOUND = 2.0

# 18.3: verification pushes B × (k + 1) positions through the target model, so
# the "compute is idle" premise is gone once B × (k + 1) reaches the ridge
# point. On the reference card (ridge 153) with k = 4 that is about 31.
REFERENCE_RIDGE = 153.0
DEFAULT_K = 4
SPEC_BATCH_CEILING = REFERENCE_RIDGE / (DEFAULT_K + 1)

# 15.6: the kernel-launch share of one step, which barely moves with model size.
LAUNCH_MS_PER_STEP = 0.5
# 18.4: below this share of the step floor, CUDA Graph stops being worth a
# memory slot. 1% at 1000 GB/s lands the threshold near 30B.
CUDA_GRAPH_SHARE_FLOOR = 0.01
# 18.4 / 18.8 case two: graph memory is NOT a per-bucket constant. Common
# engines capture from the largest batch down into one shared pool, so the
# total is set mostly by the largest captured batch. The only trustworthy
# number is the one in the engine's startup log.


class CheckError(ValueError):
    """Raised when a judgement cannot be made from the inputs given."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def bottleneck_form(tpot_measured: float, tpot_floor: float) -> dict:
    """18.1, 18.7: name the shape before judging any technique against it."""
    _require(tpot_measured > 0 and tpot_floor > 0,
             "measured TPOT and floor must both be positive")
    ratio = tpot_measured / tpot_floor
    if ratio < 1.0:
        form, reason = "口径有问题", (
            "实测比带宽下限还快。下限已假设带宽满载，所以这不是好消息，"
            "是这段时间的边界定义有问题（15.5）"
        )
    elif ratio <= RATIO_BANDWIDTH_BOUND:
        form, reason = "带宽受限", (
            f"实测是下限的 {ratio:.2f} 倍，时间确实花在读权重上，算力是空闲的"
        )
    elif ratio <= RATIO_SCHEDULER_BOUND:
        form, reason = "混合", (
            f"实测是下限的 {ratio:.2f} 倍，搬运是主项但已有可观的额外开销"
        )
    else:
        form, reason = "调度受限", (
            f"实测是下限的 {ratio:.2f} 倍，大部分时间不在读权重。"
            "先做 15.6 那个拆分，分清 kernel 启动与引擎侧准备各占多少"
        )
    return {"ratio": round(ratio, 3), "form": form, "reason": reason}


def spec_break_even(k: int, c: float) -> float:
    """18.3: `a > 1 + k × c`. The 1 is verification, which is nearly free."""
    _require(k >= 1, "k must be at least 1")
    _require(c > 0, "draft cost ratio must be positive")
    return 1.0 + k * c


def mean_accepted_from_rate(alpha: float, k: int) -> float:
    """a = (1 − α^(k+1)) ÷ (1 − α), assuming positions are accepted independently.

    α is the per-position acceptance probability engines report (0 to 1);
    a is the mean number of tokens one round produces (1 to k+1).
    """
    _require(0 <= alpha < 1, "acceptance rate α must be in [0, 1)")
    _require(k >= 1, "k must be at least 1")
    return (1 - alpha ** (k + 1)) / (1 - alpha)


def best_k(alpha: float, c: float, k_max: int = 16) -> int:
    """The k that maximises a(α, k) ÷ (1 + k × c): k has an optimum (18.3)."""
    return max(range(1, k_max + 1),
               key=lambda k: mean_accepted_from_rate(alpha, k) / (1 + k * c))


def spec_batch_ceiling(ridge: float, k: int) -> float:
    """Batch at which verification stops being free: ridge ÷ (k + 1)."""
    _require(ridge > 0 and k >= 1, "ridge must be positive and k at least 1")
    return ridge / (k + 1)


def spec_gain(acceptance: float, k: int, c: float) -> float:
    """18.3: `a ÷ (1 + k × c)`. Below 1 this technique is a net loss."""
    _require(acceptance >= 1.0,
             "平均接受数至少是 1：不匹配的位置上用的是目标模型自己的结果")
    return acceptance / spec_break_even(k, c)


def draft_memory_cost(draft_params: float, bytes_per_element: float,
                      kv_bytes_per_token: float) -> dict:
    """18.3: the draft model is resident, so its bytes come out of the KV
    budget and the capacity table shrinks.
    """
    draft_bytes = draft_params * bytes_per_element
    return {
        "draft_gb_decimal": round(draft_bytes / 1e9, 3),
        "draft_gib": round(draft_bytes / GIB, 3),
        "tokens_displaced": int(draft_bytes / kv_bytes_per_token),
    }


def cuda_graph_threshold_params(bandwidth_gb_per_s: float,
                                bytes_per_element: float = 2.0) -> float:
    """18.4's 30B line, derived rather than asserted.

    The launch overhead is a fixed ~0.5 ms per step. The floor is
    `params × bytes ÷ bandwidth`. Setting the launch share equal to 1% gives
    the parameter count above which CUDA Graph stops earning its memory:

        0.5 ÷ (params × bytes ÷ bandwidth × 1000) = 0.01

    At 2 bytes and 1000 GB/s that is 25e9, so 30B is comfortably past it. On a
    2039 GB/s card the same 1% line sits at 51e9, which is the point: the
    threshold is a property of the card, not a constant.
    """
    _require(bandwidth_gb_per_s > 0, "bandwidth must be positive")
    floor_ms_at_threshold = LAUNCH_MS_PER_STEP / CUDA_GRAPH_SHARE_FLOOR
    return floor_ms_at_threshold / 1000.0 * bandwidth_gb_per_s * 1e9 \
        / bytes_per_element


def launch_share(params: float, bandwidth_gb_per_s: float,
                 bytes_per_element: float = 2.0) -> float:
    """What fraction of the step floor the launch overhead is, at this size."""
    floor_ms = params * bytes_per_element / (bandwidth_gb_per_s * 1e9) * 1000.0
    _require(floor_ms > 0, "step floor must be positive")
    return LAUNCH_MS_PER_STEP / floor_ms


def judge_spec_decoding(*, form: str, batch_p50: int, batch_p95: int,
                        acceptance: dict | None, draft: dict | None,
                        ridge: float = REFERENCE_RIDGE) -> dict:
    """18.7's criteria, in the order the text puts them: the acceptance rule
    is last because it overrides everything else.
    """
    _require(batch_p50 >= 1 and batch_p95 >= batch_p50,
             "batch P50 must be at least 1 and P95 at least P50")

    reasons: list[str] = []
    verdict = "适用"
    k_for_ceiling = int(acceptance["k"]) if acceptance and "k" in acceptance else DEFAULT_K
    ceiling = spec_batch_ceiling(ridge, k_for_ceiling)

    if form == "调度受限":
        verdict = "不适用"
        reasons.append(
            "瓶颈在调度，不在带宽。投机解码换的是步数，换不回调度开销，"
            "先走 CUDA Graph 那条路"
        )
    elif form == "混合":
        reasons.append("瓶颈是混合形态，收益会比纯带宽受限时小，要实测确认")

    if batch_p50 > ceiling:
        verdict = "收益有限"
        reasons.append(
            f"批量 P50 是 {batch_p50}，超过 分界点 {ridge:.0f} ÷ (k + 1) ≈ {ceiling:.0f}。"
            "验证一次要处理 批量 × (k + 1) 个位置，越过这条线算力不再空闲，投机解码抢的是真实算力"
            "（18.3 那个副作用，也是 18.8 案例一多出来的那 8 个百分点）"
        )
    if batch_p95 > ceiling >= batch_p50:
        reasons.append(
            f"批量 P95 已到 {batch_p95}：高峰时段收益会缩水，"
            "按 19.4 第 3 轮的要求在两个批量档位各测一次"
        )

    # The acceptance rule is last and it wins: without a measured number there
    # is no estimate, whatever the other criteria say.
    if acceptance is None:
        return {
            "verdict": "待测",
            "reasons": reasons + [
                "没有提供 --draft-acceptance。接受率是这项技术唯一的决定因素，"
                "它取决于内容的可预测性，是业务属性，在场景之间完全不可迁移。"
                "没测过就不给预估，也不填行业平均值（18.7）"
            ],
            "gain_ratio": None,
            "break_even_acceptance": None,
            "batch_ceiling": round(ceiling, 1),
            "draft_memory": draft,
        }

    k = int(acceptance["k"])
    c = float(acceptance["draft_cost_ratio"])
    alpha = acceptance.get("acceptance_rate")
    if "mean_accepted" in acceptance:
        a = float(acceptance["mean_accepted"])
    else:
        a = mean_accepted_from_rate(float(alpha), k)
    break_even = spec_break_even(k, c)
    gain = spec_gain(a, k, c)

    if gain <= 1.0:
        verdict = "不适用"
        reasons.append(
            f"实测平均接受数 {a} 低于盈亏线 {break_even:.2f}，"
            f"收益比 {gain:.2f}，是净亏损而不是收益小（18.3）"
        )
    else:
        reasons.append(
            f"实测平均接受数 {a}，盈亏线 {break_even:.2f}，"
            f"收益比 {gain:.2f} 倍"
        )

    premise = None
    if batch_p50 > ceiling:
        premise = (
            f"这个收益比在批量 {batch_p50} 下不成立。式子分母里那个 1 代表"
            "“验证近乎免费”，批量大到算力不空闲时它会变大，所以实测会比 "
            f"{gain:.2f} 差。不是式子失灵，是式子的前提失效了（18.8 案例一）"
        )

    return {
        "verdict": verdict,
        "reasons": reasons,
        "gain_ratio": round(gain, 3),
        "break_even_acceptance": round(break_even, 3),
        "measured_acceptance": a,
        "mean_accepted_length": round(a, 3),
        "acceptance_rate": alpha,
        "best_k": best_k(float(alpha), c) if alpha is not None else None,
        "batch_ceiling": round(ceiling, 1),
        "k": k,
        "draft_cost_ratio": c,
        "premise_warning": premise,
        "draft_memory": draft,
    }


def judge_cuda_graph(*, form: str, params: float, bandwidth_gb_per_s: float,
                     captured_buckets: int | None = None,
                     graph_memory_gib: float | None = None,
                     bytes_per_element: float = 2.0) -> dict:
    threshold = cuda_graph_threshold_params(bandwidth_gb_per_s, bytes_per_element)
    share = launch_share(params, bandwidth_gb_per_s, bytes_per_element)

    reasons = [
        f"每步 kernel 启动约 {LAUNCH_MS_PER_STEP} ms，占这个规模单步下限的 "
        f"{share * 100:.2f}%；这张卡上 1% 那条线落在 {threshold / 1e9:.0f}B"
    ]
    if params > threshold:
        verdict = "收益有限"
        reasons.append(
            f"参数量 {params / 1e9:.0f}B 已越过 {threshold / 1e9:.0f}B："
            "启动开销淹没在每步的搬运里，为它付一档显存不值得"
        )
    elif form == "带宽受限":
        verdict = "确认项"
        reasons.append(
            "瓶颈在带宽而不在调度，所以这是一个确认项而非待做项："
            "多数框架默认开启，要查的是它占的显存有没有过大（18.6）"
        )
    else:
        verdict = "适用"
        reasons.append("瓶颈里有调度那一份，这项直接针对它")

    memory: dict | None = None
    if captured_buckets is not None or graph_memory_gib is not None:
        if captured_buckets is not None:
            _require(captured_buckets >= 1, "captured buckets must be at least 1")
        if graph_memory_gib is not None:
            _require(graph_memory_gib >= 0, "graph memory must not be negative")
        memory = {
            "captured_buckets": captured_buckets,
            "graph_memory_gib": graph_memory_gib,
            "source": ("启动日志" if graph_memory_gib is not None
                       else "未提供：读启动日志里图捕获那一行，用 --graph-memory-gib 传进来"),
            "note": (
                "图捕获显存不是“档位数 × 每档固定值”：常见实现从最大的批量往小捕获、"
                "所有图共用一个显存池，总量主要由最大捕获批量决定。"
                "这笔显存从第 16 章那张表的 --overhead 里出（18.4、18.8 案例二）"
            ),
        }

    return {
        "verdict": verdict,
        "reasons": reasons,
        "launch_share_of_floor": round(share, 4),
        "threshold_params": int(threshold),
        "memory_cost": memory,
    }


def kernel_level_checklist(form: str) -> dict:
    items = [
        "升级框架版本，看新版本的默认 kernel 是否更好",
        "Profiling 看实际执行的 kernel 名称，确认走的是哪条路，不是看装了哪个包",
        "排除静默回退：某些配置组合会让框架退回朴素实现，而它不会告诉你",
    ]
    return {
        "verdict": "确认项，不是改动项",
        "items": items,
        "note": (
            "这一层放最后，且主要是确认而非改动（18.5）。"
            + ("瓶颈在调度时，回退的可能性值得优先排掉"
               if form == "调度受限" else "")
        ),
    }


def build_try_order(form: str, spec: dict, graph: dict) -> list[dict]:
    """18.6's ordering: cheapest and least risky first, and always the 15.5
    comparison before any of them.
    """
    order = [{
        "step": "做 15.5 那个对照，确定瓶颈形态",
        "cost": "零",
        "risk": "零",
        "why": f"已完成，结论是{form}",
    }]
    graph_step = {
        "step": "确认 CUDA Graph 是否已启用，并查它占的显存",
        "cost": "低（多为配置确认）",
        "risk": "低",
        "why": graph["verdict"],
    }
    spec_step = {
        "step": ("先在真实请求样本上测接受率" if spec["verdict"] == "待测"
                 else "按实测接受率决定要不要开 Speculative Decoding"),
        "cost": "中（草稿模型常驻显存）",
        "risk": "中（接受率低时倒亏）",
        "why": spec["verdict"],
    }
    if form == "调度受限":
        order += [graph_step, spec_step]
    else:
        order += [spec_step, graph_step]
    order.append({
        "step": "kernel 层确认：查实际 kernel 名称，排除静默回退",
        "cost": "低",
        "risk": "低",
        "why": "确认项，不是改动项",
    })
    return order


def build_report(*, tpot_measured: float, tpot_floor: float,
                 batch_p50: int, batch_p95: int, model_params: float,
                 bandwidth_gb_per_s: float, bytes_per_element: float = 2.0,
                 acceptance: dict | None = None,
                 draft_params: float | None = None,
                 kv_bytes_per_token: float = 131072.0,
                 captured_buckets: int | None = None,
                 graph_memory_gib: float | None = None,
                 ridge: float = REFERENCE_RIDGE) -> dict:
    shape = bottleneck_form(tpot_measured, tpot_floor)

    draft = None
    if draft_params is not None:
        _require(draft_params > 0, "draft params must be positive")
        draft = draft_memory_cost(draft_params, bytes_per_element,
                                  kv_bytes_per_token)

    spec = judge_spec_decoding(form=shape["form"], batch_p50=batch_p50,
                               batch_p95=batch_p95, acceptance=acceptance,
                               draft=draft, ridge=ridge)
    graph = judge_cuda_graph(form=shape["form"], params=model_params,
                             bandwidth_gb_per_s=bandwidth_gb_per_s,
                             captured_buckets=captured_buckets,
                             graph_memory_gib=graph_memory_gib,
                             bytes_per_element=bytes_per_element)
    kernel = kernel_level_checklist(shape["form"])

    warnings: list[str] = [
        "这三项都不损失质量，但都要显存：草稿模型常驻、捕获缓冲区占用，"
        "两者都挤压第 16 章那张表里的 KV 预算（18.8 误区一）",
    ]
    if spec["verdict"] == "待测":
        warnings.append("接受率测出来之前不要部署 Speculative Decoding（18.6）")
    if spec.get("premise_warning"):
        warnings.append(spec["premise_warning"])

    return {
        "bottleneck_form": shape,
        "spec_decoding": spec,
        "cuda_graph": graph,
        "kernel_level": kernel,
        "try_order": build_try_order(shape["form"], spec, graph),
        "warnings": warnings,
    }


def print_summary(report: dict) -> None:
    shape = report["bottleneck_form"]
    print(f"瓶颈形态  {shape['form']}（实测是下限的 {shape['ratio']} 倍）")
    print(f"          {shape['reason']}")
    spec = report["spec_decoding"]
    gain = ("待测" if spec["gain_ratio"] is None
            else f"{spec['gain_ratio']} 倍（盈亏线 "
                 f"{spec['break_even_acceptance']}）")
    print(f"投机解码  {spec['verdict']}  收益比 {gain}")
    for reason in spec["reasons"]:
        print(f"          - {reason}")
    if spec["draft_memory"]:
        d = spec["draft_memory"]
        print(f"          草稿模型 {d['draft_gib']} GiB，"
              f"吃掉约 {d['tokens_displaced']} 个 token 的容量")
    graph = report["cuda_graph"]
    print(f"CUDA Graph {graph['verdict']}")
    for reason in graph["reasons"]:
        print(f"          - {reason}")
    if graph["memory_cost"]:
        m = graph["memory_cost"]
        total = (f"{m['graph_memory_gib']} GiB" if m["graph_memory_gib"] is not None
                 else "未知")
        print(f"          图捕获显存 {total}（来源：{m['source']}）")
    print(f"kernel 层  {report['kernel_level']['verdict']}")
    print("尝试顺序")
    for i, step in enumerate(report["try_order"], 1):
        print(f"  {i}. {step['step']}  代价 {step['cost']}"
              f"  风险 {step['risk']}  → {step['why']}")
    for warning in report["warnings"]:
        print(f"WARNING   {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=Path("code/ch15/model-7b-generic.json"))
    parser.add_argument("--tpot-measured", type=float, required=True)
    parser.add_argument("--tpot-floor", type=float, default=None,
                        help="不给就按配置里的参数量和带宽算")
    parser.add_argument("--batch-p50", type=int, required=True)
    parser.add_argument("--batch-p95", type=int, default=None)
    parser.add_argument("--model-params", type=float, default=None)
    parser.add_argument("--bandwidth", type=float, default=None)
    parser.add_argument("--draft-acceptance", type=Path, default=None,
                        help="实测的接受率报告；不给就不给收益预估")
    parser.add_argument("--draft-params", type=float, default=None,
                        help="草稿模型参数量，用来算它挤掉多少 KV 容量")
    parser.add_argument("--captured-buckets", type=int, default=None,
                        help="CUDA Graph 捕获的批量档位数（只记录，不拿它乘显存）")
    parser.add_argument("--graph-memory-gib", type=float, default=None,
                        help="启动日志里报告的图捕获显存")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        params = args.model_params or float(config["params_total"])
        bandwidth = args.bandwidth or float(config["bandwidth_gb_per_s"])
        bpe = float(config.get("bytes_per_element", 2))
        per_token = float(2 * config["layers"] * config["num_key_value_heads"]
                          * config["head_dim"] * bpe)
        floor = args.tpot_floor
        if floor is None:
            floor = params * bpe / (bandwidth * 1e9) * 1000.0

        acceptance = None
        if args.draft_acceptance is not None:
            acceptance = json.loads(
                args.draft_acceptance.read_text(encoding="utf-8"))
            for field in ("k", "draft_cost_ratio"):
                _require(field in acceptance,
                         f"接受率报告缺少 {field} 字段，无法代入 18.3 那个式子")
            _require("mean_accepted" in acceptance or "acceptance_rate" in acceptance,
                     "接受率报告要给平均接受长度 mean_accepted（a）或逐位置接受率 "
                     "acceptance_rate（α）之一，两者不能混用（18.3）")

        report = build_report(
            tpot_measured=args.tpot_measured,
            tpot_floor=floor,
            batch_p50=args.batch_p50,
            batch_p95=args.batch_p95 or args.batch_p50,
            model_params=params,
            bandwidth_gb_per_s=bandwidth,
            bytes_per_element=bpe,
            acceptance=acceptance,
            draft_params=args.draft_params,
            kv_bytes_per_token=per_token,
            captured_buckets=args.captured_buckets,
            graph_memory_gib=args.graph_memory_gib,
            ridge=(float(config["peak_tflops"]) * 1000 / bandwidth
                   if "peak_tflops" in config else REFERENCE_RIDGE),
        )
    except CheckError as exc:
        print(f"REJECTED: {exc}")
        return 1

    print_summary(report)
    if args.output is not None:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
