"""Build the Chapter 23 figure set defined in strategy/reviews/ch23/storyboard.md.

Both figures recompute their numbers at build time:

  fig23-01  23.1 and 23.2's decomposition, drawn from
            content/ch23/evidence/rag-trace-sample.json via
            code/ch23/rag_trace.py's `analyze`.
  fig23-02  23.3's coupling between retrieval quality and generation cost. The
            TTFT curve comes from Chapter 11's cost model, not from a linear
            rule, because the point of 23.3 is that it is not linear.

Run from the repository root:

    python3 content/ch23/figures/build_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch11"))
sys.path.insert(0, str(ROOT / "code" / "ch23"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, card, dashed, note, page, txt, write, write_note,
)
import prefill_model as pm  # noqa: E402
import rag_trace as rt  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"
MUTED_LINE = "#94A3B8"

TRACE = json.loads(
    (ROOT / "content/ch23/evidence/rag-trace-sample.json")
    .read_text(encoding="utf-8"))
READING = rt.analyze(TRACE)
CONFIG = pm.load_config(json.loads(
    (ROOT / "code/ch11/model-qwen25-05b.json").read_text(encoding="utf-8")))
WHATIF = rt.whatif(TRACE, CONFIG, final_k=5, skip_rewrite=True,
                   rerank_candidates=50)

# 23.3 那一对：3000 token 的 600 ms 与 9000 token 的 2350 ms。
SHORT_TOKENS, SHORT_TTFT = 3000, 600.0
LONG_TOKENS = 9000
LONG_TTFT = rt.ttft_after_context_change(CONFIG, SHORT_TOKENS, SHORT_TTFT,
                                         LONG_TOKENS)

STAGE_LABEL = {
    "rewrite": "查询改写", "embed": "向量化", "retrieve": "向量检索",
    "rerank": "重排", "assemble": "prompt 拼装", "ttft": "生成 TTFT",
    "generate": "生成剩余",
}


# --- 图23-1 一次 RAG 调用的时间去了哪 ---------------------------------------

def fig1() -> str:
    p = [card(72, 176, 1136, 260, cls="card", rx=16)]
    p.append(txt(96, 208, "一次热查询的逐段耗时（合成 trace）", cls="b"))

    x0, x1 = 96, 1184
    total = READING["total_warm_ms"]
    y = 240
    x = x0
    colours = {"rewrite": WARN, "embed": MUTED_LINE, "retrieve": COOL,
               "rerank": WARN, "assemble": MUTED_LINE, "ttft": BAD,
               "generate": GOOD}
    for stage in rt.STAGES:
        ms = READING["stages_warm_ms"][stage]
        w = ms / total * (x1 - x0)
        colour = colours[stage]
        p.append(f'  <rect x="{x:.1f}" y="{y}" width="{max(w - 3, 2):.1f}" '
                 f'height="52" rx="6" fill="{colour}" opacity="0.22" '
                 f'stroke="{colour}" stroke-width="1.6"/>')
        if w > 74:
            p.append(f'  <text class="b" x="{x + w / 2:.0f}" y="{y + 32}" '
                     f'text-anchor="middle" fill="{colour}">'
                     f'{STAGE_LABEL[stage]}</text>')
        x += w

    # 七段一律在条带下方列成一行图例：小段挤在条带里读不了，引线又会互相压
    lx = 96
    slot = (x1 - x0) / len(rt.STAGES)
    for stage in rt.STAGES:
        ms = READING["stages_warm_ms"][stage]
        share = READING["stage_share"][stage]
        colour = colours[stage]
        p.append(f'  <rect x="{lx:.0f}" y="{y + 68}" width="14" height="14" '
                 f'rx="4" fill="{colour}" opacity="0.28" stroke="{colour}" '
                 f'stroke-width="1.4"/>')
        p.append(txt(lx + 22, y + 80, STAGE_LABEL[stage], cls="b"))
        p.append(txt(lx + 22, y + 104, f"{ms:.0f} ms  {share:.1%}", cls="s"))
        lx += slot

    p.append(txt(96, 408,
                 f"生成那两段占 {READING['generation_share']:.1%}，"
                 f"它之前的部分占 {READING['before_generation_share']:.1%}；"
                 "这一章关注的正是前面那一小块", cls="b"))

    p.append(card(72, 452, 552, 176, cls="card", rx=16))
    p.append(txt(96, 484, "冷热对照：差距集中在检索这一段", cls="b"))
    ratios = READING["cold_vs_warm"]["per_stage_ratio"]
    rows = [("retrieve", "向量检索"), ("ttft", "生成 TTFT"), ("rerank", "重排")]
    ry = 508
    for stage, label in rows:
        warm = READING["stages_warm_ms"][stage]
        cold = READING["stages_cold_ms"][stage]
        colour = BAD if ratios[stage] >= 2 else MUTED_LINE
        p.append(txt(96, ry, label, cls="b"))
        p.append(txt(224, ry, f"热 {warm:.0f} ms", cls="s"))
        p.append(txt(352, ry, f"冷 {cold:.0f} ms", cls="s"))
        p.append(f'  <text class="b" x="480" y="{ry}" fill="{colour}">'
                 f'{ratios[stage]:.2f} 倍</text>')
        ry += 32
    p.append(txt(96, ry + 2,
                 f"而端到端只慢 "
                 f"{(READING['cold_vs_warm']['total_ratio'] - 1) * 100:.1f}%",
                 cls="b"))

    p.append(card(656, 452, 552, 176, cls="card", rx=16))
    p.append(txt(680, 484, "两处最容易被低估的地方", cls="b"))
    p.append(note(672, 500, 520, [
        "查询改写是一次完整的 LLM 调用，有自己的 TTFT 和排队",
    ], cls="warnfill"))
    p.append(note(672, 554, 520, [
        "重排的耗时和候选数成正比，这是性价比最高的旋钮之一",
    ], cls="coolfill"))

    return page(
        system=SYSTEM,
        title="一次 RAG 调用的时间去了哪",
        desc="上方是一条按比例分段的横条，依次是查询改写、向量化、向量检索、重排、prompt "
             "拼装、生成 TTFT、生成剩余七段，每段标出耗时和占比，短的几段用引线引出。下方"
             "左边是冷热对照表：向量检索冷起来是热的 3.58 倍，而端到端只慢 6.6%。下方右边"
             "列出查询改写和重排这两处最容易被低估的地方。",
        kicker="第 23 章 · 23.1、23.2、23.7",
        heading="模型生成只是最后一段",
        sub="不知道时间花在哪，优化只能凭猜；所以 RAG 性能工程第一步不是优化，是分解",
        body="\n".join(p),
        takeaway="检索冷起来慢 3.6 倍，端到端只慢 6.6%：占比小的那一段能造成的全部影响就这么多",
    )


# --- 图23-2 检索质量直接决定生成成本 ----------------------------------------

def fig2() -> str:
    p = [card(72, 176, 728, 396, cls="card", rx=16)]
    p.append(txt(96, 208, "上下文长度与 Prefill 代价：两条线不重合", cls="b"))

    x0, x1 = 176, 744
    y0, y1 = 250, 466
    max_tokens = 12000

    def px(tok: float) -> float:
        return x0 + tok / max_tokens * (x1 - x0)

    def py(v: float) -> float:
        return y1 - min(v, 6.2) / 6.2 * (y1 - y0)

    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" '
             f'stroke="{MUTED_LINE}" stroke-width="1.6"/>')
    for mult in (1, 2, 3, 4, 5, 6):
        p.append(dashed(x0, py(mult), x1, py(mult), cls="divider"))
        p.append(txt(x0 - 10, py(mult) + 5, f"{mult}×", cls="s", anchor="end"))

    # 线性参考线：token 翻几倍就是几倍
    lin = " ".join(f"{px(t):.0f},{py(t / SHORT_TOKENS):.0f}"
                   for t in range(SHORT_TOKENS, max_tokens + 1, 250))
    p.append(f'  <polyline points="{lin}" fill="none" stroke="{MUTED_LINE}" '
             f'stroke-width="2.4" stroke-dasharray="7 5"/>')
    # 真实代价：第 11 章那个模型
    real = " ".join(
        f"{px(t):.0f},"
        f"{py(pm.relative_cost(CONFIG, t) / pm.relative_cost(CONFIG, SHORT_TOKENS)):.0f}"
        for t in range(SHORT_TOKENS, max_tokens + 1, 250))
    p.append(f'  <polyline points="{real}" fill="none" stroke="{BAD}" '
             f'stroke-width="3.2"/>')

    ratio9 = (pm.relative_cost(CONFIG, LONG_TOKENS)
              / pm.relative_cost(CONFIG, SHORT_TOKENS))
    p.append(f'  <circle cx="{px(SHORT_TOKENS):.0f}" cy="{py(1):.0f}" r="6.5" '
             f'fill="{GOOD}"/>')
    p.append(f'  <circle cx="{px(LONG_TOKENS):.0f}" cy="{py(ratio9):.0f}" '
             f'r="6.5" fill="{BAD}"/>')
    p.append(f'  <circle cx="{px(LONG_TOKENS):.0f}" cy="{py(3.0):.0f}" '
             f'r="5" fill="{MUTED_LINE}"/>')
    p.append(txt(px(LONG_TOKENS) - 16, py(ratio9) - 10,
                 f"实际 {ratio9:.2f} 倍", cls="b", anchor="end"))
    p.append(txt(px(LONG_TOKENS) + 14, py(3.0) + 6, "按 token 线性推 3.0 倍",
                 cls="s"))
    p.append(txt(px(SHORT_TOKENS) + 14, py(1) + 24, "基准 3000 token",
                 cls="good"))

    for tok in (3000, 6000, 9000, 12000):
        p.append(txt(px(tok), y1 + 26, f"{tok // 1000}k", cls="s",
                     anchor="middle"))
    p.append(txt(96, y1 + 26, "上下文 token", cls="s"))
    p.append(txt(120, 240, "Prefill 代价（相对 3000 token）", cls="b"))

    p.append(txt(96, y1 + 60,
                 f"差额来自 Attention 那个平方项：Attention 占 Prefill 计算量的比例"
                 f"从 {rt.attention_share(CONFIG, SHORT_TOKENS):.0%} 涨到 "
                 f"{rt.attention_share(CONFIG, LONG_TOKENS):.0%}", cls="b"))

    p.append(card(824, 176, 384, 396, cls="card", rx=16))
    p.append(txt(848, 208, "换成 TTFT 就是这一对", cls="b"))
    p.append(note(840, 228, 344, [
        f"检索准确  Top-5 就够",
        f"prompt {SHORT_TOKENS} token",
        f"TTFT {SHORT_TTFT:.0f} ms",
    ], cls="goodfill"))
    p.append(note(840, 346, 344, [
        f"检索不准  要 Top-15",
        f"prompt {LONG_TOKENS} token",
        f"TTFT {LONG_TTFT:.0f} ms",
    ], cls="badfill"))
    p.append(note(840, 464, 344, [
        f"省下的 TTFT {LONG_TTFT - SHORT_TTFT:.0f} ms",
        "重排代价最多 300 ms",
        f"净收益 {LONG_TTFT - SHORT_TTFT - 300:.0f} 到 "
        f"{LONG_TTFT - SHORT_TTFT - 50:.0f} ms",
    ], cls="coolfill"))

    p.append(note(72, 588, 1136, [
        "提升检索质量是收益最大的那一类优化：它同时降低 TTFT、token 成本和显存占用，"
        "还提升回答质量。幅度要实测，因为它取决于你的 Attention 占比落在哪一段。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="检索不准的代价比按 token 数线性推算出来的更贵",
        desc="一张折线图，横轴是上下文 token 从 3000 到 12000，纵轴是相对 3000 token 的 "
             "Prefill 代价。虚线是按 token 数线性推算的参考线，实线是第 11 章那个模型算出来"
             "的真实代价，两条线在 9000 token 处分开：线性推算是 3.0 倍，实际是 3.92 倍。"
             "右侧把它换算成 TTFT：3000 token 对应 600 毫秒，9000 token 对应 2350 毫秒，"
             "以及重排能省下的净收益区间。",
        kicker="第 23 章 · 23.3",
        heading="token 是三倍，TTFT 却将近四倍",
        sub="多出来的那部分是第 11 章那个 Attention 平方项",
        body="\n".join(p),
        takeaway="提升检索质量同时降低 TTFT、token 成本和显存占用，没有任何一边要付出代价",
    )


FIGS = [
    ("fig23-01_rag_stage_breakdown", fig1,
     dict(title="图23-1 一次 RAG 调用的时间去了哪",
          source="23.1、23.2、23.7",
          order="先看上方那条横条里哪几段最宽，再看下面那句生成前后的占比，然后看左下角的冷热对照，最后看右下角那两处最容易被低估的地方",
          takeaway="检索冷起来慢 3.6 倍，端到端只慢 6.6%：占比小的那一段能造成的全部影响就这么多",
          boundary="数据出自 content/ch23/evidence/rag-trace-sample.json，是合成 trace 不是真机采集；各段占比随链路配置变化很大，要看的是分解这件事本身，不是这几个具体数字")),
    ("fig23-02_quality_drives_cost", fig2,
     dict(title="图23-2 检索不准的代价比按 token 数线性推算出来的更贵",
          source="23.3",
          order="先看虚线那条线性参考线，再看实线怎么在 9000 token 处甩开它，然后读 Attention 占比那一行，最后看右侧换算成 TTFT 的那一对",
          takeaway="提升检索质量同时降低 TTFT、token 成本和显存占用，没有任何一边要付出代价",
          boundary="曲线由 code/ch11/prefill_model.py 按 Qwen2.5-0.5B 的配置算出，换模型交叉点会变，曲线的弯法也会变；600 ms 那个基准是设定值，图里给的是倍数关系不是某台机器的绝对时间")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
