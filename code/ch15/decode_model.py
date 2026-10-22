#!/usr/bin/env python3
"""Estimate what one Decode step should cost, so a measured TPOT has something
to be compared against.

The whole chapter rests on one division: weight bytes over memory bandwidth.
This Demo does that division, then adds the part the floor leaves out (the KV
Cache read, which grows with batch and context) and reports where the two
cross. It answers three questions the text asks:

  15.4  how far does adding batch stay free
  15.5  is the measured TPOT near the floor, or nowhere near it
  15.7  at what point does the KV read overtake the weight read

Two unit conventions meet here, deliberately. Weight bytes and bandwidth are
DECIMAL (10^9): both are vendor-side numbers and the units cancel. Memory
occupancy is BINARY (2^30): that is what allocators and framework logs report,
and Chapter 16 has to add up against them. The report labels every field.

It never measures anything. `--measured-tpot-ms` is a number you bring from a
real Baseline; without it the report carries the theoretical side only.

Only the Python standard library. No GPU.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_CONFIG_FIELDS = (
    "params_total",
    "layers",
    "num_key_value_heads",
    "head_dim",
    "bytes_per_element",
)

# 15.5: how to read the ratio between a measured TPOT and the bandwidth floor.
# Below 1.0 the measurement is impossible and something is wrong with the
# definition, not with the system.
BAND_BANDWIDTH_BOUND = 1.3
BAND_SCHEDULER_BOUND = 2.0

GIB = 1024 ** 3
MIB = 1024 ** 2
KIB = 1024

# 15.2: A100 80GB SXM, dense FP16 — 312 TFLOPS against 2039 GB/s, giving the
# 153 FLOP/byte balance point the text uses. They are a PAIR: a balance point
# computed from one card's FLOPS and another card's bandwidth is meaningless,
# so this Demo asks for both together or neither.
A100_PEAK_TFLOPS = 312.0
A100_BANDWIDTH_GB_PER_S = 2039.0


class ModelError(ValueError):
    """Raised when a configuration cannot support an estimate."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelError(message)


def load_config(doc: object) -> dict:
    _require(isinstance(doc, dict), "model config must be an object")
    assert isinstance(doc, dict)
    for field in REQUIRED_CONFIG_FIELDS:
        value = doc.get(field)
        _require(
            isinstance(value, (int, float)) and value > 0,
            f"config.{field} must be a positive number",
        )
    if "num_attention_heads" in doc:
        _require(
            doc["num_attention_heads"] % doc["num_key_value_heads"] == 0,
            "num_attention_heads must be a multiple of num_key_value_heads (GQA)",
        )
    return doc


def weight_bytes(params_total: float, bytes_per_element: float) -> float:
    """Decimal bytes. 7e9 params at 2 bytes is 14 GB, not 13.04 GiB (15.3)."""
    return float(params_total) * float(bytes_per_element)


def step_floor_ms(weight_b: float, bandwidth_gb_per_s: float) -> float:
    """15.3: the whole chapter in one division. Decimal on both sides."""
    _require(bandwidth_gb_per_s > 0, "bandwidth must be positive")
    return weight_b / (bandwidth_gb_per_s * 1e9) * 1000.0


def kv_bytes_per_token(config: dict) -> int:
    """2 for K and V. Binary display, but the count itself is exact (16.2)."""
    return int(
        2
        * config["layers"]
        * config["num_key_value_heads"]
        * config["head_dim"]
        * config["bytes_per_element"]
    )


def decode_arithmetic_intensity(batch: int, bytes_per_element: float) -> float:
    """15.2: 2 FLOP per parameter per token, `bytes_per_element` bytes per
    parameter. The parameter count cancels, so this is independent of model
    size: 1 at FP16 and batch 1, 2 at INT8, and batch multiplies it (15.4).
    """
    _require(batch >= 1, "batch must be at least 1")
    return 2.0 * batch / float(bytes_per_element)


