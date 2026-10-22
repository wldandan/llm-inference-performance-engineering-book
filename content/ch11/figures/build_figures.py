"""Build the Chapter 11 figure set defined in strategy/reviews/ch11/storyboard.md.

Every number here comes from code/ch11/model-qwen25-05b.json and the chapter
text, and can be recomputed with code/ch11/prefill_model.py. The curves in
fig11-01 are sampled from the same two expressions the chapter gives.

Run from the repository root:

    python3 content/ch11/figures/build_figures.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, arrow, bar, card, dashed, hpath, note, page, txt,
    vpath, write, write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

CROSSOVER = 16640          # 2*896 + 2*128 + 3*4864
HIDDEN, LAYERS, KV_DIM = 896, 24, 128


def rel(s: float) -> float:
    """The chapter's relative compute: S x (crossover + S)."""
    return s * (CROSSOVER + s)


# --- 图11-1 GEMM 与 Attention 在 16640 处交叉 --------------------------------

def fig1() -> str:
    p = []
    # plot frame, linear in S so GEMM really looks straight
    x0, y0, x1, y1 = 128, 206, 712, 506
    p.append(card(72, 182, 692, 388, cls="card", rx=16))
    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.8"/>')

    hi = 24000
    top = 24000 * 24000 * 1.04

    def px(s: float) -> float:
        return x0 + s / hi * (x1 - x0)

    def py(v: float) -> float:
        return y1 - min(v / top, 1.0) * (y1 - y0)

    samples = list(range(0, hi + 1, 1000))
    gemm = " ".join(f"{px(s):.1f},{py(CROSSOVER * s):.1f}" for s in samples)
    attn = " ".join(f"{px(s):.1f},{py(s * s):.1f}" for s in samples)
    p.append(f'  <polyline points="{attn}" fill="none" stroke="{WARN}" stroke-width="3"/>')
    p.append(f'  <polyline points="{gemm}" fill="none" stroke="{COOL}" stroke-width="3"/>')

    cx, cy = px(CROSSOVER), py(CROSSOVER * CROSSOVER)
    p.append(dashed(cx, y1, cx, cy))
    p.append(f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="#0F172A"/>')
    p.append(txt(cx + 14, cy + 30, "交叉点 16640", cls="mb"))
    p.append(txt(cx + 14, cy + 52, "两部分正好相等", cls="s"))

    p.append(f'  <text class="b" x="{px(19000):.1f}" y="{py(19000 * 19000) - 16:.1f}" '
             f'text-anchor="end" fill="{WARN}">Attention  S²（抛物线）</text>')
    p.append(f'  <text class="b" x="{px(7500):.1f}" y="{py(CROSSOVER * 7500) - 26:.1f}" '
             f'fill="{COOL}">GEMM  16640 × S（直线）</text>')

    for s in (0, 8000, 16640, 24000):
        p.append(txt(px(s), y1 + 28, f"{s}" if s else "0", cls="m", anchor="middle"))
    p.append(txt(x1, y1 + 52, "输入长度 S", cls="s", anchor="end"))
    p.append(txt(x0 - 16, y0 + 4, "相对计算量", cls="s", anchor="end"))
    p.append(txt(72, 604, "交叉点 = 2 × hidden + 2 × KV 维度 + 3 × MLP 中间维度 = 2×896 + 2×128 + 3×4864，与层数无关；MLP 中间维度最大，宽 MLP 的模型交叉点更靠后", cls="s"))

    # attention share table
    p.append(card(788, 182, 436, 196, cls="soft", rx=14))
    p.append(txt(812, 216, "Attention 占总计算量", cls="h"))
    for i, (s, share) in enumerate((("512", "3%"), ("2048", "11%"), ("8000", "32%"),
                                    ("16640", "50%"), ("32768", "66%"))):
        y = 252 + 26 * i
        p.append(txt(812, y, f"{s} token", cls="m"))
        p.append(txt(1200, y, share, cls="mb" if s == "16640" else "m", anchor="end"))

    # doubling table
    p.append(card(788, 394, 436, 176, cls="soft", rx=14))
    p.append(txt(812, 426, "长度翻倍，计算量涨几倍", cls="h"))
    rows = [("1000 → 2000", "2.11"), ("2000 → 4000", "2.21"),
            ("8000 → 16000", "2.65"), ("16640 → 33280", "3.00"), ("再往长", "趋近 4，取不到")]
    for i, (a, b) in enumerate(rows):
        y = 460 + 26 * i
        p.append(txt(812, y, a, cls="m"))
        p.append(txt(1200, y, b, cls="mb" if a.startswith("16640") else "m", anchor="end"))
    return page(
        system=SYSTEM,
        title="图 11-1 GEMM 与 Attention 在 16640 处交叉",
        desc="双曲线图：GEMM 随输入长度线性增长，Attention 随长度平方增长，"
             "两者在 16640 token 处相交；右侧列出长度翻倍时计算量的实际倍数，"
             "交叉点上正好三倍，四倍取不到。",
        kicker="CH11 · 11.2",
        heading="GEMM 与 Attention 在 16640 处交叉",
        sub="输入翻倍，时间为什么不是翻倍，也到不了四倍",
        body="\n".join(p),
        takeaway="Attention 占多少由长度决定，交叉点由模型形状决定；上下文窗口内翻倍最多涨到约三倍。",
    )


# --- 图11-2 KV Cache 往两个方向长 -------------------------------------------

def fig2() -> str:
    p = []
    # single-token breakdown
    p.append(card(72, 190, 300, 196, cls="soft", rx=14))
    p.append(txt(92, 222, "一个 token 要写多少", cls="h"))
    p.append(txt(92, 256, "2 × 2 × 64 × 2 B = 512 B", cls="m"))
    p.append(txt(92, 280, "K 和 V   KV 头   head_dim   FP16", cls="s"))
    p.append(txt(92, 318, "512 B × 24 层 = 12 KiB", cls="mb"))
    p.append(txt(92, 352, "GQA 只有 2 个 KV 头，", cls="s"))
    p.append(txt(92, 374, "标准 MHA 是 14 个，大七倍", cls="s"))

    # two-axis plane
    x0, y0, x1, y1 = 470, 206, 900, 546
    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.8"/>')
    p.append(txt(x1, y1 + 30, "序列长度（线性）", cls="b", anchor="end"))
    p.append(txt(x0 - 14, y0 - 12, "并发数（线性）", cls="b"))
    for i in range(1, 5):
        p.append(dashed(x0, y1 - i * 68, x1, y1 - i * 68))
        p.append(dashed(x0 + i * 86, y0, x0 + i * 86, y1))

    pts = [
        (x0 + 86, y1 - 68, "94 MiB", "8000 token，单条", GOOD),
        (x0 + 86, y1 - 272, "4.58 GiB", "同样长度，50 并发", BAD),
        (x0 + 258, y1 - 272, "13.7 GiB", "24000 token，50 并发", BAD),
    ]
    for cx, cy, big, small, colour in pts:
        p.append(f'  <circle cx="{cx}" cy="{cy}" r="9" fill="{colour}"/>')
        p.append(f'  <text class="mb" x="{cx + 18}" y="{cy - 2}" fill="{colour}">{big}</text>')
        p.append(txt(cx + 18, cy + 22, small, cls="s"))
    p.append(dashed(x0 + 86, y1 - 78, x0 + 86, y1 - 262))
    p.append(dashed(x0 + 96, y1 - 272, x0 + 248, y1 - 272))

    # right column: the contrast that matters
    p.append(card(948, 190, 276, 152, cls="coolfill", rx=14))
    p.append(txt(968, 224, "显存", cls="h"))
    p.append(txt(968, 256, "两个方向都线性", cls="b"))
    p.append(txt(968, 288, "长度 × 2 → 显存 × 2", cls="m"))
    p.append(txt(968, 316, "并发 × 2 → 显存 × 2", cls="m"))

    p.append(card(948, 362, 276, 152, cls="warnfill", rx=14))
    p.append(txt(968, 396, "计算", cls="h"))
    p.append(txt(968, 428, "长度方向超线性", cls="b"))
    p.append(txt(968, 460, "长度 × 2 → 计算 × 2.2", cls="m"))
    p.append(txt(968, 488, "有 S² 项，显存没有", cls="m"))

    p.append(note(72, 410, 300, [
        "单位一律用二进制：KiB / MiB / GiB",
        "与框架日志和显存分配器同口径",
        "若是标准 MHA（14 个 KV 头），",
        "上面每个数都要乘以 7",
    ], h=138))
    p.append(txt(948, 546, "所以两者的拐点不在同一个地方", cls="b"))
    p.append(txt(948, 572, "权重、激活值那部分在第 16 章", cls="s"))
    return page(
        system=SYSTEM,
        title="图 11-2 KV Cache 往两个方向长",
        desc="左侧拆解单个 token 的 KV 字节数；中间以序列长度和并发数为两轴，"
             "标出 94 MiB、4.58 GiB、13.7 GiB 三个点，说明沿两个方向各自线性放大；"
             "右侧对比显存两个方向都线性、计算在长度方向超线性。",
        kicker="CH11 · 11.3",
        heading="KV Cache 往两个方向长",
        sub="显存的压力和计算的压力不在同一个地方",
        body="\n".join(p),
        takeaway="显存是严格线性的两个方向，计算是超线性的一个方向，别把两张账混着算。",
    )


# --- 图11-3 算术强度数轴上的两个点 ------------------------------------------

def fig3() -> str:
    p = []
    p.append(card(72, 176, 1152, 96, cls="soft", rx=14))
    p.append(txt(96, 210, "只算权重：(2 × 参数量 × S) ÷ (2 × 参数量) = S", cls="mb"))
    p.append(txt(96, 248, "算上激活读写：1 ÷ (1/S + 1/k + 1/n)，S 长到和矩阵宽度相当时封顶", cls="mb"))

    # log axis
    x0, x1, ay = 132, 1160, 390
    p.append(f'  <path d="M{x0} {ay}H{x1}" fill="none" stroke="#94A3B8" stroke-width="2"/>')

    def px(v: float) -> float:
        return x0 + (math.log10(v) - 0) / (math.log10(20000) - 0) * (x1 - x0)

    for v, label in ((1, "1"), (10, "10"), (100, "100"), (1000, "1000"), (10000, "10⁴")):
        p.append(vpath(px(v), ay - 7, ay + 7, cls="bracket"))
        p.append(txt(px(v), ay + 28, label, cls="m", anchor="middle"))
    p.append(txt(x1, ay + 52, "FLOP / byte", cls="s", anchor="end"))

    # hardware balance band, drawn first so labels sit on top
    bx0, bx1 = px(150), px(400)
    p.append(bar(bx0, ay - 70, bx1 - bx0, 40, cls="soft", rx=8))
    p.append(txt((bx0 + bx1) / 2, ay - 44, "分界点", cls="b", anchor="middle"))
    p.append(txt((bx0 + bx1) / 2, ay - 86, "硬件分界点：一两百到几百，随卡而变", cls="s", anchor="middle"))
    p.append(txt(bx0 - 20, ay - 44, "← 带宽受限", cls="b", anchor="end"))
    p.append(txt(900, ay - 60, "算力受限 →", cls="b"))

    # Decode
    cx = px(1)
    p.append(f'  <circle cx="{cx:.1f}" cy="{ay}" r="10" fill="{BAD}"/>')
    p.append(f'  <text class="mb" x="{cx + 20:.1f}" y="{ay - 22}" fill="{BAD}">Decode ≈ 1</text>')
    p.append(txt(cx + 20, ay + 56, "每步只有一个 token", cls="s"))
    # Prefill, weights only (hollow) and with activations (filled)
    wx = px(8000)
    p.append(f'  <circle cx="{wx:.1f}" cy="{ay}" r="9" fill="#FFFFFF" stroke="{GOOD}" '
             f'stroke-width="2.4" stroke-dasharray="4 3"/>')
    p.append(txt(wx, ay - 22, "只算权重 8000", cls="s", anchor="middle"))
    rx = px(602)
    p.append(f'  <circle cx="{rx:.1f}" cy="{ay}" r="10" fill="{GOOD}"/>')
    p.append(f'  <text class="mb" x="{rx - 8:.1f}" y="{ay - 22}" fill="{GOOD}">Prefill ≈ 602</text>')
    p.append(txt(rx, ay + 56, "8000 token，算上激活读写", cls="s", anchor="middle"))
    p.append(f'  <path class="flow" d="M{wx - 8:.1f} {ay + 16}Q{(wx + rx) / 2 + 40:.1f} {ay + 78} {rx + 12:.1f} {ay + 16}"/>')

    p.append(f'  <path d="M{px(1):.1f} {ay + 76}V{ay + 88}H{rx:.1f}V{ay + 76}" '
             f'fill="none" stroke="#64748B" stroke-width="2"/>')
    p.append(txt((px(1) + rx) / 2, ay + 112, "相差约 600 倍", cls="mb", anchor="middle"))

    # what increasing batch does
    p.append(card(72, 526, 552, 100, cls="goodfill", rx=14))
    p.append(txt(96, 558, "增大 batch：Decode 有收益", cls="b"))
    p.append(txt(96, 584, "强度变成批量大小，1 → 64", cls="m"))
    p.append(txt(96, 610, "仍在分界点左边，往右推就有空间可拿", cls="s"))

    p.append(card(672, 526, 552, 100, cls="badfill", rx=14))
    p.append(txt(696, 558, "增大 batch：Prefill 没有意义", cls="b"))
    p.append(txt(696, 584, "本来就在几百，已在分界点右边", cls="m"))
    p.append(txt(696, 610, "往右推不会变快，只会互相争抢算力", cls="s"))
    return page(
        system=SYSTEM,
        title="图 11-3 算术强度数轴上的两个点",
        desc="对数数轴上标出 Decode 每步约 1 FLOP/byte、硬件分界点的一两百到几百区间、"
             "以及 8000 token 的 Prefill：只算权重是 8000，算上激活读写封顶在约 602，与 Decode 相差约 600 倍；"
             "下方说明增大 batch 对两侧效果为何不同。",
        kicker="CH11 · 11.4",
        heading="算术强度数轴上的两个点",
        sub="Prefill 和 Decode 为什么不能互相照搬优化经验",
        body="\n".join(p),
        takeaway="Prefill 在分界点右侧几百，Decode 在左侧约 1；两侧相差几百倍，优化手段没有重合。",
    )


# --- 图11-4 实测落在下限的哪一侧 --------------------------------------------

def fig4() -> str:
    p = []
    # left: where the two reference numbers come from
    p.append(card(72, 186, 400, 288, cls="soft", rx=14))
    p.append(txt(94, 220, "下限与估计是怎么来的", cls="h"))
    rows = [("GEMM", "2 × 3.58 亿 × 8000", "5.7 TFLOPs"),
            ("Attention", "2 × 896 × 24 × 8000²", "2.75 TFLOPs")]
    for i, (a, b, c) in enumerate(rows):
        y = 254 + 60 * i
        p.append(txt(94, y, a, cls="b"))
        p.append(txt(452, y, c, cls="mb", anchor="end"))
        p.append(txt(94, y + 24, b, cls="m"))
    p.append(dashed(92, 380, 452, 380))
    p.append(txt(94, 406, "合计", cls="b"))
    p.append(txt(452, 406, "8.5 TFLOPs", cls="mb", anchor="end"))
    p.append(txt(94, 436, "÷ 峰值 153 TFLOP/s　→ 下限约 55 ms", cls="m"))
    p.append(txt(94, 462, "÷ 有效 30 TFLOP/s　→ 估计约 283 ms", cls="m"))

    p.append(note(72, 500, 400, [
        "参数量用非嵌入参数量 3.58 亿。",
        "词表嵌入 1.36 亿是查表不是 GEMM，",
        "照总参数量 4.94 亿算会高估 38%。",
    ], h=112))

    # right: the time axis, not to scale
    ax, y_top, y_bot = 556, 196, 612
    p.append(f'  <path d="M{ax} {y_top}V{y_bot}" fill="none" stroke="#94A3B8" stroke-width="2"/>')
    est_y, floor_y = 300, 500
    p.append(bar(ax - 10, floor_y, 678, y_bot - floor_y, cls="soft", rx=0))
    p.append(f'  <path d="M{ax - 10} {est_y}H{ax + 668}" stroke="#64748B" stroke-width="2" stroke-dasharray="8 5"/>')
    p.append(txt(ax + 660, est_y - 10, "估计 283 ms · 有效算力是假设值，不是规格峰值", cls="s", anchor="end"))
    p.append(f'  <path d="M{ax - 10} {floor_y}H{ax + 668}" stroke="#0F172A" stroke-width="3"/>')
    p.append(txt(ax + 660, floor_y - 10, "下限 55 ms · 硬件满载也快不过它", cls="mb", anchor="end"))

    marks = [
        (232, BAD, "实测 2400 ms", "高出估计 8.5 倍：有额外开销要查"),
        (346, GOOD, "实测 300 ms", "与估计同一量级：没有明显异常"),
        (436, GOOD, "实测 150 ms", "在下限与估计之间：实现比假设高效，不是缓存信号"),
        (560, WARN, "实测 40 ms", "低于下限：有一段计算没有发生，先查 Prefix Cache"),
    ]
    for y, colour, big, verdict in marks:
        p.append(f'  <circle cx="{ax}" cy="{y}" r="9" fill="{colour}"/>')
        p.append(f'  <text class="mb" x="{ax + 24}" y="{y - 4}" fill="{colour}">{big}</text>')
        p.append(txt(ax + 24, y + 22, verdict, cls="b"))
    return page(
        system=SYSTEM,
        title="图 11-4 实测落在下限的哪一侧",
        desc="左侧给出 8.5 TFLOPs 的完整算式，分别除以峰值 153 TFLOP/s 和有效 30 TFLOP/s，得到下限约 55 ms 与估计约 283 ms；"
             "右侧一条不按比例的时间轴，标出 2400、300、150、40 ms 四个实测值相对估计线与下限线的位置及各自的解读，"
             "只有下限以下画成阴影区。",
        kicker="CH11 · 11.5",
        heading="实测落在下限的哪一侧",
        sub="下限用峰值算，估计用有效值算，两条线回答两个问题",
        body="\n".join(p),
        takeaway="比下限快才说明计算没有发生；比估计快只说明实现比假设高效。",
    )


FIGURES = {
    "fig11-01_gemm_vs_attention.svg": (
        fig1,
        dict(title="图 11-1 制作说明：GEMM 与 Attention 在 16640 处交叉",
             source="第 11.2 节。曲线由该节两个式子采样，交叉点与占比表五行与正文一致。",
             order="先看两条曲线的形状差别，再看交叉点，然后沿横轴读 Attention 占总的五个档位，最后看右侧翻倍倍数表。",
             takeaway="Attention 占多少由长度决定，交叉点由模型形状决定；上下文窗口内翻倍最多涨到约三倍。",
             boundary="只画相对计算量，不给毫秒数（那是 11.5）；不出现 GPU 型号或算力数字。"),
    ),
    "fig11-02_kv_two_directions.svg": (
        fig2,
        dict(title="图 11-2 制作说明：KV Cache 往两个方向长",
             source="第 11.3 节。三个点的数值可用 code/ch11/prefill_model.py 复算。",
             order="先看左上单 token 的拆解，再看中间平面上三个点的位置，最后读右侧显存与计算的对照。",
             takeaway="显存是严格线性的两个方向，计算是超线性的一个方向，别把两张账混着算。",
             boundary="只画 KV Cache，不含权重、激活值与显存碎片；并发上限和抢占在第 16 章。"),
    ),
    "fig11-03_arithmetic_intensity_axis.svg": (
        fig3,
        dict(title="图 11-3 制作说明：算术强度数轴上的两个点",
             source="第 11.4 节。",
             order="先读顶部两个式子，再看数轴上 Decode、分界点、Prefill 的位置以及只算权重时那个虚线点，最后读底部两块关于 batch 的对照。",
             takeaway="Prefill 在分界点右侧几百，Decode 在左侧约 1；两侧相差几百倍，优化手段没有重合。",
             boundary="分界点画成区间而不是一条线，不写任何显卡型号（具体的卡在正文 11.4）；Prefill 的数是第 3 章那个 0.5B 模型的，宽模型封顶更高；完整 Roofline 在附录 A。"),
    ),
    "fig11-04_estimate_vs_measured.svg": (
        fig4,
        dict(title="图 11-4 制作说明：实测落在下限的哪一侧",
             source="第 11.5 节，四个实测值分别对应 11.1 的现象（2400 ms）、正常情形（300 ms）、实现较高效的情形（150 ms）与 11.7 案例二（40 ms）。",
             order="先看左侧下限与估计怎么算出来的，再看右侧四个点相对两条线的位置，最后读每个点的解读。",
             takeaway="比下限快才说明计算没有发生；比估计快只说明实现比假设高效。",
             boundary="峰值 153 TFLOP/s 是本书参考卡的合成设定，有效算力是假设值；时间轴不按比例；不把估算当预测。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
