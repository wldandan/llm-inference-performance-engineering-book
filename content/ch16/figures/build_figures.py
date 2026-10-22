"""Build the Chapter 16 figure set defined in strategy/reviews/ch16/storyboard.md.

Every number comes from code/ch15/model-7b-generic.json and 16.6's table, and
can be recomputed with code/ch16/kv_capacity.py.

Run from the repository root:

    python3 content/ch16/figures/build_figures.py
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

GIB = 1024 ** 3
KV_PER_TOKEN = 2 * 32 * 8 * 128 * 2        # 131072 bytes = 128 KiB
GPU_GIB = 80.0
UTILIZATION = 0.9                           # vLLM 默认值，16.6 第 1 步
USABLE_GIB = GPU_GIB * UTILIZATION          # 72 GiB
BUDGET_GIB = USABLE_GIB - 14.0 - 6.0        # 52 GiB
TOTAL_TOKENS = int(BUDGET_GIB * GIB / KV_PER_TOKEN)   # 425984


def conc(context: int) -> int:
    return TOTAL_TOKENS // context


# --- 图16-1 连续分配的外部碎片 vs 分页的内部碎片 -----------------------------

def fig1() -> str:
    p = []

    # left: contiguous allocation
    p.append(card(72, 176, 552, 372, cls="card", rx=16))
    p.append(txt(96, 210, "连续分配：外部碎片", cls="b"))
    p.append(txt(96, 234, "每条请求要一整块连续空间", cls="s"))

    lane_x, lane_w = 96, 504
    y = 262
    p.append(bar(lane_x, y, lane_w, 46, cls="soft", rx=6))
    # holes are drawn empty with a dashed outline; live requests are filled
    blocks = [(0, 120, "空洞", None), (120, 96, "C 运行中", COOL),
              (216, 108, "空洞", None), (324, 84, "D 运行中", GOOD),
              (408, 96, "空洞", None)]
    for off, w, label, colour in blocks:
        if colour is None:
            p.append(f'  <rect x="{lane_x + off}" y="{y}" width="{w}" height="46" rx="6" '
                     f'fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.6" '
                     f'stroke-dasharray="6 4"/>')
            p.append(txt(lane_x + off + w / 2, y + 29, label, cls="s", anchor="middle"))
        else:
            p.append(f'  <rect x="{lane_x + off}" y="{y}" width="{w}" height="46" rx="6" '
                     f'fill="{colour}" stroke="{colour}" stroke-width="1.6"/>')
            p.append(f'  <text class="b" x="{lane_x + off + w / 2}" y="{y + 30}" '
                     f'text-anchor="middle" fill="#FFFFFF">{label}</text>')
    p.append(txt(96, y + 74, "三个空洞分别是 1.2、1.1、0.9 GiB，合计 3.2 GiB", cls="s"))

    # the incoming request, drawn to scale, next to the largest hole
    ry2 = y + 92
    p.append(f'  <rect x="{lane_x}" y="{ry2}" width="176" height="34" rx="6" '
             f'fill="#FEF2F2" stroke="{BAD}" stroke-width="1.8"/>')
    p.append(txt(lane_x + 88, ry2 + 23, "新请求要连续的 2 GiB", cls="bad", anchor="middle"))
    p.append(txt(lane_x + 190, ry2 + 23, "总剩余够，却放不进任何一个空洞", cls="b"))

    p.append(note(88, ry2 + 50, 520, [
        "浪费没有上界：碎片有多碎，取决于请求的到达与结束顺序",
        "早期实现还要按 max_tokens 预留，浪费率常超过 60%",
        "16.9 案例一就是这样查了两天：剩 8 GiB，最大的一块只有 1.2 GiB",
    ], cls="badfill"))

    # right: paged allocation
    p.append(card(656, 176, 552, 372, cls="card", rx=16))
    p.append(txt(680, 210, "分页分配：内部碎片", cls="b"))
    p.append(txt(680, 234, "切成固定大小的块，块本身不要求连续", cls="s"))

    gx, gy = 680, 254
    cellw, cellh, gap = 30, 24, 4
    cols = 16
    # 40 blocks: A(10) C(9) D(7) free(13), with the last block of each
    # partially filled to show the internal fragment
    owners = ["A"] * 10 + ["C"] * 9 + ["D"] * 7 + [""] * 14
    colours = {"A": "#DBEAFE", "C": "#D1FAE5", "D": "#FEF3C7", "": "#FFFFFF"}
    strokes = {"A": COOL, "C": GOOD, "D": WARN, "": "#CBD5E1"}
    last = {"A": 9, "C": 18, "D": 25}
    for i, owner in enumerate(owners):
        cxp = gx + (i % cols) * (cellw + gap)
        cyp = gy + (i // cols) * (cellh + gap)
        p.append(f'  <rect x="{cxp}" y="{cyp}" width="{cellw}" height="{cellh}" rx="3" '
                 f'fill="{colours[owner]}" stroke="{strokes[owner]}" stroke-width="1.4"/>')
        if owner and last.get(owner) == i:
            # the partially filled tail block
            p.append(f'  <rect x="{cxp}" y="{cyp}" width="{cellw * 0.4:.0f}" '
                     f'height="{cellh}" rx="3" fill="{strokes[owner]}" opacity="0.55"/>')
    p.append(txt(680, gy + 100, "深色那一小段是每条请求最后一块里没用满的部分", cls="s"))
    p.append(txt(680, gy + 126, "任何一个空闲块都能给任何请求用", cls="b"))
    ry3 = gy + 140
    p.append(f'  <rect x="680" y="{ry3}" width="176" height="34" rx="6" '
             f'fill="#ECFDF5" stroke="{GOOD}" stroke-width="1.8"/>')
    p.append(txt(768, ry3 + 23, "同一个新请求", cls="good", anchor="middle"))
    p.append(txt(870, ry3 + 23, "凑够 16 个空闲块就能开始，不必连续", cls="b"))
    p.append(note(672, ry3 + 48, 520, [
        "浪费有上界：块大小 16 时最多 15 个 token 的空间，平均半块",
        "128 条并发、块大小 16 约浪费 128 MiB；块大小 128 约浪费 1 GiB",
        "所以块大小不是越大越省事，它直接换走一部分并发上限",
    ], cls="goodfill"))

    p.append(note(72, 564, 1136, [
        "分块分配做的其实是一次交换：用内部碎片换掉外部碎片。"
        "这笔交换划得来，因为内部碎片有上界而外部碎片没有。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="外部碎片与内部碎片：分页做的是一次交换",
        desc="左侧是连续分配：一条内存带上三段已结束的请求留下空洞，夹着两段运行中的"
             "请求，空闲总量够但没有一块连续的够用。右侧是分页分配：显存切成固定大小的"
             "块，三条请求各持有若干不连续的块，浪费缩到每条请求最后一块内的未满部分。",
        kicker="第 16 章 · 16.4",
        heading="分页不是消灭浪费，是把没有上界的浪费换成有上界的",
        sub="外部碎片是空闲总量够但没有一块连续的；内部碎片是分出去的块没被用满",
        body="\n".join(p),
        takeaway="用内部碎片换外部碎片：前者有上界，后者没有，所以这笔交换划得来",
    )


# --- 图16-2 容量表的九步瀑布 -------------------------------------------------

def fig2() -> str:
    p = []
    p.append(card(72, 176, 700, 396, cls="card", rx=16))
    p.append(txt(96, 204, "前四步：先按 utilization 折算，再减两项", cls="b"))

    x0, y0 = 120, 218
    full_w = 560
    scale = full_w / 80.0
    rows = [
        ("显存总量", GPU_GIB, None, "soft", ""),
        (f"× gpu_memory_utilization {UTILIZATION}", USABLE_GIB, None, "goodfill", ""),
        ("减权重", USABLE_GIB - 14.0, 14.0, "coolfill", "14 GiB"),
        ("减激活值与框架开销", BUDGET_GIB, 6.0, "warnfill", "6 GiB"),
    ]
    ry = y0
    for label, remain, cut, cls, cut_label in rows:
        # the full 80 GiB track, so the removed part is visibly the rest
        p.append(f'  <rect x="{x0}" y="{ry}" width="{full_w}" height="34" rx="6" '
                 f'fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1.4"/>')
        p.append(bar(x0, ry, remain * scale, 34, cls=cls, rx=6))
        p.append(txt(x0 + 12, ry + 23, label, cls="b"))
        p.append(txt(x0 + remain * scale - 12, ry + 23, f"{remain:.0f} GiB",
                     cls="s", anchor="end"))
        if cut:
            p.append(txt(x0 + full_w - 10, ry + 23, f"扣掉 {cut_label}", cls="s",
                         anchor="end"))
        ry += 42

    p.append(txt(x0, ry + 16, f"剩给 KV Cache 的 {BUDGET_GIB:.0f} GiB，后五步是除法", cls="b"))

    steps = [
        ("每 token KV", "128 KiB", "2 × 32 层 × 8 头 × 128 × 2 字节"),
        ("总 token 容量", f"{TOTAL_TOKENS}", f"{BUDGET_GIB:.0f} GiB ÷ 128 KiB"),
        ("按平均总长切分", "2300 token", "prompt 2000 + 输出 300"),
        ("理论并发", f"{conc(2300)} 条", f"{TOTAL_TOKENS} ÷ 2300"),
        ("打折后的起点", f"{round(conc(2300)*0.7)}~{round(conc(2300)*0.8)} 条", "按 70%~80% 取"),
    ]
    sy = ry + 48
    for label, value, basis in steps:
        p.append(txt(x0, sy, label, cls="b"))
        p.append(txt(x0 + 180, sy, value, cls="mb"))
        p.append(txt(x0 + 320, sy, basis, cls="s"))
        sy += 30

    p.append(card(796, 176, 412, 396, cls="card", rx=16))
    p.append(txt(820, 206, "四步只能按自己的服务取值", cls="b"))
    p.append(note(812, 222, 380, [
        "第 1 步 gpu_memory_utilization 默认 0.9",
        "按整张卡起算，KV 预算要高估 8 GiB",
    ], cls="badfill"))
    p.append(note(812, 310, 380, [
        "第 3 步 激活值与框架开销要实测",
        "读启动日志，用预算减权重减 KV 池反推",
    ], cls="warnfill"))
    p.append(note(812, 398, 380, [
        "第 7 步 用平均而不是 P99",
        "平均值默认了混合比例稳定（见图16-3）",
    ], cls="coolfill"))
    p.append(note(812, 486, 380, [
        "第 9 步 折扣是给波动留的余量",
        "长度尾部、到达突发、抢占恢复都要余量",
    ], cls="goodfill"))

    p.append(note(72, 588, 1136, [
        f"这张表的用途不是精确预测，是给容量规划一个起点：它告诉你该在 "
        f"{round(conc(2300) * 0.7 / 10) * 10} 附近做压测，而不是从 8 开始一档一档试到 300。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="容量表的九步：80 GiB 怎么变成 130 条",
        desc="上半部分是一个四级瀑布：80 GiB 的显存先按 gpu_memory_utilization 0.9 折成 72 GiB，减去 14 GiB 权重得到 58 GiB，"
             "再减去 6 GiB 激活值与框架开销得到 52 GiB。下半部分是五步除法：每 token "
             "128 KiB、总容量 425984 token、平均长度 2300、理论并发 185 条、打折后 "
             "130 到 148 条。右侧标出第 1、3、7、9 四步为什么只能按自己的服务取值。",
        kicker="第 16 章 · 16.6",
        heading="80 GiB 怎么一步步变成 130 条",
        sub="先按 utilization 折算，再减两项，后五步是除法；四步要按自己的服务取值",
        body="\n".join(p),
        takeaway="这张表给的是压测起点，不是预测；第 1 步和第 3 步取错了，后面全错",
    )


# --- 图16-3 并发与上下文长度成反比 -------------------------------------------

def fig3() -> str:
    p = []
    x0, y0, x1, y1 = 156, 214, 740, 486
    p.append(card(72, 176, 720, 372, cls="card", rx=16))
    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.8"/>')
    p.append(txt(96, 202, "理论并发随平均总长度成反比下降", cls="b"))

    hi_ctx, hi_conc = 34000, 230.0

    def cx(c: float) -> float:
        return x0 + c / hi_ctx * (x1 - x0)

    def cy(v: float) -> float:
        return y1 - min(v, hi_conc) / hi_conc * (y1 - y0)

    pts = " ".join(f"{cx(c):.0f},{cy(conc(c)):.0f}"
                   for c in range(2200, hi_ctx + 1, 200))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{COOL}" stroke-width="3"/>')

    marks = [(2300, f"{conc(2300)}", "基准", 20, 24, "start"),
             (4600, f"{conc(4600)}", "减半", 20, -18, "start"),
             (9200, f"{conc(9200)}", "四分之一", 20, -18, "start"),
             (32000, f"{conc(32000)}", "十四分之一", -14, -46, "end")]
    for c, label, rel, dx, dy, anchor in marks:
        p.append(f'  <circle cx="{cx(c):.0f}" cy="{cy(conc(c)):.0f}" r="6" fill="{COOL}"/>')
        p.append(txt(cx(c) + dx, cy(conc(c)) + dy, f"{label} 条", cls="b", anchor=anchor))
        p.append(txt(cx(c) + dx, cy(conc(c)) + dy + 20, rel, cls="s", anchor=anchor))

    for c in (2300, 4600, 9200, 16000, 24000, 32000):
        p.append(f'  <path d="M{cx(c):.0f} {y1}V{y1 + 6}" stroke="#94A3B8" stroke-width="1.6"/>')
        p.append(txt(cx(c), y1 + 26, str(c), cls="s", anchor="middle"))
    p.append(txt(x1, y1 + 48, "平均总长度（token）", cls="s", anchor="end"))
    for v in (50, 100, 150, 200):
        p.append(txt(x0 - 12, cy(v) + 5, str(v), cls="s", anchor="end"))
    p.append(txt(96, y1 + 48, "上下文翻倍，并发减半，因为它在分母上", cls="b"))

    # the mixed distribution: the average is not the ceiling
    p.append(card(816, 176, 392, 372, cls="card", rx=16))
    p.append(txt(840, 210, "平均值不是上限", cls="b"))
    p.append(note(832, 230, 344, [
        "97% 的请求 2300 token",
        "3% 的请求 32000 token",
        "混合平均 3191 token  →  133 条",
    ], cls="coolfill"))
    p.append(note(832, 344, 344, [
        "全是长请求时  →  13 条",
        "一批长请求就能把整张卡占满",
        "排队的大多是那 97% 的短请求",
    ], cls="badfill"))
    p.append(note(832, 458, 344, [
        "所以上限由最坏情况下的混合决定",
        "不是由平均长度决定",
    ], cls="soft"))

    p.append(note(72, 564, 1136, [
        "上下文长度是一个三重成本：TTFT 变长、token 账单变多、并发上限下降。"
        "前两个是每次调用的成本，第三个是基础设施的成本，而第三个往往最贵。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="并发上限与上下文长度成反比，而平均值不是上限",
        desc="一条反比曲线画出理论并发随平均总长度的下降，标出四个点：2300 token 时 "
             "185 条、4600 时 92 条、9200 时 46 条、32000 时 13 条。右侧给出一个混合"
             "长度分布的例子：97% 短请求加 3% 长请求，按平均算是 133 条，而全是长请求时"
             "只有 13 条。",
        kicker="第 16 章 · 16.7、16.9",
        heading="上下文在分母上，所以并发和它成反比",
        sub="同样的流量，上下文翻倍就要两倍的卡；而按平均长度算出来的那个数还不是上限",
        body="\n".join(p),
        takeaway="并发上限不是由平均长度决定的，是由最坏情况下的混合决定的",
    )


FIGS = [
    ("fig16-01_fragmentation", fig1,
     dict(title="图16-1 外部碎片与内部碎片：分页做的是一次交换",
          source="16.4",
          order="先看左边那条内存带上的空洞，再看右边那些不要求连续的块，最后看两块说明里“有没有上界”这一句",
          takeaway="用内部碎片换外部碎片：前者有上界，后者没有，所以这笔交换划得来",
          boundary="块的数量和大小是示意，不对应任何具体配置。左边那 8 GiB 与 1.2 GiB 来自 16.9 案例一，是合成案例的数字")),
    ("fig16-02_capacity_waterfall", fig2,
     dict(title="图16-2 容量表的九步：80 GiB 怎么变成 130 条",
          source="16.6",
          order="先看上面的瀑布怎么把 80 GiB 先按 0.9 折成 72 GiB、再削到 52 GiB，然后看下面五步除法，最后看右侧那四步为什么只能按自己的服务取值",
          takeaway="这张表给的是压测起点，不是预测；第 1 步和第 3 步取错了，后面全错",
          boundary="6 GiB 那个开销是经验值，因版本与配置而异，必须在自己的环境里实测。全部数字由 code/ch16/kv_capacity.py 算出，换模型或换卡只改共享配置")),
    ("fig16-03_context_inverse", fig3,
     dict(title="图16-3 并发上限与上下文长度成反比，而平均值不是上限",
          source="16.7、16.9",
          order="先看曲线掉得多快，再看四个标注点的相对变化，最后看右侧那个混合分布里 133 与 13 的差",
          takeaway="并发上限不是由平均长度决定的，是由最坏情况下的混合决定的",
          boundary="曲线按 52 GiB 的 KV 预算和每 token 128 KiB 算，是理论上限，不含 16.6 第 9 步那个折扣。右侧那个 97/3 的分布是 16.9 案例三的数字，换负载要重算")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
