"""Build the Chapter 22 figure set defined in strategy/reviews/ch22/storyboard.md.

Both figures recompute their numbers at build time from
code/ch22/serving_choice.py and content/ch22/evidence/route-eval-sample.json.

  fig22-01  22.4's staircase: 13.3's routing term for a session prefix under
            round-robin, at k = 2 and k = 10, against the shared-prefix case.
  fig22-02  22.4's trade-off as two numbers moving in opposite directions, with
            the third form (overflow) sitting where both are acceptable.

Run from the repository root:

    python3 content/ch22/figures/build_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch22"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, card, dashed, note, page, txt, write, write_note,
)
import serving_choice as sc  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"
MUTED_LINE = "#94A3B8"

SAMPLE = json.loads(
    (ROOT / "content/ch22/evidence/route-eval-sample.json")
    .read_text(encoding="utf-8"))
EVAL = sc.route_eval(SAMPLE)

# 22.4 那张表：会话级前缀被轮询打散时的路由项，图里画 k = 2 与 k = 10 两档。
TABLE = sc.scaling_table(1.0, instance_counts=(1, 2, 4, 8, 16), reuse_counts=(2, 10))


# --- 图22-1 扩容本身就在削会话级前缀的缓存 ----------------------------------

def fig1() -> str:
    p = [card(72, 176, 720, 396, cls="card", rx=16)]
    p.append(txt(96, 208, "会话级前缀被轮询打散时的路由项（缓存装得下时）", cls="b"))

    x0 = 152
    group_w = 120
    bar_w = 44
    y_base = 496
    full = 216  # 100% 的高度

    p.append(dashed(x0 - 16, y_base - full, 768, y_base - full))
    p.append(txt(x0 - 22, y_base - full + 5, "100%", cls="s", anchor="end"))
    p.append(txt(x0, y_base - full - 10,
                 "全体共享的前缀（同一段 system prompt）：每个实例各存一份，接近 100%",
                 cls="good"))

    for i, row in enumerate(TABLE):
        gx = x0 + i * group_w
        for j, (k, colour) in enumerate(((2, BAD), (10, WARN))):
            v = row["routing_term"][k]
            h = v * full
            x = gx + j * (bar_w + 6)
            p.append(f'  <rect x="{x}" y="{y_base - h:.0f}" width="{bar_w}" '
                     f'height="{h:.0f}" rx="6" fill="{colour}" opacity="0.18" '
                     f'stroke="{colour}" stroke-width="1.6"/>')
            pct = round(v * 100 + 1e-9, 1)
            shown = f"{pct:.1f}%" if pct < 20 else f"{pct:.0f}%"
            p.append(f'  <text class="s" x="{x + bar_w / 2:.0f}" '
                     f'y="{y_base - h - 8:.0f}" text-anchor="middle" '
                     f'fill="{colour}">{shown}</text>')
        label = "1 个实例" if row["instances"] == 1 else f'{row["instances"]} 个'
        p.append(txt(gx + bar_w + 3, y_base + 26, label, cls="b", anchor="middle"))

    p.append(f'  <path d="M{x0 - 16} {y_base}H768" stroke="{MUTED_LINE}" '
             f'stroke-width="1.6"/>')
    # 图例
    for j, (label, colour) in enumerate((("复用 2 次（k = 2）", BAD),
                                         ("复用 10 次（k = 10）", WARN))):
        lx = 176 + j * 230
        p.append(f'  <rect x="{lx}" y="{y_base + 44}" width="18" height="14" '
                 f'rx="3" fill="{colour}" opacity="0.25" stroke="{colour}"/>')
        p.append(txt(lx + 26, y_base + 56, label, cls="s"))

    p.append(card(816, 176, 392, 396, cls="card", rx=16))
    p.append(txt(840, 208, "这一刀出自第 13.3 节那个式子", cls="b"))
    p.append(note(832, 228, 344, [
        "命中率 ≈ 可缓存占比 × 局部性",
        "        × 未被淘汰 × 路由项",
    ], cls="coolfill"))
    p.append(note(832, 312, 344, [
        "路由项 ≈ 1 − N(1 − (1 − 1/N)^k)/k",
        "k 是一个前缀被复用的次数，",
        "每个被碰到的实例都先付一次写入",
    ], cls="soft"))
    p.append(note(832, 424, 344, [
        "缓存装不下时更糟：轮询让每个实例",
        "都替全部会话存一份，前缀没等到",
        "复用就被挤出去，往 1/N 掉",
    ], cls="warnfill"))

    p.append(note(72, 588, 1136, [
        "这是缓存装得下时的路由项，乘上可缓存占比才是命中率上限。"
        "复用少时副本数翻倍、路由项约减半，TTFT 可能不降反升，22.8 案例二就是这个形状。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="扩容本身就在削会话级前缀的缓存",
        desc="一张分组柱状图，横轴是实例数 1、2、4、8、16，每组两根柱子分别是会话级前缀复用 2 次"
             "和 10 次时，轮询路由下的路由项。复用 2 次时依次是 50%、25%、12.5%、6%、3%；"
             "复用 10 次时是 90%、80%、62%、41%、24%。顶部虚线是全体共享前缀的情形，"
             "接近 100%。右侧列出第 13.3 节的命中率式子和路由项式子，并说明缓存装不下时"
             "路由项会往 1/N 掉。",
        kicker="第 22 章 · 22.4",
        heading="多副本部署里一笔不写出来就不会有人算的账",
        sub="会话级前缀被轮询打散，每个碰到它的实例都要先付一次写入",
        body="\n".join(p),
        takeaway="会话级前缀复用少时，副本数翻倍、命中率大约减半；全体共享的前缀不受影响",
    )


# --- 图22-2 命中率与不均衡度的取舍 ------------------------------------------

def fig2() -> str:
    rows = {r["strategy"]: r for r in EVAL["strategies"]}
    order = ["round-robin", "prefix-hash", "prefix-hash-with-overflow"]

    p = [card(72, 176, 700, 396, cls="card", rx=16)]
    p.append(txt(96, 208, "三种路由策略在同一条链路上的两个数（合成评估）", cls="b"))

    x0, x1 = 176, 700
    y0, y1 = 250, 466

    def hx(v: float) -> float:
        return x0 + v / 1.0 * (x1 - x0)

    def sy(v: float) -> float:
        return y1 - min(v, 1.0) / 1.0 * (y1 - y0)

    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" '
             f'stroke="{MUTED_LINE}" stroke-width="1.6"/>')
    # 22.4 的两条经验界
    p.append(dashed(x0, sy(sc.SKEW_UNNOTICEABLE), x1, sy(sc.SKEW_UNNOTICEABLE)))
    p.append(txt(x1 - 4, sy(sc.SKEW_UNNOTICEABLE) - 8,
                 f"{sc.SKEW_UNNOTICEABLE} 以下感觉不到", cls="s", anchor="end"))
    p.append(dashed(x0, sy(sc.SKEW_P99_DOMINATED), x1, sy(sc.SKEW_P99_DOMINATED)))
    p.append(txt(x1 - 4, sy(sc.SKEW_P99_DOMINATED) - 8,
                 f"{sc.SKEW_P99_DOMINATED} 以上最慢的实例决定 P99",
                 cls="s", anchor="end"))

    # 标注一律贴在点的一侧，不跨过圆心，否则圆点会把文字劈成两半
    # 贴在点的一侧，不跨过圆心；不均衡度为 0 的那个点贴着横轴，两行都往上放
    # 轮询那个点贴着横轴，标注放成一行；带溢出的那个点离 0.3 线很近，两行标注
    # 收紧行距贴在点的左侧，不跨过虚线，也不压到轮询那一行
    marks = {
        "round-robin": ("轮询", COOL, "start", -12, None),
        "prefix-hash": ("纯前缀哈希", BAD, "end", -6, 22),
        "prefix-hash-with-overflow": ("带溢出的前缀哈希", GOOD, "end", -4, 19),
    }
    for name in order:
        row = rows[name]
        label, colour, anchor, dy, gap = marks[name]
        cx, cy = hx(row["cache_hit_rate"]), sy(row["load_skew"])
        tx_ = cx + (16 if anchor == "start" else -16)
        stats = (f'命中率 {row["cache_hit_rate"]:.1%}，'
                 f'不均衡度 {row["load_skew"]:.2f}')
        p.append(f'  <circle cx="{cx:.0f}" cy="{cy:.0f}" r="9" fill="{colour}"/>')
        p.append(f'  <text class="b" x="{tx_:.0f}" y="{cy + dy:.0f}" '
                 f'text-anchor="{anchor}" fill="{colour}">{label}</text>')
        if gap is None:
            p.append(f'  <text class="s" x="{tx_ + 44:.0f}" y="{cy + dy:.0f}" '
                     f'text-anchor="start">{stats}</text>')
        else:
            p.append(f'  <text class="s" x="{tx_:.0f}" y="{cy + dy + gap:.0f}" '
                     f'text-anchor="{anchor}">{stats}</text>')

    for v in (0.25, 0.5, 0.75, 1.0):
        p.append(txt(hx(v), y1 + 26, f"{v:.0%}", cls="s", anchor="middle"))
    p.append(txt(92, y1 + 26, "缓存命中率", cls="s"))
    p.append(txt(120, 240, "负载不均衡度", cls="b"))
    p.append(txt(96, y1 + 54, "右下角是两边都好，左上角是两边都差；"
                              "这两个目标互相冲突，所以取舍点在中间", cls="s"))

    p.append(card(796, 176, 412, 396, cls="card", rx=16))
    p.append(txt(820, 208, "三种形态各自的代价", cls="b"))
    blocks = [
        ("round-robin", "会话前缀被打散，缓存又装不下", "coolfill", 228),
        ("prefix-hash", "热点：最差实例 P95 比整体高出", "badfill", 340),
        ("prefix-hash-with-overflow", "两边都在可接受区间", "goodfill", 452),
    ]
    for name, why, cls, y in blocks:
        row = rows[name]
        p.append(card(812, y, 380, 96, cls=cls, rx=12))
        p.append(txt(832, y + 32, name, cls="mb"))
        if name == "prefix-hash":
            why = f"{why} {row['aggregate_hides']:.0f} ms"
        p.append(txt(832, y + 58, why, cls="s"))
        p.append(txt(832, y + 82,
                     f"整体 P95 TTFT {row['p95_ttft']:.0f} ms，"
                     f"最差实例 {row['worst_instance']['p95_ttft']:.0f} ms",
                     cls="s"))

    p.append(note(72, 588, 1136, [
        f"实际可用的是{EVAL['practical']}：在不均衡度还感觉不到的策略里，"
        f"它的命中率最高。数据是合成评估，不是真机结果。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="缓存命中率和负载均衡是互相冲突的两个目标",
        desc="一张散点图，横轴是缓存命中率，纵轴是负载不均衡度，纵轴上两条虚线标出 0.3 和 "
             "0.5 两条经验界。轮询落在左下角：命中率 29.6%、不均衡度接近 0。纯前缀哈希落在"
             "右上角：命中率 88.8%、不均衡度 0.94，已越过 0.5。带溢出的前缀哈希落在右下角："
             "命中率 79.9%、不均衡度 0.20。右侧三块列出各自的代价，包括纯前缀哈希那一版的"
             "最差实例比整体 P95 高 440 毫秒。",
        kicker="第 22 章 · 22.4、22.5、22.7",
        heading="追求均衡就打散缓存，追求命中就容易出热点",
        sub="所以带溢出的那一种才是实际可用的形态，溢出阈值就在这两个数之间定位置",
        body="\n".join(p),
        takeaway="聚合指标会掩盖单实例问题，所以整体和最差实例两个数必须一起报",
    )


FIGS = [
    ("fig22-01_cache_ceiling_staircase", fig1,
     dict(title="图22-1 扩容本身就在削会话级前缀的缓存",
          source="22.4",
          order="先看顶部那条虚线，全体共享的前缀不受副本数影响；再从左往右看两组柱子怎么随副本数掉下去，复用次数越少掉得越快；最后看右侧的式子和缓存装不下时的情形",
          takeaway="会话级前缀复用少时，副本数翻倍、命中率大约减半；全体共享的前缀不受影响",
          boundary="画的是缓存装得下时的路由项，乘上可缓存占比才是命中率上限；缓存装不下时实际值更低，往 1/N 掉；复用次数 2 和 10 是举例，换一条链路要用自己的复用次数重算")),
    ("fig22-02_routing_tradeoff", fig2,
     dict(title="图22-2 缓存命中率和负载均衡是互相冲突的两个目标",
          source="22.4、22.5、22.7",
          order="先看纵轴上那两条经验界，再看三个点分别落在哪个象限，最后看右侧三块里最差实例那一列和整体值差多少",
          takeaway="聚合指标会掩盖单实例问题，所以整体和最差实例两个数必须一起报",
          boundary="数据出自 content/ch22/evidence/route-eval-sample.json，是合成评估不是真机结果；取舍点取决于可缓存比例，可缓存占比低的链路上这张图会整体左移，前缀亲和就不值得做")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
