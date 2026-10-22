#!/usr/bin/env python3
"""Price a quantization decision before making it, then hold the quality side
of that decision to a line written down in advance.

Two subcommands, because quantization has two halves that must not be mixed:

  estimate   arithmetic only. Builds 17.2's table for every (weight, KV)
             precision combination, so the two benefits stay separated: weight
             quantization buys latency, KV quantization buys capacity.
  evaluate   compares a baseline service against a variant on a fixed evalset
             against a threshold recorded BEFORE the run.

Two things this Demo refuses to do, both on purpose:

  - `estimate` will not promise the full latency saving. 17.8's first case is a
    service where INT8 bought 8%, not 50%, because it was scheduler bound.
    Given `--measured-tpot-ms` the estimate is scaled by the real ratio; without
    it, the report says the number is an upper bound and why.
  - `evaluate` will not accept a threshold decided after seeing the results, and
    will not accept an evalset without long-answer and structured-output samples
    (17.4: a short-QA-only evalset cannot detect either failure mode).

`estimate` needs no GPU. `evaluate` needs two running services.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

GIB = 1024 ** 3
KIB = 1024

BYTES_FOR_DTYPE = {"fp16": 2.0, "bf16": 2.0, "fp8": 1.0, "int8": 1.0, "int4": 0.5}

# 17.4: the sample kinds an evalset must carry before it can clear a
# quantization change. Short QA alone passes while JSON output is breaking.
REQUIRED_SAMPLE_KINDS = ("long_answer", "structured_output")

# 17.3: the outlier magnitude used in the text, and the level count of INT8.
INT8_LEVELS = 256


class QuantError(ValueError):
    """Raised when an estimate or an evaluation cannot be trusted."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise QuantError(message)


def weight_gb(params: float, dtype: str) -> float:
    """Decimal GB, matching 15.3 so the division by bandwidth cancels."""
    _require(dtype in BYTES_FOR_DTYPE, f"unknown weight dtype {dtype!r}")
    return params * BYTES_FOR_DTYPE[dtype] / 1e9


def step_floor_ms(params: float, dtype: str, bandwidth_gb_per_s: float) -> float:
    _require(bandwidth_gb_per_s > 0, "bandwidth must be positive")
    return weight_gb(params, dtype) / bandwidth_gb_per_s * 1000.0


def kv_bytes_per_token(layers: int, kv_heads: int, head_dim: int,
                       dtype: str) -> float:
    _require(dtype in BYTES_FOR_DTYPE, f"unknown KV dtype {dtype!r}")
    _require(min(layers, kv_heads, head_dim) > 0, "model shape must be positive")
    return 2.0 * layers * kv_heads * head_dim * BYTES_FOR_DTYPE[dtype]


def arithmetic_intensity(dtype: str) -> float:
    """17.2: `2 FLOP ÷ bytes per parameter`. 1 at FP16, 2 at INT8, 4 at INT4."""
    _require(dtype in BYTES_FOR_DTYPE, f"unknown dtype {dtype!r}")
    return 2.0 / BYTES_FOR_DTYPE[dtype]


def effective_bit_width(outlier_ratio: float, levels: int = INT8_LEVELS) -> float:
    """17.3: with the scale set by the largest value, the main body of the
    distribution occupies `levels ÷ outlier_ratio` cells. The bit width that
    many cells represent is what the weights actually get.
    """
    _require(outlier_ratio >= 1, "outlier ratio must be at least 1")
    _require(levels > 1, "levels must be greater than 1")
    cells = levels / outlier_ratio
    return max(0.0, math.log2(cells)) if cells > 0 else 0.0


def weight_memory_gib_conservative(params: float, dtype: str) -> float:
    """16.2's deliberate over-deduction: round the decimal GB figure up to a
    whole GiB when subtracting it from a binary budget.
    """
    return float(math.ceil(weight_gb(params, dtype)))


