#!/usr/bin/env python3
"""Check a Decode optimization report the way Chapter 14 checks a Prefill one,
plus the three things that are specific to Decode.

Chapter 14 built the seven blocks and the four verdicts; this script imports
them rather than restating them, and adds:

  scorecard    five dimensions (latency / throughput / capacity / acceptance /
               quality). The first three are never optional: a Decode report
               without all three cannot support a conclusion, because no手段 in
               this part moves only one of them (19.1).
  sweep        the batch sweep with a Goodput curve, and the peak batch. The
               TPS peak and the Goodput peak are not in the same place, and the
               script reports both so the gap is visible (19.3).
  interaction  the check against already-enabled items (19.5).

Three hard checks, in the order 19.6 lists them:

  1. latency / throughput / capacity must all be present.
  2. A precision change requires a quality number AND a floor recorded before
     the run. This is the most important gate in the chapter: a report with a
     beautiful TPOT and no quality data should not be accepted.
  3. A speculative-decoding change requires results at two batch sizes, because
     the benefit reverses at high batch (18.3).

And one rule the scorecard enforces that no single check can: quality is a veto,
not a vote. Four dimensions improving does not outrank one breach (19.7).

The report builder and checker need no service; they run against the synthetic
sample in the repository. Collecting the numbers needs a real vLLM service.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch14"))
sys.path.insert(0, str(HERE.parent / "ch15"))

# Chapter 14 owns the shared experiment discipline; importing it is how the two
# chapters stay on one definition of "可识别线" and of the four verdicts.
from prefill_experiment import (  # noqa: E402
    INDISTINGUISHABLE,
    VERDICTS,
    coefficient_of_variation,
    detectable_difference,
)

# 第 15 章拥有单步耗时模型。扫描表的 TPS 从它生成，也由它校验，两章才不会各说各的。
import decode_model as dm  # noqa: E402

SCORECARD_DIMENSIONS = ("latency", "throughput", "capacity", "acceptance",
                        "quality")
# 19.1: the three that are never optional.
REQUIRED_DIMENSIONS = ("latency", "throughput", "capacity")

# 19.6: what counts as touching precision, and as enabling speculation.
PRECISION_KEYS = ("kv_dtype", "weight_dtype", "quantization", "kv_cache_dtype")
SPEC_KEYS = ("speculative_decoding", "spec_decoding", "draft_model",
             "num_speculative_tokens")

LATENCY_FIELDS = ("tpot_mean_ms", "itl_p95_ms", "itl_max_ms")

# 19.3: the SLO's overall requirement. A configuration is feasible only if at
# least this share of requests is good; Goodput is compared inside that set.
REQUIRED_ATTAINMENT = 0.95
# 19.3: how a batch sweep may be run. Sweeping the batch cap under one fixed
# open-loop rate is the trap: every cap below what Little's Law requires piles
# up a queue, ITL looks fine and TTFT explodes.
SWEEP_DESIGNS = ("closed_loop_fixed_concurrency", "fixed_cap_sweep_rate")


class ExperimentError(ValueError):
    """Raised when a Decode report could not support a conclusion."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentError(message)


def goodput(tps: float, slo_attainment: float) -> float:
    """19.3: throughput that actually met the SLO. `slo_attainment` is the
    fraction of requests inside the threshold, so this is the product.
    """
    _require(tps >= 0, "TPS cannot be negative")
    _require(0 <= slo_attainment <= 1,
             "达标率必须是 0 到 1 之间的比例")
    return tps * slo_attainment


# 19.3 那张扫描表的两个合成参数。
SWEEP_CONTEXT = 845          # Decode 期间的平均上下文：平均 prompt 600 + 输出 490 的一半
SWEEP_PER_REQUEST_MS = 0.08  # 每条请求每步的固定开销：采样、调度、块表维护（15.6）


