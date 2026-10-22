#!/usr/bin/env python3
"""Break a RAG call into stages, then estimate what changing a knob would buy.

23.1 puts it plainly: the first step of RAG performance work is not optimising,
it is decomposing. This script does the decomposition, and then the one thing
the decomposition makes possible, which is ordering the work before touching
anything.

Three subcommands:

  collect   send queries at a real RAG endpoint and record per-stage timings.
            Needs a live chain.
  analyze   stage shares, critical path, cold-versus-warm, cache status.
            Offline.
  whatif    re-estimate end-to-end under a different final_k, rerank candidate
            count, or with rewrite skipped. Offline.

`whatif` gets its TTFT re-estimate from Chapter 11's cost model rather than from
a linear rule, because the whole point of 23.3 is that the relationship is not
linear: 3000 → 9000 tokens is 3× the tokens and about 3.9× the Prefill. Importing
`code/ch11/prefill_model.py` is how this chapter and that one stay on one model.

Four things this script refuses to do, each from 23.6's Baseline discipline:

  A trace with no knowledge-base version is refused. The knowledge base is part
  of the environment; its size changes the fragment count, which changes the
  prompt length, which changes TTFT.

  A trace that mixes cold and warm queries without labelling them is refused.
  23.2 says the gap is several times over, so the mixed average has no use.

  A trace with no cache state is refused. Three cache layers make "was it on?"
  too easy to get wrong to leave implicit.

  `whatif --parallelize` on a main-chain stage is refused. 23.4 says 改写 →
  检索 → 重排 → 生成 is serial by the structure of RAG, and an estimate that
  parallelises it would be selling time that does not exist.

Only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch11"))

# 第 11 章拥有那个代价模型；引用它而不是重述，是这一章的 TTFT 估算和 11.2 保持
# 同一条式子的唯一办法。
from prefill_model import (  # noqa: E402
    crossover_tokens,
    load_config,
    relative_cost,
)

# 23.7 fixes the stage names.
STAGES = ("rewrite", "embed", "retrieve", "rerank", "assemble", "ttft",
          "generate")

# 23.4: this is the serial main chain, and it is all seven stages — embedding
# waits for the rewritten query, so it is on the chain too. Side branches such
# as multi-route retrieval are not separate stages here: their benefit shows up
# inside ``retrieve``. Nothing on the chain can be parallelised away.
SERIAL_CHAIN = STAGES

# 23.5's three layers, in the order the chapter puts them: 越靠后跳过的链路越长、
# 风险越大。收益不按这个顺序排（23.5）：单次命中检索结果缓存省得最少。
CACHE_LAYERS = ("prefix_cache", "retrieval_cache", "answer_cache")

# 23.6 的负载描述扩展字段。
RETRIEVAL_FIELDS = ("index_size", "top_k", "rerank_candidates", "final_k",
                    "query_repeat_rate")


class TraceError(Exception):
    """A trace that cannot support the reading asked of it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise TraceError(message)


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------

def _validate_trace(trace: dict) -> None:
    kb = trace.get("knowledge_base") or {}
    _require(bool(kb.get("version")) and kb.get("documents") is not None,
             "trace 里没有 knowledge_base 的 version 和 documents："
             "23.6 说知识库版本是环境的一部分，知识库一变片段数就变，"
             "prompt 长度和 TTFT 跟着变，没记版本的 Baseline 不能对比")
    cache = trace.get("cache_status")
    _require(cache is not None,
             "trace 里没有 cache_status：23.6 要求要么全程关掉、"
             "要么全程开着并记录命中率。RAG 有三层缓存，这件事最容易搞错")
    for layer in CACHE_LAYERS:
        _require(layer in cache, f"cache_status 缺 {layer} 这一层")
        block = cache[layer]
        _require("enabled" in block, f"{layer} 没写 enabled")
        if block["enabled"]:
            _require(block.get("hit_rate") is not None,
                     f"{layer} 开着却没记命中率：开着而不记，"
                     "这份 Baseline 之后没法和任何一次重测对比")
    calls = trace.get("calls") or []
    _require(bool(calls), "trace 里没有 calls")
    for i, call in enumerate(calls):
        _require(call.get("temperature") in ("cold", "warm"),
                 f"第 {i} 条调用没标 cold 还是 warm："
                 "23.2 说检索的冷热差几倍，混在一起的平均值没有参考价值")
        for stage in STAGES:
            _require(call.get("stages", {}).get(stage) is not None,
                     f"第 {i} 条调用缺 {stage} 这一段的耗时："
                     "缺任何一段都会让它的时间被算进别人头上")


