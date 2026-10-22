"""Build the Chapter 19 figure set defined in strategy/reviews/ch19/storyboard.md.

The sweep numbers come from content/ch19/evidence/decode-experiment-sample.json
and can be recomputed with code/ch19/decode_experiment.py. That file is
synthetic and says so; this figure repeats the label.

Run from the repository root:

    python3 content/ch19/figures/build_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, bar, card, dashed, note, page, txt, write,
    write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"
MUTED_LINE = "#94A3B8"
SAMPLE = Path(__file__).resolve().parents[3] / "content/ch19/evidence/decode-experiment-sample.json"

DOC = json.loads(SAMPLE.read_text(encoding="utf-8"))
SWEEP = next(r for r in DOC["rounds"] if r["round"] == 0)["sweep"]["points"]
SLO = DOC["rounds"][0]["fixed"]["workload"]["slo"]
SLO_MS = SLO["good_request"]["itl_p95_ms_per_request"]
REQUIRED = SLO["required_attainment"]


# --- 图19-1 TPS 峰值与 Goodput 峰值不在同一处 --------------------------------

def fig1() -> str:
    p = []
    x0, x1 = 176, 752
    p.append(card(72, 176, 720, 396, cls="card", rx=16))

    batches = [pt["batch"] for pt in SWEEP]
    tps = [pt["tps"] for pt in SWEEP]
    good = [pt["tps"] * pt["slo_attainment"] for pt in SWEEP]
    itl = [pt["itl_p95_ms"] for pt in SWEEP]

    import math

    def bx(b: int) -> float:
        return x0 + math.log2(b / 4) / math.log2(128 / 4) * (x1 - x0)

    # panel 1: TPS and Goodput
    t0, t1 = 212, 360
    top = 3600.0
    p.append(txt(96, 206, "吞吐（token/s）：名义 TPS 与达标的 Goodput", cls="b"))
    p.append(f'  <path d="M{x0} {t0}V{t1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.6"/>')

    def ty(v: float) -> float:
        return t1 - v / top * (t1 - t0)

    pts = " ".join(f"{bx(b):.0f},{ty(v):.0f}" for b, v in zip(batches, tps))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{MUTED_LINE}" '
             f'stroke-width="2.6" stroke-dasharray="7 5"/>')
    pts = " ".join(f"{bx(b):.0f},{ty(v):.0f}" for b, v in zip(batches, good))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{GOOD}" stroke-width="3"/>')
    for b, v in zip(batches, tps):
        p.append(f'  <circle cx="{bx(b):.0f}" cy="{ty(v):.0f}" r="4" fill="{MUTED_LINE}"/>')
    for b, v in zip(batches, good):
        p.append(f'  <circle cx="{bx(b):.0f}" cy="{ty(v):.0f}" r="5" fill="{GOOD}"/>')

    p.append(txt(bx(128) - 8, ty(tps[-1]) - 12, f"名义 TPS {tps[-1]:.0f}", cls="s", anchor="end"))

    gpeak = max((i for i, r in enumerate(SWEEP) if r["slo_attainment"] >= REQUIRED),
                key=lambda i: good[i])
    p.append(f'  <circle cx="{bx(batches[gpeak]):.0f}" cy="{ty(good[gpeak]):.0f}" '
             f'r="9" fill="none" stroke="{GOOD}" stroke-width="2.5"/>')
    p.append(txt(bx(batches[gpeak]) - 16, ty(good[gpeak]) + 5,
                 f"可行集里的 Goodput 峰值 {good[gpeak]:.0f}",
                 cls="good", anchor="end"))
    p.append(txt(bx(batches[-1]) - 10, ty(good[-1]) + 33,
                 f"批量 {batches[-1]} 只剩 {good[-1]:.0f}",
                 cls="good", anchor="end"))
    upeak = max(range(len(good)), key=lambda i: good[i])
    if upeak != gpeak:
        p.append(txt(bx(batches[upeak]), ty(good[upeak]) - 18,
                     f"全表最高 {good[upeak]:.0f}，达标率 "
                     f"{SWEEP[upeak]['slo_attainment'] * 100:.0f}%",
                     cls="warn", anchor="middle"))

    # panel 2: P95 ITL against the SLO line
    s0, s1 = 392, 480
    top_ms = 260.0
    p.append(txt(96, 384, "整轮的 P95 ITL（ms）与单条请求 ITL 的那条 80 ms 线", cls="b"))
    p.append(f'  <path d="M{x0} {s0}V{s1}H{x1}" fill="none" stroke="#94A3B8" stroke-width="1.6"/>')

    def sy(v: float) -> float:
        return s1 - min(v, top_ms) / top_ms * (s1 - s0)

    p.append(dashed(x0, sy(SLO_MS), x1, sy(SLO_MS)))
    p.append(txt(x1 - 6, sy(SLO_MS) - 8, f"SLO {SLO_MS} ms", cls="s", anchor="end"))
    pts = " ".join(f"{bx(b):.0f},{sy(v):.0f}" for b, v in zip(batches, itl))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{COOL}" stroke-width="3"/>')
    for b, v in zip(batches, itl):
        colour = BAD if v > SLO_MS else COOL
        p.append(f'  <circle cx="{bx(b):.0f}" cy="{sy(v):.0f}" r="5" fill="{colour}"/>')
    p.append(txt(bx(128) - 8, sy(240) + 20, "240 ms", cls="bad", anchor="end"))

    for b, att in zip(batches, [pt["slo_attainment"] for pt in SWEEP]):
        p.append(txt(bx(b), s1 + 24, str(b), cls="s", anchor="middle"))
        p.append(txt(bx(b), s1 + 46, f"{att * 100:.0f}%", cls="s", anchor="middle"))
    p.append(txt(96, s1 + 24, "批量", cls="s"))
    p.append(txt(96, s1 + 46, "达标率", cls="s"))
    feas = [pt["batch"] for pt in SWEEP if pt["slo_attainment"] >= REQUIRED]
    fx0, fx1 = bx(min(feas)) - 18, bx(max(feas)) + 18
    p.append(f'  <path d="M{fx0:.0f} {s1 + 54}H{fx1:.0f}" stroke="{GOOD}" stroke-width="3"/>')
    p.append(txt((fx0 + fx1) / 2, s1 + 72, f"可行档位：达标率 ≥ {REQUIRED * 100:.0f}%", cls="good", anchor="middle"))


    p.append(card(816, 176, 392, 396, cls="card", rx=16))
    p.append(txt(840, 210, "为什么用 Goodput 当主指标", cls="b"))
    p.append(note(832, 230, 344, [
        "SLO 把取舍变成两步规则",
        "先筛：达标率不低于 95% 的档位",
        "再选：其中 Goodput 最大的那档",
    ], cls="goodfill"))
    p.append(note(832, 348, 344, [
        "达标 = TTFT ≤ 1500 ms，且这条",
        "请求自己的 P95 ITL ≤ 80 ms",
        "Goodput 只在可行档位里比大小",
    ], cls="coolfill"))
    p.append(note(832, 466, 344, [
        "前沿上的候选都留着",
        "SLO 一变最优点就换一个，而前沿不变",
    ], cls="soft"))

    p.append(note(72, 588, 1136, [
        "数据出自 content/ch19/evidence/decode-experiment-sample.json，是合成样例，"
        "不是真机结果。要看的是两个峰值不在一处这件事，不是这几个具体数字。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="TPS 峰值与 Goodput 峰值不在同一个批量上",
        desc="上下两栏共用一根对数刻度的批量横轴，从 4 到 128。上栏两条曲线：虚线是名义 "
             "TPS，在批量 128 达到 3332 的峰值；实线是 Goodput，在可行集里于批量 32 达到 "
             "1560 的峰值，批量 64 的 1807 全表最高却不可行，到 128 时掉到 666。"
             "下栏是 P95 ITL，在批量 64 和 128 越过 80 ms 的 "
             "SLO 线。横轴下方标出各档的达标率。",
        kicker="第 19 章 · 19.3、19.7",
        heading="TPS 峰值和 Goodput 峰值不在同一处，这是常态",
        sub="批量 64 的 Goodput 全表最高却不可行，批量 128 的吞吐是靠让八成请求超时换来的",
        body="\n".join(p),
        takeaway="批量扫描要找 Goodput 的峰值，不是 TPS 的峰值；两者不在一处是常态",
    )


# --- 图19-2 五轮的五维记分卡 ------------------------------------------------

def fig2() -> str:
    p = []
    p.append(card(72, 176, 1136, 380, cls="card", rx=16))
    p.append(txt(96, 206, "五轮实验的五维记分卡（合成样例）", cls="b"))

    cols = ["latency", "throughput", "capacity", "acceptance", "quality"]
    col_label = ["单条体验", "系统吞吐", "容量", "接受长度", "质量"]
    col_x = [438, 556, 674, 792, 910]
    p.append(txt(120, 238, "轮次与改动项", cls="b"))
    for x, label in zip(col_x, col_label):
        p.append(txt(x, 238, label, cls="b", anchor="middle"))
    p.append(txt(1090, 238, "结论", cls="b", anchor="middle"))
    p.append(f'  <path d="M104 250H1176" class="divider"/>')

    # up / down / dash / cross per round, matching the sample
    rows = [
        ("0", "批量扫描", ["—", "—", "—", "", ""], "只出 Goodput 曲线", MUTED_LINE),
        ("1", "KV Cache INT8", ["+", "+", "++", "", "ok"], "符合预期  保留", GOOD),
        ("2", "权重 INT8", ["++", "+", "+", "", "x"], "质量越界  失败回滚", BAD),
        ("3", "投机解码", ["+", "-", "-", "low", ""], "低于预期  成立但不留", WARN),
        ("4", "CUDA Graph 最大批量", ["=", "+", "+", "", ""], "不可分辨  收益在容量", COOL),
    ]
    glyph = {"+": ("改善", GOOD), "++": ("明显改善", GOOD), "-": ("变差", BAD),
             "=": ("测不出", "#64748B"), "—": ("基线", "#94A3B8"),
             "ok": ("在底线内", GOOD), "x": ("越界", BAD), "low": ("2.1 离线 3.6", BAD),
             "": ("不适用", "#CBD5E1")}
    ry = 264
    for num, change, cells, verdict, colour in rows:
        p.append(f'  <rect x="104" y="{ry}" width="1072" height="48" rx="10" '
                 f'fill="{"#FEF2F2" if colour == BAD else "#FFFFFF"}" '
                 f'stroke="#E2E8F0" stroke-width="1.2"/>')
        p.append(txt(120, ry + 30, f"第 {num} 轮", cls="b"))
        p.append(txt(206, ry + 30, change, cls="s"))
        for x, cell in zip(col_x, cells):
            label, cc = glyph[cell]
            if cell in ("", "—"):
                p.append(txt(x, ry + 30, label, cls="s", anchor="middle"))
            else:
                p.append(f'  <rect x="{x - 52}" y="{ry + 12}" width="104" height="26" '
                         f'rx="8" fill="{cc}" opacity="0.10"/>')
                p.append(f'  <text class="b" x="{x}" y="{ry + 30}" text-anchor="middle" '
                         f'fill="{cc}">{label}</text>')
        p.append(f'  <text class="b" x="1090" y="{ry + 30}" text-anchor="middle" '
                 f'fill="{colour}">{verdict}</text>')
        ry += 52

    p.append(txt(120, 540, "第 2 轮能比的三个维度全部改善，只有质量越界，判失败：记分卡不是投票",
                 cls="b"))

    p.append(card(72, 572, 552, 56, cls="badfill", rx=14))
    p.append(txt(92, 606, "质量是否决项。抢占计数接近否决项，它意味着系统在不稳定区运行",
                 cls="s"))
    p.append(card(656, 572, 552, 56, cls="coolfill", rx=14))
    p.append(txt(676, 606, "第 4 轮主指标测不出来，收益写在 capacity 那一列，不往主指标上凑",
                 cls="s"))

    return page(
        system=SYSTEM,
        title="五轮实验的五维记分卡",
        desc="一张五行五列的表。行是第 0 到第 4 轮实验，列是单条体验、系统吞吐、容量、"
             "平均接受长度、质量五个维度。第 2 轮权重 INT8 能比的三个维度都标为改善，质量标为越界，"
             "结论是失败回滚。第 3 轮投机解码的吞吐与容量标为变差，平均接受长度 2.1 低于盈亏线。"
             "第 4 轮单条体验标为测不出，而容量明显改善。",
        kicker="第 19 章 · 19.1、19.4",
        heading="五个维度缺一个，结论就不完整",
        sub="没有一项手段是单向的，所以只看一个指标必然误判",
        body="\n".join(p),
        takeaway="质量是否决项不是投票项：四个维度改善抵不过一个越界",
    )


FIGS = [
    ("fig19-01_goodput_vs_tps", fig1,
     dict(title="图19-1 TPS 峰值与 Goodput 峰值不在同一个批量上",
          source="19.3、19.7",
          order="先看上栏两条曲线在批量 128 处分开，再看下栏 P95 ITL 在哪一档越过 SLO，最后看横轴下方的达标率",
          takeaway="批量扫描要找 Goodput 的峰值，不是 TPS 的峰值；两者不在一处是常态",
          boundary="数据出自 content/ch19/evidence/decode-experiment-sample.json，是合成样例不是真机结果。SLO 那条 80 ms 的线来自负载描述，业务改了这条线，最优批量就换一档，而曲线本身不变")),
    ("fig19-02_five_round_scorecard", fig2,
     dict(title="图19-2 五轮实验的五维记分卡",
          source="19.1、19.4、19.6",
          order="先看列头那五个维度，再横着读第 2 轮那一行，最后看最右边那一列的结论和左下角那句话",
          takeaway="质量是否决项不是投票项：四个维度改善抵不过一个越界",
          boundary="五轮的数据出自那份合成样例，演示的是这套结构长什么样，不是任何真实系统的结论。接受长度和质量两列按实验内容取舍：没启用投机解码就不看接受长度，没动精度就不跑质量评测")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