def sweep_step_ms(config: dict, batch: int, *, context: int = SWEEP_CONTEXT,
                  per_request_ms: float = SWEEP_PER_REQUEST_MS) -> float:
    """19.3 扫描表里一档的单步耗时。

    第 15.3 节那条搬运模型给的是下限，真机取不到。这里在它上面加一项随批量增长
    的固定开销，代表采样、调度和块表维护，`per_request_ms` 是合成设定，自己的
    服务用实测值替换。
    """
    _require(batch >= 1, "batch must be at least 1")
    _require(per_request_ms >= 0, "per-request overhead cannot be negative")
    point = dm.build_point(config, batch, context,
                           bandwidth_gb_per_s=config["bandwidth_gb_per_s"])
    return point["step_estimate_ms"] + per_request_ms * batch


def sweep_from_model(config: dict, batches: list[int],
                     attainment: dict[int, float],
                     itl_p95_ms: dict[int, float], *,
                     context: int = SWEEP_CONTEXT,
                     per_request_ms: float = SWEEP_PER_REQUEST_MS) -> list[dict]:
    """生成 19.3 那张扫描表：TPS 由模型算，达标率和 P95 ITL 是合成设定。

    达标率取决于 SLO 和负载的形状，搬运模型算不出来，所以那两列只能是设定；
    TPS 不是，它由物理决定，所以这里不手填。
    """
    _require(bool(batches), "至少要一个批量档位")
    points = []
    for b in sorted(batches):
        _require(b in attainment and b in itl_p95_ms,
                 f"批量 {b} 缺少达标率或 P95 ITL")
        step = sweep_step_ms(config, b, context=context,
                             per_request_ms=per_request_ms)
        points.append({
            "batch": b,
            "tps": round(b / step * 1000.0),
            "step_ms": round(step, 2),
            "itl_p95_ms": itl_p95_ms[b],
            "slo_attainment": attainment[b],
        })
    return points


def check_sweep_floor(points: list[dict], config: dict, *,
                      context: int = SWEEP_CONTEXT) -> dict:
    """每一档的 TPS 都要在第 15.3 节那条搬运下限之内，P95 ITL 要大于平均单步。

    这是扫描结果的第一道体检，对自己的实测同样适用：批量 B 时每步至少要搬一遍
    权重，所以 TPS 不可能超过 `B ÷ 单步下限`。超了只有两种可能，要么批量不是你
    以为的那个数，要么这一行不是量出来的。
    """
    _require(bool(points), "没有扫描点")
    weight_b = dm.weight_bytes(config["params_total"], config["bytes_per_element"])
    floor_ms = dm.step_floor_ms(weight_b, config["bandwidth_gb_per_s"])
    rows, violations = [], []
    for p in points:
        for field in ("batch", "tps"):
            _require(field in p, f"扫描点缺少 {field}")
        ceiling = p["batch"] / floor_ms * 1000.0
        mean_step = p["batch"] / p["tps"] * 1000.0 if p["tps"] else float("inf")
        row = {
            "batch": p["batch"],
            "tps": p["tps"],
            "tps_ceiling": round(ceiling, 1),
            "mean_step_ms": round(mean_step, 2),
            "headroom": round(p["tps"] / ceiling, 3),
            "ok": p["tps"] <= ceiling,
        }
        itl = p.get("itl_p95_ms")
        if itl is not None:
            row["itl_p95_ms"] = itl
            row["itl_above_mean_step"] = itl >= mean_step
            if not row["itl_above_mean_step"]:
                violations.append(
                    f"批量 {p['batch']}：P95 ITL {itl} ms 小于平均单步 "
                    f"{row['mean_step_ms']} ms，两列不可能同时成立"
                )
        if not row["ok"]:
            violations.append(
                f"批量 {p['batch']}：TPS {p['tps']} 超过搬运下限允许的 "
                f"{row['tps_ceiling']}（每步至少 {floor_ms:.1f} ms）"
            )
        rows.append(row)
    return {
        "step_floor_ms": round(floor_ms, 3),
        "context": context,
        "rows": rows,
        "ok": not violations,
        "violations": violations,
        "reading": ("每一档都在搬运下限之内" if not violations else
                    "有档位违反了第 15.3 节的搬运下限，这张表不是量出来的"),
    }


