"""Build the Chapter 27 figure set defined in strategy/reviews/ch27/storyboard.md.

  fig27-01  27.4 的回路滞后和 27.5 那三类变化画在同一根时间轴上。滞后是一条带，
            两倍滞后是一条门槛线，三类变化按各自的持续时间落在轴上，谁在门槛
            左边谁就交给不了弹性。右侧是同一条轨迹上四种策略的结果。

滞后的三段、门槛的两倍、四种策略的数都由 code/ch27/autoscale_sim.py 在构建时
算出来，图不可能报出一个仿真给不出的结论。

Run from the repository root:

    python3 content/ch27/figures/build_figures.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch27"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, MUTED, WARN, card, dashed, note, page, txt, write,
    write_note,
)
import autoscale_sim as asim  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

TRACE_PATH = ROOT / "content" / "ch27" / "evidence" / "traffic-trace-sample.csv"
TRACE = asim.load_trace(TRACE_PATH)
BASE = dict(capacity_per_instance=150, scale_up_threshold=0.7,
            scale_down_threshold=0.4, cold_start_s=300, observation_s=60,
            decision_s=60, scale_up_cooldown_s=180,
            scale_down_cooldown_s=1800, min_instances=3, max_instances=30)
LAG = asim.loop_lag()
COMPARE = asim.compare(TRACE, BASE)
SCALE = COMPARE["trace"]

# 27.5 那三类变化，按持续时间落在轴上。
KINDS = [
    ("突发", 30, 120, BAD, "秒到分钟", "弹性追不上，交给准入和排队"),
    ("日内波峰与小时级增长", 3600, 21600, GOOD, "小时",
     "可预测的用定时扩缩容，不可预测的交给弹性"),
    ("长期增长", 604800, 2592000, COOL, "周到月", "该做容量规划（第 26 章），不是弹性"),
]


def fig1() -> str:
    p = []
    p.append(card(56, 158, 744, 416, cls="card", rx=16))
    p.append(txt(80, 190, "横轴是变化持续的时间，对数刻度", cls="b"))

    x0, x1 = 128, 768
    lo, hi = math.log10(20), math.log10(2592000)

    def px(t):
        return x0 + (math.log10(t) - lo) / (hi - lo) * (x1 - x0)

    axis_y = 500
    p.append(f'  <path d="M{x0} {axis_y}H{x1}" stroke="#94A3B8" '
             f'stroke-width="1.8"/>')
    for t, label in ((60, "1 分"), (600, "10 分"), (3600, "1 时"),
                     (86400, "1 天"), (604800, "1 周")):
        xx = px(t)
        p.append(f'  <path d="M{xx:.1f} {axis_y}V{axis_y + 6}" '
                 f'stroke="#94A3B8" stroke-width="1.4"/>')
        p.append(txt(xx, axis_y + 26, label, cls="s", anchor="middle"))

    # 回路滞后带
    lx0, lx1 = px(LAG["low_s"]), px(LAG["high_s"])
    p.append(f'  <rect x="{lx0:.1f}" y="222" width="{lx1 - lx0:.1f}" '
             f'height="{axis_y - 222}" fill="{WARN}" opacity="0.12"/>')
    p.append(txt((lx0 + lx1) / 2, 214,
                 f"回路滞后 {LAG['low_min']:.0f} 到 {LAG['high_min']:.1f} 分",
                 cls="b", anchor="middle"))

    # 两倍门槛
    tx = px(LAG["actionable_threshold_min"] * 60)
    p.append(dashed(tx, 222, tx, axis_y))
    p.append(f'  <text class="b" x="{tx + 10:.1f}" y="244" fill="{WARN}">'
             f'门槛 {LAG["actionable_threshold_min"]:.0f} 分</text>')
    p.append(txt(tx + 10, 268, "右边才值得交给弹性", cls="s"))

    # 三类变化
    y = 300
    for label, t_lo, t_hi, colour, scale_label, verdict in KINDS:
        bx0, bx1 = px(t_lo), px(t_hi)
        p.append(f'  <rect x="{bx0:.1f}" y="{y}" width="{bx1 - bx0:.1f}" '
                 f'height="22" rx="8" fill="{colour}" opacity="0.28" '
                 f'stroke="{colour}" stroke-width="1.6"/>')
        right = bx1 > 600
        anchor = "end" if right else "start"
        ax = bx1 if right else bx0
        p.append(f'  <text class="b" x="{ax:.1f}" y="{y - 10}" '
                 f'text-anchor="{anchor}" fill="{colour}">'
                 f'{label}（{scale_label}）</text>')
        p.append(txt(ax, y + 42, verdict, cls="s", anchor=anchor))
        y += 66

    # 滞后取这次模拟实际用的那个（观测+决策+冷启动），不是 27.4 那张表的上界 810 秒，
    # 否则图和正文、模拟输出各给一个数（Part 6 审阅 P1-13）。
    sim_lag = BASE["observation_s"] + BASE["decision_s"] + BASE["cold_start_s"]
    p.append(f'  <text class="b" x="80" y="{axis_y + 62}" fill="{BAD}">'
             f'样例轨迹那次突发只持续 {SCALE["surge_duration_s"]:.0f} 秒，'
             f'比这次模拟的滞后 {sim_lag:.0f} 秒还短'
             f'（滞后下限也有 {LAG["low_s"]:.0f} 秒）</text>')

    # 右栏：四种策略
    p.append(card(824, 158, 400, 264, cls="card", rx=16))
    p.append(txt(848, 190, "同一条轨迹，四种策略", cls="h"))
    p.append(txt(848, 218, "未满足需求", cls="s"))
    p.append(txt(1096, 218, "成本", cls="s"))
    yy = 246
    for row in COMPARE["strategies"]:
        colour = GOOD if row["unmet_demand"] == 0 else BAD
        p.append(txt(848, yy + 14, row["strategy"], cls="b"))
        p.append(f'  <text class="m" x="1000" y="{yy + 14}" '
                 f'text-anchor="end" fill="{colour}">'
                 f'{row["unmet_demand"] / 1000:.0f}k</text>')
        p.append(f'  <text class="m" x="1180" y="{yy + 14}" '
                 f'text-anchor="end">{row["cost_index"]:.0f}</text>')
        yy += 40

    p.append(card(824, 442, 400, 132, cls="goodfill", rx=16))
    p.append(txt(848, 474, "读法", cls="h"))
    p.append(txt(848, 506, "三种靠扩缩容的策略都漏了那一段，", cls="s"))
    p.append(txt(848, 532, "而只做准入的那一列未满足为零，", cls="s"))
    p.append(f'  <text class="b" x="848" y="560" fill="{GOOD}">'
             f'成本还更低</text>')

    p.append(note(56, 588, 1168, [
        "弹性不是没用，它在趋势那一段都跟得上。这张图说的是：突发那一段不该交给它，"
        "因为无论指标选得多好、阈值调得多准，回路的三段滞后都还在。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="变化比回路快时，弹性就调不了",
        desc="主图是一根对数时间轴，从 20 秒到一个月，刻度标出 1 分、10 分、1 时、1 天、1 周。"
             "一条竖带标出回路滞后 4 到 13.5 分钟，一条竖虚线标出两倍滞后 27 分钟的门槛，"
             "门槛右边才值得交给弹性。三类变化按持续时间画成三条横条："
             "突发 30 秒到 2 分钟，落在滞后带左边，要交给准入和排队；"
             "日内波峰与小时级增长 1 到 6 小时，落在门槛右边，可预测的用定时扩缩容、"
             "不可预测的交给弹性；长期增长 1 周到 1 个月，该做容量规划。"
             "右栏是同一条轨迹上四种策略的未满足需求和成本："
             "三种扩缩容策略都有十万量级的未满足，只做准入的那一种未满足为零、成本最低。",
        kicker="第 27 章 · 27.4、27.5",
        heading="弹性能不能用，取决于变化比回路快还是慢",
        sub=f"回路滞后 {LAG['low_min']:.0f} 到 {LAG['high_min']:.1f} 分钟，"
            f"经验上取两倍，{LAG['actionable_threshold_min']:.0f} 分钟以上的变化才值得交给它",
        body="\n".join(p),
        takeaway="突发那一段不该交给弹性：轨迹上 99% 的未满足需求都在那 90 秒里",
    )


FIGS = [
    ("fig27-01_time_scales", fig1,
     dict(title="图27-1 变化比回路快时，弹性就调不了",
          source="27.4、27.5",
          order="先找到中间那条回路滞后带和它右边的门槛线，再看三类变化各自落在门槛的哪一边，最后读右栏四种策略的未满足与成本",
          takeaway="突发那一段不该交给弹性：轨迹上 99% 的未满足需求都在那 90 秒里",
          boundary="滞后的三段来自 code/ch27/autoscale_sim.py 的默认配置，冷启动压到秒级后整条带会左移，门槛也跟着左移；四种策略的数是在仓库里那条合成轨迹上跑出来的，换一条突发形状不同的轨迹，admission-only 的优势会变小")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