def realised_saving(floor_saving: float, measured_ratio: float | None) -> dict:
    """17.8 case one, as a formula rather than a lesson.

    `floor_saving` is the fraction the FLOOR drops by (0.5 for FP16 to INT8).
    If the measured TPOT is `r` times the floor, the total time saved is
    `floor_saving ÷ r`: at r = 1.2 halving the weights saves 42%, at r = 6.25 it
    saves 8%. Without a measurement there is no honest number, only the bound.
    """
    if measured_ratio is None:
        return {
            "measured_ratio": None,
            "realised_saving": None,
            "upper_bound": round(floor_saving, 4),
            "reading": (
                "没给 --measured-tpot-ms：只能给上界。实测是下限的几倍，"
                "收益就除以那个倍数（17.8 案例一）"
            ),
        }
    _require(measured_ratio >= 1.0,
             "measured TPOT cannot be below the bandwidth floor; "
             "比下限还快说明这段时间的边界定义有问题（15.5）")
    realised = floor_saving / measured_ratio
    return {
        "measured_ratio": round(measured_ratio, 3),
        "realised_saving": round(realised, 4),
        "upper_bound": round(floor_saving, 4),
        "reading": (
            f"实测是下限的 {measured_ratio:.2f} 倍，下限减少 {floor_saving * 100:.0f}%，"
            f"按 17.5 那个除法大约省下总时间的 {realised * 100:.0f}%；越远离下限，量化越不值得做"
        ),
    }