def analyse_sweep(points: list[dict],
                  required_attainment: float = REQUIRED_ATTAINMENT) -> dict:
    """19.3: filter by the SLO, then take the Goodput peak; report the TPS peak.

    Goodput is a soft score and the SLO is a hard constraint, so "the highest
    Goodput" alone can pick a point that breaks the SLO (19.3's batch-64
    counter-example). The rule is two steps: keep only points whose attainment
    meets the SLO's overall requirement, then maximise Goodput among them.
    Reporting the TPS peak next to the choice is what makes the gap visible.
    """
    _require(len(points) >= 2, "批量扫描至少要两个档位才成一条曲线")
    rows = []
    for p in points:
        for field in ("batch", "tps", "slo_attainment"):
            _require(field in p, f"扫描点缺少 {field}")
        _require(p["batch"] >= 1, "batch must be at least 1")
        rows.append({
            "batch": p["batch"],
            "tps": p["tps"],
            "itl_p95_ms": p.get("itl_p95_ms"),
            "slo_attainment": p["slo_attainment"],
            "goodput": round(goodput(p["tps"], p["slo_attainment"]), 3),
        })
    rows.sort(key=lambda r: r["batch"])

    for r in rows:
        r["feasible"] = r["slo_attainment"] >= required_attainment
    feasible = [r for r in rows if r["feasible"]]
    _require(feasible,
             f"扫描的档位里没有一档的达标率达到 {required_attainment:.0%}："
             "可行集是空的，先降负载或放宽 SLO，再谈选哪一档（19.3）")

    tps_peak = max(rows, key=lambda r: r["tps"])
    good_peak = max(feasible, key=lambda r: r["goodput"])
    unconstrained = max(rows, key=lambda r: r["goodput"])
    same = tps_peak["batch"] == good_peak["batch"]

    reading = (
        f"达标率 ≥ {required_attainment:.0%} 的可行档位是 "
        f"{[r['batch'] for r in feasible]}，其中 Goodput 最大的是批量 "
        f"{good_peak['batch']}（{good_peak['goodput']}）；TPS 峰值在批量 "
        f"{tps_peak['batch']}（{tps_peak['tps']}）。"
    )
    if unconstrained["batch"] != good_peak["batch"]:
        reading += (
            f"不加约束时 Goodput 最大的是批量 {unconstrained['batch']}，"
            "但它的达标率不满足 SLO，不在可行集里。"
        )
    if same:
        reading += (
            "这一次两个峰值重合，说明扫描的档位里还没有越过 SLO 那条线，"
            "应该再往上扫一两档确认"
        )
    else:
        shortfall = 1 - tps_peak["goodput"] / max(good_peak["goodput"], 1e-9)
        gain = tps_peak["tps"] / max(good_peak["tps"], 1e-9) - 1
        reading += (
            f"两者不在一处，按 19.3 这是常态。TPS 峰值那一档名义上高 "
            f"{gain * 100:.0f}%，但有 "
            f"{(1 - tps_peak['slo_attainment']) * 100:.0f}% 的请求超时，"
            f"Goodput 反而低 {shortfall * 100:.0f}%：那点吞吐增量是靠让这些请求"
            "超时换来的"
        )

    return {
        "points": rows,
        "required_attainment": required_attainment,
        "feasible_batches": [r["batch"] for r in feasible],
        "selection_rule": "先用 SLO 的整体要求和质量底线筛出可行集，再在其中取 Goodput 最大（19.3）",
        "peak_batch_by_goodput": good_peak["batch"],
        "peak_batch_by_tps": tps_peak["batch"],
        "peaks_coincide": same,
        "pareto_candidates": [r["batch"] for r in feasible
                              if r["goodput"] >= good_peak["goodput"] * 0.9],
        "pareto_note": (
            "前沿上的候选都留着，别只留最后选中的那一档：SLO 一变最优点就换一个，"
            "而前沿本身不变（19.3）"
        ),
        "reading": reading,
    }


def validate_latency(block: dict) -> None:
    """19.2: three numbers, not one. The third is the one that catches
    preemption, and it is the one most often left out.
    """
    for field in LATENCY_FIELDS:
        _require(field in block and block[field] is not None,
                 f"latency 缺 {field}：19.2 要三个数，平均值会掩盖抖动，"
                 "最大 ITL 才看得出抢占")
    ratio = block["itl_max_ms"] / block["tpot_mean_ms"]
    if ratio > 10:
        block.setdefault("notes", []).append(
            f"最大 ITL 是平均 TPOT 的 {ratio:.0f} 倍，是个孤立的巨大尖峰。"
            "先去查抢占计数，不要当成噪声（19.2）"
        )


