"""Build the Chapter 28 figure set defined in strategy/reviews/ch28/storyboard.md.

  fig28-01  28.1 那条累积退化：每一次都在门禁阈值下面，累积起来不在。图里同时画
            两件事，因为它们常被混成一个数：五步连乘是 1.26 倍，两周一次、半年
            十三次是 1.89 倍。右侧是 28.3 的阈值规则，说明那条 8% 的线本身是怎么
            定出来的，以及它的误报率和检出率。

每一个数都由 code/ch28/perf_gate.py 在构建时算出来。

Run from the repository root:

    python3 content/ch28/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch28"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, MUTED, WARN, card, dashed, note, page, txt, write,
    write_note,
)
import perf_gate as pg  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

GATE_THRESHOLD = 0.08
FIVE_STEPS = [0.05, 0.04, 0.06, 0.05, 0.04]
FIVE = pg.drift(FIVE_STEPS, threshold=GATE_THRESHOLD)
HALF_YEAR = pg.drift([0.05] * 13, threshold=GATE_THRESHOLD)
TO_DOUBLE_5 = pg.steps_to_double(0.05)
TO_DOUBLE_8 = pg.steps_to_double(0.08)
CASE_BAD = pg.threshold_advice(0.09)
CASE_GOOD = pg.threshold_advice(0.026)


def fig1() -> str:
    p = []
    p.append(card(56, 158, 744, 416, cls="card", rx=16))
    p.append(txt(80, 190, "每次改动的退化幅度，和它们的累积（合成设定）", cls="b"))

    x0, x1 = 128, 768
    y0, y1 = 300, 494
    n = len(HALF_YEAR["steps"])

    def px(i):
        return x0 + i / n * (x1 - x0)

    def py(mult):
        return y1 - (mult - 1.0) / 1.2 * (y1 - y0)

    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" stroke="#94A3B8" '
             f'stroke-width="1.8"/>')
    for mult in (1.2, 1.4, 1.6, 1.8, 2.0):
        yy = py(mult)
        p.append(f'  <path d="M{x0 - 6} {yy:.1f}H{x0}" stroke="#94A3B8" '
                 f'stroke-width="1.4"/>')
        p.append(txt(x0 - 14, yy + 5, f"{mult:.1f}×", cls="s", anchor="end"))
    for i in (5, 10, 13):
        p.append(txt(px(i), y1 + 26, f"第 {i} 次", cls="s", anchor="middle"))

    # 翻倍线
    p.append(dashed(x0, py(2.0), x1, py(2.0)))
    p.append(f'  <text class="b" x="{x0 + 10:.1f}" y="{py(2.0) - 10:.1f}" '
             f'fill="{BAD}">翻倍线</text>')

    # 累积曲线
    pts = [f"{px(0):.1f} {py(1.0):.1f}"]
    for row in HALF_YEAR["steps"]:
        pts.append(f'{px(row["step"]):.1f} {py(row["cumulative"]):.1f}')
    p.append(f'  <path d="M{"L".join(pts)}" fill="none" stroke="{COOL}" '
             f'stroke-width="2.6"/>')

    # 两个落点
    five = FIVE["cumulative"]
    p.append(f'  <circle cx="{px(5):.1f}" cy="{py(five):.1f}" r="7" '
             f'fill="{WARN}"/>')
    p.append(f'  <text class="b" x="{px(5) + 14:.1f}" y="{py(five) + 28:.1f}" '
             f'fill="{WARN}">5 次 = {five:.2f} 倍</text>')
    last = HALF_YEAR["cumulative"]
    p.append(f'  <circle cx="{px(13):.1f}" cy="{py(last):.1f}" r="7" '
             f'fill="{BAD}"/>')
    # 标注放在翻倍线上方，不压曲线
    p.append(f'  <text class="b" x="{px(13):.1f}" y="{py(2.0) - 10:.1f}" '
             f'text-anchor="end" fill="{BAD}">13 次 = {last:.2f} 倍</text>')

    # 上方：五步各自的幅度与门禁阈值
    bx0 = 128
    p.append(txt(80, 234, f"门禁阈值 {GATE_THRESHOLD:.0%}", cls="b"))
    p.append(dashed(bx0, 246, 480, 246))
    for i, step in enumerate(FIVE_STEPS):
        cx = bx0 + 24 + i * 60
        h = step / GATE_THRESHOLD * 28
        p.append(f'  <rect x="{cx}" y="{246 + 28 - h:.1f}" width="30" '
                 f'height="{h:.1f}" rx="4" fill="{GOOD}" opacity="0.45"/>')
        p.append(txt(cx + 15, 246 + 46, f"{step:.0%}", cls="s",
                     anchor="middle"))
    p.append(f'  <text class="b" x="500" y="252" fill="{GOOD}">'
             f'五次都在阈值下面，门禁一次都不会响</text>')
    p.append(txt(500, 276, "而它们连乘起来已经是 1.26 倍", cls="s"))

    # 右栏：阈值本身怎么定
    p.append(card(824, 158, 400, 220, cls="card", rx=16))
    p.append(txt(848, 190, "那条 8% 的线是怎么定的", cls="h"))
    p.append(txt(848, 222, "28.3：阈值不能低于可识别线（各 3 轮约 2.3 × CV）", cls="s"))
    p.append(f'  <text class="b" x="848" y="256" fill="{BAD}">'
             f'变异系数 9%：5% 的阈值没法用</text>')
    p.append(f'  <text class="b" x="848" y="292" fill="{GOOD}">'
             f'压到 2.6% 之后：8% 稳定可用</text>')
    single = CASE_GOOD["single_run"]
    triple = CASE_GOOD["three_runs"]
    p.append(txt(848, 318,
                 f"推荐 {CASE_GOOD['recommended']:.0%}，单指标误报约 "
                 f"{single['false_alarm_per_metric']:.1%}", cls="s"))
    p.append(txt(848, 344,
                 f"各跑 3 轮时 10% 回归检出约 {triple['detection']:.0%}", cls="s"))

    p.append(card(824, 398, 400, 176, cls="warnfill", rx=16))
    p.append(txt(848, 430, "两个数不能混", cls="h"))
    p.append(txt(848, 462, f"五步连乘 = {five:.2f} 倍", cls="b"))
    p.append(txt(848, 488, "结论是“门禁一次都不会响”", cls="s"))
    p.append(txt(848, 520, f"半年十三次连乘 = {last:.2f} 倍", cls="b"))
    p.append(txt(848, 546, "结论是“系统慢了将近一倍”", cls="s"))

    p.append(note(56, 588, 1168, [
        f"每次 5% 要 {TO_DOUBLE_5:.1f} 次翻倍，每次 8% 只要 {TO_DOUBLE_8:.1f} 次。"
        f"门禁拦的是单次，而用户感受到的是累积，所以基线要固定：相对阈值对着那份冻结的基线算，绝对阈值另外兜住 SLO。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="每一次都在阈值下面，累积起来不在",
        desc="上半部分是五根柱子，分别是 5%、4%、6%、5%、4% 的单次退化，"
             "一条虚线画在门禁阈值 8% 处，五根都在线下，所以门禁一次都不会响。"
             "下半部分是累积曲线，横轴是改动次数 0 到 13，纵轴是累积倍数 1.0 到 2.2，"
             "第 5 次落在 1.26 倍，第 13 次落在 1.89 倍，一条虚线标出翻倍线。"
             "右上一块讲那条 8% 的线怎么定：变异系数 9% 时 5% 的阈值没法用，"
             "压到 2.6% 之后 8% 稳定可用，单指标误报约 1.5%，两边各跑 3 轮时 10% 的回归"
             "约 83% 被拦住。右下一块强调 1.26 倍和 1.89 倍是两个数，"
             "前者的结论是门禁不会响，后者的结论是系统慢了将近一倍。",
        kicker="第 28 章 · 28.1、28.3、28.8",
        heading="门禁拦的是单次，用户感受到的是累积",
        sub=f"5% 每次要 {TO_DOUBLE_5:.1f} 次才翻倍，两周一次的发布半年就有十三次",
        body="\n".join(p),
        takeaway=f"五步连乘是 {five:.2f} 倍，半年十三步是 {last:.2f} 倍：这两个数不能混用",
    )


FIGS = [
    ("fig28-01_compounding", fig1,
     dict(title="图28-1 每一次都在阈值下面，累积起来不在",
          source="28.1、28.3、28.8",
          order="先看上排五根柱子和那条阈值虚线，再顺着累积曲线读第 5 次和第 13 次两个落点，然后看右上那条 8% 是怎么定的、它的误报率和检出率",
          takeaway="五步连乘是 1.26 倍，半年十三步是 1.89 倍：这两个数不能混用",
          boundary="合成设定，五步的幅度是设定值；曲线由 code/ch28/perf_gate.py 的 drift 在构建时算出。它假设每次退化独立且乘性叠加，真实项目里有的改动会互相抵消，也有的会互相放大，所以这条曲线给的是机制不是预测")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