def estimate(*, params: float, layers: int, kv_heads: int, head_dim: int,
             gpu_memory_gib: float, bandwidth_gb_per_s: float,
             overhead_gib: float, avg_context: int,
             weight_dtypes: list[str], kv_dtypes: list[str],
             utilization: float = 0.9,
             measured_tpot_ms: float | None = None) -> dict:
    _require(bool(weight_dtypes) and bool(kv_dtypes),
             "at least one weight dtype and one KV dtype are required")
    _require(avg_context > 0, "average context must be positive")
    _require("fp16" in weight_dtypes and "fp16" in kv_dtypes,
             "FP16 必须在两个精度列表里：所有的相对变化都以它为基线")

    baseline_floor = step_floor_ms(params, "fp16", bandwidth_gb_per_s)
    baseline_kv = kv_bytes_per_token(layers, kv_heads, head_dim, "fp16")
    _require(0 < utilization <= 1, "gpu_memory_utilization must be in (0, 1]")
    usable_gib = gpu_memory_gib * utilization
    baseline_budget = (usable_gib
                       - weight_memory_gib_conservative(params, "fp16")
                       - overhead_gib) * GIB
    _require(baseline_budget > 0, "FP16 基线下已经没有显存留给 KV Cache")
    baseline_conc = int(baseline_budget / baseline_kv // avg_context)

    measured_ratio = (measured_tpot_ms / baseline_floor
                      if measured_tpot_ms is not None else None)

    combos = []
    for wd in weight_dtypes:
        for kd in kv_dtypes:
            floor = step_floor_ms(params, wd, bandwidth_gb_per_s)
            per_token = kv_bytes_per_token(layers, kv_heads, head_dim, kd)
            budget = (usable_gib
                      - weight_memory_gib_conservative(params, wd)
                      - overhead_gib) * GIB
            if budget <= 0:
                continue
            conc = int(budget / per_token // avg_context)
            floor_saving = 1.0 - floor / baseline_floor
            combos.append({
                "combo": f"weight={wd}/kv={kd}",
                "weight_dtype": wd,
                "kv_dtype": kd,
                "weight_gb": round(weight_gb(params, wd), 3),
                "weight_gib_deducted": weight_memory_gib_conservative(params, wd),
                "step_floor_ms": round(floor, 3),
                "kv_bytes_per_token": int(per_token),
                "kv_kib_per_token": round(per_token / KIB, 1),
                "kv_budget_gib": round(budget / GIB, 2),
                "total_tokens": int(budget / per_token),
                "concurrency": conc,
                "arithmetic_intensity": arithmetic_intensity(wd),
                "delta_tpot_floor": round(-floor_saving, 4),
                "delta_concurrency": round(conc / baseline_conc - 1.0, 4),
                "realised_tpot_saving": realised_saving(floor_saving,
                                                        measured_ratio),
            })

    weight_only = next(c for c in combos
                       if c["weight_dtype"] == "int8" and c["kv_dtype"] == "fp16") \
        if any(c["weight_dtype"] == "int8" and c["kv_dtype"] == "fp16"
               for c in combos) else None
    kv_only = next((c for c in combos
                    if c["weight_dtype"] == "fp16" and c["kv_dtype"] == "int8"),
                   None)

    division: dict = {
        "note": "17.2 那条分工：权重量化主要改善延迟，KV 量化主要改善容量",
    }
    if weight_only and kv_only:
        division |= {
            "weight_int8_tpot_floor_change": weight_only["delta_tpot_floor"],
            "weight_int8_concurrency_change": weight_only["delta_concurrency"],
            "kv_int8_tpot_floor_change": kv_only["delta_tpot_floor"],
            "kv_int8_concurrency_change": kv_only["delta_concurrency"],
            "reading": (
                f"权重 INT8：单步下限 {weight_only['delta_tpot_floor'] * 100:+.0f}%，"
                f"并发 {weight_only['delta_concurrency'] * 100:+.0f}%；"
                f"KV INT8：单步下限 {kv_only['delta_tpot_floor'] * 100:+.0f}%，"
                f"并发 {kv_only['delta_concurrency'] * 100:+.0f}%。"
                "瓶颈是 TPOT 就量权重，瓶颈是并发就量 KV"
            ),
        }

    warnings = [
        "这张表只算搬运，不算质量。任何一行都要配 evaluate 的结果才算一个决策"
        "（17.4：底线必须在量化之前定）",
        "算术强度即使到 INT4 也只有 4，而卡的分界点在上百，所以单条请求的 Decode "
        "仍然是带宽受限：延迟收益接近线性，先撑不住的是质量，不是硬件",
    ]
    if measured_ratio is None:
        warnings.append(
            "没有实测 TPOT，delta_tpot_floor 是下限的变化，不是你会拿到的变化"
        )
    elif measured_ratio > 2.0:
        warnings.append(
            f"实测是下限的 {measured_ratio:.1f} 倍，时间主要不花在读权重上。"
            "先做 15.6 那个拆分，量化在这种服务上换不回多少（17.8 案例一）"
        )

    return {
        "units": {
            "weights_and_bandwidth": "decimal (GB)：与 15.3 同口径",
            "memory_budget": "binary (GiB)：与 16.6 那张表同口径，扣权重时向上取整",
        },
        "model": {"params": params, "layers": layers, "kv_heads": kv_heads,
                  "head_dim": head_dim},
        "hardware": {"gpu_memory_gib": gpu_memory_gib,
                     "gpu_memory_utilization": utilization,
                     "usable_gib": round(usable_gib, 3),
                     "bandwidth_gb_per_s": bandwidth_gb_per_s,
                     "overhead_gib": overhead_gib},
        "avg_context": avg_context,
        "baseline": {"combo": "weight=fp16/kv=fp16",
                     "step_floor_ms": round(baseline_floor, 3),
                     "concurrency": baseline_conc},
        "measured_tpot_ms": measured_tpot_ms,
        "combos": combos,
        "division_of_labour": division,
        "warnings": warnings,
    }


def check_evalset(samples: list[dict]) -> dict:
    """17.4: an evalset that cannot detect the two known failure modes is not a
    guardrail, whatever score it produces.
    """
    _require(bool(samples), "evalset is empty")
    kinds = {s.get("kind") for s in samples}
    missing = [k for k in REQUIRED_SAMPLE_KINDS if k not in kinds]
    _require(
        not missing,
        f"评测集缺少 {', '.join(missing)} 类样本：只有短问答的评测集测不出 17.4 "
        "说的那两类退化（长回答后段崩坏、格式化输出出错）",
    )
    return {"total": len(samples), "kinds": sorted(k for k in kinds if k)}


def evaluate(*, samples: list[dict], baseline_scores: list[float],
             variant_scores: list[float], threshold: float,
             threshold_written_at: str | None,
             per_kind: dict[str, dict] | None = None) -> dict:
    """Compare two services on a fixed evalset against a pre-recorded line."""
    check_evalset(samples)
    _require(
        threshold_written_at is not None,
        "缺少阈值的写入时间：事后看着结果定标准，和第 14 章说的事后补写预期"
        "是同一个毛病，这样的评估无法证伪（17.4）",
    )
    _require(0 < threshold < 1, "threshold must be a fraction between 0 and 1")
    _require(len(baseline_scores) == len(variant_scores) == len(samples),
             "baseline、variant 与评测集的样本数必须一致，否则两个分数不可比")
    _require(bool(baseline_scores), "no scores to compare")

    base = statistics.fmean(baseline_scores)
    var = statistics.fmean(variant_scores)
    drop = base - var
    passed = drop <= threshold

    kinds: list[dict] = []
    worst_kind = None
    if per_kind:
        for kind, pair in sorted(per_kind.items()):
            k_drop = pair["baseline"] - pair["variant"]
            kinds.append({
                "kind": kind,
                "baseline": round(pair["baseline"], 4),
                "variant": round(pair["variant"], 4),
                "drop": round(k_drop, 4),
                "passed": k_drop <= threshold,
            })
        worst = max(kinds, key=lambda k: k["drop"])
        worst_kind = worst["kind"]

    reading = (
        f"总分下降 {drop:.4f}，底线 {threshold:.4f}，"
        + ("通过" if passed else "不通过")
    )
    if kinds and not all(k["passed"] for k in kinds):
        failing = [k["kind"] for k in kinds if not k["passed"]]
        reading += (
            f"。但逐维度看，{', '.join(failing)} 已越界："
            "总分通过而某一维度越界是最危险的情形，17.8 案例二就是这样上线的"
        )
        passed = False

    return {
        "evalset": check_evalset(samples),
        "threshold": threshold,
        "threshold_written_at": threshold_written_at,
        "baseline_score": round(base, 4),
        "variant_score": round(var, 4),
        "drop": round(drop, 4),
        "per_kind": kinds,
        "worst_kind": worst_kind,
        "passed": passed,
        "reading": reading,
    }


def print_estimate(report: dict) -> None:
    b = report["baseline"]
    print(f"基线      {b['combo']}  单步下限 {b['step_floor_ms']} ms"
          f"  并发 {b['concurrency']} 条")
    print("组合                     权重GB  下限ms  KV/token  并发   ΔTPOT下限  Δ并发  实际省")
    for c in report["combos"]:
        realised = c["realised_tpot_saving"]["realised_saving"]
        realised_text = "  待测" if realised is None else f"{realised * 100:>5.0f}%"
        print(f"{c['combo']:<24} {c['weight_gb']:>6.2f} "
              f"{c['step_floor_ms']:>7.2f} "
              f"{c['kv_kib_per_token']:>7.1f}K "
              f"{c['concurrency']:>6} "
              f"{c['delta_tpot_floor'] * 100:>9.0f}% "
              f"{c['delta_concurrency'] * 100:>6.0f}% "
              f"{realised_text}")
    if "reading" in report["division_of_labour"]:
        print(f"分工      {report['division_of_labour']['reading']}")
    deepest = max(report["combos"], key=lambda c: -c["delta_tpot_floor"])
    print(f"实际收益  {deepest['combo']}："
          f"{deepest['realised_tpot_saving']['reading']}")
    for warning in report["warnings"]:
        print(f"WARNING   {warning}")


def print_evaluation(report: dict) -> None:
    print(f"评测集    {report['evalset']['total']} 条，"
          f"类型 {', '.join(report['evalset']['kinds'])}")
    print(f"底线      {report['threshold']}"
          f"（写于 {report['threshold_written_at']}）")
    print(f"基线      {report['baseline_score']}")
    print(f"变体      {report['variant_score']}  下降 {report['drop']}")
    for k in report["per_kind"]:
        mark = "通过" if k["passed"] else "不通过"
        print(f"  {k['kind']:<20} {k['baseline']} → {k['variant']}"
              f"  下降 {k['drop']}  {mark}")
    print(f"结论      {'通过' if report['passed'] else '不通过'}")
    print(f"解读      {report['reading']}")


def _str_list(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    est = sub.add_parser("estimate", help="算收益，不碰质量")
    est.add_argument("--config", type=Path,
                     default=Path("code/ch15/model-7b-generic.json"))
    est.add_argument("--params", type=float, default=None)
    est.add_argument("--layers", type=int, default=None)
    est.add_argument("--kv-heads", type=int, default=None)
    est.add_argument("--head-dim", type=int, default=None)
    est.add_argument("--gpu-memory", type=float, default=None)
    est.add_argument("--bandwidth", type=float, default=None)
    est.add_argument("--overhead", type=float, default=None)
    est.add_argument("--utilization", type=float, default=None,
                     help="gpu_memory_utilization，默认按 vLLM 的 0.9 取（16.6 第 1 步）")
    est.add_argument("--avg-context", type=int, default=2300)
    est.add_argument("--weight-dtype", type=_str_list,
                     default=["fp16", "int8", "int4"])
    est.add_argument("--kv-dtype", type=_str_list, default=["fp16", "int8"])
    est.add_argument("--measured-tpot-ms", type=float, default=None,
                     help="真实 Baseline 的 TPOT；不给就只报上界")
    est.add_argument("--output", type=Path, default=None)

    ev = sub.add_parser("evaluate", help="跑质量对照，需要两个服务")
    ev.add_argument("--evalset", type=Path, required=True,
                    help="JSONL，每行一个样本，必须带 kind 字段")
    ev.add_argument("--results", type=Path, required=True,
                    help="两个服务的打分结果 JSON")
    ev.add_argument("--threshold", type=float, required=True)
    ev.add_argument("--threshold-written-at", type=str, default=None,
                    help="阈值的写入时间，必填，事后补写的不被接受")
    ev.add_argument("--output", type=Path, default=None)

    args = parser.parse_args(argv)

    try:
        if args.command == "estimate":
            config = json.loads(args.config.read_text(encoding="utf-8"))

            def pick(flag, key, default=None):
                return flag if flag is not None else config.get(key, default)

            report = estimate(
                params=float(pick(args.params, "params_total")),
                layers=int(pick(args.layers, "layers")),
                kv_heads=int(pick(args.kv_heads, "num_key_value_heads")),
                head_dim=int(pick(args.head_dim, "head_dim")),
                gpu_memory_gib=float(pick(args.gpu_memory, "gpu_memory_gib")),
                utilization=float(pick(args.utilization, "gpu_memory_utilization", 0.9)),
                bandwidth_gb_per_s=float(pick(args.bandwidth,
                                              "bandwidth_gb_per_s")),
                overhead_gib=float(pick(args.overhead,
                                        "framework_overhead_gib")),
                avg_context=args.avg_context,
                weight_dtypes=args.weight_dtype,
                kv_dtypes=args.kv_dtype,
                measured_tpot_ms=args.measured_tpot_ms,
            )
            print_estimate(report)
        else:
            samples = [json.loads(line) for line
                       in args.evalset.read_text(encoding="utf-8").splitlines()
                       if line.strip()]
            results = json.loads(args.results.read_text(encoding="utf-8"))
            report = evaluate(
                samples=samples,
                baseline_scores=results["baseline_scores"],
                variant_scores=results["variant_scores"],
                threshold=args.threshold,
                threshold_written_at=(args.threshold_written_at
                                      or results.get("threshold_written_at")),
                per_kind=results.get("per_kind"),
            )
            print_evaluation(report)
    except QuantError as exc:
        print(f"REJECTED: {exc}")
        return 1

    if args.output is not None:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