def validate_quality(block: dict | None, *, touched_precision: bool) -> None:
    """19.6's middle check, the chapter's most important gate."""
    if not touched_precision:
        return
    _require(
        block is not None and block.get("score") is not None,
        "changed 里动了精度，quality 却是空的。动了精度却没有质量数据的报告，"
        "不该被接受，哪怕 TPOT 数字很漂亮（19.6）",
    )
    assert block is not None
    _require(
        block.get("floor") is not None,
        "quality 缺 floor：底线必须在实验之前写死（17.4），"
        "事后看着结果定标准的评估无法证伪",
    )
    _require(
        block.get("floor_written_at") is not None,
        "quality 缺 floor_written_at：没有写入时间就分不清底线是事前定的"
        "还是事后补的",
    )
    _require(
        block.get("evalset") is not None,
        "quality 缺 evalset：没说用哪个评测集，这个分数不可复现",
    )


def score_quality(block: dict | None) -> dict | None:
    """Quality is a veto. Below the floor is a failure, whatever else improved."""
    if block is None or block.get("score") is None:
        return None
    drop = block.get("drop")
    if drop is None and block.get("baseline_score") is not None:
        drop = block["baseline_score"] - block["score"]
    floor = block.get("floor")
    breached = drop is not None and floor is not None and drop > floor
    per_kind = block.get("per_kind") or {}
    kind_breaches = [k for k, v in per_kind.items()
                     if floor is not None and v.get("drop", 0) > floor]
    return {
        "score": block["score"],
        "drop": None if drop is None else round(drop, 4),
        "floor": floor,
        "evalset": block.get("evalset"),
        "floor_written_at": block.get("floor_written_at"),
        "breached": bool(breached or kind_breaches),
        "breached_kinds": kind_breaches,
        "is_veto": True,
        "reading": (
            "质量是否决项，不是投票项：越过底线就是失败，哪怕另外四项全部改善"
            "（19.7 误区一）"
        ),
    }


def validate_scorecard(scorecard: dict, *, touched_precision: bool,
                       touched_spec: bool) -> None:
    unknown = set(scorecard) - set(SCORECARD_DIMENSIONS)
    _require(not unknown, f"记分卡出现未定义的维度：{sorted(unknown)}")
    for dim in REQUIRED_DIMENSIONS:
        _require(
            scorecard.get(dim),
            f"记分卡缺 {dim}：latency、throughput、capacity 三项每次都要看，"
            "缺一项拒绝出报告（19.1）",
        )
    validate_latency(scorecard["latency"])
    for field in ("tps", "concurrency"):
        _require(field in scorecard["throughput"],
                 f"throughput 缺 {field}")
    for field in ("memory_gib", "preemptions"):
        _require(field in scorecard["capacity"],
                 f"capacity 缺 {field}：抢占计数接近否决项，"
                 "它意味着系统在不稳定区运行（19.7 误区一）")
    validate_quality(scorecard.get("quality"),
                     touched_precision=touched_precision)
    if touched_spec:
        acceptance = scorecard.get("acceptance")
        _require(
            acceptance is not None and acceptance.get("mean_accepted") is not None,
            "changed 里开了投机解码，acceptance 却是空的：平均接受长度是这项技术"
            "唯一的决定因素（18.7）",
        )
        assert acceptance is not None
        # 两个批量档位要的是收益比，不是接受数：接受数由草稿和目标在这批内容上的
        # 一致程度决定，与批量无关；批量影响的是分母那个「验证近乎免费」（18.3）。
        batches = acceptance.get("gain_by_batch") or {}
        _require(
            len(batches) >= 2,
            "changed 里开了投机解码，acceptance.gain_by_batch 要给两个批量档位的收益："
            "它在高批量下会反向，只在低批量下测会得出过于乐观的结论（19.6）",
        )


