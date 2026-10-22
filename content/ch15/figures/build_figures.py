"""Build the Chapter 15 figure set defined in strategy/reviews/ch15/storyboard.md.

Every number here comes from code/ch15/model-7b-generic.json and the chapter
text, and can be recomputed with code/ch15/decode_model.py. The curve in
fig15-04 is sampled from the same two terms the chapter gives.

Run from the repository root:

    python3 content/ch15/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, arrow, bar, card, dashed, hpath, note, page, txt,
    vpath, write, write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

PARAMS = 7e9
BYTES = 2
BANDWIDTH = 1000.0          # GB/s, decimal
WEIGHT_GB = PARAMS * BYTES / 1e9            # 14.0
FLOOR_MS = WEIGHT_GB / BANDWIDTH * 1000     # 14.0
KV_PER_TOKEN = 2 * 32 * 8 * 128 * BYTES     # 131072 bytes = 128 KiB
GIB = 1024 ** 3


def step_ms(batch: int, context: int) -> float:
    """Weight read plus KV read, both over the same bandwidth."""
    return (PARAMS * BYTES + batch * context * KV_PER_TOKEN) / (BANDWIDTH * 1e9) * 1000


# --- 图15-1 算术强度数轴上 Decode 的位置 -------------------------------------

def fig1() -> str:
    import math
    p = []
    p.append(card(72, 176, 1136, 248, cls="card", rx=16))
    ax_y = 300
    x0, x1 = 148, 1140
    p.append(f'  <path d="M{x0} {ax_y}H{x1}" fill="none" stroke="#94A3B8" stroke-width="2"/>')
    p.append(txt(100, 206, "算术强度（FLOP/byte，对数刻度）", cls="b"))

    lo, hi = math.log10(1), math.log10(16384)

    def px(v: float) -> float:
        return x0 + (math.log10(v) - lo) / (hi - lo) * (x1 - x0)

    for v, label in ((16, "16"), (64, "64"), (256, "256"), (1024, "1024"),
                     (4096, "4096"), (16384, "16384")):
        xv = px(v)
        p.append(f'  <path d="M{xv:.0f} {ax_y - 6}V{ax_y + 6}" stroke="#94A3B8" stroke-width="1.6"/>')
        p.append(txt(xv, ax_y + 26, label, cls="s", anchor="middle"))

    bx = px(153)
    p.append(dashed(bx, 232, bx, ax_y - 12))
    p.append(txt(bx, 226, "A100 分界点 153", cls="b", anchor="middle"))
    p.append(f'  <rect x="{x0}" y="{ax_y - 24}" width="{bx - x0:.0f}" height="16" '
             f'fill="#DBEAFE" stroke="none"/>')
    p.append(f'  <rect x="{bx:.0f}" y="{ax_y - 24}" width="{x1 - bx:.0f}" height="16" '
             f'fill="#D1FAE5" stroke="none"/>')
    p.append(txt((x0 + bx) / 2, ax_y - 34, "带宽受限：算力在等数据", cls="cool", anchor="middle"))
    p.append(txt((bx + x1) / 2, ax_y - 34, "算力受限", cls="good", anchor="middle"))

    # Decode's three points sit within one doubling of each other, so they share
    # one bracket rather than three colliding labels.
    for v in (1, 2, 4):
        p.append(f'  <circle cx="{px(v):.0f}" cy="{ax_y}" r="6" fill="{COOL}"/>')
    b1, b4 = px(1), px(4)
    p.append(f'  <path d="M{b1:.0f} {ax_y + 14}V{ax_y + 28}H{b4:.0f}V{ax_y + 14}" '
             f'fill="none" stroke="{COOL}" stroke-width="1.8"/>')
    p.append(f'  <path d="M{(b1 + b4) / 2:.0f} {ax_y + 28}V{ax_y + 42}" '
             f'stroke="{COOL}" stroke-width="1.8"/>')
    p.append(txt(b1 - 6, ax_y + 64, "Decode 批量 1", cls="b"))
    p.append(txt(b1 - 6, ax_y + 86, "FP16 是 1 · INT8 是 2 · INT4 是 4", cls="s"))

    pxp = px(602)
    p.append(f'  <circle cx="{pxp:.0f}" cy="{ax_y}" r="6" fill="{GOOD}"/>')
    p.append(f'  <path d="M{pxp:.0f} {ax_y + 8}V{ax_y + 42}" stroke="{GOOD}" stroke-width="1.8"/>')
    p.append(txt(pxp, ax_y + 64, "Prefill 8000 token ≈ 602", cls="b", anchor="middle"))
    p.append(txt(pxp, ax_y + 86, "算上激活读写，0.5B 模型（第 11.4 节）", cls="s", anchor="middle"))

    p.append(note(72, 444, 552, [
        "这个 1 不是巧合，是恒等式",
        "每个参数每 token 约 2 次运算 ÷ 每参数 2 字节 = 1",
        "参数量在分子分母里约掉，所以与模型多大无关",
    ], cls="coolfill"))
    p.append(note(656, 444, 552, [
        "量化是把 Decode 往右推，但推不了多远",
        "INT4 之后也才 4，离 153 还差近两个数量级",
        "所以先撑不住的是质量，不是硬件（第 17 章）",
    ], cls="goodfill"))
    p.append(note(72, 564, 1136, [
        "Prefill 和 Decode 落在分界点的两侧，相差两到三个数量级。"
        "这一根轴就是这两篇分开写的理由：优化方向完全相反。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="算术强度数轴上 Prefill 与 Decode 的位置",
        desc="一根对数刻度的算术强度数轴。A100 的 153 FLOP/byte 分界点把它分成"
             "带宽受限与算力受限两段。Decode 批量 1 在 FP16、INT8、INT4 下分别落在 "
             "1、2、4，全部在带宽受限那一侧；Prefill 处理 8000 token 时，算上激活读写约 602，"
             "在算力受限那一侧。",
        kicker="第 15 章 · 15.2",
        heading="Decode 和 Prefill 在同一根轴的两端",
        sub="批量 1 的 Decode 恒等于 1 FLOP/byte，与模型多大无关；卡的分界点在上百",
        body="\n".join(p),
        takeaway="批量 1 的 Decode 是 1 FLOP/byte，卡的分界点是 153，差两个数量级，算力在等数据",
    )


# --- 图15-2 单步耗时的构成 ---------------------------------------------------

def fig2() -> str:
    p = []
    p.append(card(72, 176, 1136, 244, cls="card", rx=16))
    p.append(txt(96, 208, "一步 Decode 的时间去哪了（7B、FP16、1000 GB/s）", cls="b"))

    # 14 + 0.5 + 2.5 = 17, exactly the arithmetic 15.6 gives.
    scale = 60.0
    x, y, h = 120, 264, 52
    segs = [
        ("权重搬运", 14.0, "coolfill", COOL),
        ("kernel 启动", 0.5, "warnfill", WARN),
        ("引擎侧准备", 2.5, "badfill", BAD),
    ]
    narrow: list[tuple[float, str, str]] = []
    for label, ms, fill, colour in segs:
        w = ms * scale
        p.append(bar(x, y, w, h, cls=fill, rx=4))
        if w > 110:
            p.append(txt(x + w / 2, y + 28, label, cls="b", anchor="middle"))
            p.append(txt(x + w / 2, y + 48, f"{ms} ms", cls="m", anchor="middle"))
        else:
            narrow.append((x + w / 2, f"{label} {ms} ms", colour))
        x += w
    end = x

    # narrow segments get leader lines instead of labels inside the bar
    for i, (lx, label, colour) in enumerate(narrow):
        ly = y + h + 24 + i * 26
        p.append(f'  <path d="M{lx:.0f} {y + h}V{ly - 10}" stroke="{colour}" stroke-width="1.6"/>')
        p.append(txt(lx - 6, ly, label, cls="s", anchor="end"))

    floor_end = 120 + FLOOR_MS * scale
    p.append(f'  <path d="M120 {y - 26}V{y - 16}H{floor_end:.0f}V{y - 26}" class="bracket"/>')
    p.append(txt(120 + FLOOR_MS * scale / 2, y - 34, f"理论下限 {FLOOR_MS:.0f} ms（只有权重）",
                 cls="b", anchor="middle"))
    p.append(f'  <path d="M120 {y + h + 68}V{y + h + 58}H{end:.0f}V{y + h + 68}" class="bracket"/>')
    p.append(txt((120 + end) / 2, y + h + 90, "实测 17 ms", cls="b", anchor="middle"))
    p.append(txt((120 + end) / 2 + 84, y + h + 90, f"（比值 {17 / FLOOR_MS:.2f}，带宽受限）", cls="cool"))

    p.append(note(72, 438, 552, [
        "那 3 ms 是每一步都要付的",
        "3 ms × 500 步 = 1.5 秒，用户等的是这个总和",
        "算每步耗时时看毫秒，算用户等待时看总和",
        "两个视角都要有，但不能互相冒充",
    ], cls="badfill"))
    p.append(note(656, 438, 552, [
        "第 18 章的 CUDA Graph 只治 kernel 启动那 0.5 ms",
        "引擎侧那 2.5 ms 它治不了",
        "比值 1.21 在 1.3 以内，判带宽受限",
        "比值超过 2，先去查这 3 ms 而不是去量化",
    ], cls="warnfill"))
    p.append(note(72, 564, 1136, [
        "这张图没画 KV 搬运那一份，因为它随上下文和批量变，不是定值，见图15-4。"
        "下限算的是“最好能多快”，不是“会有多快”，所以实测总比它大。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="一步 Decode 的时间构成与实测的差",
        desc="一条横向堆叠条，按毫秒成比例分成三段：权重搬运 14 ms、kernel 启动 0.5 ms、"
             "引擎侧准备 2.5 ms，合计 17 ms。上方括号标出 14 ms 的理论下限，"
             "下方括号标出 17 ms 的实测值，比值 1.21。",
        kicker="第 15 章 · 15.3、15.6",
        heading="理论下限 14 ms，实测 17 ms，中间那 3 ms 去哪了",
        sub="下限只算权重搬运；差出来的是 kernel 启动加引擎侧准备，两者治法不同",
        body="\n".join(p),
        takeaway="下限只算权重；差出来的 3 ms 里只有 0.5 ms 是 CUDA Graph 能治的",
    )


# --- 图15-3 批量的免费区间与三处边界 ----------------------------------------

def fig3() -> str:
    """Two stacked panels sharing one x-axis.

    Throughput and single-request TPOT have different units, so a twin y-axis
    would put them in the same coordinate space and invite a comparison that
    means nothing. Stacked panels keep the one claim that matters visible: the
    top line climbs steeply while the bottom line barely moves.
    """
    import math
    p = []
    p.append(card(72, 176, 680, 396, cls="card", rx=16))

    x0, x1 = 152, 700
    batches = [1, 2, 4, 8, 16, 32, 64, 128, 256]
    tps = [b / step_ms(b, 512) * 1000 for b in batches]
    tpot = [step_ms(b, 512) for b in batches]

    def bx(b: float) -> float:
        return x0 + math.log2(b) / math.log2(256) * (x1 - x0)

    cross_x = bx(153)

    # panel 1: throughput
    t0, t1 = 206, 346
    top_tps = 8600.0
    p.append(txt(96, 200, "吞吐（token/s）", cls="b"))
    p.append(f'  <rect x="{x0}" y="{t0}" width="{cross_x - x0:.0f}" height="{t1 - t0}" '
             f'fill="#ECFDF5" stroke="none"/>')
    p.append(f'  <rect x="{cross_x:.0f}" y="{t0}" width="{x1 - cross_x:.0f}" '
             f'height="{t1 - t0}" fill="#F1F5F9" stroke="none"/>')
    p.append(f'  <path d="M{x0} {t0}V{t1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.6"/>')
    pts = " ".join(f"{bx(b):.0f},{t1 - v / top_tps * (t1 - t0):.0f}"
                   for b, v in zip(batches, tps))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{COOL}" stroke-width="3"/>')
    p.append(txt(bx(32) + 8, t1 - tps[5] / top_tps * (t1 - t0) + 4, "1982", cls="m"))
    p.append(txt(x0 + 8, t1 - 8, "71", cls="m"))

    # panel 2: single-request TPOT
    s0, s1 = 380, 500
    top_ms = 36.0
    p.append(txt(96, 374, "单条请求的 TPOT（ms）", cls="b"))
    p.append(f'  <rect x="{x0}" y="{s0}" width="{cross_x - x0:.0f}" height="{s1 - s0}" '
             f'fill="#ECFDF5" stroke="none"/>')
    p.append(f'  <rect x="{cross_x:.0f}" y="{s0}" width="{x1 - cross_x:.0f}" '
             f'height="{s1 - s0}" fill="#F1F5F9" stroke="none"/>')
    p.append(f'  <path d="M{x0} {s0}V{s1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.6"/>')
    pts = " ".join(f"{bx(b):.0f},{s1 - v / top_ms * (s1 - s0):.0f}"
                   for b, v in zip(batches, tpot))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{GOOD}" stroke-width="3"/>')
    p.append(txt(x0 + 8, s1 - tpot[0] / top_ms * (s1 - s0) - 8, "14.1", cls="m"))
    p.append(txt(bx(32) - 4, s1 - tpot[5] / top_ms * (s1 - s0) - 8, "16.1", cls="m"))

    # shared x axis
    p.append(dashed(cross_x, t0 - 14, cross_x, s1 + 6))
    p.append(txt(cross_x, t0 - 20, "交叉批量 153", cls="b", anchor="middle"))
    for b in (1, 8, 32, 128, 256):
        p.append(txt(bx(b), s1 + 22, str(b), cls="s", anchor="middle"))
    p.append(txt(96, s1 + 22, "批量", cls="s"))

    p.append(txt(96, 548, "批量 1 → 32：吞吐涨 28 倍，单条 TPOT 只从 14.1 涨到 16.1 ms", cls="b"))

    p.append(card(776, 176, 432, 396, cls="card", rx=16))
    p.append(txt(800, 210, "免费到哪里为止：三处边界", cls="b"))
    bounds = [
        ("一 KV 显存装不下", "每条请求各存一份 KV，批量越大占越多", "第 16 章", WARN),
        ("二 滑向算力受限", "算术强度 ≈ 批量，越过 153 就真的变慢", "15.4", BAD),
        ("三 Attention 不摊薄", "KV 是各自的，读取量随批量线性涨", "15.7", COOL),
    ]
    by_ = 236
    for title, why, where, colour in bounds:
        p.append(f'  <rect x="800" y="{by_}" width="384" height="88" rx="12" '
                 f'fill="#FFFFFF" stroke="{colour}" stroke-width="1.6"/>')
        p.append(txt(818, by_ + 28, title, cls="b"))
        p.append(txt(818, by_ + 52, why, cls="s"))
        p.append(txt(818, by_ + 74, where, cls="m"))
        by_ += 100
    p.append(txt(800, 552, "灰色那段是估算模型自己失效的地方：它只算搬运，不算算力", cls="s"))

    p.append(note(72, 588, 1136, [
        "两栏共用一根横轴，不叠成双纵轴：两者量纲不同，叠在一起会诱导一个没有意义的比较。"
        "要看的只有一件事，就是上面那条涨得很陡而下面那条几乎不动。",
    ], cls="goodfill"))

    return page(
        system=SYSTEM,
        title="批量的免费区间与三处边界",
        desc="左侧两栏共用一根对数刻度的批量横轴，从 1 到 256。批量 1 到 32，上栏吞吐从 71 涨到"
             "1982 token/s，下栏单条 TPOT 只从 14.1 ms 涨到 16.1 ms；到批量 256 吞吐八千多，"
             "TPOT 也到了 31 ms。批量 153 以下的区域标为绿色，以上标为灰色，表示估算模型在那里失效。"
             "右侧列出让免费停止的三处边界。",
        kicker="第 15 章 · 15.4",
        heading="批量是 Decode 唯一的免费午餐，但免费有边界",
        sub="权重只读一遍却服务 B 个 token，所以吞吐涨而单条 TPOT 几乎不变",
        body="\n".join(p),
        takeaway="带宽受限区间内加批量近乎免费；越过交叉批量 153 之后，再加就真的变慢",
    )


# --- 图15-4 单步时间随生成长度的爬升 ----------------------------------------

def fig4() -> str:
    p = []
    x0, y0, x1, y1 = 156, 214, 772, 492
    p.append(card(72, 176, 740, 380, cls="card", rx=16))
    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.8"/>')
    p.append(txt(96, 202, "单步耗时（ms）随已生成长度爬升", cls="b"))

    hi_ctx = 16000
    hi_ms = 90.0

    def cx(c: float) -> float:
        return x0 + c / hi_ctx * (x1 - x0)

    def cy(v: float) -> float:
        return y1 - min(v, hi_ms) / hi_ms * (y1 - y0)

    p.append(dashed(x0, cy(FLOOR_MS), x1, cy(FLOOR_MS)))
    p.append(txt(x1 - 6, cy(FLOOR_MS) + 22, f"权重下限 {FLOOR_MS:.0f} ms，不随长度变",
                 cls="s", anchor="end"))

    for batch, colour, label, dy in ((1, COOL, "批量 1", -10),
                                     (8, GOOD, "批量 8", -14),
                                     (32, BAD, "批量 32", -14)):
        pts = " ".join(f"{cx(c):.0f},{cy(step_ms(batch, c)):.0f}"
                       for c in range(0, hi_ctx + 1, 500))
        p.append(f'  <polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="3"/>')
        p.append(txt(cx(hi_ctx) - 8, cy(step_ms(batch, hi_ctx)) + dy, label,
                     cls="b", anchor="end"))

    for c, label in ((0, "0"), (4000, "4000"), (8000, "8000"),
                     (12000, "12000"), (16000, "16000")):
        p.append(f'  <path d="M{cx(c):.0f} {y1}V{y1 + 6}" stroke="#94A3B8" stroke-width="1.6"/>')
        p.append(txt(cx(c), y1 + 26, label, cls="s", anchor="middle"))
    p.append(txt(x1, y1 + 48, "已生成长度（token）", cls="s", anchor="end"))
    for v in (14, 30, 50, 70, 90):
        p.append(txt(x0 - 12, cy(v) + 5, str(v), cls="s", anchor="end"))

    # the point where the KV read overtakes the weight read, annotated inside
    cross, cbatch = 8000, 32
    mx, my = cx(cross), cy(step_ms(cbatch, cross))
    p.append(f'  <circle cx="{mx:.0f}" cy="{my:.0f}" r="8" fill="none" '
             f'stroke="{BAD}" stroke-width="2.5"/>')
    p.append(f'  <path d="M{mx:.0f} {my:.0f}L{mx - 70:.0f} {my - 46:.0f}" '
             f'stroke="{BAD}" stroke-width="1.6" fill="none"/>')
    p.append(txt(mx - 76, my - 52, "批量 32、8000 token", cls="bad", anchor="end"))
    p.append(txt(mx - 76, my - 32, "KV 31 GiB 已超过权重 13 GiB", cls="bad", anchor="end"))

    p.append(txt(96, y1 + 48, "批量 1 几乎贴着下限，批量 32 到右端已是下限的近六倍", cls="b"))

    p.append(card(836, 176, 372, 380, cls="card", rx=16))
    p.append(txt(860, 210, "两条曲线，两种机理", cls="b"))
    p.append(note(852, 230, 340, [
        "Prefill 那边：计算量的平方项",
        "输入翻倍，时间涨不到四倍但超过两倍",
        "机理是注意力矩阵的面积",
    ], cls="goodfill"))
    p.append(note(852, 346, 340, [
        "Decode 这边：KV 读取量的线性增长",
        "而且会被批量放大：32 条各 8000 token",
        "读取量是单条的 32 倍，摊不掉",
    ], cls="badfill"))
    p.append(note(852, 462, 340, [
        "所以“长上下文让 Decode 变慢”",
        "不是错觉，但和 Prefill 完全不同",
    ], cls="soft"))

    p.append(note(72, 572, 1136, [
        "权重那一份是每条请求共用的，KV 那一份是每条请求各自的。"
        "这一句话同时解释了批量为什么在短上下文下几乎免费、在长上下文下为什么不再免费。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="单步耗时随生成长度的爬升，以及批量怎么放大它",
        desc="三条曲线画出批量 1、8、32 下单步耗时随已生成长度的变化，横轴 0 到 16000 "
             "token。一条虚线标出 14 ms 的权重下限，它不随长度变化。批量 32 在 8000 "
             "token 处被圈出，此处 KV 读取量 31 GiB 已超过权重的 13 GiB。",
        kicker="第 15 章 · 15.7",
        heading="生成越长，单步越慢，而批量会放大这件事",
        sub="权重那一份共用，KV 那一份各自；只有后者随长度和批量一起涨",
        body="\n".join(p),
        takeaway="权重共用、KV 各自：批量 32 到 8000 token 时 KV 读取已超过权重，批量不再免费",
    )


FIGS = [
    ("fig15-01_intensity_axis", fig1,
     dict(title="图15-1 算术强度数轴上 Decode 的位置",
          source="15.2",
          order="先看轴上那条 153 的分界线，再看 Decode 的三个点全在左侧，最后看 Prefill 在右端",
          takeaway="批量 1 的 Decode 恒等于 1 FLOP/byte，与模型大小无关；量化最多推到 4，离 153 还差两个数量级",
          boundary="153 是 A100 的规格峰值算力除以规格带宽，是量级而非阈值；常见数据中心卡的分界点在一两百到几百之间。Prefill 那一点按第 11.4 节算上激活读写，是 0.5B 模型的值，宽模型会更高。轴用对数刻度")),
    ("fig15-02_step_breakdown", fig2,
     dict(title="图15-2 一步 Decode 的时间构成与实测的差",
          source="15.3、15.6",
          order="先看上方那个 14 ms 的下限括号，再看条里三段各占多少，最后看下方 17 ms 的实测括号",
          takeaway="下限只算权重搬运；差出来的 3 ms 里只有 0.5 ms 是 CUDA Graph 能治的",
          boundary="三段的长度按毫秒成比例。0.5 ms 与 2.5 ms 是这个量级上的典型值，不是实测，具体系统要用 Profiling 自己拆；14 ms 由 code/ch15/decode_model.py 算出")),
    ("fig15-03_batch_free_lunch", fig3,
     dict(title="图15-3 批量的免费区间与三处边界",
          source="15.4",
          order="先看上栏那条涨得很陡的吞吐曲线，再看下栏几乎不动的 TPOT，最后看右侧三处边界",
          takeaway="带宽受限区间内加批量近乎免费；越过交叉批量 153 之后，再加就真的变慢",
          boundary="两条曲线按参考卡（带宽 1000 GB/s、分界点 153，与 A100 相同）和 512 token 上下文算，长上下文下会明显不同（见图15-4）。灰色区从 153 起，是忽略 KV 读取时的交叉批量；把 512 token 的 KV 算进去，交叉批量其实要到五六百。它们只算搬运不算算力，所以 153 右侧那段灰色区域是模型自己失效的地方，不是预测。换卡或换位宽，交叉批量都会移动")),
    ("fig15-04_context_climb", fig4,
     dict(title="图15-4 单步耗时随生成长度的爬升，以及批量怎么放大它",
          source="15.7",
          order="先看那条不动的权重下限虚线，再看三条曲线的斜率差，最后看批量 32 在 8000 token 处被圈出的那一点",
          takeaway="权重共用、KV 各自：批量 32 到 8000 token 时 KV 读取已超过权重，批量不再免费",
          boundary="三条曲线只算权重搬运加 KV 搬运，不含调度开销，所以它们都低于实测。图里的长度是已生成长度加输入长度的总和")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
