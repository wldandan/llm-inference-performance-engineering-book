#!/usr/bin/env python3
"""Turn a prompt into an itemised bill: what each segment costs and who chose it.

12.1's point is that the person who raises Top-K never sees this bill. This
Demo is that bill. It answers three questions: how many tokens does each
segment cost, how much of the prompt is the same on every call (which is the
ceiling for Chapter 13's Prefix Cache), and what does one more notch of Top-K
cost.

It does **not** evaluate answer quality. The cost side is computable; the
quality side needs your own evaluation set. Both are required before you can
draw 12.4's curve, so the script refuses a spec that tries to assert quality.

Only the Python standard library. No GPU.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ch11"))
from prefill_model import (  # noqa: E402
    ModelError,
    crossover_tokens,
    load_config,
    relative_cost,
)

# Who decides this segment's length. 12.2: the distinction matters because
# controllability differs completely.
SOURCES = ("fixed", "retrieval", "history", "user")
CACHEABLE_SOURCES = ("fixed",)
VARIABLE_SOURCES = ("retrieval", "history", "user")

# Fields that would make this a performance report rather than a cost sheet.
FORBIDDEN_FIELDS = (
    "quality",
    "quality_score",
    "accuracy",
    "recall",
    "ttft_ms",
    "results",
)


class SpecError(ValueError):
    """Raised when a prompt spec is not something a bill can be built from."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message)


def _segment_tokens(segment: dict, index: int) -> int:
    has_flat = "tokens" in segment
    has_per_item = "tokens_per_item" in segment
    _require(
        has_flat != has_per_item,
        f"segments[{index}] 必须给 tokens 或 tokens_per_item 之一，不能都给也不能都不给",
    )
    if has_flat:
        value = segment["tokens"]
        _require(
            isinstance(value, int) and value > 0,
            f"segments[{index}].tokens 必须是正整数",
        )
        return value
    per_item = segment["tokens_per_item"]
    items = segment.get("items")
    _require(
        isinstance(per_item, int) and per_item > 0,
        f"segments[{index}].tokens_per_item 必须是正整数",
    )
    _require(
        isinstance(items, int) and items >= 0,
        f"segments[{index}] 用了 tokens_per_item 就必须给 items（12.2：取几段是代码里的常数）",
    )
    return per_item * items


def validate_spec(doc: object) -> None:
    _require(isinstance(doc, dict), "prompt spec must be an object")
    assert isinstance(doc, dict)
    for field in FORBIDDEN_FIELDS:
        _require(
            field not in doc,
            f"prompt spec 里不该有 {field}：这份文件只算成本，质量要靠你自己的评测集（12.6）",
        )
    segments = doc.get("segments")
    _require(
        isinstance(segments, list) and segments,
        "segments 必须是非空列表",
    )
    seen = set()
    for i, segment in enumerate(segments):
        _require(isinstance(segment, dict), f"segments[{i}] must be an object")
        name = segment.get("name")
        _require(
            isinstance(name, str) and name.strip() != "",
            f"segments[{i}].name is required",
        )
        _require(name not in seen, f"segment 名字重复：{name}")
        seen.add(name)
        source = segment.get("source")
        _require(
            source in SOURCES,
            f"segments[{i}].source 必须是 {SOURCES} 之一，现在是 {source!r}",
        )
        for field in FORBIDDEN_FIELDS:
            _require(
                field not in segment,
                f"segments[{i}] 里不该有 {field}（12.6）",
            )
        _segment_tokens(segment, i)

    baseline = doc.get("baseline")
    if baseline is not None:
        _require(isinstance(baseline, dict), "baseline must be an object")
        for field in ("tokens", "ttft_ms"):
            value = baseline.get(field)
            _require(
                isinstance(value, (int, float)) and value > 0,
                f"baseline.{field} 必须是正数：标定 TTFT 需要一个实测锚点",
            )