def classify_change(changed: dict) -> dict:
    _require(isinstance(changed, dict) and changed,
             "changed 不能为空")
    _require(len(changed) == 1,
             f"changed 有 {len(changed)} 项：一次只改一项，"
             "同时改两项结果好了也不知道是谁的功劳（第 14 章）")
    key = next(iter(changed))
    lowered = key.lower()
    return {
        "key": key,
        "value": changed[key],
        "touched_precision": any(p in lowered for p in PRECISION_KEYS),
        "touched_spec": any(s in lowered for s in SPEC_KEYS),
    }


DIRECTIONS = ("lower_is_better", "higher_is_better")


def judge_round(*, baseline: list[float], variant: list[float],
                expected_pct: float, quality: dict | None,
                direction: str = "lower_is_better") -> dict:
    """Chapter 14's four verdicts, with quality able to override all of them.

    Chapter 14 only ever judged TTFT, where lower is better. Decode has metrics
    in both directions in the same report: TPOT down is good, concurrency up is
    good. So the direction is explicit here rather than assumed, and a report
    that forgets to state it for a capacity metric would otherwise read every
    improvement as a regression.
    """
    _require(direction in DIRECTIONS,
             f"direction 必须是 {DIRECTIONS} 之一，容量类指标越大越好，"
             "不写清楚会把改善读成劣化")
    _require(len(baseline) >= 3 and len(variant) >= 3,
             "每轮至少三轮数据才能谈波动（7.3）")
    # Means, not medians: the CV and the line are built on means (7.3), and
    # the two-step reading is Chapter 14's (14.5).
    base = statistics.fmean(baseline)
    var = statistics.fmean(variant)
    _require(base > 0, "Baseline 均值必须为正")
    observed = ((base - var) / base if direction == "lower_is_better"
                else (var - base) / base)
    line = detectable_difference(baseline)
    gap = observed - expected_pct

    if abs(observed) < line:
        label = INDISTINGUISHABLE
        reading = (
            f"改善 {observed * 100:.1f}% 小于可识别线 {line * 100:.1f}%，"
            "当前精度区分不出来"
        )
    elif abs(gap) < line:
        label = "符合预期"
        reading = (f"改善 {observed * 100:.1f}%，预期 {expected_pct * 100:.1f}%，"
                   f"相差在可识别线 {line * 100:.1f}% 以内")
    elif gap > 0:
        label = "高于预期"
        reading = (f"改善 {observed * 100:.1f}%，比预期的 {expected_pct * 100:.1f}% "
                   "高出可识别线以上，高于预期同样要找原因")
    else:
        label = "低于预期"
        reading = (
            f"改善 {observed * 100:.1f}%，低于预期的 {expected_pct * 100:.1f}%。"
            "按 14.5 的顺序排查：先查变量泄漏，再查前提条件，最后才怀疑预期"
        )

    failed_by_quality = bool(quality and quality["breached"])
    if failed_by_quality:
        detail = (f"，越界的维度是 {', '.join(quality['breached_kinds'])}"
                  if quality and quality["breached_kinds"] else "")
        reading += (
            f"。但质量越过了底线{detail}，所以这一轮判失败："
            "主指标改善了不等于这一轮成功（19.7 误区一）"
        )

    return {
        "label": label,
        "passed": not failed_by_quality,
        "failed_by": "quality" if failed_by_quality else None,
        "direction": direction,
        "baseline_mean": round(base, 2),
        "variant_mean": round(var, 2),
        "observed_pct": round(observed, 4),
        "expected_pct": round(expected_pct, 4),
        "gap_pct": round(gap, 4),
        "detectable_difference": round(line, 4),
        "coefficient_of_variation": round(coefficient_of_variation(baseline), 4),
        "reading": reading,
    }


def check_interaction(interaction: dict | None, *, enabled: list[str]) -> dict:
    """19.5: a round stacked on top of earlier rounds must say what it stacked
    on, and whether the combined change was re-measured.
    """
    if not enabled:
        return {
            "already_enabled": [],
            "reading": "这是第一项改动，没有叠加对象",
        }
    _require(
        interaction is not None,
        f"这一轮叠加在 {', '.join(enabled)} 之上，interaction 不能为空："
        "一次只叠加一项，每叠一项就重测全部五个维度（19.5）",
    )
    assert interaction is not None
    _require(
        interaction.get("remeasured_all_dimensions") is True,
        "interaction.remeasured_all_dimensions 不为 true：叠加之后没有重测"
        "全部五个维度，就判断不出有没有抵消（19.5）",
    )
    missing = [item for item in enabled
               if item not in (interaction.get("stacked_on") or [])]
    _require(not missing,
             f"interaction.stacked_on 没列出 {missing}，叠加对象要写全")
    return {
        "already_enabled": enabled,
        "stacked_on": interaction["stacked_on"],
        "net_change": interaction.get("net_change"),
        "cancelled": interaction.get("cancelled", False),
        "reading": interaction.get("note",
                                   "叠加后已重测全部五个维度，未发现抵消"),
    }


