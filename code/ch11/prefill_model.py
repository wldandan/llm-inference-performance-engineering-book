#!/usr/bin/env python3
"""Estimate what one Prefill should cost, so a measurement has something to be
compared against.

This Demo produces an order of magnitude, not a prediction. It keeps two
numbers apart (11.5):

* the lower bound, FLOPs over *peak* compute: no measurement can beat it, so a
  measurement below it means some of the computation did not happen;
* the estimate, FLOPs over *effective* compute (peak times an assumed
  efficiency): a measurement several times above it means overhead to find.

With a second, shorter measurement it also runs the ratio check of 11.2: does
the growth from the short prompt to the long one follow the FLOPs shape? The
ratio check and the absolute check answer different questions and can
disagree.

It never measures anything. `--measured-ms` is a number you bring from a real
Baseline; without it the report carries the theoretical side only and says so.

Only the Python standard library. No GPU.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_CONFIG_FIELDS = (
    "layers",
    "hidden_size",
    "num_attention_heads",
    "num_key_value_heads",
    "head_dim",
    "intermediate_size",
    "vocab_size",
    "bytes_per_element",
)

# 11.5: the ratio bands the book uses to read a measurement against the
# estimate. Anything below 1.0 is the interesting one.
BAND_SAME_ORDER = 3.0


class ModelError(ValueError):
    """Raised when a model configuration cannot support an estimate."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelError(message)


def load_config(doc: object) -> dict:
    _require(isinstance(doc, dict), "model config must be an object")
    assert isinstance(doc, dict)
    for field in REQUIRED_CONFIG_FIELDS:
        value = doc.get(field)
        _require(
            isinstance(value, int) and value > 0,
            f"config.{field} must be a positive integer",
        )
    _require(
        doc["num_attention_heads"] % doc["num_key_value_heads"] == 0,
        "num_attention_heads must be a multiple of num_key_value_heads (GQA)",
    )
    _require(
        doc["num_attention_heads"] * doc["head_dim"] == doc["hidden_size"],
        "num_attention_heads * head_dim must equal hidden_size",
    )
    return doc


def kv_dim(config: dict) -> int:
    """Width of one position's K (or V) across all KV heads."""
    return config["num_key_value_heads"] * config["head_dim"]


def params_per_layer(config: dict) -> int:
    """Weights in one transformer layer.

    Q and O are hidden x hidden, K and V are hidden x kv_dim, and the MLP has
    three hidden x intermediate matrices (gate, up, down).
    """
    h = config["hidden_size"]
    return 2 * h * h + 2 * h * kv_dim(config) + 3 * h * config["intermediate_size"]


def embedding_params(config: dict) -> int:
    n = config["vocab_size"] * config["hidden_size"]
    return n if config.get("tied_word_embeddings", True) else 2 * n


def non_embedding_params(config: dict) -> int:
    """The parameter count that belongs in `2 x params x tokens`.

    Embedding lookup is a table read, not a matrix multiply. Counting it
    inflates the GEMM term, and the wider the vocabulary the worse it gets
    (11.5).
    """
    return params_per_layer(config) * config["layers"]


def crossover_tokens(config: dict) -> int:
    """Input length at which Attention FLOPs equal GEMM FLOPs.

    Setting `2 x params_per_layer x S == 2 x hidden x S^2` gives
    `S = params_per_layer / hidden`, which is independent of layer count:
    `2*hidden + 2*kv_dim + 3*intermediate` (11.2).
    """
    h = config["hidden_size"]
    return 2 * h + 2 * kv_dim(config) + 3 * config["intermediate_size"]


def gemm_flops(config: dict, tokens: int) -> int:
    return 2 * non_embedding_params(config) * tokens


def attention_flops(config: dict, tokens: int) -> int:
    """QK^T plus AV over all layers, with causal masking folded in.

    Each of the two products costs `2 * hidden * S^2 / 2` per layer once the
    causal triangle is accounted for, so the pair is `2 * hidden * S^2`.
    """
    return 2 * config["hidden_size"] * config["layers"] * tokens * tokens


def relative_cost(config: dict, tokens: int) -> int:
    """`S x (crossover + S)`: total compute with the common factor divided out.

    This is the function the chapters use to compare two lengths (11.2). Ratios
    of it are exactly ratios of total FLOPs.
    """
    return tokens * (crossover_tokens(config) + tokens)


def doubling_factor(config: dict, tokens: int) -> float:
    """How much compute grows when the input doubles.

    Never 4: at the crossover it is exactly 3, and 4 is the limit as the input
    grows without bound (11.7 case 1).
    """
    return relative_cost(config, 2 * tokens) / relative_cost(config, tokens)


