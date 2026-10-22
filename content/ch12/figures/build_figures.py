"""Build the Chapter 12 figure set defined in strategy/reviews/ch12/storyboard.md.

Token counts come from code/ch12/rag-prompt.json and TTFT values from the
Chapter 11 model calibrated on the one measured anchor (Top-K=3, 320 ms), so
every number here can be recomputed with code/ch12/context_cost.py.

Run from the repository root:

    python3 content/ch12/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, MUTED, WARN, arrow, bar, card, dashed, hpath, note, page,
    txt, vpath, write, write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

CROSSOVER = 16640
FIXED, SEG = 630, 200          # 12.2's segment table
ANCHOR_TOKENS, ANCHOR_MS = 1230, 320.0


def rel(s: float) -> float:
    return s * (CROSSOVER + s)


def tokens_at(k: int) -> int:
    return FIXED + SEG * k


def ttft_at(k: int) -> float:
    return rel(tokens_at(k)) * (ANCHOR_MS / rel(ANCHOR_TOKENS))


# --- 图12-1 prompt 的五段各由谁决定 -----------------------------------------

def fig1() -> str:
    p = []
    total = tokens_at(10)
    x0, x1 = 96, 1184
    bar_y, bar_h = 238, 72
    segs = [
        ("system prompt", 200, "应用层", COOL, "#EFF6FF"),
        ("few-shot 示例", 400, "应用层", COOL, "#EFF6FF"),
        ("检索片段 10 段", 2000, "应用层：Top-K", WARN, "#FFFBEB"),
        ("用户问题", 30, "用户输入", GOOD, "#ECFDF5"),
    ]
    p.append(txt(x0, 208, f"Top-K = 10 的一条 prompt，共 {total} token（段宽按 token 数成比例，左边就是拼接顺序）", cls="b"))
    edges = []
    x = x0
    for name, tok, who, colour, fillc in segs:
        w = (x1 - x0) * tok / total
        edges.append((x, w, name, tok, who, colour))
        p.append(f'  <rect x="{x:.1f}" y="{bar_y}" width="{w:.1f}" height="{bar_h}" '
                 f'rx="8" fill="{fillc}" stroke="{colour}" stroke-width="1.8"/>')
        x += w

    for x, w, name, tok, who, colour in edges:
        cx = x + w / 2
        if w > 150:                     # wide enough to label inside the bar
            p.append(f'  <text class="b" x="{cx:.1f}" y="{bar_y + 30}" '
                     f'text-anchor="middle" fill="{colour}">{name}</text>')
            p.append(txt(cx, bar_y + 54, f"{tok} token", cls="m", anchor="middle"))
            p.append(txt(cx, bar_y + 104, who, cls="s", anchor="middle"))
        else:                           # leader line down to a label below
            p.append(f'  <path d="M{cx:.1f} {bar_y + bar_h}V{bar_y + 96}" '
                     f'fill="none" stroke="{colour}" stroke-width="2"/>')
            anchor = "start" if name.startswith("system") else "end"
            lx = cx - 10
            p.append(f'  <text class="b" x="{lx:.1f}" y="{bar_y + 120}" '
                     f'text-anchor="{anchor}" fill="{colour}">{name} {tok} token</text>')
            tail = who if anchor == "start" else "用户输入，整条里最短的一段，却排在最后"
            p.append(txt(lx, bar_y + 142, tail, cls="s", anchor=anchor))

    # cacheable prefix bracket
    pref_w = (x1 - x0) * 600 / total
    p.append(f'  <path class="bracket" d="M{x0} {bar_y + 174}V{bar_y + 188}'
             f'H{x0 + pref_w:.1f}V{bar_y + 174}"/>')
    p.append(txt(x0 + pref_w + 16, bar_y + 192, "可缓存前缀 600 token", cls="mb"))

    p.append(card(96, 478, 528, 132, cls="soft", rx=14))
    p.append(txt(118, 510, "为什么是 600 而不是 630", cls="h"))
    p.append(txt(118, 542, "不随请求变化的内容有 630 token，但缓存按前缀匹配。", cls="s"))
    p.append(txt(118, 568, "用户问题排在最后，它前面的检索片段一变，前缀早就", cls="s"))
    p.append(txt(118, 594, "断了，那 30 token 永远命中不了。", cls="s"))

    p.append(card(656, 478, 528, 132, cls="coolfill", rx=14))
    p.append(txt(678, 510, "同一份 prompt，两个档位", cls="h"))
    p.append(txt(678, 544, "Top-K = 3    1230 token    前缀占 49%", cls="m"))
    p.append(txt(678, 572, "Top-K = 10   2630 token    前缀占 23%", cls="m"))
    p.append(txt(678, 600, "档位一变，该不该开缓存的答案就变了", cls="s"))
    return page(
        system=SYSTEM,
        title="图 12-1 prompt 的五段各由谁决定",
        desc="一条按 token 数成比例的堆叠条，依次是 system prompt 200、few-shot 400、"
             "检索片段 2000、用户问题 30，共 2630 token；下方括号标出可缓存前缀 600 token，"
             "并说明它为什么不是不随请求变化的那 630。",
        kicker="CH12 · 12.2",
        heading="prompt 的五段各由谁决定",
        sub="最长的那一段是谁选的",
        body="\n".join(p),
        takeaway="最大的那一段是应用层选的；能被缓存的只有排在最前面那一段。",
    )


# --- 图12-2 拐点在 5，不在质量最高的 10 --------------------------------------

def fig2() -> str:
    p = []
    ks = [3, 5, 10, 20]
    quality = {3: 0.71, 5: 0.78, 10: 0.79, 20: 0.78}
    x0, x1 = 178, 754
    p.append(card(72, 182, 728, 400, cls="card", rx=16))

    # two stacked panels sharing one x axis: quality on top, cost below
    qt, qb = 226, 338          # quality band
    ct, cb = 402, 524          # cost band
    p.append(f'  <path d="M{x0} {qt - 16}V{qb}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.6"/>')
    p.append(f'  <path d="M{x0} {ct - 16}V{cb}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.6"/>')

    xs = {k: x0 + 46 + i * (x1 - x0 - 92) / (len(ks) - 1) for i, k in enumerate(ks)}
    max_ms = ttft_at(20) * 1.05

    def cost_y(ms: float) -> float:
        return cb - ms / max_ms * (cb - ct)

    def q_y(q: float) -> float:
        return qb - (q - 0.68) / (0.82 - 0.68) * (qb - qt)

    q_pts = " ".join(f"{xs[k]:.1f},{q_y(quality[k]):.1f}" for k in ks)
    cost_pts = " ".join(f"{xs[k]:.1f},{cost_y(ttft_at(k)):.1f}" for k in ks)
    p.append(f'  <polyline points="{q_pts}" fill="none" stroke="{GOOD}" stroke-width="3"/>')
    p.append(f'  <polyline points="{cost_pts}" fill="none" stroke="{WARN}" stroke-width="3"/>')

    for k in ks:
        p.append(f'  <circle cx="{xs[k]:.1f}" cy="{q_y(quality[k]):.1f}" r="6" fill="{GOOD}"/>')
        p.append(f'  <circle cx="{xs[k]:.1f}" cy="{cost_y(ttft_at(k)):.1f}" r="6" fill="{WARN}"/>')
        p.append(f'  <text class="m" x="{xs[k]:.1f}" y="{q_y(quality[k]) - 14:.1f}" '
                 f'text-anchor="middle" fill="{GOOD}">{quality[k]}</text>')
        p.append(f'  <text class="m" x="{xs[k]:.1f}" y="{cost_y(ttft_at(k)) - 14:.1f}" '
                 f'text-anchor="middle" fill="{WARN}">{ttft_at(k):.0f} ms</text>')
        p.append(txt(xs[k], cb + 28, f"K={k}", cls="mb", anchor="middle"))
        p.append(txt(xs[k], cb + 50, f"{tokens_at(k)} token", cls="s", anchor="middle"))

    p.append(f'  <text class="b" x="{x0 - 14}" y="{qt + 4}" text-anchor="end" '
             f'fill="{GOOD}">质量分</text>')
    p.append(txt(x0 - 14, qt + 26, "示意值", cls="s", anchor="end"))
    p.append(f'  <text class="b" x="{x0 - 14}" y="{ct + 4}" text-anchor="end" '
             f'fill="{WARN}">TTFT</text>')
    p.append(txt(x0 - 14, ct + 26, "算出来的", cls="s", anchor="end"))

    # knee, spanning both panels
    p.append(dashed(xs[5], qt - 30, xs[5], cb))
    p.append(txt(xs[5], qt - 40, "拐点", cls="mb", anchor="middle"))

    p.append(txt(xs[10] + 16, q_y(quality[10]) + 34, "质量在 10 到 20 之间反而下降", cls="s"))
    p.append(txt(96, 610, "新增片段相关性低、互相稀释，所以“取质量最高那一档”会买到一个更贵且更差的结果", cls="s"))

    # the criterion
    p.append(card(824, 182, 400, 214, cls="soft", rx=14))
    p.append(txt(848, 216, "判据：增量质量 ÷ 增量成本", cls="h"))
    p.append(txt(848, 254, "3 → 5", cls="b"))
    p.append(txt(848, 280, "+0.07 质量   +400 token   +114 ms", cls="m"))
    p.append(txt(848, 318, "5 → 10", cls="b"))
    p.append(txt(848, 344, "+0.01 质量   +1000 token  +304 ms", cls="m"))
    p.append(dashed(846, 364, 1200, 364))
    p.append(txt(848, 386, "前一步的性价比是后一步的 17.5 倍", cls="mb"))

    p.append(card(824, 416, 400, 166, cls="coolfill", rx=14))
    p.append(txt(848, 450, "两个答案不一样", cls="h"))
    p.append(txt(848, 484, "质量最高的一档", cls="s"))
    p.append(txt(1200, 484, "K = 10", cls="mb", anchor="end"))
    p.append(txt(848, 520, "划算的那一档", cls="s"))
    p.append(txt(1200, 520, "K = 5", cls="mb", anchor="end"))
    p.append(txt(848, 552, "拐点附近两档要按可识别线判断能否分辨", cls="s"))
    return page(
        system=SYSTEM,
        title="图 12-2 拐点在 5，不在质量最高的 10",
        desc="上下两栏折线图，共用 Top-K 横轴：上栏是质量分，先陡后平并在 10 到 20 之间下降；下栏是 TTFT，随 Top-K 单调上升且越来越陡；两栏分开画是因为量纲不同，不能放在同一根纵轴上比；"
             "右侧用增量质量除以增量成本算出拐点在 5，与质量最高的 10 不是同一档。",
        kicker="CH12 · 12.4",
        heading="拐点在 5，不在质量最高的 10",
        sub="该停在哪一档",
        body="\n".join(p),
        takeaway="判据是增量质量除以增量成本，它给出的答案和取质量最高那一档不同。",
    )


# --- 图12-3 Agent 的上下文是一条阶梯 ----------------------------------------

def fig3() -> str:
    p = []
    steps = [("第 1 步", "system + 任务描述", 600),
             ("第 2 步", "上一步 + 工具A结果", 1400),
             ("第 3 步", "上两步 + 工具B结果", 2600),
             ("第 4 步", "上三步 + 工具C结果", 4100),
             ("第 5 步", "上四步 + 工具D结果", 5800)]
    x0, w_max = 368, 470
    for i, (label, what, tok) in enumerate(steps):
        y = 200 + i * 66
        w = w_max * tok / 5800
        p.append(txt(96, y + 38, label, cls="b"))
        p.append(txt(352, y + 38, what, cls="s", anchor="end"))
        p.append(bar(x0, y + 12, w, 40, cls="coolfill", rx=6))
        if w > 120:
            p.append(txt(x0 + w - 14, y + 38, f"{tok} token", cls="m", anchor="end"))
        else:
            p.append(txt(x0 + w + 14, y + 38, f"{tok} token", cls="m"))
    p.append(dashed(x0, 190, x0, 530))

    # cumulative vs the naive estimate
    p.append(card(908, 196, 316, 160, cls="badfill", rx=14))
    p.append(txt(932, 230, "按任务算", cls="h"))
    p.append(txt(932, 268, "14500 token", cls="mb"))
    p.append(txt(932, 296, "五步相加", cls="s"))
    p.append(txt(932, 330, "600+1400+2600+4100+5800", cls="s"))

    p.append(card(908, 376, 316, 130, cls="soft", rx=14))
    p.append(txt(932, 410, "按调用算", cls="h"))
    p.append(txt(932, 448, "3000 token", cls="mb"))
    p.append(txt(932, 476, "首步 600 × 5，估少了", cls="s"))

    p.append(f'  <path class="flow" d="M1066 512V548"/>')
    p.append(txt(1066, 576, "差 4.8 倍", cls="mb", anchor="middle"))

    p.append(note(96, 548, 700, [
        "延迟也在逐步恶化：每一步的 TTFT 都比上一步长，用户感受到的是任务越往后越卡。",
        "这就是第 6 章那个“Agent 的账算少了”案例的机理；压缩历史的具体策略在第 24 章。",
    ], h=78))
    return page(
        system=SYSTEM,
        title="图 12-3 Agent 的上下文是一条阶梯",
        desc="五级阶梯按 token 数成比例，从 600 递增到 5800，总计 14500；"
             "右侧对比按调用估算的 3000 token，两者相差 4.8 倍。",
        kicker="CH12 · 12.5",
        heading="Agent 的上下文是一条阶梯",
        sub="为什么五步任务的账单不是单步的五倍",
        body="\n".join(p),
        takeaway="Agent 的成本要按任务算，按调用算会少算好几倍。",
    )


FIGURES = {
    "fig12-01_prompt_segments.svg": (
        fig1,
        dict(title="图 12-1 制作说明：prompt 的五段各由谁决定",
             source="第 12.2 节，段长取自 code/ch12/rag-prompt.json。",
             order="先看条的宽度比例，再看每段下方“谁决定它”，然后看下方那个可缓存前缀的括号，最后读左下解释它为什么是 600 而不是 630。",
             takeaway="最大的那一段是应用层选的；能被缓存的只有排在最前面那一段。",
             boundary="只画成本一边，不含任何质量分；命中率的折扣在第 13.3 节。"),
    ),
    "fig12-02_quality_vs_cost.svg": (
        fig2,
        dict(title="图 12-2 制作说明：拐点在 5，不在质量最高的 10",
             source="第 12.4 节。token 与 TTFT 由模型算出，质量分是示意值，图内已标注。",
             order="先看两条曲线的形状差别，再看质量曲线在 10 到 20 之间的下降，然后看拐点那条竖线，最后读右上的性价比对照。",
             takeaway="判据是增量质量除以增量成本，它给出的答案和取质量最高那一档不同。",
             boundary="质量分标明是示意值，真实曲线要用自己的评测集测；本图不涉及任何技术手段。"),
    ),
    "fig12-03_agent_ladder.svg": (
        fig3,
        dict(title="图 12-3 制作说明：Agent 的上下文是一条阶梯",
             source="第 12.5 节。",
             order="自上而下看五级阶梯怎么变长，再看右侧两个总量的对比，最后看那个 4.8 倍。",
             takeaway="Agent 的成本要按任务算，按调用算会少算好几倍。",
             boundary="不画压缩或摘要的具体策略（第 24 章），不含显存占用（第 16 章）。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
