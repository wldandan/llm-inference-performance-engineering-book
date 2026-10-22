#!/usr/bin/env python3
"""Check which of the four Prefill options this workload can actually use.

13.1's table says the four paths change different things. This Demo takes the
workload description from Chapter 6 and the context bill from Chapter 12 and,
for each path, says whether the preconditions hold, what improves, who pays,
and how to roll it back.

It does not decide for you. **Four paths marked applicable still means one at
a time** (13.6, 14.2).

Only the Python standard library. No GPU.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch11"))
sys.path.insert(0, str(HERE.parent / "ch12"))
from context_cost import prefix_cache_saving  # noqa: E402
from prefill_model import (  # noqa: E402
    ModelError,
    attention_matrix_bytes,
    crossover_tokens,
    load_config,
    relative_cost,
)

PATHS = ("context_trim", "prefix_cache", "flash_attention", "chunked_prefill")
VERDICTS = ("适用", "有限", "不适用")

# 13.6's thresholds. Each one is a number the chapter states, kept here so the
# text and the tool cannot drift apart.
CACHEABLE_FLOOR = 0.30          # below this, Prefix Cache is not worth the work
FLASH_SHORT_PROMPT = 1000       # under this, the attention matrix is small
MIXED_LENGTH_RATIO = 3.0        # p99 / p50 below this is not a mixed workload
TRIM_FRACTION = 0.40            # the cut 13.2 works through


class CheckError(ValueError):
    """Raised when the inputs cannot support a judgement."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def validate_inputs(workload: object, bill: object) -> None:
    _require(isinstance(workload, dict), "workload must be an object")
    _require(isinstance(bill, dict), "context cost bill must be an object")
    assert isinstance(workload, dict) and isinstance(bill, dict)
    length = workload.get("length")
    _require(isinstance(length, dict), "workload.length is required (第 6 章)")
    prompt = length.get("prompt")
    _require(isinstance(prompt, dict), "workload.length.prompt is required")
    for q in ("p50", "p99"):
        value = prompt.get(q)
        _require(
            isinstance(value, (int, float)) and value > 0,
            f"workload.length.prompt.{q} is required：判断长短混跑要靠分布",
        )
    _require(
        isinstance(workload.get("arrival"), dict),
        "workload.arrival is required：Chunked Prefill 的前提是有并发",
    )
    cacheable = bill.get("cacheable")
    _require(
        isinstance(cacheable, dict) and "prefix_share_of_tokens" in cacheable,
        "context cost bill 缺 cacheable：请用 code/ch12/context_cost.py 生成",
    )
    totals = bill.get("totals")
    _require(
        isinstance(totals, dict) and isinstance(totals.get("input_tokens"), int),
        "context cost bill 缺 totals.input_tokens",
    )


def _trim_gain(config: dict, tokens: int, fraction: float) -> float:
    kept = max(1, int(round(tokens * (1 - fraction))))
    return 1.0 - relative_cost(config, kept) / relative_cost(config, tokens)


def check_context_trim(workload: dict, bill: dict, config: dict) -> dict:
    tokens = bill["totals"]["input_tokens"]
    gain = _trim_gain(config, tokens, TRIM_FRACTION)
    has_quality = bool(workload.get("quality_eval") or bill.get("quality_eval"))
    warnings = []
    if not has_quality:
        warnings.append(
            "没有提供质量评测配置：这条路的代价是质量，没有评测集就无法判断是否划算（13.2）"
        )
    return {
        "path": "context_trim",
        "name": "上下文裁剪",
        "applicable": "适用",
        "reason": (
            f"输入 P50 {int(workload['length']['prompt']['p50'])} token，"
            f"账单总长 {tokens} token；这是唯一减少输入长度的一条，任何负载上都先试它"
        ),
        "expected": (
            f"砍掉 {int(TRIM_FRACTION * 100)}% 的输入，计算量降 {gain * 100:.1f}%，"
            f"改善的是本条请求；多出来的 {(gain - TRIM_FRACTION) * 100:.1f} "
            f"个百分点来自 Attention 平方项"
        ),
        "improves_whose_metric": "本条请求",
        "cost": "质量，必须实测",
        "prerequisite": "有一个可量化的质量指标，且能画出质量随长度变化的曲线（12.4）",
        "risk": "低：改参数即可，随时回滚",
        "warnings": warnings,
        "evidence_field": "context_cost.totals.input_tokens",
    }


def routing_term(replicas: int, reuse: int) -> float:
    """Share of requests that hit when a prefix is reused k times over N replicas.

    Requests land uniformly at random; every replica that sees the prefix pays
    one first write, so the hit share is 1 - N(1 - (1 - 1/N)^k) / k (13.3).
    A prefix shared by all traffic has k so large that this is close to 1.
    """
    if replicas < 1 or reuse < 1:
        raise ValueError("replicas and reuse must be at least 1")
    touched = replicas * (1 - (1 - 1 / replicas) ** reuse)
    return 1 - touched / reuse