def _totals(calls: list[dict]) -> list[float]:
    return [sum(c["stages"][s] for s in STAGES) for c in calls]


def analyze(trace: dict) -> dict:
    _validate_trace(trace)
    calls = trace["calls"]
    cold = [c for c in calls if c["temperature"] == "cold"]
    warm = [c for c in calls if c["temperature"] == "warm"]
    _require(bool(cold) and bool(warm),
             "只有冷查询或只有热查询：23.6 要求至少给出两组数据，"
             "否则看不出冷热差多少")

    def stage_means(group: list[dict]) -> dict[str, float]:
        return {s: round(statistics.fmean(c["stages"][s] for c in group), 3)
                for s in STAGES}

    warm_stages = stage_means(warm)
    cold_stages = stage_means(cold)
    warm_total = sum(warm_stages.values())
    cold_total = sum(cold_stages.values())

    # 各段占比按热查询算，因为线上大部分请求是热的；冷热对照单列。
    share = {s: round(warm_stages[s] / warm_total, 4) for s in STAGES}
    ranked = sorted(STAGES, key=lambda s: warm_stages[s], reverse=True)
    critical = [{"stage": s, "ms": warm_stages[s], "share": share[s]}
                for s in ranked[:3]]

    ratios = {s: (round(cold_stages[s] / warm_stages[s], 3)
                  if warm_stages[s] > 0 else None)
              for s in STAGES}
    worst_cold = max((s for s in STAGES if ratios[s] is not None),
                     key=lambda s: ratios[s])

    retrieval = trace.get("retrieval") or {}
    missing = [f for f in RETRIEVAL_FIELDS if retrieval.get(f) is None]

    return {
        "calls": len(calls),
        "knowledge_base": trace["knowledge_base"],
        "stages_warm_ms": warm_stages,
        "stages_cold_ms": cold_stages,
        "stage_share": share,
        "total_warm_ms": round(warm_total, 3),
        "total_cold_ms": round(cold_total, 3),
        "cold_vs_warm": {
            "total_ratio": round(cold_total / warm_total, 3),
            "per_stage_ratio": ratios,
            "worst_stage": worst_cold,
            "reading": (
                f"冷查询总时长是热查询的 {round(cold_total / warm_total, 3)} 倍，"
                f"差距集中在 {worst_cold}（{ratios[worst_cold]} 倍）。"
                "压测时一直用同一批查询测的是热路径，线上真实的冷查询会慢得多。"),
        },
        "context_tokens": trace.get("context_tokens"),
        "cache_status": trace["cache_status"],
        "critical_path": critical,
        "critical_path_note": (
            "这三段在串行主链上，所以它们的耗时是可以逐段相加的。"
            "支线上的等待不在这张表里，按 9.4 那条关键路径判据，"
            "并到别人的等待里去的那一段优化了端到端也不会变快。"),
        "retrieval_fields_missing": missing,
        "generation_share": round(
            (warm_stages["ttft"] + warm_stages["generate"]) / warm_total, 4),
        "before_generation_share": round(
            1 - (warm_stages["ttft"] + warm_stages["generate"]) / warm_total, 4),
    }


# --------------------------------------------------------------------------
# whatif
# --------------------------------------------------------------------------