def kv_cache_bytes(config: dict, tokens: int) -> int:
    """K and V for every layer and every position."""
    return (
        2
        * config["layers"]
        * kv_dim(config)
        * tokens
        * config["bytes_per_element"]
    )


def attention_matrix_bytes(config: dict, tokens: int) -> int:
    """One layer's full S x S attention matrix, all heads, if materialised.

    A naive implementation writes this out and reads it back; FlashAttention
    does not (13.4). It grows with the square of the length, which is why that
    technique only pays off on long sequences.
    """
    return (
        config["num_attention_heads"]
        * tokens
        * tokens
        * config["bytes_per_element"]
    )


def compute_block(config: dict, tokens: int) -> dict:
    gemm = gemm_flops(config, tokens)
    attn = attention_flops(config, tokens)
    total = gemm + attn
    return {
        "input_tokens": tokens,
        "non_embedding_params": non_embedding_params(config),
        "embedding_params": embedding_params(config),
        "total_params": non_embedding_params(config) + embedding_params(config),
        "params_overcount_if_embedding_included": round(
            (non_embedding_params(config) + embedding_params(config))
            / non_embedding_params(config),
            3,
        ),
        "gemm_flops": gemm,
        "attention_flops": attn,
        "total_flops": total,
        "attention_share_of_gemm": round(attn / gemm, 4),
        "attention_share_of_total": round(attn / total, 4),
        "crossover_tokens": crossover_tokens(config),
        "relative_cost": relative_cost(config, tokens),
        "doubling_factor": round(doubling_factor(config, tokens), 3),
    }


def memory_block(config: dict, tokens: int, concurrency: int) -> dict:
    per_token_per_layer = 2 * kv_dim(config) * config["bytes_per_element"]
    one = kv_cache_bytes(config, tokens)
    return {
        "kv_bytes_per_token_per_layer": per_token_per_layer,
        "kv_bytes_per_token": per_token_per_layer * config["layers"],
        "kv_bytes_one_request": one,
        "kv_mib_one_request": round(one / 1024**2, 2),
        "concurrency": concurrency,
        "kv_gib_at_concurrency": round(one * concurrency / 1024**3, 2),
        "kv_mib_if_mha": round(
            one
            * config["num_attention_heads"]
            / config["num_key_value_heads"]
            / 1024**2,
            2,
        ),
        "attention_matrix_mib_one_layer": round(
            attention_matrix_bytes(config, tokens) / 1024**2, 2
        ),
        "note": "二进制单位（MiB/GiB），与框架日志和显存分配器同口径（11.3）",
    }


def projection_shapes(config: dict) -> list[tuple[int, int]]:
    """The seven weight matrices of one layer, as (k, n)."""
    h = config["hidden_size"]
    kvd = kv_dim(config)
    inter = config["intermediate_size"]
    return [(h, h), (h, kvd), (h, kvd), (h, h), (h, inter), (h, inter), (inter, h)]


def intensity_with_activations(config: dict, tokens: int) -> float:
    """FLOPs per byte when the activations read and written also count (11.4).

    One projection of S tokens through a k x n matrix does 2Skn FLOPs and moves
    2(Sk + kn + Sn) bytes in FP16: input activations, weights, output
    activations. The ratio is 1 / (1/S + 1/k + 1/n), so it tracks S while S is
    small and is capped by the matrix width once S grows.
    """
    shapes = projection_shapes(config)
    b = config["bytes_per_element"]
    flops = sum(2 * tokens * k * n for k, n in shapes)
    moved = sum(b * (tokens * k + k * n + tokens * n) for k, n in shapes)
    return flops / moved


def arithmetic_intensity_block(config: dict, tokens: int) -> dict:
    """FLOPs per byte, two ways (11.4).

    Counting the weights only, the ratio reduces to the token count. Counting
    the activations too, it is capped well below that for long prompts.
    """
    weight_bytes = 2 * non_embedding_params(config)
    return {
        "weight_bytes_read": weight_bytes,
        "prefill_flops_per_byte_weights_only": round(gemm_flops(config, tokens) / weight_bytes, 1),
        "prefill_flops_per_byte": round(intensity_with_activations(config, tokens), 1),
        "decode_flops_per_byte": round(gemm_flops(config, 1) / weight_bytes, 1),
        "note": (
            "只算权重读取时 Prefill 的强度约等于输入 token 数；算上激活读写后在几百处封顶。"
            "Decode 每步约等于 1。分界点 = 峰值算力 ÷ 峰值带宽，A100 约 153，H100 约 295（附录 A）"
        ),
    }


