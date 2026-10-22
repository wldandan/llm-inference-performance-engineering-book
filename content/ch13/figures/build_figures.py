"""Build the Chapter 13 figure set defined in strategy/reviews/ch13/storyboard.md.

Numbers come from the chapter text and can be recomputed with
code/ch13/prefill_optimization_check.py and code/ch11/prefill_model.py.

Run from the repository root:

    python3 content/ch13/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, MUTED, WARN, arrow, bar, card, dashed, hpath, note, page,
    txt, vpath, write, write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"


# --- 图13-1 四条路改的不是同一件事 ------------------------------------------

def fig1() -> str:
    p = []
    # the four quantities one Prefill has
    quantities = [
        ("输入长度", 232), ("计算量", 322), ("搬运量", 412), ("调度顺序", 502),
    ]
    qx, qw = 470, 268
    p.append(card(qx - 20, 196, qw + 40, 372, cls="card", rx=16))
    p.append(txt(qx + qw / 2, 226, "一次 Prefill 里可以被改动的四个量", cls="b", anchor="middle"))
    for label, y in quantities:
        p.append(bar(qx, y + 6, qw, 54, cls="soft", rx=10))
        p.append(txt(qx + qw / 2, y + 40, label, cls="h", anchor="middle"))

    paths = [
        ("上下文裁剪", 232, GOOD, "本条请求", ["输入长度", "计算量"]),
        ("Prefix Cache", 322, GOOD, "本条请求", ["计算量"]),
        ("FlashAttention", 412, COOL, "本条请求", ["搬运量"]),
        ("Chunked Prefill", 502, WARN, "其他请求", ["调度顺序"]),
    ]
    ymap = {label: y + 33 for label, y in quantities}
    for name, y, colour, whose, targets in paths:
        p.append(f'  <rect x="96" y="{y + 6}" width="300" height="54" rx="10" '
                 f'fill="#FFFFFF" stroke="{colour}" stroke-width="1.8"/>')
        p.append(f'  <text class="b" x="116" y="{y + 30}" fill="{colour}">{name}</text>')
        p.append(txt(116, y + 50, f"改善 {whose}", cls="s"))
        for target in targets:
            ty = ymap[target]
            if abs(ty - (y + 33)) < 2:
                p.append(hpath(400, ty, qx - 8))
            else:
                p.append(f'  <path class="flow" d="M400 {y + 33}'
                         f'C436 {y + 33} 436 {ty} {qx - 8} {ty}"/>')

    p.append(card(822, 196, 402, 180, cls="soft", rx=14))
    p.append(txt(846, 230, "为什么这张图重要", cls="h"))
    p.append(txt(846, 264, "它们改的是四个不同的量，", cls="s"))
    p.append(txt(846, 290, "所以收益不一定叠加，", cls="s"))
    p.append(txt(846, 316, "代价却一定叠加。", cls="s"))
    p.append(txt(846, 350, "四条都标为适用，也要一次只试一条。", cls="s"))

    p.append(card(822, 396, 402, 172, cls="warnfill", rx=14))
    p.append(txt(846, 430, "最后一条和前三条不是一类", cls="h"))
    p.append(txt(846, 464, "Chunked Prefill 不让任何一条", cls="s"))
    p.append(txt(846, 490, "请求变快，它改善的是别人的", cls="s"))
    p.append(txt(846, 516, "指标，代价由本条请求承担。", cls="s"))
    p.append(txt(846, 550, "现象是“单条长请求慢”时它帮不上忙。", cls="s"))
    return page(
        system=SYSTEM,
        title="图 13-1 四条路改的不是同一件事",
        desc="左侧四条路各连向右侧一次 Prefill 中不同的可改动量："
             "上下文裁剪改输入长度并连带减少计算量，Prefix Cache 只减计算量，"
             "FlashAttention 只减搬运量，Chunked Prefill 只改调度顺序且改善的是其他请求。",
        kicker="CH13 · 13.1",
        heading="四条路改的不是同一件事",
        sub="它们是可以互相替代的选项吗",
        body="\n".join(p),
        takeaway="它们改的是四个不同的量，所以收益不叠加，代价一定叠加。",
    )


# --- 图13-2 命中率的三刀乘法 ------------------------------------------------

def fig2() -> str:
    p = []
    stages = [
        ("可缓存占比", "60%", 0.60, "天花板：token 占比"),
        ("× 没被淘汰", "× 1", 0.60, "复用间隔 vs 缓存容量 ÷ 流量"),
        ("× 路由项", "× 12.5%", 0.075, "会话前缀复用 2 次，四副本"),
    ]
    x, y0 = 88, 240
    band, w, gap = 160, 200, 44
    for i, (label, factor, value, why) in enumerate(stages):
        h = band * value / 0.60
        top = y0 + (band - h) / 2
        colour = BAD if i == 2 else COOL
        fillc = "#FEF2F2" if i == 2 else "#EFF6FF"
        p.append(f'  <rect x="{x}" y="{top:.1f}" width="{w}" height="{h:.1f}" rx="10" '
                 f'fill="{fillc}" stroke="{colour}" stroke-width="1.8"/>')
        p.append(f'  <text class="mb" x="{x + w / 2}" y="{y0 + band / 2 + 6}" '
                 f'text-anchor="middle" fill="{colour}">{factor}</text>')
        p.append(txt(x + w / 2, y0 - 22, label, cls="b", anchor="middle"))
        p.append(txt(x + w / 2, y0 + band + 34, why, cls="s", anchor="middle"))
        p.append(hpath(x + w + 6, y0 + band / 2, x + w + gap - 6))
        x += w + gap

    p.append(txt(x + 8, y0 + band / 2 - 4, "= 7.5%", cls="mb"))
    p.append(txt(x + 8, y0 + band / 2 + 24, "实际命中率", cls="b"))

    p.append(card(88, 462, 540, 148, cls="warnfill", rx=14))
    p.append(txt(112, 496, "这几刀是乘法，不是减法", cls="h"))
    p.append(txt(112, 528, "路由项 = 1 − N × (1 − (1 − 1/N)^k) ÷ k", cls="mb"))
    p.append(txt(112, 560, "N = 4、k = 2 时 12.5%；N = 1 时 50%，首次写入省不掉。", cls="s"))
    p.append(txt(112, 586, "八倍里两倍是首次写入，四倍是路由打散；第 22 章收回后者。", cls="s"))

    p.append(card(676, 462, 548, 148, cls="soft", rx=14))
    p.append(txt(700, 496, "还有第二层折扣：占比不等于省下的计算", cls="h"))
    p.append(txt(700, 530, "S = 3000   前缀 1800（60%）   实际省 56%", cls="m"))
    p.append(txt(700, 558, "S = 8000   前缀 4800（60%）   实际省 52%", cls="m"))
    p.append(txt(700, 586, "S = 16640  前缀 9984（60%）   实际省 48%", cls="m"))
    return page(
        system=SYSTEM,
        title="图 13-2 命中率的三刀乘法：60% 到 7.5%",
        desc="一条逐级变窄的条带，从可缓存占比 60% 的天花板开始，"
             "依次乘上没被淘汰的比例和路由命中的比例；"
             "示例里只有路由项不理想：会话前缀只复用 2 次、四副本随机路由时约 12.5%，结果掉到 7.5%；"
             "全体共享的前缀路由项接近 1，单实例也只有 50%，因为首次写入省不掉。",
        kicker="CH13 · 13.3",
        heading="命中率的三刀乘法：60% 到 7.5%",
        sub="可缓存比例高，为什么命中率还是很低",
        body="\n".join(p),
        takeaway="这几刀是乘法不是减法，天花板 60% 落到个位数并不稀奇。",
    )


# --- 图13-3 那个矩阵大 178 倍 -----------------------------------------------

def fig3() -> str:
    p = []
    # two squares, area proportional to S^2
    big = 262.0
    small = big * 600 / 8000
    base_y = 498
    p.append(f'  <rect x="140" y="{base_y - small:.1f}" width="{small:.1f}" height="{small:.1f}" '
             f'rx="4" fill="#ECFDF5" stroke="{GOOD}" stroke-width="2"/>')
    p.append(txt(140 + small / 2, base_y + 30, "600 token", cls="mb", anchor="middle"))
    p.append(f'  <text class="b" x="{140 + small / 2}" y="{base_y + 54}" '
             f'text-anchor="middle" fill="{GOOD}">约 10 MiB</text>')

    p.append(f'  <rect x="340" y="{base_y - big:.1f}" width="{big:.1f}" height="{big:.1f}" '
             f'rx="6" fill="#FEF2F2" stroke="{BAD}" stroke-width="2"/>')
    p.append(txt(340 + big / 2, base_y + 30, "8000 token", cls="mb", anchor="middle"))
    p.append(f'  <text class="b" x="{340 + big / 2}" y="{base_y + 54}" '
             f'text-anchor="middle" fill="{BAD}">约 1710 MiB</text>')
    p.append(txt(340 + big / 2, base_y - big / 2 + 6, "S × S 的注意力矩阵", cls="b", anchor="middle"))

    p.append(txt(140, 214, "朴素实现要把这张矩阵写出显存再读回（单层、全部 14 个头、FP16）", cls="b"))
    p.append(txt(140, 240, "面积按 S² 成比例画", cls="s"))

    p.append(f'  <path class="bracket" d="M140 {base_y + 76}V{base_y + 90}H{340 + big}V{base_y + 76}"/>')
    p.append(txt((140 + 340 + big) / 2, base_y + 116, "长度 13 倍，矩阵大 178 倍", cls="mb", anchor="middle"))

    p.append(card(700, 214, 524, 176, cls="soft", rx=14))
    p.append(txt(724, 248, "它减少的是搬运，不是计算", cls="h"))
    p.append(txt(724, 282, "S² 项一个都没少，算的是同一个数学结果，", cls="s"))
    p.append(txt(724, 308, "不是近似。收益来自不再落盘这张矩阵。", cls="s"))
    p.append(txt(724, 344, "S² × 2 B × 14 头", cls="mb"))
    p.append(txt(724, 372, "所以它随长度平方增长", cls="s"))

    p.append(card(700, 410, 524, 198, cls="coolfill", rx=14))
    p.append(txt(724, 444, "适用条件跟着矩阵大小走", cls="h"))
    rows = [("长序列", "明显"), ("短序列", "有限，矩阵本来就不大"),
            ("Prefill", "适用"), ("Decode", "几乎无关，没有大矩阵")]
    for i, (a, b) in enumerate(rows):
        y = 480 + 32 * i
        p.append(txt(724, y, a, cls="b"))
        p.append(txt(1200, y, b, cls="s", anchor="end"))
    return page(
        system=SYSTEM,
        title="图 13-3 那个矩阵大 178 倍",
        desc="两个面积按 S² 成比例的正方形：600 token 约 10 MiB，8000 token 约 1710 MiB，"
             "相差 178 倍；右侧说明 FlashAttention 减少的是这张矩阵的读写而不是计算量，"
             "以及适用条件如何跟着矩阵大小走。",
        kicker="CH13 · 13.4",
        heading="那个矩阵大 178 倍",
        sub="为什么同一个改动在短 prompt 上没效果",
        body="\n".join(p),
        takeaway="收益随矩阵大小走，而矩阵按长度平方长，所以只有长序列拿得到。",
    )


# --- 图13-4 拆开之后，谁快了谁慢了 ------------------------------------------

def fig4() -> str:
    p = []
    x0, x1 = 152, 872

    # top: not chunked
    p.append(txt(96, 226, "不拆", cls="h"))
    p.append(bar(x0, 240, 392, 44, cls="badfill", rx=6))
    p.append(txt(x0 + 196, 268, "长请求 Prefill 一次占满", cls="b", anchor="middle"))
    p.append(bar(x0 + 400, 240, x1 - x0 - 400, 44, cls="soft", rx=6))
    p.append(txt(x0 + 400 + 20, 268, "其他请求继续", cls="s"))
    for i in range(3):
        y = 300 + i * 26
        p.append(f'  <path d="M{x0} {y}H{x0 + 392}" stroke="{MUTED}" stroke-width="2.4" '
                 f'stroke-dasharray="2 12"/>')
        p.append(f'  <path d="M{x0 + 400} {y}H{x1}" stroke="{GOOD}" stroke-width="2.4"/>')
    p.append(txt(x0 + 196, 396, "这段时间里其他请求全部停顿", cls="b", anchor="middle"))
    p.append(txt(x1, 212, "时间 →", cls="s", anchor="end"))

    # bottom: chunked
    p.append(txt(96, 448, "拆开", cls="h"))
    seg = (x1 - x0) / 6
    for i in range(6):
        cls = "badfill" if i % 2 == 0 else "soft"
        label = f"块{i // 2 + 1}" if i % 2 == 0 else "其他"
        p.append(bar(x0 + i * seg + 2, 462, seg - 4, 44, cls=cls, rx=6))
        p.append(txt(x0 + i * seg + seg / 2, 490, label, cls="b", anchor="middle"))
    for i in range(3):
        y = 522 + i * 26
        p.append(f'  <path d="M{x0} {y}H{x1}" stroke="{GOOD}" stroke-width="2.4"/>')
    p.append(txt((x0 + x1) / 2, 618, "其他请求始终能拿到机会", cls="b", anchor="middle"))

    p.append(card(908, 214, 316, 186, cls="goodfill", rx=14))
    p.append(txt(932, 248, "受益：其他请求", cls="h"))
    p.append(txt(932, 282, "ITL 从有明显停顿变成稳定", cls="s"))
    p.append(txt(932, 320, "判据", cls="b"))
    p.append(txt(932, 346, "其他请求的 ITL P99", cls="s"))
    p.append(txt(932, 372, "超过 P50 三倍才需要开", cls="s"))

    p.append(card(908, 420, 316, 188, cls="badfill", rx=14))
    p.append(txt(932, 454, "受损：本条长请求", cls="h"))
    p.append(txt(932, 488, "TTFT 2.4 s → 3.1 s", cls="mb"))
    p.append(txt(932, 520, "被拆成几轮，中间穿插别人的活", cls="s"))
    p.append(txt(932, 556, "清一色长请求且低并发时", cls="s"))
    p.append(txt(932, 582, "开了只会添乱", cls="s"))
    return page(
        system=SYSTEM,
        title="图 13-4 拆开之后，谁快了谁慢了",
        desc="上下两条时间线：不拆时长请求的 Prefill 占满一整段，其他请求的 token 流断成虚线；"
             "拆开后块与块之间其他请求都能拿到机会，token 流连续，代价是本条长请求的 TTFT 变差。",
        kicker="CH13 · 13.5",
        heading="拆开之后，谁快了谁慢了",
        sub="这一项改善的是谁的指标",
        body="\n".join(p),
        takeaway="它的收益体现在别人的指标上，代价由本条请求承担。",
    )


FIGURES = {
    "fig13-01_four_paths.svg": (
        fig1,
        dict(title="图 13-1 制作说明：四条路改的不是同一件事",
             source="第 13.1 节。",
             order="先看右侧那四个可被改动的量，再顺着连线看每条路改的是哪一个，最后看每条路旁边“改善谁的指标”那一行。",
             takeaway="它们改的是四个不同的量，所以收益不叠加，代价一定叠加。",
             boundary="不给收益百分比（各自条件不同，放进来会被当成普适数字），不出现框架名或库名。"),
    ),
    "fig13-02_hit_rate_four_cuts.svg": (
        fig2,
        dict(title="图 13-2 制作说明：命中率的三刀乘法",
             source="第 13.3 节。",
             order="从左往右看条带怎么一级级变窄，读每一刀乘的是什么，最后看右下那层“占比不等于省下的计算”的折扣。",
             takeaway="这几刀是乘法不是减法，天花板 60% 落到个位数并不稀奇。",
             boundary="7.5% 是这个假设场景算出来的上限，不是任何真实系统的实测命中率；路由项的式子假设请求随机落到各副本、每个副本缓存装得下；它含首次写入那一刀，路由再好也省不掉。"),
    ),
    "fig13-03_attention_matrix_size.svg": (
        fig3,
        dict(title="图 13-3 制作说明：那个矩阵大 178 倍",
             source="第 13.4 节。两个面积按 S² 成比例。",
             order="先比两个正方形的面积，再读中间那句“长度 13 倍，矩阵大 178 倍”，最后看右侧它减的是搬运不是计算。",
             takeaway="收益随矩阵大小走，而矩阵按长度平方长，所以只有长序列拿得到。",
             boundary="不画分块算法的实现细节，也不给任何“提速百分之多少”的数字（取决于卡和实现）。"),
    ),
    "fig13-04_chunked_two_timelines.svg": (
        fig4,
        dict(title="图 13-4 制作说明：拆开之后，谁快了谁慢了",
             source="第 13.5 节，长请求 TTFT 的两个值取自 13.8 案例三。",
             order="先看上面那条时间线里其他请求的 token 流怎么断掉，再看下面拆开后它怎么连续，最后读右侧受益与受损两块。",
             takeaway="它的收益体现在别人的指标上，代价由本条请求承担。",
             boundary="不展开 Token Budget 怎么分、块该多大（第 20 章）；不把长请求变差说成可以忽略。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