def hardware_balance_point(peak_tflops: float, bandwidth_gb_per_s: float) -> float:
    """15.2: peak FLOPS over peak bandwidth. Both are spec numbers, so this is
    an order of magnitude, not a threshold to tune against.
    """
    _require(peak_tflops > 0 and bandwidth_gb_per_s > 0,
             "peak_tflops and bandwidth must be positive")
    return (peak_tflops * 1e12) / (bandwidth_gb_per_s * 1e9)


def crossover_batch(peak_tflops: float, bandwidth_gb_per_s: float,
                    bytes_per_element: float) -> float:
    """15.4 reason two: intensity is `2 × batch ÷ bytes_per_element`, so the
    batch at which Decode stops being bandwidth bound is the card's balance
    point scaled by the weight width. On a 153 FLOP/byte card at FP16 that is
    a batch in the low hundreds, which is why batching is nearly free below it.
    """
    balance = hardware_balance_point(peak_tflops, bandwidth_gb_per_s)
    return balance * float(bytes_per_element) / 2.0


def read_ratio(ratio: float) -> str:
    """15.5: the three bands. The first is the one worth remembering."""
    if ratio < 1.0:
        return "低于带宽下限：下限已假设带宽满载，比它快说明这段时间的边界定义有问题"
    if ratio <= BAND_BANDWIDTH_BOUND:
        return "带宽受限：时间确实花在读权重上，提升只有量化或换卡两条路"
    if ratio <= BAND_SCHEDULER_BOUND:
        return "混合：搬运是主项，但已有可观的额外开销，两头都要查"
    return "调度受限：大部分时间不在读权重，先查 kernel 启动与引擎侧准备（15.6）"


def build_point(config: dict, batch: int, context: int, *,
                bandwidth_gb_per_s: float) -> dict:
    """One (batch, context) cell of the sweep."""
    _require(batch >= 1, "batch must be at least 1")
    _require(context >= 1, "context must be at least 1")
    window = config.get("context_window")
    warnings: list[str] = []
    if isinstance(window, int) and context > window:
        warnings.append(
            f"context {context} 超过配置里的 context_window {window}，这一行只是算术"
        )

    weight_b = weight_bytes(config["params_total"], config["bytes_per_element"])
    per_token = kv_bytes_per_token(config)
    kv_b = float(batch) * context * per_token
    floor_ms = step_floor_ms(weight_b, bandwidth_gb_per_s)
    estimate_ms = (weight_b + kv_b) / (bandwidth_gb_per_s * 1e9) * 1000.0

    return {
        "batch": batch,
        "context": context,
        "kv_bytes_per_step": int(kv_b),
        "kv_gib_per_step": round(kv_b / GIB, 3),
        "kv_over_weight": round(kv_b / weight_b, 3),
        "step_floor_ms": round(floor_ms, 3),
        "step_estimate_ms": round(estimate_ms, 3),
        "tpot_ms": round(estimate_ms, 3),
        "amortized_ms_per_token": round(estimate_ms / batch, 4),
        "throughput_tps": round(batch / estimate_ms * 1000.0, 1),
        "arithmetic_intensity": round(
            decode_arithmetic_intensity(batch, config["bytes_per_element"]), 2
        ),
        "kv_dominates": kv_b > weight_b,
        "warnings": warnings,
    }