def interpret(measured_ms: float, lower_bound_ms: float, estimate_ms: float) -> str:
    """Read a measurement against 11.5's two reference numbers."""
    if measured_ms < lower_bound_ms:
        return (
            "低于下限：硬件满载也快不过下限，比它快说明某段计算没有发生。"
            "先查是不是命中了 Prefix Cache，或者这段时间的边界定义不对"
        )
    if measured_ms < estimate_ms:
        return (
            "在下限与估计之间：实现效率比估计时假设的高，属正常，"
            "不能据此断定缓存命中"
        )
    if measured_ms / estimate_ms <= BAND_SAME_ORDER:
        return "与估计同一量级：Prefill 本身没有明显异常，要优化就得减少计算量或换更高效的实现"
    return "高出估计数倍：有额外开销，可能是 kernel 效率低、被拆成多轮调度，或这段时间里混着别的东西"


def comparison_block(
    total_flops: int,
    peak_tflops: float,
    effective_tflops: float,
    measured_ms: float | None,
) -> dict:
    _require(peak_tflops > 0, "--peak-tflops must be positive")
    _require(effective_tflops > 0, "--effective-tflops must be positive")
    _require(effective_tflops <= peak_tflops,
             "--effective-tflops cannot exceed --peak-tflops")
    lower_bound_ms = total_flops / (peak_tflops * 1e12) * 1000
    estimate_ms = total_flops / (effective_tflops * 1e12) * 1000
    block: dict = {
        "peak_tflops": peak_tflops,
        "effective_tflops": effective_tflops,
        "assumed_efficiency": round(effective_tflops / peak_tflops, 3),
        "lower_bound_ms": round(lower_bound_ms, 1),
        "estimate_ms": round(estimate_ms, 1),
        "note": (
            "下限用峰值算，任何实测都快不过它；估计用峰值乘经验效率算，"
            "用来判断有没有额外开销（11.5）"
        ),
    }
    if measured_ms is None:
        block["measured_ms"] = None
        block["ratio_to_estimate"] = None
        block["reading"] = "未提供实测值，本报告只有理论一侧。没有测就是没有测"
        return block
    _require(measured_ms > 0, "--measured-ms must be positive")
    implied = total_flops / (measured_ms / 1000) / 1e12
    block["measured_ms"] = measured_ms
    block["ratio_to_estimate"] = round(measured_ms / estimate_ms, 2)
    block["implied_tflops"] = round(implied, 2)
    block["implied_share_of_peak"] = round(implied / peak_tflops, 3)
    block["reading"] = interpret(measured_ms, lower_bound_ms, estimate_ms)
    return block


def ratio_check_block(
    config: dict,
    tokens: int,
    measured_ms: float | None,
    reference_tokens: int | None,
    reference_ms: float | None,
) -> dict:
    """11.2's check: does the growth between two lengths follow the FLOPs shape?

    It cancels every constant factor, so it can pass while the absolute check
    fails; the two checks answer different questions.
    """
    if reference_tokens is None or reference_ms is None or measured_ms is None:
        return {"available": False,
                "reading": "需要 --reference-tokens、--reference-ms 和 --measured-ms 才能做比值检验"}
    _require(0 < reference_tokens < tokens, "--reference-tokens must be shorter than --input-tokens")
    _require(reference_ms > 0, "--reference-ms must be positive")
    expected = relative_cost(config, tokens) / relative_cost(config, reference_tokens)
    measured = measured_ms / reference_ms
    agree = 1 / 1.25 <= measured / expected <= 1.25
    return {
        "available": True,
        "reference_tokens": reference_tokens,
        "expected_ratio": round(expected, 2),
        "measured_ratio": round(measured, 2),
        "shape_agrees": agree,
        "reading": (
            "增长形状与计算量一致：长度带来的增长由计算量解释得了；常数因子要看绝对值检验"
            if agree else
            "增长形状与计算量不一致：长度之外还有别的东西随长度变化"
        ),
    }


