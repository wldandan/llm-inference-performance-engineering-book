"""Build the Chapter 18 figure set defined in strategy/reviews/ch18/storyboard.md.

Every number comes from 18.3's formula and 18.4's derivation, and can be
recomputed with code/ch18/decode_optimization_check.py.

Run from the repository root:

    python3 content/ch18/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, bar, card, dashed, note, page, txt, write,
    write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

K, C = 4, 0.1
BREAK_EVEN = 1 + K * C        # 1.4


def gain(a: float) -> float:
    return a / BREAK_EVEN


# --- 图18-1 收益比随接受数变化，以及盈亏线 -----------------------------------

def fig1() -> str:
    p = []
    x0, y0, x1, y1 = 168, 214, 760, 486
    p.append(card(72, 176, 740, 380, cls="card", rx=16))
    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.8"/>')
    p.append(txt(96, 202, "收益比 = 平均接受长度 a ÷ (1 + k × c)，这里 k=4、c=0.1", cls="b"))

    a_lo, a_hi = 1.0, 4.0
    g_hi = 3.0

    def ax(a: float) -> float:
        return x0 + (a - a_lo) / (a_hi - a_lo) * (x1 - x0)

    def gy(g: float) -> float:
        return y1 - g / g_hi * (y1 - y0)

    # loss region below gain 1
    p.append(f'  <rect x="{x0}" y="{gy(1.0):.0f}" width="{x1 - x0}" '
             f'height="{y1 - gy(1.0):.0f}" fill="#FEF2F2" stroke="none"/>')
    p.append(dashed(x0, gy(1.0), x1, gy(1.0)))
    p.append(txt(x1 - 10, gy(1.0) - 10, "收益比 1：不快不慢", cls="s", anchor="end"))
    p.append(txt(x1 - 10, gy(1.0) + 28, "这条线以下是净亏损，不是收益小", cls="bad",
                 anchor="end"))

    pts = " ".join(f"{ax(a):.0f},{gy(gain(a)):.0f}"
                   for a in [a_lo + i * 0.05 for i in range(61)])
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{COOL}" stroke-width="3"/>')

    # the break-even point
    p.append(dashed(ax(BREAK_EVEN), y0, ax(BREAK_EVEN), y1))
    p.append(txt(ax(BREAK_EVEN) + 12, y0 + 22, f"盈亏线 a = 1 + k×c = {BREAK_EVEN}",
                 cls="b"))

    marks = [
        (1.1, "1.1", "18.3 那个反例", BAD, -4, -58, "start"),
        (1.3, "1.3", "客服对话（18.8 案例一）", BAD, 34, 50, "start"),
        (3.2, "3.2", "18.3 那个正例", GOOD, -14, 42, "end"),
        (3.6, "3.6", "代码补全（18.8 案例一）", GOOD, -14, -46, "end"),
    ]
    for a, label, who, colour, dx, dy, anchor in marks:
        px_, py_ = ax(a), gy(gain(a))
        p.append(f'  <circle cx="{px_:.0f}" cy="{py_:.0f}" r="6" fill="{colour}"/>')
        p.append(f'  <path d="M{px_:.0f} {py_:.0f}L{px_ + dx:.0f} {py_ + dy - 14:.0f}" '
                 f'stroke="{colour}" stroke-width="1.4" fill="none"/>')
        p.append(txt(px_ + dx, py_ + dy,
                     f"{label} → {gain(a):.2f} 倍", cls="b", anchor=anchor))
        p.append(txt(px_ + dx, py_ + dy + 20, who, cls="s", anchor=anchor))

    for a in (1.0, 1.4, 2.0, 3.0, 4.0):
        p.append(f'  <path d="M{ax(a):.0f} {y1}V{y1 + 6}" stroke="#94A3B8" stroke-width="1.6"/>')
        p.append(txt(ax(a), y1 + 26, f"{a}", cls="s", anchor="middle"))
    p.append(txt(x1, y1 + 48, "平均接受长度 a", cls="s", anchor="end"))
    p.append(txt(96, y1 + 48, "同一套配置，两个场景落在线的两侧", cls="b"))
    for g in (1.0, 2.0, 3.0):
        p.append(txt(x0 - 12, gy(g) + 5, f"{g:.0f}", cls="s", anchor="end"))

    p.append(card(836, 176, 372, 380, cls="card", rx=16))
    p.append(txt(860, 210, "分母里那个 1 是什么", cls="b"))
    p.append(note(852, 230, 340, [
        "1 = 验证。目标模型一次前向过 k+1 个位置",
        "Decode 是带宽受限的，权重反正要搬一遍",
        "多算几个位置几乎不增加时间",
    ], cls="goodfill"))
    p.append(note(852, 348, 340, [
        "k × c = 草稿的时间。k=4 次草稿",
        "草稿模型是目标模型的十分之一大",
        "所以 4 × 0.1 = 0.4，这部分是净增的",
    ], cls="coolfill"))
    p.append(note(852, 466, 340, [
        "批量大到算力不空闲时，那个 1 会变大",
        "不是式子失灵，是式子的前提失效",
    ], cls="badfill"))

    p.append(note(72, 572, 1136, [
        "接受数取决于内容的可预测性，是业务属性，在场景之间完全不可迁移。"
        "别人的 3.6 来自代码补全，你的开放式对话可能只有 1.1，而 1.1 在这条线的下面。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="投机解码的收益比与盈亏线",
        desc="一条直线画出收益比随平均接受数的变化，k 为 4、c 为 0.1 时收益比等于接受数"
             "除以 1.4。收益比 1 以下的区域标为红色，表示净亏损。盈亏线画在接受数 1.4 处。"
             "四个点分别是 1.1、1.3、3.2、3.6，前两个在线的左侧，后两个在右侧。",
        kicker="第 18 章 · 18.3",
        heading="接受数低于 1.4，投机解码是净亏损而不是收益小",
        sub="收益比 = a ÷ (1 + k×c)；分母里那个 1 代表验证近乎免费，这是它成立的前提",
        body="\n".join(p),
        takeaway="盈亏线是 a > 1 + k×c；接受率没测过就不该部署它，那个数不可迁移",
    )


# --- 图18-2 Timeline 上 kernel 空隙的消失 ------------------------------------

def fig2() -> str:
    p = []
    p.append(card(72, 176, 1136, 296, cls="card", rx=16))
    p.append(txt(96, 208, "同一步 Decode 的 Timeline（示意，空隙被放大了，不按比例）", cls="b"))

    x0, w = 200, 984
    n = 12

    # before: kernels with visible gaps
    y = 232
    p.append(txt(96, y + 22, "未启用", cls="b"))
    p.append(bar(x0, y + 4, w, 42, cls="soft", rx=6))
    kw = w / n * 0.62
    gap = w / n * 0.38
    for i in range(n):
        cx_ = x0 + i * (kw + gap) + 4
        p.append(f'  <rect x="{cx_:.0f}" y="{y + 10}" width="{kw:.0f}" height="30" rx="3" '
                 f'fill="{COOL}" opacity="0.85"/>')
    p.append(txt(96, y + 72, "每步几十到上百个 kernel，每个之间一道启动空隙；"
                 "单次几微秒，每步合计约 0.5 ms", cls="s"))

    # after: one contiguous block, ending earlier
    y = 332
    p.append(txt(96, y + 22, "已启用", cls="b"))
    p.append(bar(x0, y + 4, w, 42, cls="soft", rx=6))
    filled = w * 0.62 * (n / n)
    filled = sum(kw for _ in range(n)) + 8
    p.append(f'  <rect x="{x0 + 4}" y="{y + 10}" width="{filled:.0f}" height="30" rx="3" '
             f'fill="{GOOD}" opacity="0.9"/>')
    p.append(f'  <text class="hw" x="{x0 + 18}" y="{y + 32}">一次提交替代上百次启动</text>')
    p.append(f'  <path d="M{x0 + filled + 8:.0f} {y + 54}V{y + 62}H{x0 + w:.0f}V{y + 54}" '
             f'class="bracket"/>')
    p.append(txt(x0 + filled + 8 + (w - filled - 8) / 2, y + 82, "省下的那一段",
                 cls="b", anchor="middle"))
    p.append(txt(96, y + 108, "空隙消失，变成连续密集的执行", cls="s"))

    # the derived threshold
    p.append(card(72, 488, 552, 128, cls="card", rx=16))
    p.append(txt(96, 520, "那 0.5 ms 值多少，取决于单步下限", cls="b"))
    p.append(txt(96, 548, "7B   下限 14 ms   0.5 ÷ 14 = 3.6%   值得做", cls="m"))
    p.append(txt(96, 574, "30B  下限 60 ms   0.5 ÷ 60 = 0.8%   不值那份捕获显存", cls="m"))
    p.append(txt(96, 600, "上面那两条轴里的空隙按真实比例只有 3.6%，画不出来", cls="s"))
    p.append(txt(72, 636, "0.5 ms 当定值是简化：kernel 数随层数涨，60 层约 0.9 ms，真实的线比 25B 更靠后", cls="s"))

    p.append(card(656, 488, 552, 128, cls="card", rx=16))
    p.append(txt(680, 520, "分界线是卡的属性，不是常数", cls="b"))
    p.append(txt(680, 548, "0.5 ÷ 下限 = 1%  →  下限 50 ms", cls="m"))
    p.append(txt(680, 574, "1000 GB/s → 25B", cls="m"))
    p.append(txt(896, 574, "2039 GB/s → 51B", cls="m"))
    p.append(txt(680, 600, "带宽越高，同样参数量下单步越短，这项反而越值得做", cls="s"))

    return page(
        system=SYSTEM,
        title="CUDA Graph 让 Timeline 上的 kernel 空隙消失",
        desc="上下两条等长的时间轴示意图，空隙被刻意放大以便看清。上面一条是未启用 "
             "CUDA Graph 时：十二个 kernel 之间夹着启动空隙。下面一条是启用后：变成一整块"
             "连续执行，右侧空出的一段标为省下的时间。下方给出这 0.5 ms 在 7B 上占单步下限"
             "的 3.6%、在 30B 上只占 0.8%，以及 1% 那条分界线在 1000 GB/s 的卡上落在 25B、"
             "在 2039 GB/s 的卡上落在 51B。",
        kicker="第 18 章 · 18.4",
        heading="CUDA Graph 治的是启动开销，而它值多少随卡而变",
        sub="录一次、每步提交一次；省下的启动开销占单步下限的比例决定它值不值那份捕获显存",
        body="\n".join(p),
        takeaway="启动开销涨得比单步下限慢得多，所以分界线是卡的属性，不是写死的 30B",
    )


FIGS = [
    ("fig18-01_acceptance_breakeven", fig1,
     dict(title="图18-1 投机解码的收益比与盈亏线",
          source="18.3、18.8",
          order="先看那条 1.4 的竖线，再看红色区域表示净亏损，最后看四个实例点分别落在哪一侧",
          takeaway="盈亏线是 a > 1 + k×c；接受率没测过就不该部署它，那个数不可迁移",
          boundary="这条线按 k=4、c=0.1 画；换草稿模型大小或每轮猜的个数，线的位置就变。图里假定批量足够低使得验证近乎免费；批量超过分界点 ÷ (k + 1)（参考卡上约 31）时分母里那个 1 会变大；c 若算上每步固定开销会在 0.11 到 0.26 之间，盈亏线随之右移，实测会比图上的差（18.8 案例一）")),
    ("fig18-02_cuda_graph_timeline", fig2,
     dict(title="图18-2 CUDA Graph 让 Timeline 上的 kernel 空隙消失",
          source="18.4",
          order="先对比上下两条时间轴上空隙的有无，再看下面那条右侧空出的一段，最后看下方两行占比和随带宽移动的分界线",
          takeaway="启动开销涨得比单步下限慢得多，所以分界线是卡的属性，不是写死的 30B",
          boundary="两条轴是示意，空隙被刻意放大了：按真实比例那 0.5 ms 在 7B 上只占单步的 3.6%，画出来看不见。kernel 的数量和宽度不对应任何一次真实 Profiling；0.5 ms 是这个量级上的典型值，具体系统要按 15.6 那个拆分自己测")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