def ttft_after_context_change(config: dict, baseline_tokens: int,
                              baseline_ttft_ms: float,
                              new_tokens: int) -> float:
    """Scale a measured TTFT by Chapter 11's cost ratio.

    Using `relative_cost` rather than the token count is the whole point of
    23.3: the ratio of Prefill compute is not the ratio of tokens.
    """
    _require(baseline_tokens > 0 and new_tokens > 0,
             "上下文长度必须为正")
    _require(baseline_ttft_ms > 0, "基准 TTFT 必须为正")
    ratio = (relative_cost(config, new_tokens)
             / relative_cost(config, baseline_tokens))
    return baseline_ttft_ms * ratio


def attention_share(config: dict, tokens: int) -> float:
    """S / (crossover + S)：Attention 占 Prefill 计算量的比例。

    23.3 引的那两个数就是这个函数：3000 token 时 15%，9000 token 时 35%。
    """
    _require(tokens > 0, "上下文长度必须为正")
    return tokens / (crossover_tokens(config) + tokens)


def whatif(trace: dict, config: dict, *,
           final_k: int | None = None,
           rerank_candidates: int | None = None,
           skip_rewrite: bool = False,
           skip_rewrite_share: float = 1.0,
           parallelize: list[str] | None = None) -> dict:
    _validate_trace(trace)
    for name in (parallelize or []):
        _require(name not in SERIAL_CHAIN,
                 f"不能把 {name} 并行掉：23.4 说改写、检索、重排、生成这条主链"
                 "是 RAG 的结构决定的严格串行，把它并行掉等于卖一份不存在的时间")

    base = analyze(trace)
    stages = dict(base["stages_warm_ms"])
    retrieval = trace.get("retrieval") or {}
    baseline_tokens = trace.get("context_tokens")
    _require(baseline_tokens is not None,
             "trace 里没有 context_tokens：TTFT 的重估要靠它和第 11 章那个模型")
    composition = trace.get("context_composition") or {}
    fixed = composition.get("fixed_tokens")
    per_chunk = composition.get("tokens_per_chunk")
    changes: list[dict] = []
    new_stages = dict(stages)
    new_tokens = baseline_tokens

    if skip_rewrite:
        _require(0 < skip_rewrite_share <= 1,
                 "跳过改写的请求占比要在 (0, 1] 内")
        saved = stages["rewrite"] * skip_rewrite_share
        new_stages["rewrite"] = round(stages["rewrite"] - saved, 3)
        changes.append({
            "knob": "skip-rewrite",
            "stage": "rewrite",
            "saved_ms": round(saved, 3),
            "why": (f"改写这一段 {stages['rewrite']} ms，"
                    f"其中 {round(skip_rewrite_share * 100)}% 的请求跳过。"
                    "它在串行主链上，所以省下的是净收益"),
        })

    if rerank_candidates is not None:
        old_candidates = retrieval.get("rerank_candidates")
        _require(old_candidates is not None,
                 "retrieval 里没有 rerank_candidates，无法按候选数折算重排耗时")
        _require(rerank_candidates > 0, "重排候选数必须为正")
        # 23.2：重排的耗时和候选数成正比，候选数翻倍耗时翻倍。
        scaled = stages["rerank"] * rerank_candidates / old_candidates
        new_stages["rerank"] = round(scaled, 3)
        changes.append({
            "knob": "rerank-candidates",
            "stage": "rerank",
            "saved_ms": round(stages["rerank"] - scaled, 3),
            "why": (f"候选数 {old_candidates} → {rerank_candidates}，"
                    "重排耗时与候选数成正比"),
        })

    if final_k is not None:
        _require(fixed is not None and per_chunk is not None,
                 "trace 里没有 context_composition 的 fixed_tokens 和 "
                 "tokens_per_chunk：改 final_k 要靠它们算新的上下文长度")
        _require(final_k > 0, "final_k 必须为正")
        old_k = retrieval.get("final_k")
        _require(old_k is not None, "retrieval 里没有 final_k")
        implied = fixed + old_k * per_chunk
        _require(abs(implied - baseline_tokens) <= max(1, 0.02 * baseline_tokens),
                 f"context_composition 算出来是 {implied} token，"
                 f"而 context_tokens 写的是 {baseline_tokens}，两者对不上："
                 "先把拼装口径对齐再估算")
        new_tokens = fixed + final_k * per_chunk
        new_ttft = ttft_after_context_change(
            config, baseline_tokens, stages["ttft"], new_tokens)
        new_stages["ttft"] = round(new_ttft, 3)
        token_ratio = new_tokens / baseline_tokens
        cost_ratio = new_ttft / stages["ttft"]
        changes.append({
            "knob": "final-k",
            "stage": "ttft",
            "saved_ms": round(stages["ttft"] - new_ttft, 3),
            "context_tokens": new_tokens,
            "token_ratio": round(token_ratio, 4),
            "compute_ratio": round(cost_ratio, 4),
            "why": (f"上下文 {baseline_tokens} → {new_tokens} token，"
                    f"token 是 {round(token_ratio, 3)} 倍而 Prefill 计算量是 "
                    f"{round(cost_ratio, 3)} 倍；这两个数不相等正是 23.3 的重点。"
                    f"Attention 占比从 "
                    f"{round(attention_share(config, baseline_tokens) * 100, 1)}% "
                    f"变成 {round(attention_share(config, new_tokens) * 100, 1)}%"),
        })

    old_total = sum(stages.values())
    total = sum(new_stages.values())
    ranked = sorted(changes, key=lambda c: c["saved_ms"], reverse=True)
    return {
        "is_estimate": True,
        "estimate_note": (
            "这个模式只给估算，不替代实测。它的用途是在动手之前排出优先级："
            "省得多的先做。改完之后要按 23.6 那套 Baseline 重测，"
            "不能把这里的数字当成结果写进报告。"),
        "baseline_total_ms": round(old_total, 3),
        "estimated_total_ms": round(total, 3),
        "estimated_saving_ms": round(old_total - total, 3),
        "estimated_saving_share": round((old_total - total) / old_total, 4),
        "context_tokens_before": baseline_tokens,
        "context_tokens_after": new_tokens,
        "stages_before_ms": stages,
        "stages_after_ms": new_stages,
        "changes": changes,
        "priority": [c["knob"] for c in ranked],
        "priority_reading": (
            "，".join(f"{c['knob']} 省 {round(c['saved_ms'])} ms"
                      for c in ranked)
            + "。按这个顺序动手。" if ranked else "没有指定任何旋钮"),
    }


