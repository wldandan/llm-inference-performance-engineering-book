#!/usr/bin/env python3
"""Turn a GPU's memory into a concurrency number, and say why the real ceiling
is lower than the arithmetic.

This is 16.6's table in code. The nine steps are all one-line divisions; the
value is in the three things the table cannot say by itself and this Demo does:

  - it reports the average-length and the P99-length concurrency TOGETHER,
    because the safe number lies between them (16.6);
  - it computes the block-level waste that `--block-size` costs you, so the
    block size stops looking free (16.4);
  - it can compute the mixed-distribution ceiling, which is the number 16.9's
    third case shows is NOT the average (the worst-case mix decides).

Memory is BINARY throughout (GiB = 2^30), matching allocators and framework
logs, which is the convention 11.3 set. Transfer bandwidth is the one decimal
number here, because PCIe specs are decimal; `swap_ms` labels the conversion.

It measures nothing. Every number is arithmetic on the arguments, and
`--overhead` in particular is an empirical value you must measure yourself.

Only the Python standard library. No GPU.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

GIB = 1024 ** 3
MIB = 1024 ** 2
KIB = 1024

# 16.6 step 9: the discount that covers length-distribution tails, arrival
# bursts and preemption recovery. A range, not a number, on purpose.
DISCOUNT_LOW = 0.70
DISCOUNT_HIGH = 0.80

BYTES_FOR_DTYPE = {"fp16": 2, "bf16": 2, "fp8": 1, "int8": 1, "int4": 0.5}


class CapacityError(ValueError):
    """Raised when a capacity estimate cannot be produced."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapacityError(message)


def bytes_per_token(layers: int, kv_heads: int, head_dim: int,
                    bytes_per_element: float) -> float:
    """16.2: `2 × 层数 × KV头数 × head_dim × 字节数`. The 2 is K and V."""
    _require(layers > 0, "layers must be positive")
    _require(kv_heads > 0, "kv_heads must be positive")
    _require(head_dim > 0, "head_dim must be positive")
    _require(bytes_per_element > 0, "bytes_per_element must be positive")
    return 2.0 * layers * kv_heads * head_dim * bytes_per_element


def kv_budget_bytes(gpu_memory_gib: float, weight_memory_gib: float,
                    overhead_gib: float, utilization: float = 0.9) -> float:
    """16.6 steps 1-4. The engine only gets `utilization` of the card, so the
    subtraction starts from that budget, not from the card's full capacity.
    Rejects a budget that has already gone negative rather than reporting a
    concurrency of zero and letting you wonder why.
    """
    _require(gpu_memory_gib > 0, "gpu memory must be positive")
    _require(0 < utilization <= 1, "gpu_memory_utilization must be in (0, 1]")
    _require(weight_memory_gib >= 0, "weight memory cannot be negative")
    _require(overhead_gib >= 0, "overhead cannot be negative")
    usable = gpu_memory_gib * utilization
    budget = (usable - weight_memory_gib - overhead_gib) * GIB
    _require(
        budget > 0,
        f"权重 {weight_memory_gib} GiB 加开销 {overhead_gib} GiB 已经吃掉了"
        f"引擎能用的 {usable:.1f} GiB（{gpu_memory_gib} GiB 的 {utilization}），"
        f"没有显存留给 KV Cache",
    )
    return budget