def check_prefix_cache(workload: dict, bill: dict, config: dict) -> dict:
    share = bill["cacheable"]["prefix_share_of_tokens"]
    tokens = bill["totals"]["input_tokens"]
    saving = bill["cacheable"].get("prefill_saving_if_fully_hit")
    if saving is None:
        saving = prefix_cache_saving(config, tokens, int(tokens * share))
    deployment = workload.get("deployment", {})
    replicas = int(deployment.get("replicas", 1) or 1)
    cache_aware = bool(deployment.get("cache_aware_routing"))
    scope = deployment.get("prefix_scope", "session")
    reuse = deployment.get("prefix_reuse")
    warnings = list(bill.get("warnings") or [])
    if scope == "shared":
        # 全体共享的前缀：每个实例第一次各写一份，之后都能命中，路由项接近 1。
        routing_factor = 1.0
    elif replicas == 1 or cache_aware:
        # 路由不再打散，但每个前缀第一次出现时总要写一次，这一刀路由收不回来。
        routing_factor = routing_term(1, int(reuse)) if reuse else 0.5
        if reuse is None:
            warnings.append(
                "会话级前缀没有写 deployment.prefix_reuse（同一前缀被复用几次），"
                "按复用两次折算，单实例的路由项是 50%：每个前缀第一次总要写一次（13.3）"
            )
    elif reuse is None:
        # 路由项随复用次数单调上升，确有复用时的最小值在 k = 2，等于 1/(2N)。
        routing_factor = 1.0 / (2 * replicas)
        warnings.append(
            f"{replicas} 副本随机路由，又没有写 deployment.prefix_reuse（同一前缀被复用几次），"
            f"按复用两次这种最保守的情形取 1/(2 × {replicas})；"
            f"补上复用次数会得到更准的路由项（13.3）"
        )
    else:
        routing_factor = routing_term(replicas, int(reuse))
        warnings.append(
            f"会话级前缀复用 {int(reuse)} 次、{replicas} 副本随机路由，"
            f"路由项约 {routing_factor * 100:.1f}%；缓存感知路由能收回这一刀（第 22 章）"
        )
    ceiling = saving * routing_factor
    verdict = "适用" if share >= CACHEABLE_FLOOR else "有限"
    return {
        "path": "prefix_cache",
        "name": "Prefix Cache",
        "applicable": verdict,
        "reason": (
            f"可缓存前缀占 {share * 100:.0f}% 的 token"
            + (
                f"，高于三成的门槛"
                if share >= CACHEABLE_FLOOR
                else f"，低于三成的门槛，先去改 prompt 拼接顺序或减少内容"
            )
        ),
        "expected": (
            f"全命中能省 {saving * 100:.0f}% 的 Prefill 计算；"
            f"按当前部署的路由折算，请求命中的概率约 {routing_factor * 100:.1f}%，"
            f"期望收益上限约 {ceiling * 100:.0f}%（计算节省 = 命中概率 × 每次命中省的份额）"
        ),
        "improves_whose_metric": "本条请求（命中时）",
        "cost": "前缀哈希与查找的开销；它不另占显存，显存紧张时反而是缓存块先被淘汰（13.3）",
        "prerequisite": "固定内容排在 prompt 最前面；多副本时，会话级前缀要有缓存感知路由（13.3）",
        "risk": "中：要确认前缀顺序和路由",
        "warnings": warnings,
        "evidence_field": "context_cost.cacheable.prefix_share_of_tokens",
    }


def check_flash_attention(workload: dict, bill: dict, config: dict) -> dict:
    p50 = int(workload["length"]["prompt"]["p50"])
    p99 = int(workload["length"]["prompt"]["p99"])
    matrix_mib = attention_matrix_bytes(config, p50) / 1024**2
    crossover = crossover_tokens(config)
    attn_share = (p50 / crossover) / (1 + p50 / crossover)
    verdict = "适用" if p50 >= FLASH_SHORT_PROMPT else "有限"
    return {
        "path": "flash_attention",
        "name": "FlashAttention",
        "applicable": verdict,
        "reason": (
            f"输入 P50 {p50} token，单层注意力矩阵约 {matrix_mib:.0f} MiB，"
            f"Attention 占总计算量 {attn_share * 100:.1f}%（交叉点 {crossover}）"
            + ("" if p50 >= FLASH_SHORT_PROMPT else "；矩阵本来就不大，搬运不是瓶颈")
        ),
        "expected": (
            "减少注意力矩阵的显存读写，不减少计算量；"
            f"P99 那一档（{p99} token）的矩阵是 "
            f"{attention_matrix_bytes(config, p99) / 1024 ** 2:.0f} MiB，长尾请求收益更大"
        ),
        "improves_whose_metric": "本条请求（长序列）",
        "cost": "无",
        "prerequisite": "先查实际走的是哪条 kernel，不是装了哪个包；多数框架已默认启用（13.4）",
        "risk": "低：通常只是确认而非改动",
        "warnings": [],
        "evidence_field": "workload.length.prompt.p50",
    }


