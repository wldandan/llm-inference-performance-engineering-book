"""Build the Chapter 9 figure set defined in strategy/reviews/ch09/storyboard.md.

Run from the repository root:

    python3 content/ch09/figures/build_figures.py
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
    layers = [
        ("请求级", "排队、首 token、生成各占多久", "引擎请求级指标、日志、Trace", "极低，可以常开", "goodfill"),
        ("进程级", "CPU 忙在哪、有没有阻塞", "采样式 profiler、py-spy 一类", "低", "goodfill"),
        ("框架级", "调度批次怎么形成、有没有抢占", "框架自带 profiler、engine trace", "中", "warnfill"),
        ("设备级", "kernel 执行、空隙、显存带宽", "GPU 时间线、kernel 分析器", "中到高", "badfill"),
    ]
    y = 176
    for i, (name, answers, tools, cost, cls) in enumerate(layers):
        indent = i * 26
        p.append(card(96 + indent, y, 856 - indent, 92, cls=cls, rx=14))
        p.append(txt(120 + indent, y + 38, name, cls="h"))
        p.append(txt(120 + indent, y + 70, answers, cls="s"))
        p.append(txt(430, y + 38, tools, cls="s"))
        p.append(txt(430, y + 70, f"开销　{cost}", cls="s"))
        y += 108

    # the downward rule
    p.append(f'  <path class="flow" d="M76 196V580"/>')
    p.append(txt(46, 392, "从便宜到昂贵", cls="s", anchor="middle") .replace('x="46"', 'x="46" transform="rotate(-90 46 392)"'))

    # judgement + no-skipping
    p.append(card(988, 176, 220, 200, cls="card", rx=14))
    p.append(txt(1098, 214, "往下走的判据", cls="b", anchor="middle"))
    p.append(txt(1012, 254, "上一层的数据里，", cls="s"))
    p.append(txt(1012, 282, "还有没有解释不了", cls="s"))
    p.append(txt(1012, 310, "的部分？", cls="s"))
    p.append(txt(1012, 350, "没有就不要往下", cls="b"))

    p.append(card(988, 400, 220, 176, cls="badfill", rx=14))
    p.append(txt(1098, 438, "跳级", cls="b", anchor="middle"))
    p.append(txt(1012, 478, "请求级还没看就", cls="s"))
    p.append(txt(1012, 506, "去抓 kernel：", cls="s"))
    p.append(txt(1012, 534, "花半天得到的结论", cls="s"))
    p.append(txt(1012, 562, "可能只是“在排队”", cls="s"))
    # the skipping arrow: request level straight to device level, crossed out
    p.append('  <path d="M952 222 Q 992 384 952 546" fill="none" stroke="#B91C1C" '
             'stroke-width="2.4" stroke-dasharray="7 5"/>')
    p.append('  <path d="M962 368L986 400" stroke="#B91C1C" stroke-width="3.4"/>')
    p.append('  <path d="M986 368L962 400" stroke="#B91C1C" stroke-width="3.4"/>')
    return page(
        system=SYSTEM,
        title="图 9-1 四层从便宜到昂贵",
        desc="请求级、进程级、框架级、设备级四层从外到内排列，各列出回答什么、典型手段与开销；右侧给出往下走的判据，并用一个叉标出跳级。",
        kicker="FOUR LAYERS · 09",
        heading="四层从便宜到昂贵",
        sub="上一层能解释清楚的现象，不需要下一层的数据",
        body="\n".join(p),
        takeaway="判断该不该往下走，只看上一层还有没有解释不了的部分。",
    )


def fig2() -> str:
    p = []
    # sorted table on the left
    p.append(txt(72, 186, "按耗时排序的表", cls="b"))
    p.append(card(72, 204, 360, 228, cls="card", rx=14))
    rows = [("生成", "800 ms", 140), ("向量检索", "120 ms", 60),
            ("关键词检索", "70 ms", 40), ("重排", "40 ms", 26)]
    for i, (name, ms, w) in enumerate(rows):
        p.append(txt(96, 248 + 50 * i, name, cls="b"))
        p.append(bar(200, 232 + 50 * i, w, 20, cls="coolfill", rx=4))
        p.append(txt(352, 248 + 50 * i, ms, cls="m"))
    p.append(txt(72, 462, "排序表看不出下面这件事", cls="bad"))

    # two timelines on the right; generation is drawn shortened with a break mark
    x0 = 470
    lx = x0 + 100
    gen_w = 250

    def seg_w(ms):
        return gen_w if ms == 800 else ms

    p.append(txt(x0, 186, "同一次 RAG 请求的两种时间线", cls="b"))
    # serial
    p.append(txt(x0, 238, "串行", cls="b"))
    x = lx
    for name, ms, cls in (("向量 120", 120, "coolfill"), ("关键词 70", 70, "warnfill"),
                          ("重排", 40, "coolfill"), ("生成 800", 800, "coolfill")):
        w = seg_w(ms)
        p.append(bar(x, 216, w, 34, cls=cls))
        if ms != 40:
            p.append(txt(x + w / 2, 238, name, cls="s", anchor="middle"))
        x += w
    p.append(txt(lx + 190 + 20, 276, "↑ 重排 40", cls="s", anchor="middle"))
    p.append(txt(x - 30, 238, "≈", cls="s", anchor="middle"))
    p.append(txt(x + 14, 238, "关键路径 1030 ms", cls="b"))
    # parallel: two retrievals stacked, then rerank, then generation
    p.append(txt(x0, 334, "并行", cls="b"))
    p.append(bar(lx, 300, 120, 28, cls="coolfill"))
    p.append(txt(lx + 60, 319, "向量 120", cls="s", anchor="middle"))
    p.append(bar(lx, 334, 70, 28, cls="warnfill"))
    p.append(txt(lx + 35, 353, "关键词 70", cls="s", anchor="middle"))
    p.append(bar(lx + 120, 300, 40, 62, cls="coolfill"))
    p.append(txt(lx + 140, 384, "重排 40", cls="s", anchor="middle"))
    p.append(bar(lx + 160, 300, gen_w, 62, cls="coolfill"))
    p.append(txt(lx + 160 + gen_w / 2, 336, "生成 800", cls="s", anchor="middle"))
    p.append(txt(lx + 160 + gen_w - 30, 336, "≈", cls="s", anchor="middle"))
    p.append(txt(lx + 160 + gen_w + 14, 336, "关键路径 960 ms", cls="b"))

    p.append(card(470, 404, 738, 128, cls="card", rx=14))
    p.append(txt(494, 440, "把关键词检索从 70 ms 优化到 20 ms", cls="b"))
    p.append(txt(494, 476, "串行", cls="b"))
    p.append(txt(560, 476, "端到端省 50 ms", cls="good"))
    p.append(txt(494, 510, "并行", cls="b"))
    p.append(txt(560, 510, "端到端省 0，它本来就躲在向量检索的 120 ms 里", cls="bad"))

    p.append(note(72, 552, 1136, [
        "重排要等两路候选集都回来，在两种结构里都在链上；能不能藏起来，看的是依赖关系，不是耗时排序",
    ]))
    p.append(txt(1208, 404 - 10, "生成段按比例缩短画出", cls="s", anchor="end"))
    p.append(f'  <path class="flow" d="M444 300H462"/>')
    return page(
        system=SYSTEM,
        title="图 9-2 排序表与关键路径不是一回事",
        desc="左侧一张按耗时排序的表，右侧同一次 RAG 请求的串行（1030 ms）与并行（960 ms）两条时间线：向量检索与关键词检索互不依赖，可以同时发出，重排要等两路结果；把关键词检索从 70 ms 优化到 20 ms，串行省 50 ms，并行省 0。",
        kicker="CRITICAL PATH · 09",
        heading="排序表与关键路径不是一回事",
        sub="占比最高的那一项，未必是缩短它就能让请求变快的那一项",
        body="\n".join(p),
        takeaway="只有缩短关键路径上的段，端到端才会变快。",
    )


def fig3() -> str:
    p = []
    base = 620
    y0, hmax, top = 540, 300, 1400

    def bh(v):
        return v / top * hmax

    # the random-fluctuation band around the baseline, drawn first
    band_lo, band_hi = base * 0.87, base * 1.13
    p.append(bar(110, y0 - bh(band_hi), 720, bh(band_hi) - bh(band_lo), cls="soft", rx=0))
    p.append(bar(110, 172, 28, 18, cls="soft", rx=0))
    p.append(txt(150, 187, "灰带：假如照搬第 7.3 节 TTFT P95 那条 13% 的线", cls="warn"))

    bars = [
        ("不采集", 620, "soft", "基线"),
        ("采样 profiler", 650, "goodfill", "+4.8%"),
        ("框架 trace", 710, "warnfill", "+14.5%"),
        ("kernel 分析器", 1340, "badfill", "+116%"),
    ]
    x = 150
    for name, v, cls, delta in bars:
        h = bh(v)
        p.append(bar(x, y0 - h, 130, h, cls=cls))
        p.append(txt(x + 65, y0 - h - 14, f"{v} ms", cls="mb", anchor="middle"))
        p.append(txt(x + 65, y0 + 30, name, cls="s", anchor="middle"))
        p.append(txt(x + 65, y0 + 56, delta, cls="b", anchor="middle"))
        x += 170

    p.append(card(870, 176, 338, 396, cls="card", rx=16))
    p.append(txt(894, 214, "这三份开销怎么处理", cls="b"))
    verdicts = [
        ("+4.8%", "两边都开着测", "偏差在差值里抵消，可以比", "good"),
        ("+14.5%", "条件相同才可比", "调度结论仍然可用", "warn"),
        ("+116%", "另一个系统", "任何延迟数字都不要拿去比", "bad"),
    ]
    yy = 262
    for value, verdict, why, cls in verdicts:
        p.append(txt(894, yy, value, cls="mb"))
        p.append(txt(990, yy, verdict, cls=cls))
        p.append(txt(894, yy + 28, why, cls="s"))
        yy += 92
    p.append(txt(894, 528, "或者先测出开销，再从数字里扣掉", cls="s"))
    p.append(txt(894, 556, "图中四个数是合成设定，不是实测", cls="s"))

    p.append(txt(110, y0 + 92, "+4.8% 落在波动带里，但它每一轮都在，多跑几轮也平均不掉", cls="s"))
    return page(
        system=SYSTEM,
        title="图 9-3 采集开销是偏差，不是波动",
        desc="四根柱子分别是不采集 620 ms、采样 profiler 650、框架 trace 710、kernel 分析器 1340；灰带是照搬第 7.3 节那条 13% 的线画出来的，采样 profiler 的 +4.8% 落在带里，但它是每轮都有的固定偏差，不该拿这条线去衡量，要靠两边条件对齐或先测出再扣除来处理。",
        kicker="OBSERVER EFFECT · 09",
        heading="采集开销是偏差，不是波动",
        sub="可识别线管的是随机波动；采集开销每一轮都在，不会被多跑几轮平均掉",
        body="\n".join(p),
        takeaway="偏差靠对齐采集条件或扣除来处理，不靠和可识别线比大小。",
    )


def fig4() -> str:
    p = []
    x0, wmax = 120, 1000
    t0, t1 = 8.5, 10.5

    def px(h):
        return x0 + (h - t0) / (t1 - t0) * wmax

    y = 300
    p.append(txt(72, 190, "三段都是 5 分钟长，差别只在位置", cls="b"))
    p.append(f'  <path d="M{x0} {y}H{x0 + wmax}" stroke="#94A3B8" stroke-width="1.6" fill="none"/>')
    for h, label in ((8.5, "8:30"), (9.0, "9:00"), (9.5, "9:30"), (10.0, "10:00"), (10.5, "10:30")):
        p.append(f'  <path d="M{px(h)} {y}V{y + 8}" stroke="#94A3B8" stroke-width="1.6"/>')
        p.append(txt(px(h), y + 30, label, cls="s", anchor="middle"))

    # the symptom window
    p.append(bar(px(9.033), y - 74, px(9.117) - px(9.033), 60, cls="badfill"))
    p.append(txt((px(9.033) + px(9.117)) / 2, y - 92, "现象 9:02 – 9:07", cls="bad", anchor="middle"))

    # two candidate collection windows
    p.append(bar(px(10.0), y + 56, px(10.083) - px(10.0), 60, cls="soft"))
    p.append(txt((px(10.0) + px(10.083)) / 2, y + 140, "采集窗口 A", cls="b", anchor="middle"))
    p.append(txt((px(10.0) + px(10.083)) / 2, y + 166, "10:00 – 10:05", cls="m", anchor="middle"))
    p.append(txt((px(10.0) + px(10.083)) / 2, y + 194, "重叠 0 分钟", cls="bad", anchor="middle"))
    p.append(txt((px(10.0) + px(10.083)) / 2, y + 220, "数据干净，但里面没有问题", cls="s", anchor="middle"))

    p.append(bar(px(9.033), y + 56, px(9.117) - px(9.033), 60, cls="goodfill"))
    p.append(txt((px(9.033) + px(9.117)) / 2, y + 140, "采集窗口 B", cls="b", anchor="middle"))
    p.append(txt((px(9.033) + px(9.117)) / 2, y + 166, "9:02 – 9:07", cls="m", anchor="middle"))
    p.append(txt((px(9.033) + px(9.117)) / 2, y + 194, "完全覆盖", cls="good", anchor="middle"))
    p.append(txt((px(9.033) + px(9.117)) / 2, y + 220, "一次就抓到", cls="s", anchor="middle"))

    p.append(note(72, 560, 1136, [
        "两个窗口一样长、数据一样干净，唯一的差别是一个覆盖了现象、一个没有",
    ]))
    return page(
        system=SYSTEM,
        title="图 9-4 采集窗口的位置比长度重要",
        desc="一条时间轴上，现象发生在 9:02 到 9:07；采集窗口 A 落在 10:00 到 10:05，与现象零重叠；采集窗口 B 落在同一段，完全覆盖。两个窗口长度相同。",
        kicker="WINDOW POSITION · 09",
        heading="采集窗口的位置比长度重要",
        sub="现象是偶发的，而采集窗口是随手挑的一分钟，两者没有重叠",
        body="\n".join(p),
        takeaway="五分钟采对了，比一小时采错了有用得多。",
    )


FIGURES = {
    "fig09-01_four_layers.svg": (
        fig1,
        dict(title="图 9-1 制作说明：四层从便宜到昂贵",
             source="第 9.2 节。",
             order="从上往下读四层的名称、回答什么与开销，再读右上角往下走的判据，最后看右下角被打叉的跳级。",
             takeaway="判断该不该往下走，只看上一层还有没有解释不了的部分。",
             boundary="不出现工具的命令行与截图。"),
    ),
    "fig09-02_critical_path.svg": (
        fig2,
        dict(title="图 9-2 制作说明：排序表与关键路径不是一回事",
             source="第 9.4 节。",
             order="先读左边那张排序表，再看右边串行与并行两条时间线的关键路径，最后读把关键词检索优化到 20 ms 在两种结构下的不同收益。",
             takeaway="只有缩短关键路径上的段，端到端才会变快。",
             boundary="不展开 RAG 链路的完整结构（属于第 23 章）。"),
    ),
    "fig09-03_observer_effect.svg": (
        fig3,
        dict(title="图 9-3 制作说明：采集开销是偏差，不是波动",
             source="第 9.5 节；灰带是照搬第 7.3 节那条线画的，用来说明不该这样比。",
             order="先看四根柱子的高度差，再看那条照搬来的灰带，最后读右侧三份开销各自的处理办法。",
             takeaway="偏差靠对齐采集条件或扣除来处理，不靠和可识别线比大小。",
             boundary="图上四个数是合成设定，不是任何真机的实测值，已在图内标注；不展开具体 profiler 的实现细节。"),
    ),
    "fig09-04_window_position.svg": (
        fig4,
        dict(title="图 9-4 制作说明：采集窗口的位置比长度重要",
             source="第 9.6 节与 9.8 案例三。",
             order="先看时间轴上方那段现象窗口，再看下方两个等长的采集窗口分别落在哪里，最后读两者的结论。",
             takeaway="五分钟采对了，比一小时采错了有用得多。",
             boundary="不讨论触发采集的具体实现方案。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