def concurrency(total_tokens: float, context: int) -> int:
    """16.6 steps 7-8. Floor, not round: a request that does not fit does not
    half-fit.
    """
    _require(context > 0, "context length must be positive")
    return int(total_tokens // context)


def mixed_average_context(mix: list[tuple[float, int]]) -> float:
    """16.9 case three: the average of a mixed length distribution.

    `mix` is a list of (share, context) pairs whose shares sum to 1. The number
    it returns is what step 7 of the table wants, and the case exists to show
    that this number is NOT the ceiling: see `worst_case_concurrency`.
    """
    _require(bool(mix), "mix must not be empty")
    total_share = sum(share for share, _ in mix)
    _require(abs(total_share - 1.0) < 1e-6,
             f"mix shares must sum to 1, got {total_share}")
    for share, ctx in mix:
        _require(share > 0, "each share must be positive")
        _require(ctx > 0, "each context length must be positive")
    return sum(share * ctx for share, ctx in mix)


def worst_case_concurrency(total_tokens: float,
                           mix: list[tuple[float, int]]) -> int:
    """16.9 case three's real lesson: the ceiling is set by the longest bucket,
    because a burst of those alone can fill the card.
    """
    longest = max(ctx for _, ctx in mix)
    return concurrency(total_tokens, longest)


def block_accounting(total_tokens: float, block_size: int,
                     per_token: float, concurrency_count: int) -> dict:
    """16.4: paging removes the reservation waste but introduces block waste.

    The average waste is half a block per request, so the total scales with
    concurrency. That is why a large block size is not free: it converts
    directly into lost concurrency.
    """
    _require(block_size > 0, "block size must be positive")
    waste_tokens_per_request = block_size / 2.0
    waste_bytes_per_request = waste_tokens_per_request * per_token
    total_waste = waste_bytes_per_request * concurrency_count
    return {
        "block_size": block_size,
        "blocks_total": int(total_tokens // block_size),
        "bytes_per_block": int(block_size * per_token),
        "waste_tokens_per_request": waste_tokens_per_request,
        "waste_mib_per_request": round(waste_bytes_per_request / MIB, 3),
        "waste_tokens_total": round(waste_tokens_per_request * concurrency_count, 1),
        "waste_gib_total": round(total_waste / GIB, 3),
        "waste_share_of_budget": round(total_waste / (total_tokens * per_token), 4),
    }


def preemption_cost(context: int, per_token: float, *,
                    pcie_gb_per_s: float = 16.0,
                    recompute_ms: float | None = None,
                    concurrency_for_host_memory: int | None = None) -> dict:
    """16.5: recompute versus swap, for one request of this length.

    Writing this function is what showed the chapter's first draft was wrong.
    Swap is not "cheaper for long sequences and dearer for short ones": per
    token, recompute costs `2 × params ÷ effective FLOPS` and a swap round trip
    costs `2 × bytes_per_token ÷ PCIe`, both linear in length, with swap about
    nine times cheaper at 7B. Prefill's quadratic term only widens that gap.

    So this function does NOT say which one is "划算". It reports which is
    faster on wall clock, and names the two costs wall clock does not capture:
    swap spends bandwidth everyone shares, and it needs host memory that
    scales with concurrency. Those are what make recompute a sane default.

    The KV size is binary (MiB); PCIe bandwidth is decimal (GB/s). The
    conversion happens here, once, and is labelled, because doing it silently
    is how "62 ms" and "65 ms" end up in the same book.
    """
    _require(pcie_gb_per_s > 0, "PCIe bandwidth must be positive")
    _require(context > 0, "context length must be positive")
    kv_bytes = float(context) * per_token
    one_way_ms = kv_bytes / (pcie_gb_per_s * 1e9) * 1000.0
    round_trip_ms = one_way_ms * 2

    faster = "没给 --recompute-ms：不比时间，这一项要用实测的 Prefill 耗时"
    speedup = None
    if recompute_ms is not None:
        _require(recompute_ms > 0, "recompute time must be positive")
        if recompute_ms > round_trip_ms:
            speedup = round(recompute_ms / round_trip_ms, 1)
            faster = f"换出在墙钟上快 {speedup} 倍"
        else:
            speedup = round(round_trip_ms / recompute_ms, 1)
            faster = f"重算在墙钟上快 {speedup} 倍"

    host_mem: dict | None = None
    if concurrency_for_host_memory:
        host_mem = {
            "concurrency": concurrency_for_host_memory,
            "host_gib_needed": round(
                kv_bytes * concurrency_for_host_memory / GIB, 2
            ),
        }

    return {
        "context": context,
        "kv_mib": round(kv_bytes / MIB, 2),
        "kv_gb_decimal": round(kv_bytes / 1e9, 4),
        "pcie_gb_per_s": pcie_gb_per_s,
        "swap_one_way_ms": round(one_way_ms, 1),
        "swap_round_trip_ms": round(round_trip_ms, 1),
        "recompute_ms": recompute_ms,
        "faster_on_wall_clock": faster,
        "wall_clock_speedup": speedup,
        "host_memory": host_mem,
        "why_wall_clock_is_not_the_judge": (
            "重算的代价是一段占满整卡算力的 Prefill，重跑的那一秒多里，同一张卡上"
            "正在 Decode 的请求都跟着停，所以它把一条请求的麻烦摊给了所有人；"
            "换出走 PCIe，带宽相对显存带宽很小，对其他请求影响有限，它的代价是"
            "主机内存（随并发线性增长）和引擎复杂度。"
            "所以判据不是哪个更快，是愿不愿意让一次抢占打断所有人"
        ),
    }


def build_report(*, layers: int, kv_heads: int, head_dim: int,
                 dtype: str, gpu_memory_gib: float, weight_memory_gib: float,
                 overhead_gib: float, avg_context: int,
                 utilization: float = 0.9,
                 p99_context: int | None = None, block_size: int = 16,
                 mix: list[tuple[float, int]] | None = None,
                 pcie_gb_per_s: float = 16.0,
                 preempt_context: int | None = None,
                 recompute_ms: float | None = None,
                 measured_concurrency: int | None = None) -> dict:
    _require(dtype in BYTES_FOR_DTYPE, f"unknown dtype {dtype!r}")
    per_token = bytes_per_token(layers, kv_heads, head_dim,
                                BYTES_FOR_DTYPE[dtype])
    budget = kv_budget_bytes(gpu_memory_gib, weight_memory_gib, overhead_gib,
                             utilization)
    total_tokens = budget / per_token

    conc_avg = concurrency(total_tokens, avg_context)
    conc_p99 = concurrency(total_tokens, p99_context) if p99_context else None
    if p99_context is not None:
        _require(p99_context >= avg_context,
                 "P99 length cannot be shorter than the average length")

    warnings: list[str] = [
        "--overhead 是经验值，必须在自己的环境里实测：不要看空载时的 nvidia-smi，"
        "vLLM 一类引擎启动时已按 gpu_memory_utilization 留出 KV 池；读启动日志里的权重显存"
        "与 KV 池容量，用 gpu_memory_utilization × 显存总量 − 权重 − KV 池反推（16.6 第 3 步）",
        f"第 1 步按 gpu_memory_utilization {utilization} 折算：整张卡 "
        f"{gpu_memory_gib} GiB 里引擎只拿到 {gpu_memory_gib * utilization:.1f} GiB。"
        "自己的服务按启动参数的实际取值改 --utilization",
    ]

    mixed: dict | None = None
    if mix:
        avg_mixed = mixed_average_context(mix)
        conc_mixed = concurrency(total_tokens, int(avg_mixed))
        conc_worst = worst_case_concurrency(total_tokens, mix)
        mixed = {
            "buckets": [{"share": s, "context": c} for s, c in mix],
            "average_context": round(avg_mixed, 1),
            "concurrency_at_mixed_average": conc_mixed,
            "longest_bucket_context": max(c for _, c in mix),
            "concurrency_if_all_longest": conc_worst,
            "reading": (
                f"平均值给出 {conc_mixed} 条，全是最长那一档时只有 {conc_worst} 条。"
                "并发上限不是由平均长度决定的，是由最坏情况下的混合决定的（16.9 案例三）"
            ),
        }
        warnings.append(
            "容量表第 7 步用平均值，等于默认了混合比例稳定；混合比例一变，"
            f"上限会往 {conc_worst} 条那边掉"
        )

    blocks = block_accounting(total_tokens, block_size, per_token, conc_avg)
    if blocks["waste_share_of_budget"] > 0.02:
        warnings.append(
            f"块大小 {block_size} 下的平均浪费已占 KV 预算的 "
            f"{blocks['waste_share_of_budget'] * 100:.1f}%，它直接换走一部分并发上限"
        )

    recommended_low = int(conc_avg * DISCOUNT_LOW)
    recommended_high = int(conc_avg * DISCOUNT_HIGH)

    comparison: dict = {
        "measured_concurrency": measured_concurrency,
        "reading": "没有实测值：这张表只是压测的起点，不是结论（16.6）",
    }
    if measured_concurrency is not None:
        _require(measured_concurrency > 0, "measured concurrency must be positive")
        if measured_concurrency < recommended_low:
            comparison["reading"] = (
                f"实测 {measured_concurrency} 低于建议区间 {recommended_low}，"
                "先怀疑 --overhead 估小了，或者存在别的显存占用"
            )
        elif measured_concurrency > conc_avg:
            comparison["reading"] = (
                f"实测 {measured_concurrency} 高于按平均长度算出的 {conc_avg}，"
                "说明真实的平均长度比你以为的短，回去核对负载画像"
            )
        else:
            comparison["reading"] = (
                f"实测 {measured_concurrency} 落在建议区间与理论上限之间，显存账对得上"
            )

    return {
        "units": {
            "memory": "binary (GiB = 2^30 B)：与分配器和框架日志同口径（11.3、16.2）",
            "transfer": "decimal (GB/s)：PCIe 规格是十进制，swap_ms 里做了换算",
        },
        "model": {
            "layers": layers, "kv_heads": kv_heads, "head_dim": head_dim,
            "dtype": dtype, "bytes_per_element": BYTES_FOR_DTYPE[dtype],
        },
        "bytes_per_token": int(per_token),
        "kib_per_token": round(per_token / KIB, 2),
        "budget": {
            "gpu_memory_gib": gpu_memory_gib,
            "gpu_memory_utilization": utilization,
            "usable_gib": round(gpu_memory_gib * utilization, 3),
            "weight_memory_gib": weight_memory_gib,
            "overhead_gib": overhead_gib,
            "kv_budget_gib": round(budget / GIB, 3),
        },
        "total_tokens": int(total_tokens),
        "avg_context": avg_context,
        "concurrency_avg": conc_avg,
        "p99_context": p99_context,
        "concurrency_p99": conc_p99,
        "recommended": [recommended_low, recommended_high],
        "recommended_note": (
            f"按 {int(DISCOUNT_LOW * 100)}%~{int(DISCOUNT_HIGH * 100)}% 打折。"
            + (f"真实的安全并发在 {conc_p99} 和 {conc_avg} 之间，"
               "具体位置取决于长度分布的形状和你能接受多少抢占"
               if conc_p99 is not None else "建议同时给 --p99-context")
        ),
        "blocks": blocks,
        "mixed": mixed,
        "preemption": preemption_cost(
            preempt_context or p99_context or avg_context,
            per_token, pcie_gb_per_s=pcie_gb_per_s, recompute_ms=recompute_ms,
            concurrency_for_host_memory=conc_avg),
        "comparison": comparison,
        "warnings": warnings,
    }


def print_summary(report: dict) -> None:
    b = report["budget"]
    print(f"每 token KV  {report['kib_per_token']} KiB"
          f"  ({report['bytes_per_token']} 字节)")
    print(f"1 可用预算   {b['usable_gib']} GiB"
          f"  = {b['gpu_memory_gib']} × {b['gpu_memory_utilization']}")
    print(f"2 减权重     -{b['weight_memory_gib']} GiB")
    print(f"3 减开销     -{b['overhead_gib']} GiB（经验值，需实测）")
    print(f"4 KV 预算    {b['kv_budget_gib']} GiB")
    print(f"6 总 token   {report['total_tokens']}")
    print(f"8 平均长度 {report['avg_context']} → 并发 {report['concurrency_avg']} 条")
    if report["concurrency_p99"] is not None:
        print(f"  P99 长度 {report['p99_context']} → 并发 "
              f"{report['concurrency_p99']} 条（保守下界）")
    print(f"9 建议起点   {report['recommended'][0]}~{report['recommended'][1]} 条")
    blk = report["blocks"]
    print(f"块           {blk['block_size']} token/块  共 {blk['blocks_total']} 块"
          f"  每条平均浪费 {blk['waste_mib_per_request']} MiB"
          f"  合计 {blk['waste_gib_total']} GiB")
    if report["mixed"] is not None:
        m = report["mixed"]
        print(f"混合分布     平均 {m['average_context']} token → "
              f"{m['concurrency_at_mixed_average']} 条；"
              f"全是 {m['longest_bucket_context']} token 时 "
              f"{m['concurrency_if_all_longest']} 条")
    p = report["preemption"]
    print(f"抢占         {p['context']} token 占 {p['kv_mib']} MiB；"
          f"换出单程 {p['swap_one_way_ms']} ms，往返 {p['swap_round_trip_ms']} ms")
    print(f"             {p['faster_on_wall_clock']}")
    if p["host_memory"] is not None:
        print(f"             换出还要 {p['host_memory']['host_gib_needed']} GiB "
              f"主机内存（按 {p['host_memory']['concurrency']} 条并发）")
    print(f"对照         {report['comparison']['reading']}")
    for warning in report["warnings"]:
        print(f"WARNING      {warning}")


def _parse_mix(text: str) -> list[tuple[float, int]]:
    """`0.97:2300,0.03:32000` → [(0.97, 2300), (0.03, 32000)]"""
    out: list[tuple[float, int]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise CapacityError(f"mix 项要写成 占比:长度，收到 {part!r}")
        share, ctx = part.split(":", 1)
        out.append((float(share), int(ctx)))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None,
                        help="读 Part 4 共享的 code/ch15/model-7b-generic.json，"
                             "下面各项可以逐个覆盖")
    parser.add_argument("--layers", type=int, default=None)
    parser.add_argument("--kv-heads", type=int, default=None)
    parser.add_argument("--head-dim", type=int, default=None)
    parser.add_argument("--dtype", default=None,
                        choices=tuple(BYTES_FOR_DTYPE))
    parser.add_argument("--gpu-memory", type=float, default=None,
                        help="显存总量 GiB")
    parser.add_argument("--weight-memory", type=float, default=None,
                        help="权重占用 GiB；16.2 说过按 14 GiB 扣 14 GB 的权重"
                             "是刻意的保守")
    parser.add_argument("--overhead", type=float, default=None,
                        help="激活值、框架开销、通信缓冲区 GiB，必须实测")
    parser.add_argument("--utilization", type=float, default=None,
                        help="gpu_memory_utilization，引擎能用整张卡的几成，"
                             "默认按 vLLM 的 0.9 取（16.6 第 1 步）")
    parser.add_argument("--avg-context", type=int, required=True)
    parser.add_argument("--p99-context", type=int, default=None)
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--mix", type=str, default=None,
                        help="混合长度分布，例如 0.97:2300,0.03:32000")
    parser.add_argument("--pcie", type=float, default=16.0,
                        help="PCIe 带宽 GB/s（十进制）")
    parser.add_argument("--preempt-context", type=int, default=None,
                        help="算抢占代价用的序列长度；省略时用 P99，再退到平均")
    parser.add_argument("--recompute-ms", type=float, default=None,
                        help="实测的这个长度的 Prefill 耗时；不给就不判换出/重算")
    parser.add_argument("--measured-concurrency", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    config: dict = {}
    if args.config is not None:
        config = json.loads(args.config.read_text(encoding="utf-8"))

    def pick(flag, key, default=None):
        if flag is not None:
            return flag
        if key in config:
            return config[key]
        return default

    try:
        report = build_report(
            layers=pick(args.layers, "layers"),
            kv_heads=pick(args.kv_heads, "num_key_value_heads"),
            head_dim=pick(args.head_dim, "head_dim"),
            dtype=pick(args.dtype, "dtype", "fp16"),
            gpu_memory_gib=pick(args.gpu_memory, "gpu_memory_gib"),
            weight_memory_gib=args.weight_memory if args.weight_memory is not None
            else round(
                float(config.get("params_total", 0))
                * float(config.get("bytes_per_element", 2)) / GIB, 2
            ),
            overhead_gib=pick(args.overhead, "framework_overhead_gib"),
            utilization=pick(args.utilization, "gpu_memory_utilization", 0.9),
            avg_context=args.avg_context,
            p99_context=args.p99_context,
            block_size=args.block_size,
            mix=_parse_mix(args.mix) if args.mix else None,
            pcie_gb_per_s=args.pcie,
            preempt_context=args.preempt_context,
            recompute_ms=args.recompute_ms,
            measured_concurrency=args.measured_concurrency,
        )
    except (CapacityError, TypeError) as exc:
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
