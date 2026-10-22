"""Build the Chapter 24 figure set defined in strategy/reviews/ch24/storyboard.md.

Both figures recompute their numbers at build time from
code/ch24/agent_profile.py and content/ch24/evidence/agent-traces-sample.jsonl.

  fig24-01  24.2 and 24.3's three amplifications side by side: time grows
            linearly with the step count, cumulative tokens grow like its
            square, and the task-level pass rate decays exponentially.
  fig24-02  24.7's tail analysis: the same waste patterns showing up in more
            than one long task is the whole reason to start there.

Run from the repository root:

    python3 content/ch24/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch24"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, card, dashed, note, page, txt, write, write_note,
)
import agent_profile as ap  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"
MUTED_LINE = "#94A3B8"

TRACES = ap.load_traces(
    ROOT / "content/ch24/evidence/agent-traces-sample.jsonl")
PROFILE = ap.build_profile(TRACES)
TAIL = ap.tail(TRACES, percentile=0.7)
SLO = ap.step_slo(0.95, 15, 0.95)

# 24.3 那个 12 步的例子。
EXAMPLE = next(t for t in TRACES if t["task_id"] == "t-001")
EXAMPLE_INPUTS = [s["input_tokens"] for s in EXAMPLE["steps"]]
EXAMPLE_TOKENS = ap.cumulative_tokens(EXAMPLE_INPUTS)


# --- 图24-1 步数放大的三样东西，倍数各不相同 --------------------------------

def fig1() -> str:
    p = []
    panels = [
        (72, "时间", "按步数线性放大", "步数从 5 变 15，任务时间大致三倍", GOOD),
        (452, "累计 token", "按步数的平方放大", "步数翻倍，token 账单变四倍", WARN),
        (832, "任务级达标率", "按步数指数衰减", "单步 95%，15 步只剩 46%", BAD),
    ]
    for x, title, how, why, colour in panels:
        p.append(card(x, 176, 376, 300, cls="card", rx=16))
        p.append(txt(x + 24, 208, title, cls="h"))
        p.append(f'  <text class="b" x="{x + 24}" y="236" fill="{colour}">'
                 f'{how}</text>')
        p.append(txt(x + 24, 460, why, cls="s"))

    px0, px1 = 120, 400
    py0, py1 = 252, 408

    def sx(n: int, x0=px0, x1=px1) -> float:
        return x0 + (n - 1) / 34 * (x1 - x0)

    # 一、时间：线性
    def ty(v: float) -> float:
        return py1 - v / 35 * (py1 - py0)
    pts = " ".join(f"{sx(n):.0f},{ty(n):.0f}" for n in range(1, 36))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{GOOD}" '
             f'stroke-width="3"/>')

    # 二、累计 token：平方
    qx0, qx1 = 500, 780
    def qy(v: float) -> float:
        return py1 - v / (35 * 35) * (py1 - py0)
    pts = " ".join(f"{sx(n, qx0, qx1):.0f},{qy(n * n):.0f}" for n in range(1, 36))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{WARN}" '
             f'stroke-width="3"/>')

    # 三、达标率：指数衰减
    ax0, ax1 = 880, 1160
    def ay(v: float) -> float:
        return py1 - v * (py1 - py0)
    pts = " ".join(f"{sx(n, ax0, ax1):.0f},{ay(ap.task_pass_rate(0.95, n)):.0f}"
                   for n in range(1, 36))
    p.append(f'  <polyline points="{pts}" fill="none" stroke="{BAD}" '
             f'stroke-width="3"/>')

    for x0, x1 in ((px0, px1), (qx0, qx1), (ax0, ax1)):
        p.append(f'  <path d="M{x0} {py0}V{py1}H{x1}" fill="none" '
                 f'stroke="{MUTED_LINE}" stroke-width="1.6"/>')
        for n in (5, 15, 35):
            p.append(txt(sx(n, x0, x1), py1 + 22, str(n), cls="s",
                         anchor="middle"))
        p.append(txt(x0 - 26, py1 + 22, "步数", cls="s"))

    # 达标率那一栏把 24.2 的四个数标出来
    for n in (5, 8, 15, 35):
        rate = ap.task_pass_rate(0.95, n)
        p.append(f'  <circle cx="{sx(n, ax0, ax1):.0f}" cy="{ay(rate):.0f}" '
                 f'r="5" fill="{BAD}"/>')
        p.append(txt(sx(n, ax0, ax1) + 10, ay(rate) - 8, f"{rate:.0%}",
                     cls="b"))

    p.append(card(72, 496, 700, 132, cls="card", rx=16))
    p.append(txt(96, 528, "24.3 那个 12 步的例子：累计输入不是最后一步的数字",
                 cls="b"))
    p.append(txt(96, 562,
                 f"首步 {EXAMPLE_TOKENS['first_step']:.0f}，"
                 f"末步 {EXAMPLE_TOKENS['last_step']:.0f}，"
                 f"逐步累加 {EXAMPLE_TOKENS['exact']:.0f} token", cls="s"))
    p.append(txt(96, 590,
                 f"梯形式子 步数 × (首步 + 末步) / 2 = "
                 f"{EXAMPLE_TOKENS['trapezoid_estimate']:.0f}，"
                 f"偏高 {EXAMPLE_TOKENS['estimate_error_share']:.1%}", cls="s"))
    p.append(txt(96, 616,
                 f"而把首步乘以步数只得 "
                 f"{EXAMPLE_TOKENS['naive_first_step_times_steps']:.0f}，"
                 f"低估 {EXAMPLE_TOKENS['naive_understates_by']:.1f} 倍",
                 cls="bad"))

    p.append(card(796, 496, 412, 132, cls="warnfill", rx=16))
    p.append(txt(820, 528, "反过来推更有说服力", cls="b"))
    p.append(txt(820, 562,
                 f"要让 15 步任务做到 95%，"
                 f"单步需要 {SLO['required_step_pass_rate']:.2%}", cls="s"))
    p.append(txt(820, 590,
                 f"而把步数砍到 {SLO['halved_steps']} 步，"
                 f"同样的单步 95% 就能到 "
                 f"{SLO['halved_task_pass_rate']:.0%}", cls="s"))
    p.append(txt(820, 616, "所以第一优先级是减步数，不是让每一步更快", cls="b"))

    return page(
        system=SYSTEM,
        title="步数放大三样东西，而三者的倍数各不相同",
        desc="上方三栏并排，横轴都是步数从 1 到 35。第一栏是任务时间，随步数线性上升；"
             "第二栏是累计输入 token，随步数的平方上升；第三栏是任务级达标率，单步 95% 时"
             "随步数指数衰减，在 5、8、15、35 步上分别标出 77%、66%、46%、17%。下方左边"
             "用 24.3 那个 12 步的例子对比三种算法：逐步累加 174500、梯形估算 180000、"
             "把首步乘以步数只得 24000。下方右边是反推：15 步要做到 95% 需要单步 99.66%。",
        kicker="第 24 章 · 24.2、24.3",
        heading="时间是线性的，账单是平方的，达标率是指数的",
        sub="没有任何单点优化能抵消这个倍数，所以第一优先级是减少步数",
        body="\n".join(p),
        takeaway="单步 95% 达标的系统，八步任务只有三分之二达标，三十五步任务只剩不到两成",
    )


# --- 图24-2 长尾里的浪费模式 ------------------------------------------------

def fig2() -> str:
    p = [card(72, 176, 1136, 320, cls="card", rx=16)]
    p.append(txt(96, 208,
                 f"按步数取 P{TAIL['percentile'] * 100:.0f} 以上的 "
                 f"{TAIL['tasks_in_tail']} 个任务（合成追踪）", cls="b"))

    x0 = 232
    y = 232
    colour_of = {"search": COOL, "read_file": WARN, "run_code": BAD}
    for row in TAIL["tail_tasks"]:
        seq = row["tool_sequence"]
        cell = min(28, (1160 - x0) / max(len(seq), 1))
        p.append(txt(96, y + 18, row["task_id"], cls="b"))
        p.append(txt(96, y + 40, f"{row['steps']} 步", cls="s"))
        for i, tool in enumerate(seq):
            c = colour_of.get(tool, MUTED_LINE)
            p.append(f'  <rect x="{x0 + i * cell:.1f}" y="{y + 4}" '
                     f'width="{cell - 4:.1f}" height="26" rx="5" fill="{c}" '
                     f'opacity="0.55"/>')
        names = "、".join(w["pattern"] for w in row["waste"]) or "无"
        p.append(txt(x0, y + 52, f"浪费模式：{names}", cls="s"))
        y += 58

    p.append(txt(96, 478, "颜色就是工具：", cls="s"))
    lx = 232
    for tool, c in colour_of.items():
        p.append(f'  <rect x="{lx}" y="466" width="16" height="16" rx="4" '
                 f'fill="{c}" opacity="0.55"/>')
        p.append(txt(lx + 24, 479, tool, cls="m"))
        lx += 160

    cards = [
        ("repeated_tool", "同一个工具被连续调用 ≥ 4 次", "工具粒度太细，"
         "一件事要调好几次", WARN),
        ("oscillation", "在两个工具之间来回 ≥ 4 步", "错误信息不够清楚，"
         "Agent 决定不了下一步", COOL),
        ("same_resource", "≥ 4 次调用指向同一份资源", "同一份长文档被反复解析，"
         "后面每步都重复付费", BAD),
    ]
    x = 72
    for name, rule, why, colour in cards:
        p.append(card(x, 512, 368, 116, cls="card", rx=16))
        p.append(f'  <text class="mb" x="{x + 24}" y="542" fill="{colour}">'
                 f'{name}</text>')
        p.append(txt(x + 24, 568, rule, cls="s"))
        p.append(txt(x + 24, 594, why, cls="s"))
        count = TAIL["pattern_counts"].get(name, 0)
        mark = "在这批长尾里出现在 " + str(count) + " 个任务里"
        p.append(f'  <text class="b" x="{x + 24}" y="620" fill="{colour}">'
                 f'{mark}</text>')
        x += 384

    return page(
        system=SYSTEM,
        title="长尾任务里的浪费模式，修一个能改善很多任务",
        desc="上方四行，每行是一个长尾任务的工具调用序列，用彩色方块按顺序排开，颜色对应 "
             "search、read_file、run_code 三种工具。可以直接看出连续相同颜色的长串和两种"
             "颜色交替的段落。每行下方标出脚本检出的浪费模式。下方三块分别说明三种模式的"
             "判据、成因，以及它在这批长尾里出现在几个任务中。",
        kicker="第 24 章 · 24.7",
        heading="长尾里的浪费模式通常很明显",
        sub="修掉一个模式能同时改善很多任务，这是从长尾下手的全部理由",
        body="\n".join(p),
        takeaway=(f"{len(TAIL['shared_patterns'])} 种模式出现在两个以上的任务里，"
                  f"它们才值得先动手"),
    )


FIGS = [
    ("fig24-01_step_amplification", fig1,
     dict(title="图24-1 步数放大三样东西，而三者的倍数各不相同",
          source="24.2、24.3",
          order="先横着比上方三条曲线的弯法，再看第三栏标出的四个达标率，然后看左下角三种算累计 token 的方法差多少，最后看右下角那个反推",
          takeaway="单步 95% 达标的系统，八步任务只有三分之二达标，三十五步任务只剩不到两成",
          boundary="达标率那条曲线算的是每一步都必须成功、各步独立的情形；各步正相关时实际比它高，变重的是任务总时长的尾巴，延迟要直接测总时长；带重试的 Agent 不适用这条式子，要按 24.6 用完成率定义达标")),
    ("fig24-02_tail_waste_patterns", fig2,
     dict(title="图24-2 长尾任务里的浪费模式",
          source="24.7",
          order="先扫一眼四行方块里哪里出现了连续的同色长串，再找两色交替的段落，然后读每行下方检出的模式，最后看下方三块里每种模式出现在几个任务里",
          takeaway="修掉一个模式能同时改善很多任务，这是从长尾下手的全部理由",
          boundary="数据出自 content/ch24/evidence/agent-traces-sample.jsonl，是合成追踪不是真机采集；十个任务的样本太小，P95 就是最大值，所以这张图取的是 P70")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