def cacheable_prefix_tokens(segments: list[dict]) -> tuple[int, list[str]]:
    """Tokens in the leading run of fixed segments, plus any misordering found.

    Prefix Cache matches from the first token, so a fixed segment sitting
    behind a variable one can never be hit (13.3). Reporting the prefix rather
    than the total of all fixed segments is the difference between the ceiling
    you can actually reach and the one you wish you had.
    """
    prefix = 0
    warnings = []
    seen_variable = False
    for i, segment in enumerate(segments):
        tokens = _segment_tokens(segment, i)
        if segment["source"] in CACHEABLE_SOURCES:
            if seen_variable:
                warnings.append(
                    f"固定段“{segment['name']}”排在变化内容后面，前缀匹配永远到不了它。"
                    f"把它移到最前面（13.3）"
                )
            else:
                prefix += tokens
        else:
            seen_variable = True
    return prefix, warnings


def prefix_cache_saving(config: dict, total: int, prefix: int) -> float:
    """Share of Prefill compute a fully hit prefix removes.

    Lower than the prefix's share of tokens, because the cached positions are
    the cheapest ones: early positions attend to fewer positions than late
    ones (13.3).
    """
    if prefix <= 0 or total <= 0:
        return 0.0
    prefix = min(prefix, total)
    crossover = crossover_tokens(config)
    remaining = total - prefix
    # GEMM for the positions still computed, plus their causal attention pairs.
    pairs = (prefix + 1 + total) * remaining // 2
    partial = crossover * remaining + 2 * pairs
    return 1.0 - partial / relative_cost(config, total)


def _ttft_ms(config: dict, tokens: int, baseline: dict | None) -> float | None:
    if baseline is None:
        return None
    scale = baseline["ttft_ms"] / relative_cost(config, int(baseline["tokens"]))
    return relative_cost(config, tokens) * scale


def build_bill(doc: dict, config: dict) -> dict:
    validate_spec(doc)
    segments: list[dict] = doc["segments"]
    baseline = doc.get("baseline")

    rows = []
    total = 0
    for i, segment in enumerate(segments):
        tokens = _segment_tokens(segment, i)
        total += tokens
        rows.append(
            {
                "name": segment["name"],
                "source": segment["source"],
                "tokens": tokens,
                "items": segment.get("items"),
                "tokens_per_item": segment.get("tokens_per_item"),
                "repeats_every_call": segment["source"] in CACHEABLE_SOURCES,
                "decided_by": {
                    "fixed": "应用层，写在代码或配置里",
                    "retrieval": "应用层，由 Top-K 和片段长度决定",
                    "history": "应用层，由保留几轮决定",
                    "user": "用户输入",
                }[segment["source"]],
            }
        )
    _require(total > 0, "prompt 总长度为 0，没有账可算")
    for row in rows:
        row["share"] = round(row["tokens"] / total, 4)

    prefix, warnings = cacheable_prefix_tokens(segments)
    saving = prefix_cache_saving(config, total, prefix)

    pricing = doc.get("pricing") or {}
    input_per_1k = pricing.get("input_per_1k")
    input_cost = (
        round(total / 1000 * input_per_1k, 6)
        if isinstance(input_per_1k, (int, float))
        else None
    )

    ttft = _ttft_ms(config, total, baseline)
    totals = {
        "input_tokens": total,
        "relative_cost": relative_cost(config, total),
        "crossover_tokens": crossover_tokens(config),
        "estimated_ttft_ms": None if ttft is None else round(ttft, 1),
        "ttft_basis": (
            "由 baseline 那个实测锚点按第 11 章的模型标定"
            if baseline
            else "未提供 baseline，只给相对计算量。没有锚点就不编绝对毫秒数"
        ),
        "input_cost": input_cost,
        "output_tokens_note": "输入变长不会让输出变长，输出那笔账不在这里（12.3）",
    }

    cacheable = {
        "prefix_tokens": prefix,
        "prefix_share_of_tokens": round(prefix / total, 4),
        "prefill_saving_if_fully_hit": round(saving, 4),
        "note": (
            "占比是 token 占比，省下的计算比它低，因为被缓存的是最便宜的前缀（13.3）"
        ),
        # 三成是个粗线：真正该比的是「全命中省下的份额 × 请求命中的概率」和
        # Baseline 的可识别线（13.6）。这里只给出前一项，命中概率要按部署算。
        "verdict": (
            "全命中能省 {:.0%} 的 Prefill 计算；乘上你那套部署的请求命中概率，"
            "高过 Baseline 的可识别线才值得走这条路（13.3、13.6）"
        ).format(saving),
    }

    return {
        "name": doc.get("name", "unnamed"),
        "model": config.get("name", "unnamed"),
        "segments": rows,
        "totals": totals,
        "cacheable": cacheable,
        "sensitivity": sensitivity(doc, config),
        "warnings": warnings,
        "disclaimer": (
            "这份账单只算成本，不评估质量。两边都有才能画出 12.4 那条曲线"
        ),
    }


