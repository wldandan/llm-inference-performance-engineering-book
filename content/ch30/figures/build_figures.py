"""Build the Chapter 30 figure set defined in strategy/reviews/ch30/storyboard.md.

  fig30-01  30.2 那七个阶段，连同它们之间的依赖，以及第 0 章那三条规律各自落在
            哪个阶段的验收判据上。这张图要回答的是「为什么这个顺序不能打乱」，
            不是「项目有哪七步」。

七个阶段的目录名和五项交付物由 code/ch30/project/verify.py 提供，所以图和验收器
说的是同一套东西。

Run from the repository root:

    python3 content/ch30/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch30" / "project"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, MUTED, WARN, card, dashed, note, page, txt, write,
    write_note,
)
import verify as vf  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

# 30.2 那七个阶段。目录名取自 verify.py，保证图和验收器对得上。
STAGES = [
    ("一", "跑起来并说清楚", "Ch0–Ch5", None,
     "能说出每个阶段的时间戳来自哪里"),
    ("二", "把负载和基准立住", "Ch6–Ch7", "workload",
     "同事拿着这两份文件能重跑出同一批请求"),
    ("三", "让系统可观测", "Ch8–Ch10", "observe",
     "随便指一条慢请求，能说出它慢在哪一段"),
    ("四", "Prefill 与上下文", "Ch11–Ch14", "experiment",
     "报告里有“不可分辨”这类结论的空间"),
    ("五", "Decode 与显存", "Ch15–Ch19", None,
     "每个收益数字都标注了对应的批量"),
    ("六", "服务与链路", "Ch20–Ch25", None,
     "过载演练的 goodput 在超容量后保持平稳"),
    ("七", "容量、门禁与评审", "Ch26–Ch29", "capacity",
     "门禁能真的拦住一次人为制造的回归"),
]

# 第 0 章那三条规律（0.3、0.4、0.5 的标题），各自落在哪些阶段的验收判据上。
# Part 4、5、6 开篇那三个名字（搬运下限、排队与放大、稳态与余量）是它们的
# 定量形式，不是另外三条。
LAWS = [
    ("规律一", "写比读贵", "阶段四、五",
     "Prefill 算术强度，TPOT 实测与搬运下限之比", COOL),
    ("规律二", "批量摊薄搬运，满载拉长等待", "阶段五、六、七",
     "Goodput 峰值批量，负载率与放大，余量", WARN),
    ("规律三", "只有有用的产出才算数", "阶段六、七与报告",
     "goodput 平稳，成本按有用产出，质量否决", GOOD),
]

DEPENDENCIES = [
    "没有 workload 就没有 Baseline",
    "没有 Baseline 就没有门禁",
    "没有容量模型就没有成本讨论",
]


def fig1() -> str:
    p = []

    p.append(card(56, 158, 620, 416, cls="card", rx=16))
    p.append(txt(80, 190, "七个阶段，后面每一个都依赖前面的产出", cls="b"))

    y = 214
    for num, name, chapters, _dirname, criterion in STAGES:
        p.append(f'  <circle cx="98" cy="{y + 20}" r="15" fill="{MUTED}" '
                 f'opacity="0.18"/>')
        p.append(txt(98, y + 26, num, cls="b", anchor="middle"))
        p.append(txt(124, y + 16, f"{name}　{chapters}", cls="b"))
        p.append(txt(124, y + 40, criterion, cls="s"))
        if num != "七":
            p.append(f'  <path d="M98 {y + 37}V{y + 51}" stroke="#94A3B8" '
                     f'stroke-width="2"/>')
        y += 50

    p.append(card(700, 158, 524, 136, cls="warnfill", rx=16))
    p.append(txt(724, 190, "顺序不能大幅打乱", cls="h"))
    yy = 220
    for line in DEPENDENCIES:
        p.append(txt(724, yy, line, cls="s"))
        yy += 24

    p.append(card(700, 310, 524, 264, cls="card", rx=16))
    p.append(txt(724, 342, "第 0 章那三条规律落在哪里", cls="h"))
    p.append(txt(724, 368, "它们是后面各阶段验收判据的来源，不是开场白", cls="s"))
    yy = 384
    for num, law, stages, criterion, colour in LAWS:
        p.append(f'  <text class="b" x="724" y="{yy + 24}" fill="{colour}">'
                 f'{num}</text>')
        p.append(txt(788, yy + 24, law, cls="b"))
        p.append(txt(788, yy + 48, f"{stages}　{criterion}", cls="s"))
        yy += 60

    p.append(note(56, 588, 1168, [
        "五项交付物里最容易被低估的是“可解释”：前二十九章那些错误，"
        "绝大多数的根源都是某个数字的含义没说清。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="七个阶段，以及为什么这个顺序不能打乱",
        desc="左栏是七个阶段的阶梯，依次是：跑起来并说清楚（Ch0 到 Ch5）、"
             "把负载和基准立住（Ch6 到 Ch7）、让系统可观测（Ch8 到 Ch10）、"
             "Prefill 与上下文（Ch11 到 Ch14）、Decode 与显存（Ch15 到 Ch19）、"
             "服务与链路（Ch20 到 Ch25）、容量门禁与评审（Ch26 到 Ch29），"
             "每一阶段下面写着它的验收判据。右上一块列出三条依赖："
             "没有 workload 就没有 Baseline，没有 Baseline 就没有门禁，"
             "没有容量模型就没有成本讨论。右下一块把第 0 章那三条规律对应到验收判据上："
             "规律一写比读贵，落在阶段四、五，看 Prefill 算术强度和 TPOT 实测与搬运下限之比；"
             "规律二批量摊薄搬运、满载拉长等待，落在阶段五、六、七，看 Goodput 峰值批量、"
             "负载率与放大、余量；规律三只有有用的产出才算数，落在阶段六、七与报告，"
             "看过载后 goodput 是否平稳、成本是否按有用产出算、质量是否是否决项。",
        kicker="第 30 章 · 30.1、30.2",
        heading="七个阶段，以及为什么这个顺序不能打乱",
        sub="后面每个阶段都依赖前面的产出，而第 0 章那三条是判据的来源",
        body="\n".join(p),
        takeaway="顺序打乱的代价不是返工，是前面那一步没有可用的验收判据",
    )


FIGS = [
    ("fig30-01_seven_stages", fig1,
     dict(title="图30-1 七个阶段，以及为什么这个顺序不能打乱",
          source="30.1、30.2",
          order="先从上往下读七个阶段和它们各自的验收判据，再看右上三条依赖，最后看右下第 0 章那三条规律各自落在哪几个阶段、拿什么判",
          takeaway="顺序打乱的代价不是返工，是前面那一步没有可用的验收判据",
          boundary="这是推荐顺序，不是唯一顺序；规模可以小到单卡小模型，重要的是每一环真实存在。图里的验收判据是 30.2 各阶段那一句，完整的产出清单在正文表里")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