def build_report(config: dict, batches: list[int], contexts: list[int], *,
                 bandwidth_gb_per_s: float | None = None,
                 peak_tflops: float | None = None,
                 balance_bandwidth_gb_per_s: float | None = None,
                 measured_tpot_ms: float | None = None) -> dict:
    if bandwidth_gb_per_s is None:
        bandwidth_gb_per_s = float(config.get("bandwidth_gb_per_s") or 0)
    _require(bandwidth_gb_per_s > 0,
             "bandwidth must come from --bandwidth or config.bandwidth_gb_per_s")
    _require(bool(batches), "at least one batch size is required")
    _require(bool(contexts), "at least one context length is required")

    weight_b = weight_bytes(config["params_total"], config["bytes_per_element"])
    per_token = kv_bytes_per_token(config)
    floor_ms = step_floor_ms(weight_b, bandwidth_gb_per_s)
    # The balance point needs a matching (FLOPS, bandwidth) pair from one card.
    # `--bandwidth` may legitimately be a rounded teaching number (15.3 uses
    # 1000 GB/s), so it is not reused here unless the caller says to.
    balance: float | None = None
    cross: float | None = None
    if peak_tflops is not None:
        pair_bandwidth = balance_bandwidth_gb_per_s or bandwidth_gb_per_s
        balance = hardware_balance_point(peak_tflops, pair_bandwidth)
        cross = crossover_batch(peak_tflops, pair_bandwidth,
                                config["bytes_per_element"])

    points = [
        build_point(config, b, c, bandwidth_gb_per_s=bandwidth_gb_per_s)
        for b in sorted(set(batches))
        for c in sorted(set(contexts))
    ]

    comparison: dict = {
        "step_floor_ms": round(floor_ms, 3),
        "tpot_floor_ms": round(floor_ms, 3),
        "tokens_per_second_at_floor": round(1000.0 / floor_ms, 1),
        "measured_tpot_ms": measured_tpot_ms,
        "ratio": None,
        "reading": "没有实测值：本次只有理论一侧，不给解读（15.5 要的是比值，不是单个数）",
    }
    if measured_tpot_ms is not None:
        _require(measured_tpot_ms > 0, "measured TPOT must be positive")
        ratio = measured_tpot_ms / floor_ms
        comparison["ratio"] = round(ratio, 3)
        comparison["reading"] = read_ratio(ratio)

    warnings = [w for p in points for w in p["warnings"]]
    if cross is not None and cross < max(batches):
        warnings.append(
            f"扫描里最大的批量 {max(batches)} 已越过估算的交叉批量 {cross:.0f}，"
            "越过之后加批量会真的变慢，15.4 那条“免费”不再成立"
        )

    return {
        "config": {
            "name": config.get("name", "unnamed"),
            "revision": config.get("revision"),
            "params_total": config["params_total"],
            "layers": config["layers"],
            "num_key_value_heads": config["num_key_value_heads"],
            "head_dim": config["head_dim"],
            "bytes_per_element": config["bytes_per_element"],
        },
        "units": {
            "weights_and_bandwidth": "decimal (GB = 10^9 B)：两边都是厂商口径，相除约掉",
            "memory_occupancy": "binary (GiB = 2^30 B)：与分配器和框架日志同口径（11.3、16.2）",
        },
        "weights": {
            "weight_bytes": int(weight_b),
            "weight_gb_decimal": round(weight_b / 1e9, 3),
            "weight_gib_binary": round(weight_b / GIB, 3),
        },
        "kv": {
            "bytes_per_token": per_token,
            "kib_per_token": round(per_token / KIB, 2),
        },
        "hardware": {
            "bandwidth_gb_per_s": bandwidth_gb_per_s,
            "peak_tflops": peak_tflops,
            "balance_bandwidth_gb_per_s": (
                balance_bandwidth_gb_per_s or bandwidth_gb_per_s
            ) if peak_tflops is not None else None,
            "balance_point_flops_per_byte": (
                round(balance, 1) if balance is not None else None
            ),
            "crossover_batch": round(cross, 1) if cross is not None else None,
        },
        "points": points,
        "comparison": comparison,
        "warnings": warnings,
    }