def check_report(doc: dict, *, enabled_before: list[str] | None = None) -> dict:
    _require(isinstance(doc, dict), "报告必须是一个对象")
    for block in ("expectation", "fixed", "changed", "scorecard", "boundary"):
        _require(block in doc, f"报告缺 {block} 块")
    # 有对照数据就必须写下结论；只做扫描的那一轮没有对照，不强求一个假结论。
    has_results = bool((doc.get("results") or {}).get("baseline"))
    _require(
        not has_results or "verdict" in doc,
        "报告有 results 却没有 verdict：有了对照数据就要写下结论，"
        "检查器会拿它和数据对一遍",
    )
    _require(
        has_results or doc.get("sweep") or "verdict" in doc,
        "报告既没有 results 也没有 sweep：这一轮什么都没测",
    )
    change = classify_change(doc["changed"])
    validate_scorecard(doc["scorecard"],
                       touched_precision=change["touched_precision"],
                       touched_spec=change["touched_spec"])
    quality = score_quality(doc["scorecard"].get("quality"))

    sweep = None
    if doc.get("sweep"):
        design = doc["sweep"].get("design")
        _require(design in SWEEP_DESIGNS,
                 f"sweep.design 必须是 {SWEEP_DESIGNS} 之一：用一个固定的开环到达率去扫"
                 "批量上限，装不下的档位会一直排队，ITL 好看而 TTFT 失控（19.3）")
        sweep = analyse_sweep(doc["sweep"]["points"])

    claimed = doc.get("verdict") or {}
    if has_results:
        _require(claimed.get("label"),
                 "verdict 缺 label：报告要写下它自己的结论，检查器才能核对")
        _require(claimed["label"] in VERDICTS,
                 f"verdict.label 必须是四种之一：{VERDICTS}")
    elif claimed.get("label"):
        _require(claimed["label"] in VERDICTS,
                 f"这一轮没有对照数据，却写了一个结论标签。要么去掉它，"
                 f"要么它必须是四种之一：{VERDICTS}")
    if claimed.get("label") == INDISTINGUISHABLE:
        prose = json.dumps(claimed, ensure_ascii=False)
        for phrase in ("小幅有效", "略有改善", "小幅提升", "有一定改善"):
            _require(phrase not in prose,
                     f"verdict 标了“{INDISTINGUISHABLE}”却又写着“{phrase}”："
                     "那是在用噪声支撑结论（第 14 章）")

    results = doc.get("results") or {}
    verdict = None
    if results.get("baseline") and results.get("variant"):
        expected = (doc["expectation"].get("magnitude", {})
                    .get(results.get("primary_metric", ""), {})
                    .get("expected_pct"))
        _require(expected is not None,
                 f"expectation.magnitude 里没有 {results.get('primary_metric')}"
                 " 这一项，无法与预期对照")
        verdict = judge_round(baseline=results["baseline"],
                              variant=results["variant"],
                              expected_pct=expected, quality=quality,
                              direction=results.get("direction",
                                                    "lower_is_better"))
        _require(
            verdict["label"] == claimed["label"],
            f"报告自己写的结论是“{claimed['label']}”，但按它自己的数据算出来是"
            f"“{verdict['label']}”。结论要从数据里出来，不是写上去的",
        )
        if claimed.get("passed") is not None:
            _require(
                bool(claimed["passed"]) == verdict["passed"],
                f"报告写 passed={claimed['passed']}，但记分卡算出来是 "
                f"{verdict['passed']}"
                + ("：质量越过底线就是失败，哪怕主指标符合预期（19.7 误区一）"
                   if not verdict["passed"] else ""),
            )
        verdict["claimed"] = claimed
        # 一轮实验可以成立而这项改动仍然不留。19.4 第 3 轮就是这种：结论有效，
        # 收益不值得付出的容量代价。所以“保留”是一个独立的字段，不是 passed
        # 的同义词，否则后面几轮会算错自己叠加在什么之上。
        verdict["kept"] = bool(claimed.get("kept", verdict["passed"]))
        if verdict["kept"]:
            _require(verdict["passed"],
                     "这一轮判失败却写着保留：失败的改动不该留在配置里")

    interaction = check_interaction(doc.get("interaction"),
                                   enabled=enabled_before or [])

    return {
        "round": doc.get("round"),
        "changed": change,
        "scorecard": doc["scorecard"],
        "quality": quality,
        "sweep": sweep,
        "verdict": verdict,
        "interaction": interaction,
        "boundary": doc["boundary"],
    }