def check_chunked_prefill(workload: dict, bill: dict, config: dict) -> dict:
    prompt = workload["length"]["prompt"]
    p50, p99 = float(prompt["p50"]), float(prompt["p99"])
    ratio = p99 / p50
    arrival = workload.get("arrival", {})
    concurrency = arrival.get("concurrency")
    rate = arrival.get("rate")
    serial = arrival.get("mode") == "closed" and concurrency is not None and concurrency <= 1
    mixed = ratio >= MIXED_LENGTH_RATIO
    has_concurrency = bool(rate) or (concurrency is not None and concurrency > 1)

    if not mixed:
        verdict, reason = "不适用", (
            f"P99/P50 = {ratio:.1f}，低于 {MIXED_LENGTH_RATIO} 的门槛，"
            f"长短差异不大；没有“别人被卡住”这个问题，拆分只带来调度开销"
        )
    elif not has_concurrency or serial:
        verdict, reason = "不适用", (
            "负载里没有并发，请求基本串着处理；没有其他请求要保护，开了只会更慢"
        )
    else:
        verdict, reason = "适用", (
            f"P99/P50 = {ratio:.1f}，长短混跑，且有并发；"
            f"长请求的 Prefill 会挡住正在生成的请求"
        )
    return {
        "path": "chunked_prefill",
        "name": "Chunked Prefill",
        "applicable": verdict,
        "reason": reason,
        "expected": (
            "其他请求的 ITL 更稳定；本条长请求的 TTFT 会变差。"
            "判据是其他请求的 ITL P99 超过 P50 三倍（13.6）"
        ),
        "improves_whose_metric": "其他请求",
        "cost": "本条长请求的 TTFT",
        "prerequisite": "负载里长短混跑且有并发；要单独统计短请求的 ITL（13.5、14.4）",
        "risk": "中：要配合调度参数（第 20 章）",
        "warnings": [],
        "evidence_field": "workload.length.prompt.p99 / p50",
    }


CHECKS = (
    check_context_trim,
    check_prefix_cache,
    check_flash_attention,
    check_chunked_prefill,
)


def build_options(workload: dict, bill: dict, config: dict) -> dict:
    validate_inputs(workload, bill)
    options = [check(workload, bill, config) for check in CHECKS]
    applicable = [o["name"] for o in options if o["applicable"] == "适用"]
    order = [o["name"] for o in options]  # 13.6's order is the list order
    return {
        "workload": workload.get("identity", {}).get("name", "unnamed"),
        "model": config.get("name", "unnamed"),
        "options": options,
        "try_in_this_order": order,
        "applicable_count": len(applicable),
        "discipline": (
            f"当前有 {len(applicable)} 条标为适用（{'、'.join(applicable) or '无'}）。"
            "**一次只试一条**，每次按第 7 章的协议同流量重跑，"
            "并和 Baseline 的可识别线对比（13.6、14.2）"
        ),
        "disclaimer": "脚本不替你做决定，它只把判断依据摆出来",
    }


def print_summary(doc: dict) -> None:
    print(f"负载 {doc['workload']}  模型 {doc['model']}")
    for o in doc["options"]:
        print(f"\n[{o['applicable']}] {o['name']}   改善 {o['improves_whose_metric']}")
        print(f"  依据    {o['reason']}")
        print(f"  预期    {o['expected']}")
        print(f"  代价    {o['cost']}")
        print(f"  前提    {o['prerequisite']}")
        print(f"  风险    {o['risk']}")
        for w in o["warnings"]:
            print(f"  WARNING {w}")
    print(f"\n纪律    {doc['discipline']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", type=Path, required=True,
                        help="第 6 章 workload_builder.py 的产物")
    parser.add_argument("--context-cost", type=Path, required=True,
                        help="第 12 章 context_cost.py 的产物")
    parser.add_argument("--model-config", type=Path, required=True,
                        help="第 11 章那份共享配置")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        config = load_config(json.loads(args.model_config.read_text(encoding="utf-8")))
        workload = json.loads(args.workload.read_text(encoding="utf-8"))
        bill = json.loads(args.context_cost.read_text(encoding="utf-8"))
        doc = build_options(workload, bill, config)
    except (CheckError, ModelError) as exc:
        print(f"REJECTED: {exc}")
        return 1

    print_summary(doc)
    if args.output is not None:
        args.output.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