def print_summary(report: dict) -> None:
    w = report["weights"]
    k = report["kv"]
    h = report["hardware"]
    cmp_ = report["comparison"]
    params = report["config"]["params_total"]
    print(f"模型      {report['config']['name']}"
          f"  {params / 1e9:g}B 参数"
          f"  {report['config']['bytes_per_element']} 字节/参数")
    print(f"权重      {w['weight_gb_decimal']} GB（十进制）"
          f" = {w['weight_gib_binary']} GiB（二进制）")
    print(f"单步下限  {cmp_['step_floor_ms']} ms"
          f"  对应每秒 {cmp_['tokens_per_second_at_floor']} 个 token")
    print(f"每 token KV  {k['kib_per_token']} KiB")
    if h["balance_point_flops_per_byte"] is None:
        print("分界点    没给 --peak-tflops：不算分界点，也不给交叉批量")
    else:
        print(f"分界点    {h['balance_point_flops_per_byte']} FLOP/byte"
              f"  @ {h['peak_tflops']} TFLOPS / {h['balance_bandwidth_gb_per_s']} GB/s"
              f"  估算交叉批量 {h['crossover_batch']}")
    print("批量  上下文   每步 KV      KV/权重  单步估算   摊薄后     吞吐")
    for p in report["points"]:
        flag = "  ← KV 已超过权重" if p["kv_dominates"] else ""
        print(f"{p['batch']:>4}  {p['context']:>7}  "
              f"{p['kv_gib_per_step']:>7.3f} GiB  "
              f"{p['kv_over_weight']:>6.2f}  "
              f"{p['step_estimate_ms']:>7.2f} ms  "
              f"{p['amortized_ms_per_token']:>7.3f} ms  "
              f"{p['throughput_tps']:>7.1f} tps{flag}")
    if cmp_["measured_tpot_ms"] is not None:
        print(f"实测      {cmp_['measured_tpot_ms']} ms  比值 {cmp_['ratio']}")
    print(f"解读      {cmp_['reading']}")
    for warning in report["warnings"]:
        print(f"WARNING   {warning}")


def _int_list(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=Path("code/ch15/model-7b-generic.json"),
                        help="模型配置，默认 Part 4 共享的 model-7b-generic.json")
    parser.add_argument("--params", type=float, default=None,
                        help="覆盖配置里的参数量，例如 7e9")
    parser.add_argument("--dtype", choices=("fp16", "bf16", "int8", "int4"),
                        default=None, help="覆盖权重位宽")
    parser.add_argument("--bandwidth", type=float, default=None,
                        help="显存带宽 GB/s（十进制，厂商规格口径）")
    parser.add_argument("--peak-tflops", type=float, default=None,
                        help="规格峰值算力，只用来算分界点的量级；不给就不算")
    parser.add_argument("--balance-bandwidth", type=float, default=None,
                        help="与 --peak-tflops 配对的同一张卡的带宽规格；"
                             "省略时用 --bandwidth，但两者必须来自同一张卡")
    parser.add_argument("--a100", action="store_true",
                        help="按 15.2 那对 A100 规格（312 TFLOPS / 2039 GB/s）算分界点")
    parser.add_argument("--batch", type=_int_list, default=[1, 8, 32, 64])
    parser.add_argument("--context", type=_int_list, default=[512, 4096, 16384])
    parser.add_argument("--measured-tpot-ms", type=float, default=None,
                        help="真实 Baseline 的 TPOT；不给就只出理论值")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    bytes_for = {"fp16": 2, "bf16": 2, "int8": 1, "int4": 0.5}
    try:
        config = load_config(json.loads(args.config.read_text(encoding="utf-8")))
        if args.params is not None:
            config = {**config, "params_total": args.params}
        if args.dtype is not None:
            config = {**config, "dtype": args.dtype,
                      "bytes_per_element": bytes_for[args.dtype]}
        report = build_report(
            config, args.batch, args.context,
            bandwidth_gb_per_s=args.bandwidth,
            peak_tflops=A100_PEAK_TFLOPS if args.a100 else args.peak_tflops,
            balance_bandwidth_gb_per_s=(
                A100_BANDWIDTH_GB_PER_S if args.a100 else args.balance_bandwidth
            ),
            measured_tpot_ms=args.measured_tpot_ms,
        )
    except ModelError as exc:
        print(f"REJECTED: {exc}")
        return 1

    print_summary(report)
    if args.output is not None:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