def check_series(doc: dict) -> dict:
    """A five-round series: each round checked, and the enabled set carried
    forward so round N knows what it is stacked on.
    """
    _require("rounds" in doc and isinstance(doc["rounds"], list),
             "系列报告缺 rounds 列表")
    _require(doc.get("synthetic") is not True or "_note" in doc,
             "合成数据必须在 _note 里写明它是合成的")
    enabled: list[str] = []
    checked = []
    for raw in doc["rounds"]:
        result = check_report(raw, enabled_before=list(enabled))
        checked.append(result)
        kept = (result["verdict"] is None or result["verdict"]["kept"])
        if kept and raw["changed"] and raw.get("round") != 0:
            enabled.append(result["changed"]["key"])
    labels = [c["verdict"]["label"] for c in checked if c["verdict"]]
    failures = [c["round"] for c in checked
                if c["verdict"] and not c["verdict"]["passed"]]
    dropped = [c["round"] for c in checked
               if c["verdict"] and c["verdict"]["passed"]
               and not c["verdict"]["kept"]]
    return {
        "name": doc.get("name"),
        "synthetic": bool(doc.get("synthetic")),
        "rounds": checked,
        "verdict_labels": labels,
        "rounds_failed": failures,
        "rounds_valid_but_not_kept": dropped,
        "enabled_at_end": enabled,
    }


def print_summary(result: dict) -> None:
    if "rounds" in result and isinstance(result.get("rounds"), list):
        print(f"系列      {result['name']}"
              + ("（合成数据）" if result["synthetic"] else ""))
        for r in result["rounds"]:
            mark = "" if r["verdict"] is None else (
                "  通过" if r["verdict"]["passed"] else "  失败")
            label = "—" if r["verdict"] is None else r["verdict"]["label"]
            print(f"  第 {r['round']} 轮  {r['changed']['key']}"
                  f" = {r['changed']['value']}  {label}{mark}")
            if r["verdict"]:
                print(f"            {r['verdict']['reading']}")
            if r["sweep"]:
                print(f"            {r['sweep']['reading']}")
            if r["quality"] and r["quality"]["breached"]:
                print(f"            质量越界：{r['quality']['breached_kinds']}")
        print(f"结论分布  {result['verdict_labels']}")
        print(f"失败轮次  {result['rounds_failed'] or '无'}")
        print(f"成立但不留 {result['rounds_valid_but_not_kept'] or '无'}")
        print(f"最终启用  {result['enabled_at_end'] or '无'}")
        return
    print(f"改动      {result['changed']['key']} = {result['changed']['value']}")
    if result["verdict"]:
        print(f"结论      {result['verdict']['label']}"
              f"  {'通过' if result['verdict']['passed'] else '失败'}")
        print(f"解读      {result['verdict']['reading']}")
    if result["sweep"]:
        print(f"扫描      {result['sweep']['reading']}")
    print(f"叠加      {result['interaction']['reading']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True,
                        help="一份报告，或一份含 rounds 的系列报告")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        doc = json.loads(args.report.read_text(encoding="utf-8"))
        result = (check_series(doc) if "rounds" in doc
                  else check_report(doc))
    except ExperimentError as exc:
        print(f"REJECTED: {exc}")
        return 1

    print_summary(result)
    if args.output is not None:
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