def build_report(
    config: dict,
    tokens: int,
    *,
    peak_tflops: float = 153.0,
    effective_tflops: float,
    concurrency: int,
    measured_ms: float | None,
    reference_tokens: int | None = None,
    reference_ms: float | None = None,
) -> dict:
    _require(tokens > 0, "--input-tokens must be positive")
    _require(concurrency > 0, "--concurrency must be positive")
    window = config.get("context_window")
    warnings = []
    if isinstance(window, int) and tokens > window:
        warnings.append(
            f"输入 {tokens} token 超过配置里的上下文窗口 {window}，这个估算没有意义"
        )
    compute = compute_block(config, tokens)
    return {
        "config": {
            "name": config.get("name", "unnamed"),
            "revision": config.get("revision"),
            "layers": config["layers"],
            "hidden_size": config["hidden_size"],
            "num_attention_heads": config["num_attention_heads"],
            "num_key_value_heads": config["num_key_value_heads"],
            "head_dim": config["head_dim"],
            "intermediate_size": config["intermediate_size"],
            "kv_dim": kv_dim(config),
            "dtype": config.get("dtype", "fp16"),
        },
        "compute": compute,
        "memory": memory_block(config, tokens, concurrency),
        "arithmetic_intensity": arithmetic_intensity_block(config, tokens),
        "comparison": comparison_block(
            compute["total_flops"], peak_tflops, effective_tflops, measured_ms
        ),
        "ratio_check": ratio_check_block(
            config, tokens, measured_ms, reference_tokens, reference_ms
        ),
        "warnings": warnings,
        "disclaimer": (
            "这份报告只给量级和线索，不给结论。它不会告诉你该优化什么"
        ),
    }


def _fmt_flops(n: int) -> str:
    return f"{n / 1e12:.2f} TFLOPs"


def print_summary(report: dict) -> None:
    c = report["compute"]
    m = report["memory"]
    a = report["arithmetic_intensity"]
    cmp_ = report["comparison"]
    print(f"模型      {report['config']['name']}  交叉点 {c['crossover_tokens']} token")
    print(f"输入      {c['input_tokens']} token")
    print(f"GEMM      {_fmt_flops(c['gemm_flops'])}")
    print(f"Attention {_fmt_flops(c['attention_flops'])}"
          f"  占总 {c['attention_share_of_total'] * 100:.1f}%")
    print(f"合计      {_fmt_flops(c['total_flops'])}")
    print(f"长度翻倍  计算量 × {c['doubling_factor']}  （四倍是取不到的上限）")
    print(f"KV Cache  {m['kv_mib_one_request']} MiB 单条"
          f"  {m['kv_gib_at_concurrency']} GiB @ {m['concurrency']} 并发")
    print(f"算术强度  Prefill {a['prefill_flops_per_byte']}"
          f"（只算权重 {a['prefill_flops_per_byte_weights_only']}）"
          f"  Decode {a['decode_flops_per_byte']} FLOP/byte")
    print(f"下限      {cmp_['lower_bound_ms']} ms  @ 峰值 {cmp_['peak_tflops']} TFLOP/s")
    print(f"估计      {cmp_['estimate_ms']} ms  @ 有效 {cmp_['effective_tflops']} TFLOP/s")
    if cmp_["measured_ms"] is not None:
        print(f"实测      {cmp_['measured_ms']} ms  是估计的 {cmp_['ratio_to_estimate']} 倍"
              f"  折合 {cmp_['implied_tflops']} TFLOP/s")
    print(f"绝对值    {cmp_['reading']}")
    rc = report["ratio_check"]
    if rc["available"]:
        print(f"比值检验  {rc['reference_tokens']} → {c['input_tokens']} token"
              f"  预期 {rc['expected_ratio']} 倍  实测 {rc['measured_ratio']} 倍")
    print(f"比值      {rc['reading']}")
    for w in report["warnings"]:
        print(f"WARNING   {w}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True,
                        help="模型配置，例如 code/ch11/model-qwen25-05b.json")
    parser.add_argument("--input-tokens", type=int, required=True)
    parser.add_argument("--peak-tflops", type=float, default=153.0,
                        help="规格峰值，用来算下限（11.5）")
    parser.add_argument("--effective-tflops", type=float, default=30.0,
                        help="有效算力 = 峰值 × 经验效率，用来算估计（11.5）")
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--measured-ms", type=float, default=None,
                        help="真实 Baseline 的 Scheduled-to-First-Token；不给就只出理论值")
    parser.add_argument("--reference-tokens", type=int, default=None,
                        help="较短那次测量的输入长度，用于比值检验（11.2）")
    parser.add_argument("--reference-ms", type=float, default=None,
                        help="较短那次测量的实测值")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        config = load_config(json.loads(args.config.read_text(encoding="utf-8")))
        report = build_report(
            config,
            args.input_tokens,
            peak_tflops=args.peak_tflops,
            effective_tflops=args.effective_tflops,
            concurrency=args.concurrency,
            measured_ms=args.measured_ms,
            reference_tokens=args.reference_tokens,
            reference_ms=args.reference_ms,
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
