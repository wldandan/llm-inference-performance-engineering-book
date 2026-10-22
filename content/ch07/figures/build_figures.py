"""Build the Chapter 7 figure set defined in strategy/reviews/ch07/storyboard.md.

Run from the repository root:

    python3 content/ch07/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    arrow, bar, card, dashed, hpath, note, page, txt, vpath, write, write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"


def fig1() -> str:
    p = []
    y = 216
    segs = [
        ("服务启动", 150, "soft"),
        ("就绪检查", 150, "soft"),
        ("Warmup", 170, "warnfill"),
        ("测量窗口", 430, "coolfill"),
        ("冷却", 176, "soft"),
    ]
    x = 72
    win_x = win_w = 0
    for name, w, cls in segs:
        p.append(bar(x, y, w, 62, cls=cls if cls != "soft" else "soft"))
        p.append(txt(x + w / 2, y + 38, name, cls="b", anchor="middle"))
        if name == "测量窗口":
            win_x, win_w = x, w
        x += w + 8
    p.append(txt(x - 8 + 16, y + 38, "", cls="s"))

    # window endpoints
    p.append(vpath(win_x, y + 62, y + 106, cls="flow"))
    p.append(vpath(win_x + win_w, y + 62, y + 106, cls="flow"))
    p.append(txt(win_x, y + 132, "第一个计数请求发出", cls="s", anchor="middle"))
    p.append(txt(win_x + win_w, y + 132, "最后一个计数请求完成", cls="s", anchor="middle"))
    p.append(txt(640, 190, "Warmup 和冷却都在窗口外", cls="s", anchor="middle"))

    # in-flight at the tail
    p.append(txt(72, 400, "窗口末尾还有 18 条请求已发出、未返回，两种算法：", cls="b"))
    p.append(card(72, 424, 528, 168, cls="card", rx=16))
    p.append(txt(96, 458, "排除", cls="h"))
    p.append(txt(96, 494, "完成 1182 条 ÷ 60 秒", cls="m"))
    p.append(txt(96, 524, "= 19.70 req/s", cls="mb"))
    p.append(txt(96, 562, "占用了资源却不计入产出，吞吐偏低", cls="s"))
    p.append(card(680, 424, 528, 168, cls="card", rx=16))
    p.append(txt(704, 458, "算完", cls="h"))
    p.append(txt(704, 494, "完成 1200 条 ÷ 62.4 秒", cls="m"))
    p.append(txt(704, 524, "= 19.23 req/s", cls="mb"))
    p.append(txt(704, 562, "窗口比设定时长长，分母要跟着改", cls="s"))
    p.append(f'  <path class="bracket" d="M640 448V568"/>')
    p.append(txt(640, 492, "差", cls="s", anchor="middle"))
    p.append(txt(640, 518, "2.4%", cls="b", anchor="middle"))

    p.append(txt(72, 618, "窗口缩到 10 秒、在途仍是 18 条时，两者相差 11%，和吞吐自己那条可识别线是一个量级", cls="s"))
    return page(
        system=SYSTEM,
        title="图 7-2 测量窗口的两端与窗外那几段",
        desc="一条运行时间线标出服务启动、就绪检查、Warmup、测量窗口与冷却；窗口两端是首末计数请求；窗口末尾 18 条在途请求的两种算法分别得到 19.70 与 19.23 req/s。",
        kicker="MEASUREMENT WINDOW · 07",
        heading="测量窗口的两端与窗外那几段",
        sub="窗口的起点和终点要写成具体事件，不是“大概一分钟”",
        body="\n".join(p),
        takeaway="窗口越短、在途占比越高，在途请求的算法选择越要紧。",
    )


def fig2() -> str:
    p = []
    # number line for three runs
    ax_y = 250
    p.append(txt(72, 186, "三轮 TTFT P95", cls="b"))
    p.append(f'  <path d="M120 {ax_y}H700" stroke="#94A3B8" stroke-width="1.6" fill="none"/>')
    for x, v in ((160, 210), (536, 235), (280, 218)):
        p.append(f'  <circle cx="{x}" cy="{ax_y}" r="8" fill="#1D4ED8"/>')
        p.append(txt(x, ax_y - 18, v, cls="mb", anchor="middle"))
    p.append(f'  <path class="bracket" d="M160 {ax_y + 22}V{ax_y + 34}"/>')
    p.append(f'  <path class="bracket" d="M536 {ax_y + 22}V{ax_y + 34}"/>')
    p.append(f'  <path class="bracket" d="M160 {ax_y + 34}H536"/>')
    p.append(txt(348, ax_y + 58, "极差 25 ms，均值 221 ms", cls="s", anchor="middle"))

    # conversion to the line
    p.append(card(72, 344, 636, 190, cls="card", rx=16))
    p.append(txt(96, 380, "极差带单位，只由两个极端点决定，所以换成不带单位的量", cls="s"))
    rows = [("标准差", "12.8 ms　除以 n−1"), ("CV", "12.8 ÷ 221 ≈ 5.8%"),
            ("差值波动", "CV × √(2/3)，三轮对三轮"), ("可识别线", "t × √(2/3) × CV ≈ 2.3 × CV ≈ 13%")]
    for i, (k, v) in enumerate(rows):
        p.append(txt(96, 418 + 30 * i, k, cls="b"))
        p.append(txt(230, 418 + 30 * i, v, cls="m"))
    p.append(txt(96, 560, "除以 n 得 10.4 ms，可识别线随之约 11%，所以口径必须写明", cls="s"))

    # case one: means, then the interval of the difference
    p.append(txt(748, 186, "7.8 案例一：两组各跑三轮", cls="b"))
    lo, hi = 170, 250

    def px(v):
        return 860 + (v - lo) / (hi - lo) * 340

    for name, vals, ycc, mean in (
        ("基线", (210, 238, 225), 236, 224.3),
        ("优化后", (180, 228, 214), 300, 207.3),
    ):
        p.append(txt(748, ycc + 6, name, cls="b"))
        p.append(f'  <path d="M{px(lo):.0f} {ycc}H{px(hi):.0f}" stroke="#CBD5E1" stroke-width="1.4" fill="none"/>')
        for v in vals:
            p.append(f'  <circle cx="{px(v):.0f}" cy="{ycc}" r="5" fill="#334155"/>')
        p.append(f'  <path d="M{px(mean):.0f} {ycc - 12}V{ycc + 12}" stroke="#1D4ED8" stroke-width="3" fill="none"/>')
        p.append(txt(px(mean), ycc - 18, f"均值 {mean}", cls="m", anchor="middle"))

    # difference interval: 17 ms, half width = pooled line 45.5 ms (7.8 案例一)
    d_lo, d_hi = -50, 80

    def dx(v):
        return 860 + (v - d_lo) / (d_hi - d_lo) * 340

    y0 = 372
    p.append(txt(748, y0 + 6, "差值", cls="b"))
    p.append(f'  <path d="M{dx(d_lo):.0f} {y0}H{dx(d_hi):.0f}" stroke="#94A3B8" stroke-width="1.6" fill="none"/>')
    p.append(bar(dx(-28.5), y0 - 12, dx(62.5) - dx(-28.5), 24, cls="warnfill", rx=4))
    p.append(f'  <path d="M{dx(0):.0f} {y0 - 26}V{y0 + 26}" stroke="#B91C1C" stroke-width="2.4" fill="none"/>')
    p.append(txt(dx(0), y0 + 46, "0", cls="mb", anchor="middle"))
    p.append(f'  <circle cx="{dx(17):.0f}" cy="{y0}" r="6" fill="#1D4ED8"/>')
    p.append(txt(dx(50), y0 + 46, "17 ms ± 45 ms", cls="m", anchor="middle"))
    p.append(note(748, 430, 460, [
        "均值改善 (224.3 − 207.3) ÷ 224.3 ≈ 7.6%",
        "两组合并的可识别线 2.78 × √(2/3) × 20 ms ≈ 45 ms",
        "差值区间跨过 0，结论是分辨不出来",
    ]))
    p.append(txt(748, 572, "那个 14% 是拿单轮 210 比单轮 180 得来的", cls="s"))
    p.append(txt(748, 598, "而 180 恰好是优化后三轮里最好的一个", cls="s"))
    return page(
        system=SYSTEM,
        title="图 7-1 三轮结果与可识别线",
        desc="左侧把 210、235、218 三轮换算成均值 221、标准差 12.8、CV 5.8%，再按三轮对三轮乘 2.3 得到可识别线约 13%；右侧是 7.8 案例一，两组 CV 相差近一倍，按合并波动算出的可识别线约 45 ms，差值区间 17 ± 45 ms 跨过 0，7.6% 的改善分辨不出来。",
        kicker="DETECTABLE DIFFERENCE · 07",
        heading="三轮结果与可识别线",
        sub="极差是看到的波动，可识别线是由 CV 和轮数推出的判据，两者不是一回事",
        body="\n".join(p),
        takeaway="差值的区间跨过 0，结论是分辨不出来，不是有改善。",
    )


def fig3() -> str:
    p = []
    blocks = [
        ("workload", ["第 6 章那份描述", "含随机种子"],
         "缺种子：生成的是另一批请求", "长度分布对不上，差异被误读"),
        ("protocol", ["Warmup 数量与是否排除", "轮次、窗口、在途处理"],
         "缺窗口定义：不知道分母怎么算", "吞吐差几个百分点，短窗口更大"),
        ("environment", ["Python / vLLM 版本", "模型名与 revision", "GPU、驱动、启动命令"],
         "缺 revision：可能拉到另一版权重", "整份对比作废"),
        ("results", ["每轮原始记录", "统计摘要"],
         "缺原始记录：只能看结论", "换分位数算法或分桶都做不到"),
    ]
    x = 72
    for name, items, blocked, cost in blocks:
        p.append(card(x, 176, 266, 206, cls="card", rx=16))
        p.append(txt(x + 133, 214, name, cls="mb", anchor="middle"))
        for i, it in enumerate(items):
            p.append(txt(x + 20, 252 + 28 * i, it, cls="s"))
        p.append(vpath(x + 133, 382, 416, cls="flow"))
        p.append(card(x, 420, 266, 128, cls="warnfill", rx=14))
        p.append(txt(x + 20, 454, "同事卡在哪", cls="b"))
        p.append(txt(x + 20, 482, blocked, cls="s"))
        p.append(txt(x + 20, 518, cost, cls="s"))
        x += 288
    p.append(note(72, 566, 1136, [
        "判断标准只有一句：把这份报告交给一个没参与过实验的同事，他能不能重跑出接近的数字",
    ]))
    return page(
        system=SYSTEM,
        title="图 7-4 Baseline 报告的四块与缺一块的后果",
        desc="workload、protocol、environment、results 四块各列必填项，每块下方对应“缺了它同事会卡在哪一步”和它带来的后果。",
        kicker="BASELINE CONTRACT · 07",
        heading="Baseline 报告的四块与缺一块的后果",
        sub="前三块决定能不能重跑，第四块决定重跑之后能不能重新分析",
        body="\n".join(p),
        takeaway="缺任何一块，这份 Baseline 就不该再被引用。",
    )


def fig4() -> str:
    p = []
    # two压测 rows
    p.append(card(72, 176, 1136, 128, cls="card", rx=16))
    p.append(txt(96, 214, "一千次同一句 prompt", cls="h"))
    p.append(txt(96, 246, "第二个请求开始命中 Prefix Cache", cls="s"))
    p.append(bar(430, 196, 40, 40, cls="coolfill"))
    p.append(txt(450, 222, "算", cls="s", anchor="middle"))
    for i in range(6):
        p.append(bar(484 + i * 46, 196, 40, 40, cls="soft"))
        p.append(txt(504 + i * 46, 222, "命中", cls="s", anchor="middle"))
    p.append(txt(646, 276, "Prefill 几乎不用算", cls="s", anchor="middle"))
    p.append(card(852, 192, 332, 96, cls="badfill", rx=14))
    p.append(txt(876, 230, "TTFT P50 约 12 ms", cls="mb"))
    p.append(txt(876, 262, "测的是缓存查找加一次采样", cls="s"))

    p.append(card(72, 324, 1136, 128, cls="card", rx=16))
    p.append(txt(96, 362, "一千句不同 prompt", cls="h"))
    p.append(txt(96, 394, "每一次都要真算", cls="s"))
    for i in range(7):
        p.append(bar(430 + i * 46, 344, 40, 40, cls="coolfill"))
        p.append(txt(450 + i * 46, 370, "算", cls="s", anchor="middle"))
    p.append(txt(646, 424, "这才是这台机器的 Prefill 能力", cls="s", anchor="middle"))
    p.append(card(852, 340, 332, 96, cls="goodfill", rx=14))
    p.append(txt(876, 378, "TTFT P50 约 180 ms", cls="mb"))
    p.append(txt(876, 410, "十五倍的差距", cls="s"))

    # the floor problem
    p.append(txt(72, 500, "拿 12 ms 当 Baseline 之后会发生什么", cls="b"))
    p.append(f'  <path class="rule" d="M72 546H820" fill="none"/>')
    p.append(txt(836, 551, "以 12 ms 为基准", cls="s"))
    for i, label in enumerate(("优化 A", "优化 B", "优化 C")):
        cx = 180 + i * 220
        p.append(bar(cx, 552, 140, 34, cls="soft"))
        p.append(txt(cx + 70, 574, label, cls="s", anchor="middle"))
    p.append(txt(72, 616, "任何真实优化都落在这条线下方，全部显得“没有效果”，因为基准已经被抬到了不可能的高度", cls="s"))
    return page(
        system=SYSTEM,
        title="图 7-3 被缓存抬高的 Baseline",
        desc="同一句 prompt 发一千次时 TTFT P50 约 12 ms，一千句不同 prompt 约 180 ms，相差十五倍；以 12 ms 为基准后所有真实优化都落在基准线下方。",
        kicker="CACHE INFLATED · 07",
        heading="被缓存抬高的 Baseline",
        sub="压测里出现异常漂亮的数字，第一反应应该是怀疑而不是高兴",
        body="\n".join(p),
        takeaway="12 ms 测的是缓存能力，不是服务能力。",
    )


FIGURES = {
    "fig07-02_measurement_window.svg": (
        fig1,
        dict(title="图 7-2 制作说明：测量窗口的两端与窗外那几段",
             source="第 7.4 节。",
             order="先读上面那条时间线与窗口两端的事件名，再读下面在途请求的两种算法与它们的差。",
             takeaway="窗口越短、在途占比越高，在途请求的算法选择越要紧。",
             boundary="不画引擎内部的 Queue / Prefill / Decode；数字只用正文出现过的那两组。"),
    ),
    "fig07-01_three_runs_and_the_line.svg": (
        fig2,
        dict(title="图 7-1 制作说明：三轮结果与可识别线",
             source="第 7.3 节与 7.8 案例一。",
             order="先看左上三个点与极差，再往下看它怎么换算成 CV、差值波动和可识别线；然后看右侧两组均值，最后看差值的区间有没有跨过 0。",
             takeaway="差值的区间跨过 0，结论是分辨不出来，不是有改善。",
             boundary="只画三轮对三轮这一种情形，t 值取 95% 双侧；两组数字都来自正文，不冒充真机结果。"),
    ),
    "fig07-04_baseline_four_blocks.svg": (
        fig3,
        dict(title="图 7-4 制作说明：Baseline 报告的四块与缺一块的后果",
             source="第 7.6 节。",
             order="上排读四块各自装什么，下排读缺了它同事会卡在哪一步，最后读底部那句判断标准。",
             takeaway="缺任何一块，这份 Baseline 就不该再被引用。",
             boundary="不列完整 JSON 字段表，那在 Demo README。"),
    ),
    "fig07-03_cache_inflated_baseline.svg": (
        fig4,
        dict(title="图 7-3 制作说明：被缓存抬高的 Baseline",
             source="第 7.5 节与 7.8 案例二。",
             order="先对比上下两行的方块（命中与真算）和右侧两个结果，再看下半部分那条基准线为什么让后续优化全部失效。",
             takeaway="12 ms 测的是缓存能力，不是服务能力。",
             boundary="不展开 Prefix Cache 的块共享机制（属于第 13、16 章）。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
