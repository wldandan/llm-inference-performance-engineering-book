#!/usr/bin/env python3
"""Decide which profiling layer to use, before spending hours collecting data.

This Demo collects nothing. Its only job is to make you write down what
question you are trying to answer, and to refuse two habits: skipping layers,
and starting from an unfalsifiable symptom.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Ordered outside-in, cheap to expensive. 9.2's table.
LAYERS = ("request", "process", "framework", "device")

LAYER_INFO = {
    "request": {
        "answers": "哪一段耗时，排队、首 token 还是生成",
        "tools": "引擎的请求级指标、日志、Trace",
        "overhead": "极低，可以常开",
        "overhead_pct": 0.0,
    },
    "process": {
        "answers": "CPU 侧有没有卡住，哪个函数占时间，有没有锁阻塞",
        "tools": "采样式 profiler、py-spy 一类",
        "overhead": "个位数百分比",
        "overhead_pct": 5.0,
    },
    "framework": {
        "answers": "调度是否高效，批次怎么形成，有没有抢占",
        "tools": "框架自带 profiler、engine trace",
        "overhead": "中等，可能影响调度时序",
        "overhead_pct": 15.0,
    },
    "device": {
        "answers": "kernel 执行、空隙、显存带宽、通信",
        "tools": "GPU timeline、kernel profiler",
        "overhead": "显著，常需要序列化 GPU 执行，延迟可能翻倍",
        "overhead_pct": 100.0,
    },
}

# How numbers collected at each layer may be compared with a Baseline that
# was measured without collection (9.5). The first item is the strict answer
# to "can I compare directly"; the second says what to do instead.
COMPARISON_RULE = {
    "request": ("yes", "开销可以忽略，可以直接和未采集的 Baseline 比"),
    "process": ("same_conditions_only", "改前改后都开着同样的采样，或先测出开销再扣掉，才能比延迟"),
    "framework": ("same_conditions_only", "延迟数字只在两边采集条件相同时可比，调度结论仍然可用"),
    "device": ("never", "已经是另一个系统，延迟数字不要和任何 Baseline 比，只用相对结论"),
}

# Evidence names a user can claim to already have, mapped to the layer it covers.
EVIDENCE_LAYER = {
    "request_metrics": "request",
    "trace": "request",
    "logs": "request",
    "cpu_profile": "process",
    "engine_trace": "framework",
    "kernel_profile": "device",
}

# Symptom keyword -> the layer that can actually answer it.
SYMPTOM_ROUTES = (
    (("queue", "排队", "队列"), "request"),
    (("cpu", "gil", "序列化", "tokenize", "预处理"), "process"),
    (("batch", "批次", "调度", "抢占", "preempt"), "framework"),
    (("kernel", "显存带宽", "bandwidth", "sm ", "空隙", "gap"), "device"),
    (("ttft", "tpot", "itl", "吞吐", "利用率"), "framework"),
)

VAGUE = ("服务慢", "很慢", "性能差", "不稳定", "slow", "bad performance")


class PlannerError(ValueError):
    """Raised when a plan cannot be produced from the given inputs."""


def _normalize(evidence: list[str]) -> list[str]:
    unknown = [e for e in evidence if e not in EVIDENCE_LAYER]
    if unknown:
        raise PlannerError(
            f"unknown evidence {unknown}; known kinds: {sorted(EVIDENCE_LAYER)}"
        )
    return list(dict.fromkeys(evidence))


def is_falsifiable(symptom: str) -> bool:
    """A symptom is workable when it carries a quantity or a named segment.

    "服务慢" carries neither, so no layer can answer it (9.1, 10.1).
    """
    text = symptom.strip().lower()
    if not text:
        return False
    if any(v in text for v in VAGUE) and not any(ch.isdigit() for ch in text):
        return False
    has_number = any(ch.isdigit() for ch in text)
    has_named_segment = any(
        kw in text for kws, _ in SYMPTOM_ROUTES for kw in kws
    )
    return has_number or has_named_segment


def route_symptom(symptom: str) -> str:
    text = symptom.strip().lower()
    for keywords, layer in SYMPTOM_ROUTES:
        if any(kw in text for kw in keywords):
            return layer
    return "request"


def plan(symptom: str, evidence_have: list[str], *, want_layer: str | None = None) -> dict:
    evidence = _normalize(evidence_have)
    warnings: list[str] = []

    if not is_falsifiable(symptom):
        warnings.append(
            "目标不清：现象描述里没有量值，也没有指明哪一段。先按 10.1 补上"
            "量值、范围、时间和对照，再决定采哪一层。"
        )

    covered = {EVIDENCE_LAYER[e] for e in evidence}
    target = want_layer or route_symptom(symptom)
    if target not in LAYERS:
        raise PlannerError(f"want_layer must be one of {LAYERS}, got {target!r}")

    # The next layer to collect is the shallowest one not already covered.
    next_layer = target
    for layer in LAYERS:
        if layer not in covered:
            next_layer = layer
            break
    else:
        next_layer = target

    target_idx = LAYERS.index(target)
    if target_idx > 0 and "request" not in covered:
        warnings.append(
            "跳级：请求级证据还没看就要往下采。上一层能解释清楚的现象不需要"
            "下一层的数据，而请求级几乎不花钱（9.2）。"
        )
        next_layer = "request"

    info = LAYER_INFO[next_layer]
    rationale_parts = []
    if covered:
        rationale_parts.append(f"已有 {sorted(covered)} 层证据")
    else:
        rationale_parts.append("目前没有任何层的证据")
    rationale_parts.append(f"现象指向 {target} 层")
    rationale_parts.append(f"所以下一步采 {next_layer} 层")

    return {
        "symptom": symptom,
        "already_known": {
            "evidence": evidence,
            "layers_covered": sorted(covered),
            "ruled_out": (
                "请求级已覆盖，可以排除“完全不知道时间去向”这一类解释"
                if "request" in covered else "尚未排除任何解释"
            ),
        },
        "next_layer": next_layer,
        "rationale": "；".join(rationale_parts) + f"。这一层回答：{info['answers']}",
        "expected_cost": {
            "tools": info["tools"],
            "overhead": info["overhead"],
            "overhead_pct": info["overhead_pct"],
            # Overhead is a fixed bias, not random noise: it does not average
            # out over runs, so it is never compared with the 7.3 line (9.5).
            "comparable_to_baseline": COMPARISON_RULE[next_layer][0],
            "comparison_rule": COMPARISON_RULE[next_layer][1],
            "note": (
                "采集开销是每一轮都有的固定偏差，不是随机波动，不能拿它和第 7.3 节的可识别线比大小；"
                "要么改前改后用同样的采集条件，要么先测出开销再扣掉（9.5）。"
            ),
        },
        "window": {
            "how_to_locate": "先用请求级记录找出慢请求集中的时间段，再在那个时间段重开采集",
            "trigger": "可复现负载触发优先；偶发现象用阈值自动触发",
            "must_overlap": "采集窗口必须覆盖现象发生的时刻，位置比长度重要（9.6）",
        },
        "must_record": [
            "采集起止时刻",
            "覆盖的请求数",
            "期间是否有其他流量",
            "采样率",
            "采集开销的实测值",
            "是否强制了 GPU 同步",
        ],
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symptom", required=True)
    parser.add_argument("--evidence-have", nargs="*", default=[])
    parser.add_argument("--want-layer", default=None, choices=list(LAYERS))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        result = plan(args.symptom, args.evidence_have, want_layer=args.want_layer)
    except PlannerError as exc:
        print(f"REJECTED: {exc}")
        return 1

    for warning in result["warnings"]:
        print(f"WARNING: {warning}")

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
