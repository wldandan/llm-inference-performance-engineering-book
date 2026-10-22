"""Build the Chapter 17 figure set defined in strategy/reviews/ch17/storyboard.md.

Every number comes from code/ch15/model-7b-generic.json and 17.2's two tables,
and can be recomputed with code/ch17/quant_tradeoff.py.

Run from the repository root:

    python3 content/ch17/figures/build_figures.py
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


# --- 图17-1 两笔账的分工 -----------------------------------------------------

def fig1() -> str:
    p = []
    p.append(card(72, 176, 1136, 380, cls="card", rx=16))
    p.append(txt(96, 210, "量化的对象有两类，收益完全不同，必须分开算", cls="b"))

    # two axes: latency (left) and capacity (right)
    mid = 640
    p.append(dashed(mid, 234, mid, 522))

    # --- weight quantization: latency
    p.append(txt(120, 256, "权重量化：改的是单步下限", cls="b"))
    scale = 32.0
    y = 276
    for label, ms, cls in (("FP16  14 ms", 14.0, "soft"),
                           ("INT8   7 ms", 7.0, "coolfill"),
                           ("INT4 3.5 ms", 3.5, "coolfill")):
        p.append(bar(120, y, ms * scale, 38, cls=cls, rx=6))
        p.append(txt(132, y + 25, label, cls="m"))
        y += 48
    p.append(txt(120, y + 18, "按比例下降，因为它就是分子上的减法", cls="s"))
    p.append(txt(120, y + 42, "14 GB ÷ 1000 GB/s = 14 ms，字节减半，下限减半", cls="s"))

    p.append(bar(120, y + 60, 480, 76, cls="coolfill", rx=12))
    p.append(txt(136, y + 86, "并发只涨 14%", cls="b"))
    p.append(txt(136, y + 110, "权重只占显存的一小部分：52 → 59 GiB，185 → 210 条", cls="s"))

    # --- KV quantization: capacity
    p.append(txt(680, 256, "KV 量化：改的是每 token 的占用", cls="b"))
    y = 276
    for label, kib, cls in (("FP16  128 KiB / token", 128, "soft"),
                            ("INT8   64 KiB / token", 64, "goodfill")):
        p.append(bar(680, y, kib * 3.5, 38, cls=cls, rx=6))
        p.append(txt(692, y + 25, label, cls="m"))
        y += 48
    p.append(txt(680, y + 6, "52 GiB 的预算不变，能装的 token 翻倍", cls="s"))
    p.append(txt(680, y + 30, "42.6 万 → 85.2 万 token，并发 185 → 370 条", cls="s"))

    p.append(bar(680, y + 48, 480, 76, cls="goodfill", rx=12))
    p.append(txt(696, y + 74, "单步下限一点没动", cls="b"))
    p.append(txt(696, y + 98, "权重字节数没变，所以 14 ms 还是 14 ms", cls="s"))

    p.append(note(72, 572, 1136, [
        "瓶颈是 TPOT 就量权重，瓶颈是并发就量 KV。两者可以叠加，但要按第 14 章的纪律"
        "一次只上一项，因为它们的质量风险不同：KV 量化最低，权重 INT4 最高。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="权重量化推延迟，KV 量化推容量",
        desc="左右两栏。左栏是权重量化：三条按比例缩短的条表示 FP16 的 14 ms、INT8 的 "
             "7 ms、INT4 的 3.5 ms 单步下限，下方标出并发只涨 14%。右栏是 KV 量化："
             "每 token 从 128 KiB 降到 64 KiB，并发从 185 涨到 370，而单步下限一点没动。",
        kicker="第 17 章 · 17.2",
        heading="同一个 INT8，两笔账的收益落在不同的地方",
        sub="权重量化改的是单步下限，KV 量化改的是每 token 占用，两者几乎不互相影响",
        body="\n".join(p),
        takeaway="瓶颈是 TPOT 就量权重，瓶颈是并发就量 KV；把两者当成一件事会选错",
    )


# --- 图17-2 三项的收益与质量风险 ---------------------------------------------

def fig2() -> str:
    p = []
    x0, y0, x1, y1 = 180, 214, 740, 492
    p.append(card(72, 176, 720, 380, cls="card", rx=16))
    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.8"/>')
    p.append(txt(96, 202, "收益越大，质量风险通常越高", cls="b"))
    p.append(txt(x1, y1 + 46, "收益（越往右越大）", cls="s", anchor="end"))
    p.append(txt(96, y1 + 46, "低", cls="s"))
    p.append(txt(x0 - 16, y0 + 10, "高", cls="s", anchor="end"))
    p.append(txt(x0 - 16, y1 - 4, "低", cls="s", anchor="end"))
    p.append(txt(112, (y0 + y1) / 2, "质", cls="s"))
    p.append(txt(112, (y0 + y1) / 2 + 20, "量", cls="s"))
    p.append(txt(112, (y0 + y1) / 2 + 40, "风", cls="s"))
    p.append(txt(112, (y0 + y1) / 2 + 60, "险", cls="s"))

    # three items placed by (benefit, risk); order 1..3 is the recommended order
    items = [
        (0.62, 0.18, "① KV Cache INT8", "并发翻倍 · 风险低", GOOD, "goodfill"),
        (0.52, 0.52, "② 权重 INT8", "单步下限减半 · 风险中等", WARN, "warnfill"),
        (0.80, 0.88, "③ 权重 INT4", "下限再减半 · 风险最高", BAD, "badfill"),
    ]
    for bx_, by_, label, sub, colour, fill in items:
        px_ = x0 + bx_ * (x1 - x0)
        py_ = y1 - by_ * (y1 - y0)
        p.append(f'  <rect x="{px_ - 104:.0f}" y="{py_ - 34:.0f}" width="208" height="68" '
                 f'rx="14" class="{fill}"/>')
        p.append(txt(px_, py_ - 8, label, cls="b", anchor="middle"))
        p.append(txt(px_, py_ + 16, sub, cls="s", anchor="middle"))

    int4_x = x0 + 0.80 * (x1 - x0)
    int4_y = y1 - 0.88 * (y1 - y0)
    p.append(txt(int4_x, int4_y + 54, "没有评测集就不要进这一格", cls="bad", anchor="middle"))

    p.append(card(816, 176, 392, 380, cls="card", rx=16))
    p.append(txt(840, 210, "在它们之前先做两件事", cls="b"))
    p.append(note(832, 230, 344, [
        "一 按长度分流",
        "少量长请求走单独的实例组",
        "max_model_len 只管最坏情况的并发",
    ], cls="coolfill"))
    p.append(note(832, 348, 344, [
        "二 查框架开销",
        "读启动日志，不看空载的 nvidia-smi",
        "权重和 KV 池之外占了 20 GiB，先查这里",
    ], cls="coolfill"))
    p.append(note(832, 466, 344, [
        "这两件都比量化便宜，且没有质量风险",
    ], cls="soft", h=42))

    p.append(note(72, 572, 1136, [
        "顺序不是按收益排的，是按“收益除以质量风险”排的。"
        "17.8 案例三那个团队花两周做 INT4，后来发现只要把长请求分流出去。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="三项量化手段的收益与质量风险",
        desc="一个二维图，横轴是收益，纵轴是质量风险。KV Cache INT8 在右下角，收益大而"
             "风险低；权重 INT8 同属低风险档；权重 INT4 在右上角，收益最大而风险最高。右侧列出"
             "两件应该先做的、没有质量风险的事：按长度分流与查框架开销。",
        kicker="第 17 章 · 17.5、17.6",
        heading="该先做哪一个：按收益除以质量风险排",
        sub="KV 量化排第一，是因为收益最直接、能单独开关回退，而且风险和权重 INT8 同档",
        body="\n".join(p),
        takeaway="量化是最后一步：先按长度分流、先查框架开销，这两件没有质量风险",
    )


FIGS = [
    ("fig17-01_two_ledgers", fig1,
     dict(title="图17-1 权重量化推延迟，KV 量化推容量",
          source="17.2",
          order="先看左栏三条按比例缩短的下限，再看右栏每 token 占用减半，最后看两块里“另一头几乎没动”那句",
          takeaway="瓶颈是 TPOT 就量权重，瓶颈是并发就量 KV；把两者当成一件事会选错",
          boundary="左栏的毫秒数按 1000 GB/s 的规格带宽算，是下限不是预期值；实测能拿到多少要按 17.8 案例一那条除法折算。右栏的并发按 16.6 那张表的口径算")),
    ("fig17-02_benefit_vs_risk", fig2,
     dict(title="图17-2 三项量化手段的收益与质量风险",
          source="17.5、17.6",
          order="先看三项在图上的相对位置，再看编号给出的推荐顺序，最后看右侧那两件该先做的事",
          takeaway="量化是最后一步：先按长度分流、先查框架开销，这两件没有质量风险",
          boundary="纵轴的质量风险是相对排序，不是可测量的刻度；具体损失多大只能用自己的评测集测。横轴的收益按 17.2 的估算，随实测与下限的比值折算后会小很多")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
