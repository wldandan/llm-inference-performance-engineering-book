"""Build the Chapter 10 figure set defined in strategy/reviews/ch10/storyboard.md.

Every number in these figures comes from the investigation in 10.1 to 10.6 and
is synthetic; the figures say so where it matters.

Run from the repository root:

    python3 content/ch10/figures/build_figures.py
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
    p.append(card(72, 200, 268, 130, cls="badfill", rx=16))
    p.append(txt(206, 258, "服务慢了", cls="h", anchor="middle"))
    p.append(txt(206, 294, "没有任何可以被证明为假的内容", cls="s", anchor="middle"))
    p.append(hpath(340, 265, 400))

    items = [
        ("现象", "TTFT P99 从 400 ms 升到 6 s", "要有量：从多少变成多少"),
        ("范围", "只影响 prompt > 4000 token，约 8%", "最容易漏的两项之一"),
        ("时间", "9 月 8 日 14:20 开始", "突然开始指向某个变更"),
        ("对照", "9 月 1 日同负载 Baseline 400 ms", "最容易漏的两项之二"),
    ]
    y = 176
    for name, value, why in items:
        p.append(card(420, y, 500, 96, cls="card", rx=14))
        p.append(txt(444, y + 38, name, cls="h"))
        p.append(txt(520, y + 38, value, cls="m"))
        p.append(txt(520, y + 68, why, cls="s"))
        y += 108

    # candidates shrinking
    p.append(txt(960, 186, "候选解释", cls="b"))
    counts = [(176, 12), (284, 9), (392, 5), (500, 3)]
    for yy, n in counts:
        p.append(hpath(928, yy + 48, 956))
        for i in range(n):
            p.append(bar(962 + (i % 6) * 40, yy + 26 + (i // 6) * 22, 32, 14,
                         cls="soft" if i else "badfill", rx=3))
    p.append(txt(962, 606, "每补一项，剩下要查的就少一批", cls="s"))
    p.append(txt(72, 380, "补完之后，很多可能性", cls="s"))
    p.append(txt(72, 406, "已经自动被排除", cls="s"))
    p.append(txt(72, 452, "写不出这四项，说明", cls="s"))
    p.append(txt(72, 478, "可观测性还不够，", cls="s"))
    p.append(txt(72, 504, "该回第 8 章补请求级记录", cls="s"))
    return page(
        system=SYSTEM,
        title="图 10-1 把“服务慢”补成可调查的问题",
        desc="左侧是一句无法调查的“服务慢了”，右侧补上现象、范围、时间、对照四项，每补一项要查的候选解释就少一批；方块只画递减的示意，不代表具体种数。",
        kicker="INVESTIGABLE PROBLEM · 10",
        heading="把“服务慢”补成可调查的问题",
        sub="范围和对照是最容易漏的两项：没有范围只能大海捞针，没有对照连算不算异常都判断不了",
        body="\n".join(p),
        takeaway="写不出这四项，说明可观测性还不够，不是调查方法不对。",
    )


def fig2() -> str:
    p = []
    heads = ("假设", "需要哪一层证据", "成立的门槛", "门槛的来处")
    xs = (96, 392, 640, 960)
    p.append(card(72, 176, 1136, 300, cls="card", rx=16))
    for x, h in zip(xs, heads):
        p.append(txt(x, 214, h, cls="b"))
    p.append(f'  <path d="M72 232H1208" class="divider"/>')
    rows = [
        ("H1 队列积压", "请求级", "Queue 占 TTFT ≥ 70%", "唯一原因约 94%，解释一半约 48%", "goodfill"),
        ("H2 Prefill 被拆分", "框架级", "首 token 前 scheduled > 1 次", "机制本身给出的判定", "warnfill"),
        ("H3 缓存被关闭", "配置 + 请求级", "同前缀比冷请求快 < 30%", "生效时快约 60%，失效时约 0", "coolfill"),
    ]
    y = 262
    for name, layer, threshold, source, cls in rows:
        p.append(bar(84, y - 24, 292, 56, cls=cls))
        p.append(txt(96, y + 8, name, cls="b"))
        p.append(txt(392, y + 8, layer, cls="s"))
        p.append(txt(640, y + 8, threshold, cls="m"))
        p.append(txt(960, y + 8, source, cls="s"))
        y += 70

    # cost ordering
    p.append(txt(72, 520, "按采集成本排序，先查便宜的", cls="b"))
    order = [("H3 看配置 diff", "10 分钟", "goodfill"),
             ("H1 查已有请求级记录", "30 分钟", "goodfill"),
             ("H2 需要框架级 trace", "尚未采集", "warnfill")]
    x = 72
    for name, cost, cls in order:
        p.append(card(x, 540, 332, 70, cls=cls, rx=14))
        p.append(txt(x + 20, 570, name, cls="b"))
        p.append(txt(x + 20, 596, cost, cls="s"))
        if x < 700:
            p.append(hpath(x + 336, 575, x + 396))
        x += 402
    return page(
        system=SYSTEM,
        title="图 10-2 三个竞争假设、各自的层次与门槛",
        desc="H1、H2、H3 三个竞争假设各写出所需证据层次、成立的判定门槛与门槛的来处；下方按采集成本排序，H3 十分钟、H1 三十分钟、H2 需要尚未采集的框架级 trace。",
        kicker="COMPETING HYPOTHESES · 10",
        heading="三个竞争假设、各自的层次与门槛",
        sub="一次列多个假设，调查就变成“哪个能活下来”，而不是“能不能证明我是对的”",
        body="\n".join(p),
        takeaway="没有门槛的假设，仍然是不可证伪的。",
    )


def fig3() -> str:
    p = []
    # confounder triangle
    p.append(txt(72, 186, "同时发生不等于因果", cls="b"))
    p.append(card(72, 206, 540, 200, cls="card", rx=16))
    p.append(card(212, 232, 260, 56, cls="warnfill", rx=12))
    p.append(txt(342, 267, "并发 20 → 90", cls="b", anchor="middle"))
    p.append(arrow(280, 288, 190, 344))
    p.append(arrow(404, 288, 494, 344))
    p.append(card(104, 348, 172, 44, cls="soft", rx=10))
    p.append(txt(190, 376, "GPU 利用率 60→95", cls="s", anchor="middle"))
    p.append(card(408, 348, 172, 44, cls="soft", rx=10))
    p.append(txt(494, 376, "TTFT 升高", cls="s", anchor="middle"))
    p.append(dashed(276, 370, 408, 370))
    p.append(txt(342, 342, "看起来互为因果", cls="s", anchor="middle"))
    p.append(txt(342, 424, "流量是混杂因子：它同时推高了两者", cls="s", anchor="middle"))

    # the counterexample
    p.append(txt(660, 186, "一个反例就够了", cls="b"))
    p.append(card(660, 206, 548, 200, cls="card", rx=16))
    cols = ("", "GPU 利用率", "并发", "TTFT P99")
    for i, c in enumerate(cols):
        p.append(txt(684 + i * 134, 244, c, cls="b"))
    p.append(f'  <path d="M672 258H1196" class="divider"/>')
    p.append(txt(684, 296, "9/8 14:20 后", cls="s"))
    p.append(txt(818, 296, "95%", cls="m"))
    p.append(txt(952, 296, "90", cls="m"))
    p.append(txt(1086, 296, "6 s", cls="bad"))
    p.append(txt(684, 346, "8/26 下午", cls="s"))
    p.append(txt(818, 346, "93%", cls="m"))
    p.append(txt(952, 346, "24", cls="m"))
    p.append(txt(1086, 346, "430 ms", cls="good"))
    p.append(txt(684, 386, "利用率几乎一样，TTFT 差十几倍，差的是并发", cls="s"))

    # what it takes to get from correlation to cause
    p.append(txt(72, 464, "从相关走到因果，至少做到两件事之一", cls="b"))
    p.append(card(72, 486, 548, 136, cls="card", rx=14))
    p.append(txt(96, 522, "找出机制", cls="h"))
    p.append(txt(96, 554, "并发超过 max-num-seqs，多出来的请求", cls="s"))
    p.append(txt(96, 582, "在队列里等待，Queue 时间因此上升", cls="s"))
    p.append(txt(96, 608, "10.6 会把这条机制再证伪一次", cls="warn"))
    p.append(card(660, 486, 548, 136, cls="card", rx=14))
    p.append(txt(684, 522, "做受控变更", cls="h"))
    p.append(txt(684, 554, "只改一个变量，同流量重跑。第 7 章那份", cls="s"))
    p.append(txt(684, 582, "可复现 Baseline 在这里是前提", cls="s"))
    return page(
        system=SYSTEM,
        title="图 10-3 混杂因子与那个反例",
        desc="左上是并发同时推高 GPU 利用率与 TTFT 的混杂关系；右上是 8 月 26 日利用率 93% 但 TTFT 仅 430 ms 的反例；下方是从相关走到因果的两条路。",
        kicker="CONFOUNDER · 10",
        heading="混杂因子与那个反例",
        sub="调查里最容易出错的一步，是把同时发生当成了因果",
        body="\n".join(p),
        takeaway="找反例比采新数据便宜，应该排在前面。",
    )


def fig4() -> str:
    p = []
    steps = [
        ("第 1 步", "H3 缓存被关闭", "看配置 diff，10 分钟", "排除", "goodfill"),
        ("第 2 步", "H1 队列积压", "查已有请求级记录，30 分钟", "成立　Queue 占 82%", "warnfill"),
        ("第 2.5 步", "回头证伪 H1 的机制", "短 prompt Queue P99 35 → 40 ms", "机制要修正", "warnfill"),
        ("第 3 步", "H2 Prefill 被拆分", "需要框架级 trace，未采集", "残留不确定性", "soft"),
    ]
    y = 176
    for tag, name, how, verdict, cls in steps:
        half = tag == "第 2.5 步"
        h = 54 if half else 80
        p.append(card(72, y, 660, h, cls=cls, rx=14))
        if half:
            p.append(txt(96, y + 34, tag, cls="b"))
            p.append(txt(186, y + 34, f"{name}　{how}", cls="s"))
        else:
            p.append(txt(96, y + 34, tag, cls="b"))
            p.append(txt(178, y + 34, name, cls="h"))
            p.append(txt(178, y + 62, how, cls="s"))
        p.append(txt(712, y + (34 if half else 44), verdict, cls="b", anchor="end"))
        y += h + 10

    p.append(card(72, 500, 660, 64, cls="coolfill", rx=14))
    p.append(txt(96, 528, "最小改动", cls="b"))
    p.append(txt(206, 528, "批处理任务并发上限 70 → 20", cls="m"))
    p.append(txt(206, 552, "改配置、不改代码、可随时回滚", cls="s"))

    # verification
    p.append(txt(72, 590, "同流量重跑三轮 640 / 590 / 620 ms，均值约 620 ms", cls="s"))
    chips = [
        ("9/1 基线", "400 ms", "goodfill"),
        ("9/8 故障期", "6 s", "badfill"),
        ("改动后", "620 ms　仍差 220 ms", "warnfill"),
    ]
    x = 72
    for name, value, cls in chips:
        w = 196 if name != "改动后" else 264
        p.append(card(x, 600, w, 38, cls=cls, rx=12))
        p.append(txt(x + 14, 625, name, cls="s"))
        p.append(txt(x + w - 14, 625, value, cls="b", anchor="end"))
        x += w + 16

    # report shape
    p.append(card(756, 176, 452, 410, cls="card", rx=16))
    p.append(txt(780, 214, "报告要分开写的七行", cls="b"))
    lines = [
        ("结论", "H1 成立，是主要原因", "s"),
        ("置信度", "高。有干预、有反例", "s"),
        ("机制", "长请求进不了调度；KV 还是 token 预算未定", "warn"),
        ("已解决", "P99 从 6 s 回到 620 ms", "good"),
        ("未解决", "620 与 400 相差 55%，不是波动", "warn"),
        ("未确认", "机制是哪一种；H2 是否同时成立", "s"),
        ("下一步", "看 KV 使用率与抢占计数；再采框架级 trace", "s"),
    ]
    yy = 252
    for k, v, cls in lines:
        p.append(txt(780, yy, k, cls="b"))
        p.append(txt(872, yy, v, cls=cls))
        yy += 48
    p.append(txt(780, 574, "图中数字为合成数据", cls="s"))
    return page(
        system=SYSTEM,
        title="图 10-4 一次走完的调查",
        desc="调查依次排除 H3、确认 H1、回头证伪 H1 自己的机制、把 H2 留作残留不确定性；最小改动是把批处理并发从 70 压到 20；同流量重跑均值约 620 ms，与 9/1 的 400 ms 仍差 55%；右侧是报告要分开写的七行。",
        kicker="INVESTIGATION CLOSED · 10",
        heading="一次走完的调查",
        sub="它刻意没有完全恢复：620 ms 与 400 ms 相差 55%，不是波动",
        body="\n".join(p),
        takeaway="“已解决”和“未解决”要分两行写，那 220 ms 是下一次的起点。",
    )


FIGURES = {
    "fig10-01_investigable_problem.svg": (
        fig1,
        dict(title="图 10-1 制作说明：把“服务慢”补成可调查的问题",
             source="第 10.1 节。",
             order="先看左边那句无法调查的话，再顺箭头读右边补上的四项，注意最右侧候选解释随之减少。",
             takeaway="写不出这四项，说明可观测性还不够，不是调查方法不对。",
             boundary="不出现具体假设的内容，那是图 10-2。"),
    ),
    "fig10-02_hypotheses_to_layers.svg": (
        fig2,
        dict(title="图 10-2 制作说明：三个竞争假设、各自的层次与门槛",
             source="第 10.2 节。",
             order="先横着读三行假设的层次与门槛，再看最后一列门槛数字的来处，最后看下方按成本排序的查证顺序。",
             takeaway="没有门槛的假设，仍然是不可证伪的。",
             boundary="不出现调查结果，那是图 10-4。"),
    ),
    "fig10-03_confounder.svg": (
        fig3,
        dict(title="图 10-3 制作说明：混杂因子与那个反例",
             source="第 10.3 节。",
             order="先看左上那个三角：并发同时推高利用率与 TTFT；再看右上两行对照，利用率几乎一样而 TTFT 差十几倍；最后读下方从相关走到因果的两条路。",
             takeaway="找反例比采新数据便宜，应该排在前面。",
             boundary="不展开干预的实施细节，那是图 10-4。"),
    ),
    "fig10-04_investigation_closed.svg": (
        fig4,
        dict(title="图 10-4 制作说明：一次走完的调查",
             source="第 10.6 节。",
             order="从左上四步依次往下读，注意第 2.5 步是回头证伪自己已经认定的机制，再看最小改动那一格，然后看底部三个点的位置关系，最后读右侧报告的六行。",
             takeaway="“已解决”和“未解决”要分两行写，那 220 ms 是下一次的起点。",
             boundary="图中数字为合成数据，图内已标注；不把 620 ms 说成真机结果。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
