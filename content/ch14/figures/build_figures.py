"""Build the Chapter 14 figure set defined in strategy/reviews/ch14/storyboard.md.

The four rounds and their numbers come from
content/ch14/evidence/prefill-experiment-sample.json, which is synthetic data.
The figures say so where a number appears.

Run from the repository root:

    python3 content/ch14/figures/build_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch14"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, MUTED, WARN, arrow, bar, card, dashed, hpath, note, page,
    txt, vpath, write, write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

SAMPLE = json.loads(
    (ROOT / "content" / "ch14" / "evidence" / "prefill-experiment-sample.json")
    .read_text(encoding="utf-8"))
ROUNDS = SAMPLE["rounds"]


# --- 图14-1 四轮各看什么，各自的护栏是什么 -----------------------------------

def fig1() -> str:
    p = []
    # shared baseline
    p.append(card(72, 262, 168, 196, cls="soft", rx=14))
    p.append(txt(156, 300, "同一个", cls="b", anchor="middle"))
    p.append(txt(156, 328, "Baseline", cls="h", anchor="middle"))
    p.append(txt(156, 362, "四轮都从", cls="s", anchor="middle"))
    p.append(txt(156, 384, "这里出发", cls="s", anchor="middle"))
    p.append(txt(156, 424, "重启后测的", cls="s", anchor="middle"))

    rows = [
        ("1", "Top-K 10 → 6", "TTFT P50", "质量分、TTFT P95", COOL),
        ("2", "启用 Prefix Cache", "TTFT P50", "显存、并发上限", COOL),
        ("3", "确认 Attention 实现", "TTFT P50", "输出质量分不变", COOL),
        ("4", "启用 Chunked Prefill", "短请求的 ITL", "长请求 TTFT（预期变差）", WARN),
    ]
    y0, rh = 252, 92
    p.append(txt(320, 226, "轮次", cls="b"))
    p.append(txt(400, 226, "改动项", cls="b"))
    p.append(txt(700, 226, "主指标", cls="b"))
    p.append(txt(940, 226, "护栏（不是可选项）", cls="b"))
    for i, (n, change, metric, guard, colour) in enumerate(rows):
        y = y0 + i * rh
        p.append(hpath(244, y + 34, 300))
        p.append(card(300, y, 924, 74, cls="card", rx=12))
        p.append(txt(320, y + 44, n, cls="h"))
        p.append(txt(400, y + 44, change, cls="b"))
        p.append(f'  <text class="b" x="700" y="{y + 44}" fill="{colour}">{metric}</text>')
        p.append(txt(940, y + 44, guard, cls="s"))
    # the row that is different
    p.append(f'  <rect x="300" y="{y0 + 3 * rh}" width="924" height="74" rx="12" '
             f'fill="none" stroke="{WARN}" stroke-width="3"/>')
    p.append(txt(700, y0 + 3 * rh + 66, "不是 TTFT", cls="s"))

    p.append(card(72, 486, 168, 124, cls="coolfill", rx=14))
    p.append(txt(92, 518, "固定件", cls="b"))
    p.append(txt(92, 544, "workload", cls="m"))
    p.append(txt(92, 568, "protocol", cls="m"))
    p.append(txt(92, 592, "environment", cls="m"))

    p.append(txt(300, 626, "第 4 轮若把主指标写成长请求 TTFT，结论会反；第 3 轮的护栏是一个很好的自检点：输出变了说明走的不是同一条路径。", cls="s"))
    return page(
        system=SYSTEM,
        title="图 14-1 四轮各看什么，各自的护栏是什么",
        desc="四轮实验从同一个 Baseline 出发，每行列出改动项、主指标与护栏；"
             "第 4 轮的主指标是短请求的 ITL 而不是长请求 TTFT，用加框强调；"
             "左下列出 workload、protocol、environment 三组固定件。",
        kicker="CH14 · 14.4",
        heading="四轮各看什么，各自的护栏是什么",
        sub="每一轮的主指标真的是同一个吗",
        body="\n".join(p),
        takeaway="四轮的主指标不是同一个；护栏那一列不是可选项。",
    )


# --- 图14-2 四种结论，第四种最容易被改写 -------------------------------------

def fig2() -> str:
    p = []
    # troubleshooting order on top
    p.append(card(72, 176, 1152, 84, cls="soft", rx=14))
    p.append(txt(96, 206, "对不上的时候，按这个顺序排查（顺序不能颠倒）", cls="b"))
    steps = ["1 越过可识别线了吗", "2 有变量泄漏吗", "3 前提条件满足吗", "4 最后才怀疑预期"]
    for i, s_ in enumerate(steps):
        x = 96 + i * 280
        p.append(txt(x, 242, s_, cls="m"))
        if i < 3:
            p.append(hpath(x + 216, 237, x + 262))

    # step 1: |improvement| against the line
    p.append(txt(72, 300, "第一步：改善越过可识别线了吗", cls="b"))
    ax_y = 380
    l0, l1 = 92, 412

    def sx(v):  # -10% .. +10%
        return l0 + (v + 10) / 20 * (l1 - l0)

    p.append(bar(sx(-2.5), ax_y - 16, sx(2.5) - sx(-2.5), 32, cls="soft", rx=6))
    p.append(f'  <path d="M{l0} {ax_y}H{l1}" fill="none" stroke="#94A3B8" stroke-width="2"/>')
    p.append(txt(sx(0), ax_y - 40, "±2.5% 以内：在波动内不可分辨", cls="s", anchor="middle"))
    p.append(f'  <circle cx="{sx(-0.4):.1f}" cy="{ax_y}" r="9" fill="{MUTED}"/>')
    p.append(f'  <text class="mb" x="{sx(-0.4):.1f}" y="{ax_y + 34}" text-anchor="middle" fill="{MUTED}">−0.4%</text>')
    p.append(txt(sx(-0.4), ax_y + 58, "第 3 轮　确认 Attention 实现", cls="s", anchor="middle"))
    for v, lab in ((-10, "−10%"), (0, "0"), (10, "+10%")):
        p.append(txt(sx(v), ax_y + 84, lab, cls="m", anchor="middle"))

    # the thing that must not happen
    p.append(f'  <rect x="92" y="{ax_y + 104}" width="180" height="40" rx="10" '
             f'fill="#FEF2F2" stroke="{BAD}" stroke-width="1.8"/>')
    p.append(f'  <text class="b" x="182" y="{ax_y + 130}" text-anchor="middle" '
             f'fill="{BAD}">小幅有效</text>')
    p.append(f'  <path d="M100 {ax_y + 142}L264 {ax_y + 106}" stroke="{BAD}" stroke-width="3"/>')
    p.append(txt(92, ax_y + 172, "灰带里的结论不是失败，硬写成“小幅有效”", cls="s"))
    p.append(txt(92, ax_y + 194, "是在用噪声支撑结论。", cls="s"))

    # step 2: observed minus expected, judged by the same line
    p.append(txt(476, 300, "第二步：改善 − 预期，拿同一条线衡量", cls="b"))
    r0, r1 = 496, 1200

    def gx(v):  # -25 .. +15 percentage points
        return r0 + (v + 25) / 40 * (r1 - r0)

    p.append(bar(gx(-2.5), ax_y - 16, gx(2.5) - gx(-2.5), 32, cls="goodfill", rx=6))
    p.append(f'  <path d="M{r0} {ax_y}H{r1}" fill="none" stroke="#94A3B8" stroke-width="2"/>')
    p.append(txt(gx(0), ax_y - 40, "符合预期", cls="b", anchor="middle"))
    p.append(txt((r0 + gx(-2.5)) / 2, ax_y - 40, "低于预期", cls="b", anchor="middle"))
    p.append(txt((gx(2.5) + r1) / 2 + 20, ax_y - 40, "高于预期", cls="b", anchor="middle"))
    pts = [
        (-20.1, "29.9%", "预期 50%", "第 4 轮　Chunked Prefill", WARN),
        (-0.1, "33.2%", "预期 33.3%", "第 1 轮　Top-K 10 → 6", GOOD),
        (7.7, "15.7%", "预期 8%", "第 2 轮　Prefix Cache", COOL),
    ]
    for v, obs, exp, what, colour in pts:
        x = gx(v)
        anchor = "end" if v < 3 and v > -3 else ("start" if v >= 3 else "middle")
        dx = 6 if anchor == "end" else (-6 if anchor == "start" else 0)
        p.append(f'  <circle cx="{x:.1f}" cy="{ax_y}" r="9" fill="{colour}"/>')
        p.append(f'  <text class="mb" x="{x + dx:.1f}" y="{ax_y + 40}" text-anchor="{anchor}" fill="{colour}">实测 {obs}</text>')
        p.append(txt(x + dx, ax_y + 62, exp, cls="s", anchor=anchor))
        p.append(txt(x + dx, ax_y + 84, what, cls="s", anchor=anchor))
    p.append(txt(r1, ax_y + 110, "改善 − 预期（百分点）→", cls="s", anchor="end"))

    p.append(note(476, ax_y + 128, 748, [
        "可识别线 = t × √(2/n) × CV，三轮对三轮约 2.3 × 变异系数，不是极差",
        "合成样例：TTFT P50 那条线 2.5%，第 4 轮短请求 ITL 那条线 4.2%",
    ], h=78))
    return page(
        system=SYSTEM,
        title="图 14-2 四种结论，第四种最容易被改写",
        desc="上方是对不上时的排查顺序。左侧第一步：改善幅度和可识别线比，第 3 轮 −0.4% 落在 ±2.5% 的灰带里，"
             "结论是在波动内不可分辨，下方画出被划掉的“小幅有效”。右侧第二步：改善减预期，拿同一条线衡量，"
             "合成样例第 1 轮差 −0.1 个百分点为符合预期，第 2 轮差 +7.7 为高于预期，第 4 轮差 −20.1 为低于预期。",
        kicker="CH14 · 14.5、14.7",
        heading="四种结论，第四种最容易被改写",
        sub="同一条可识别线用两次：先判有没有变化，再判和预期差多少",
        body="\n".join(p),
        takeaway="可识别线决定了这次实验能说什么；测不出来是一个合法且诚实的结论。",
    )


# --- 图14-3 四项边界与各自的失效方式 -----------------------------------------

def fig3() -> str:
    p = []
    cx, cy = 640, 386
    p.append(f'  <circle cx="{cx}" cy="{cy}" r="88" fill="#0F172A"/>')
    p.append(f'  <text class="hw" x="{cx}" y="{cy - 6}" text-anchor="middle">收益 33%</text>')
    p.append(f'  <text class="sw" x="{cx}" y="{cy + 20}" text-anchor="middle">合成样例第 1 轮</text>')

    sides = [
        ("模型", 72, 206, 452, 130, BAD, True,
         ["交叉点 0.5B 16640 → 7B 65024", "同样 3000 token 的负载上",
          "Attention 占比 15.3% → 4.4%"]),
        ("负载", 756, 206, 468, 130, WARN, False,
         ["换成短 prompt，注意力矩阵", "1710 MiB → 10 MiB，",
          "FlashAttention 的收益缩水"]),
        ("硬件", 72, 466, 452, 130, WARN, False,
         ["单副本变多副本，命中率被路由除一刀；", "换 GPU 可能翻转算力受限",
          "还是带宽受限的判断"]),
        ("配置", 756, 466, 468, 130, WARN, False,
         ["temperature、缓存状态、分位数算法，", "任一不同，两个数字就只是长得像"]),
    ]
    for name, x, y, w, h, colour, thick, lines in sides:
        sw = 3 if thick else 1.8
        fill = "#FEF2F2" if thick else "#FFFBEB"
        p.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" '
                 f'fill="{fill}" stroke="{colour}" stroke-width="{sw}"/>')
        p.append(f'  <text class="h" x="{x + 22}" y="{y + 34}" fill="{colour}">{name}</text>')
        for i, line in enumerate(lines):
            p.append(txt(x + 22, y + 66 + 24 * i, line, cls="s"))
        ax = x + w + 8 if x < cx else x - 8
        ay = y + h / 2
        tx = cx - 94 if x < cx else cx + 94
        ty = cy - 46 if y < cy else cy + 46
        p.append(arrow(ax, ay, tx, ty))

    p.append(txt(cx, 622, "没有边界说明的收益数字，会被当成普适结论到处引用", cls="b", anchor="middle"))
    return page(
        system=SYSTEM,
        title="图 14-3 四项边界与各自的失效方式",
        desc="中间是合成样例第 1 轮的收益 33%，四项边界从四个方向把它框住："
             "模型给出两个交叉点与 Attention 占比的变化，负载给出注意力矩阵的两档，"
             "硬件是路由与卡的差别，配置是三样容易漏掉的东西。",
        kicker="CH14 · 14.6",
        heading="四项边界与各自的失效方式",
        sub="这个收益数字能推广到哪里",
        body="\n".join(p),
        takeaway="收益绑定四个条件，报告里要带上交叉点这类具体数字，别人才判断得了能不能套用。",
    )


FIGURES = {
    "fig14-01_four_rounds.svg": (
        fig1,
        dict(title="图 14-1 制作说明：四轮各看什么，各自的护栏是什么",
             source="第 14.4 节，四轮取自 content/ch14/evidence/prefill-experiment-sample.json。",
             order="先看左边那个共用的 Baseline，再逐行读改动项、主指标、护栏，最后停在加框的第 4 行。",
             takeaway="四轮的主指标不是同一个；护栏那一列不是可选项。",
             boundary="不给收益数字（那是图 14-2），不出现具体框架参数名。"),
    ),
    "fig14-02_four_verdicts.svg": (
        fig2,
        dict(title="图 14-2 制作说明：四种结论，第四种最容易被改写",
             source="第 14.5、14.7 节。四个点是合成样例四轮的实测改善，图内已标注。",
             order="先读上方的排查顺序，再看左侧第一步的灰带和落在里面的第 3 轮，然后看右侧第二步三个点各落在哪个区间，最后看被划掉的那个标签。",
             takeaway="可识别线决定了这次实验能说什么；测不出来是一个合法且诚实的结论。",
             boundary="判据一律用可识别线（t × √(2/n) × 变异系数，三轮对三轮约 2.3 倍），不用极差；灰带不画成红色警告，它是一个正常结论；右轴是改善减预期，不是改善本身。"),
    ),
    "fig14-03_boundary_four_axes.svg": (
        fig3,
        dict(title="图 14-3 制作说明：四项边界与各自的失效方式",
             source="第 14.6 节与 14.8 案例三。交叉点两个数可用 code/ch11/prefill_model.py 复算。",
             order="先看中间那个收益数字，再逐个读四项边界“换了它会怎样”，注意模型那一条的线更粗。",
             takeaway="收益绑定四个条件，报告里要带上交叉点这类具体数字，别人才判断得了能不能套用。",
             boundary="不出现具体显卡型号与规格；四项边界是必填项，不画成可选清单。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