# --------------------------------------------------------------------------
# collect: needs a live chain
# --------------------------------------------------------------------------

def collect(endpoint: str, queries: list[dict], repeat: int,
            cold_start: bool, knowledge_base: dict, cache_status: dict,
            retrieval: dict,
            fetch=None) -> dict:  # pragma: no cover - needs a chain
    """Send each query `repeat` times and record the per-stage timings.

    The first pass is labelled cold and the rest warm, which is what
    `--cold-start` is for: without it, every number is a warm number and 23.2's
    cold/warm gap is invisible.
    """
    if fetch is None:
        def fetch(payload: dict) -> dict:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                endpoint, data=body,
                headers={"Content-Type": "application/json"})
            started = time.monotonic()
            with urllib.request.urlopen(req, timeout=120) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
            doc.setdefault("wall_ms", (time.monotonic() - started) * 1000)
            return doc

    calls = []
    for query in queries:
        for pass_index in range(repeat):
            doc = fetch(query)
            calls.append({
                "query_id": query.get("id"),
                "temperature": ("cold" if (cold_start and pass_index == 0)
                                else "warm"),
                "pass": pass_index,
                "stages": {s: doc.get("stages", {}).get(s) for s in STAGES},
                "context_tokens": doc.get("context_tokens"),
            })
    return {
        "endpoint": endpoint,
        "repeat": repeat,
        "cold_start": cold_start,
        "knowledge_base": knowledge_base,
        "cache_status": cache_status,
        "retrieval": retrieval,
        "calls": calls,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def print_analyze(r: dict) -> None:
    kb = r["knowledge_base"]
    print(f"知识库            {kb['version']}，{kb['documents']} 篇")
    print(f"调用数            {r['calls']}")
    print("热查询各段")
    for stage, ms in r["stages_warm_ms"].items():
        print(f"  {stage:<10}{ms:>9.1f} ms   {round(r['stage_share'][stage] * 100, 1)}%")
    print(f"热查询总时长      {r['total_warm_ms']} ms")
    print(f"冷查询总时长      {r['total_cold_ms']} ms")
    print(f"                  {r['cold_vs_warm']['reading']}")
    print("关键路径前三段")
    for item in r["critical_path"]:
        print(f"  {item['stage']:<10}{item['ms']:>9.1f} ms   "
              f"{round(item['share'] * 100, 1)}%")
    print(f"生成两段占比      {round(r['generation_share'] * 100, 1)}%")
    print(f"生成之前占比      {round(r['before_generation_share'] * 100, 1)}%")
    if r["retrieval_fields_missing"]:
        print(f"负载描述缺字段    {r['retrieval_fields_missing']}")


def print_whatif(r: dict) -> None:
    print(f"基准总时长        {r['baseline_total_ms']} ms")
    print(f"估算总时长        {r['estimated_total_ms']} ms")
    print(f"估算节省          {r['estimated_saving_ms']} ms"
          f"（{round(r['estimated_saving_share'] * 100, 1)}%）")
    print(f"上下文            {r['context_tokens_before']} → "
          f"{r['context_tokens_after']} token")
    for c in r["changes"]:
        print(f"  {c['knob']:<20}省 {c['saved_ms']} ms")
        print(f"    {c['why']}")
    print(f"优先级            {r['priority_reading']}")
    print(f"注意              {r['estimate_note']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_c = sub.add_parser("collect", help="采集逐段耗时（需要真实 RAG 链路）")
    p_c.add_argument("--endpoint", required=True)
    p_c.add_argument("--queries", type=Path, required=True)
    p_c.add_argument("--repeat", type=int, default=3)
    p_c.add_argument("--cold-start", action="store_true")
    p_c.add_argument("--meta", type=Path, required=True,
                     help="知识库版本、缓存状态、检索参数三项，JSON")
    p_c.add_argument("--output", type=Path, required=True)

    p_a = sub.add_parser("analyze", help="逐段占比、关键路径、冷热对照")
    p_a.add_argument("--trace", type=Path, required=True)
    p_a.add_argument("--output", type=Path, default=None)

    p_w = sub.add_parser("whatif", help="按给定的参数变化重新估算")
    p_w.add_argument("--trace", type=Path, required=True)
    p_w.add_argument("--config", type=Path,
                     default=HERE.parent / "ch11" / "model-qwen25-05b.json")
    p_w.add_argument("--final-k", type=int, default=None)
    p_w.add_argument("--rerank-candidates", type=int, default=None)
    p_w.add_argument("--skip-rewrite", action="store_true")
    p_w.add_argument("--skip-rewrite-share", type=float, default=1.0)
    p_w.add_argument("--parallelize", default="",
                     help="要并行掉的段，逗号分隔；主链上的段会被拒绝")
    p_w.add_argument("--output", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    try:
        if args.cmd == "collect":  # pragma: no cover - needs a chain
            queries = [json.loads(line) for line
                       in args.queries.read_text(encoding="utf-8").splitlines()
                       if line.strip()]
            meta = json.loads(args.meta.read_text(encoding="utf-8"))
            trace = collect(args.endpoint, queries, args.repeat,
                            args.cold_start, meta["knowledge_base"],
                            meta["cache_status"], meta["retrieval"])
            args.output.write_text(
                json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}")
            return 0
        trace = json.loads(args.trace.read_text(encoding="utf-8"))
        if args.cmd == "analyze":
            result = analyze(trace)
            print_analyze(result)
        else:
            config = load_config(
                json.loads(args.config.read_text(encoding="utf-8")))
            result = whatif(
                trace, config, final_k=args.final_k,
                rerank_candidates=args.rerank_candidates,
                skip_rewrite=args.skip_rewrite,
                skip_rewrite_share=args.skip_rewrite_share,
                parallelize=[x for x in args.parallelize.split(",") if x])
            print_whatif(result)
        if args.output is not None:
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"wrote {args.output}")
        return 0
    except TraceError as exc:
        print(f"REJECTED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