def _retrieval_index(segments: list[dict]) -> int | None:
    for i, segment in enumerate(segments):
        if segment["source"] == "retrieval" and "tokens_per_item" in segment:
            return i
    return None


def sensitivity(doc: dict, config: dict) -> dict:
    """What one more notch of Top-K costs, for the person about to change it."""
    segments: list[dict] = doc["segments"]
    index = _retrieval_index(segments)
    if index is None:
        return {
            "available": False,
            "reason": "没有按 tokens_per_item 描述的检索段，无法算 Top-K 的敏感度",
        }
    segment = segments[index]
    per_item = segment["tokens_per_item"]
    current = segment["items"]
    others = sum(
        _segment_tokens(s, i) for i, s in enumerate(segments) if i != index
    )
    baseline = doc.get("baseline")

    rows = []
    for items in sorted({1, 3, 5, current, current + 1, current * 2, 20}):
        if items < 0:
            continue
        tokens = others + per_item * items
        ttft = _ttft_ms(config, tokens, baseline)
        rows.append(
            {
                "items": items,
                "input_tokens": tokens,
                "estimated_ttft_ms": None if ttft is None else round(ttft, 1),
                "is_current": items == current,
            }
        )

    here = next(r for r in rows if r["is_current"])
    nxt = next((r for r in rows if r["items"] == current + 1), None)
    one_more = None
    if nxt is not None:
        one_more = {
            "extra_input_tokens": nxt["input_tokens"] - here["input_tokens"],
            "extra_ttft_ms": (
                None
                if nxt["estimated_ttft_ms"] is None
                else round(nxt["estimated_ttft_ms"] - here["estimated_ttft_ms"], 1)
            ),
        }

    return {
        "available": True,
        "variable": segment["name"],
        "tokens_per_item": per_item,
        "current_items": current,
        "table": rows,
        "one_more_item": one_more,
        "note": "调 Top-K 之前先看一眼这一档要多花多少，比上线后查投诉便宜（12.6）",
    }


def print_summary(bill: dict) -> None:
    print(f"{bill['name']}  模型 {bill['model']}")
    print(f"{'段':<16}{'来源':<10}{'token':>7}{'占比':>8}  每次重复")
    for row in bill["segments"]:
        print(
            f"{row['name']:<16}{row['source']:<10}{row['tokens']:>7}"
            f"{row['share'] * 100:>7.1f}%  {'是' if row['repeats_every_call'] else '否'}"
        )
    t = bill["totals"]
    print(f"合计 {t['input_tokens']} token", end="")
    if t["estimated_ttft_ms"] is not None:
        print(f"  估算 TTFT {t['estimated_ttft_ms']} ms", end="")
    if t["input_cost"] is not None:
        print(f"  输入成本 {t['input_cost']}", end="")
    print()
    c = bill["cacheable"]
    print(
        f"可缓存前缀 {c['prefix_tokens']} token"
        f"（{c['prefix_share_of_tokens'] * 100:.0f}% 的 token），"
        f"全命中能省 {c['prefill_saving_if_fully_hit'] * 100:.0f}% 的 Prefill 计算"
    )
    print(f"判断     {c['verdict']}")
    s = bill["sensitivity"]
    if s["available"] and s["one_more_item"]:
        o = s["one_more_item"]
        print(
            f"再多取一段：+{o['extra_input_tokens']} token"
            + (f"、+{o['extra_ttft_ms']} ms" if o["extra_ttft_ms"] is not None else "")
        )
    for w in bill["warnings"]:
        print(f"WARNING  {w}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-spec", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True,
                        help="第 11 章那份共享配置")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        config = load_config(json.loads(args.model_config.read_text(encoding="utf-8")))
        doc = json.loads(args.prompt_spec.read_text(encoding="utf-8"))
        bill = build_bill(doc, config)
    except (SpecError, ModelError) as exc:
        print(f"REJECTED: {exc}")
        return 1

    print_summary(bill)
    if args.output is not None:
        args.output.write_text(
            json.dumps(bill, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
