"""Build the Chapter 20 figure set defined in strategy/reviews/ch20/storyboard.md.

Every number drawn here comes from one of two places and can be recomputed:

  fig20-01  20.2's state machine. No numbers.
  fig20-02  20.6's ρ/(1−ρ) curve. The four tabulated points come from
            code/ch20/scheduler_watch.py's `amplification`; the lower curve is
            the same instance read as 64 slots, from `multi_server_wait_factor`.
  fig20-03  20.7's three signals in order. The three onsets and the lead time
            come from content/ch20/evidence/scheduler-trace-sample.json via
            `scheduler_watch.analyze`.

Run from the repository root:

    python3 content/ch20/figures/build_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch20"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, card, dashed, note, page, txt, write, write_note,
)
import scheduler_watch as sw  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"
MUTED_LINE = "#94A3B8"

TRACE = json.loads(
    (ROOT / "content/ch20/evidence/scheduler-trace-sample.json")
    .read_text(encoding="utf-8"))
READING = sw.analyze(TRACE)
RHO_ROWS = sw.queue_model()["table"]


# --- 图20-1 三个状态，一条路径，两条非常规边 --------------------------------

def fig1() -> str:
    p = [card(72, 176, 760, 396, cls="card", rx=16)]
    p.append(txt(96, 208, "调度器眼里只有三个状态", cls="b"))

    boxes = [
        (120, 256, "Waiting", "已接受但还没开始算", "soft"),
        (400, 256, "Running", "正在参与每一步前向", "coolfill"),
        (664, 256, "Finished", "生成完毕或被取消", "goodfill"),
    ]
    for x, y, name, sub, cls in boxes:
        w = 168 if name != "Finished" else 144
        p.append(card(x, y, w, 84, cls=cls, rx=14))
        p.append(txt(x + 16, y + 34, name, cls="h"))
        p.append(txt(x + 16, y + 62, sub, cls="s"))
    p.append('  <path class="flow" d="M288 298H392"/>')
    p.append('  <path class="flow" d="M568 298H656"/>')

    # 两条非常规边，各自走在主链的上下方，不穿过任何文字
    p.append('  <path class="feedback" d="M204 256Q204 226 240 226H412"/>')
    p.append(txt(424, 231, "拒绝：超出准入限制（第 21 章）", cls="good"))
    p.append('  <path class="feedback" d="M470 340Q470 396 340 396Q204 396 204 352"/>')
    p.append(txt(300, 422, "抢占：KV 被释放，退回队列（第 16 章）", cls="good"))

    p.append(txt(96, 448, "每一步做的事", cls="b"))
    steps = [
        "1  看 Running 还能不能再加（受槽位上限、KV 余量和 token 预算限制）",
        "2  能加就从 Waiting 队首取出来，分配 KV 块，放进 Running",
        "3  Running 里的请求要长新 KV 块而显存不够时，抢占一条（默认挑最晚进来的）",
        "4  对整个 Running 集合执行一步前向",
        "5  完成的移出，循环",
    ]
    for i, line in enumerate(steps):
        p.append(txt(120, 470 + 21 * i, line, cls="m"))

    p.append(card(856, 176, 352, 396, cls="card", rx=16))
    p.append(txt(880, 208, "第 4 步是所有副作用的来源", cls="b"))
    p.append(note(872, 228, 320, [
        "整个 Running 集合一起算一步",
        "一条请求进 Running 之后，",
        "它的节奏就和同批的其他请求绑在一起",
    ], cls="coolfill"))
    p.append(note(872, 346, 320, [
        "批次成员每步都在变",
        "所以每步的耗时也在变",
        "ITL 的抖动来自别的请求何时进出",
    ], cls="warnfill"))
    p.append(note(872, 464, 320, [
        "第 15 章案例二那个现象就在这里：",
        "平均 TPOT 没变，P99 ITL 从 40 涨到 210",
    ], cls="soft"))

    p.append(note(72, 588, 1136, [
        "队列长度为零不代表系统空闲：请求一到就被吸进 Running，"
        "而 Running 可能已经满载。这是 20.7 要换一组指标的理由。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="三个状态，一条路径，两条非常规边",
        desc="左侧是 Waiting、Running、Finished 三个方框，用实线箭头依次相连。两条虚线"
             "箭头是非常规边：一条从 Waiting 折回外部，标为准入拒绝；一条从 Running 折回 "
             "Waiting，标为抢占。下方列出调度器每一步做的五件事，第 4 步是对整个 Running "
             "集合执行一步前向。右侧三块说明这一步带来的后果：节奏绑定、每步耗时变化、"
             "ITL 抖动。",
        kicker="第 20 章 · 20.2、20.3",
        heading="请求在进 GPU 之前只经过三个状态",
        sub="真正决定一切的是第 4 步：整个 Running 集合一起算一步",
        body="\n".join(p),
        takeaway="进了 Running，这条请求的节奏就和同批其他请求绑在一起，ITL 抖动由此而来",
    )


# --- 图20-2 ρ/(1−ρ) 的形状 --------------------------------------------------

def fig2() -> str:
    p = [card(72, 176, 728, 396, cls="card", rx=16)]
    p.append(txt(96, 208, "平均排队是几个 S：W_q ≈ S × ρ/(1−ρ)，S = 1/满载吞吐", cls="b"))

    x0, x1 = 152, 748
    y0, y1 = 240, 496
    top = 20.0

    def px(rho: float) -> float:
        return x0 + rho / 0.97 * (x1 - x0)

    def py(v: float) -> float:
        return y1 - min(v, top) / top * (y1 - y0)

    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" '
             f'stroke="{MUTED_LINE}" stroke-width="1.6"/>')
    for v in (1, 4, 9, 19):
        p.append(dashed(x0, py(v), x1, py(v)))
        p.append(txt(x0 - 10, py(v) + 5, f"{v}×", cls="s", anchor="end"))

    pts = []
    rho = 0.0
    while rho <= 0.955:
        pts.append(f"{px(rho):.1f},{py(sw.amplification(rho)):.1f}")
        rho += 0.005
    p.append(f'  <polyline points="{" ".join(pts)}" fill="none" '
             f'stroke="{COOL}" stroke-width="3.2"/>')

    # 同一个实例按 64 个槽位读（Erlang C）。它是单服务台那条线的下界，
    # 画出来是为了让读者看到两件事：低负载时几乎不排队，接近饱和时一样陡。
    multi = []
    rho = 0.0
    while rho <= 0.955:
        multi.append(f"{px(rho):.1f},{py(sw.multi_server_wait_factor(64, rho)):.1f}")
        rho += 0.005
    p.append(f'  <polyline points="{" ".join(multi)}" fill="none" '
             f'stroke="{GOOD}" stroke-width="2.6" stroke-dasharray="8 6"/>')
    # 两条线用图例区分，放在左上那片空白里，不往曲线旁边挤
    for i, (label, colour, dash, cls) in enumerate((
            ("单服务台（按服务台个数的上界）", COOL, "", "cool"),
            ("同一实例按 64 个槽位算（Erlang C，下界）", GOOD, ' stroke-dasharray="8 6"', "good"))):
        y = 340 + i * 26
        p.append(f'  <path d="M176 {y - 5}H212" stroke="{colour}" stroke-width="3"{dash}/>')
        p.append(txt(222, y, label, cls=cls))

    # 0.7 到 0.9 之间那一段是全图的重点，浅色标出来。说明放在左上那片空白里，
    # 不压曲线：曲线在 ρ < 0.8 的整段都贴着横轴。
    p.append(f'  <rect x="{px(0.7):.0f}" y="{y0}" width="{px(0.9) - px(0.7):.0f}" '
             f'height="{y1 - y0}" fill="{WARN}" opacity="0.07"/>')
    p.append(txt(px(0.7) + 6, y1 - 14, "0.7–0.9", cls="warn"))
    p.append(txt(176, 280, "浅色那一段是同样加 5% 流量后果差最远的地方", cls="warn"))
    p.append(txt(176, 306, "在 0.7 那头排队涨约两成，到 0.9 那头接近翻倍", cls="s"))

    labels = {0.5: "1 倍", 0.8: "4 倍", 0.9: "9 倍", 0.95: "19 倍"}
    for row in RHO_ROWS:
        rho = row["rho"]
        v = row["amplification"]
        colour = BAD if rho >= 0.9 else (WARN if rho >= 0.8 else GOOD)
        p.append(f'  <circle cx="{px(rho):.1f}" cy="{py(v):.1f}" r="6.5" '
                 f'fill="{colour}"/>')
        dx, anchor = (12, "start") if rho < 0.95 else (-12, "end")
        p.append(txt(px(rho) + dx, py(v) - 10, labels[rho], cls="b", anchor=anchor))
    # 横轴刻度和那四个点分开标，否则 0.90 和 0.95 会挤在一起
    for tick in (0.2, 0.4, 0.6, 0.8, 0.95):
        p.append(f'  <path d="M{px(tick):.1f} {y1}V{y1 + 7}" stroke="{MUTED_LINE}" '
                 f'stroke-width="1.6"/>')
        p.append(txt(px(tick), y1 + 28, f"{tick:g}", cls="s", anchor="middle"))
    p.append(txt(96, y1 + 28, "负载率 ρ", cls="s"))
    p.append(txt(96, y1 + 54, "负载率是到达速率占整个实例满载吞吐的比例，"
                              "不是监控面板上的 GPU 利用率", cls="s"))

    p.append(card(824, 176, 384, 396, cls="card", rx=16))
    p.append(txt(848, 208, "用它之前要知道差在哪", cls="b"))
    p.append(note(840, 228, 352, [
        "服务台不止一个",
        "按服务台个数，单服务台是上界，64 个槽位低得多，",
        "但接近饱和时陡增这个形状不变",
    ], cls="soft"))
    p.append(note(840, 336, 352, [
        "服务时长不服从指数分布",
        "长尾输出把等待乘上 (Ca² + Cs²)/2，",
        "式子给的是平均，P99 要另算",
    ], cls="soft"))
    p.append(note(840, 444, 352, [
        "容量本身会缩",
        "抢占要重算 Prefill，等效于 ρ 自己往上走，",
        "式子里没有这一项",
    ], cls="warnfill"))

    p.append(note(72, 588, 1136, [
        "正确用法是回答“再加 10% 流量会怎样”，不是算出一个毫秒数写进报告。"
        "ρ 到 1 时队列没有上界地增长，这时要看的是队列增长速度，不是等待时间。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="接近饱和时排队时间对负载的敏感度急剧上升",
        desc="两条曲线，横轴是负载率从 0 到 0.95，纵轴是平均排队时间相当于几个 S。"
             "实线是单服务台，在 0.5 处是 1 倍，0.8 处是 4 倍，0.9 处是 9 倍，0.95 处是 19 倍，"
             "四个点分别用绿、橙、红标出；虚线是同一实例按 64 个槽位算的 Erlang C，低负载时"
             "几乎贴着横轴，接近饱和时一样陡起来。0.7 到 0.9 之间用浅色带标出，说明同样加 5% "
             "流量在这一段里后果差别很大。右侧三块列出 LLM 服务与 M/M/1 前提的三处不符。",
        kicker="第 20 章 · 20.6",
        heading="“负载没变，P99 为什么跳”的答案在这条曲线的形状里",
        sub="ρ/(1−ρ) 在 0.5、0.8、0.9、0.95 上分别是 1、4、9、19",
        body="\n".join(p),
        takeaway="70% 负载率下加 5% 流量排队涨约两成，90% 下加同样的 5% 接近翻倍",
    )


# --- 图20-3 三个信号的先后顺序与 lead_time ---------------------------------

def fig3() -> str:
    p = [card(72, 176, 1136, 328, cls="card", rx=16)]
    p.append(txt(96, 208, "同一段阶梯式增压里，三个信号先后动起来（合成 trace）",
                 cls="b"))

    x0, x1 = 272, 1064
    duration = float(TRACE["duration_s"])

    def tx(t: float) -> float:
        return x0 + t / duration * (x1 - x0)

    lanes = [
        ("槽位占用率", "running_ratio 持续 ≥ 0.95",
         READING["saturation_onset"], COOL, 244),
        ("Waiting 队列长度", "waiting 持续 > 0",
         READING["queue_onset"], WARN, 312),
        ("抢占计数", "preemption_total 上涨",
         READING["preemption_onset"], BAD, 380),
    ]
    for name, cond, onset, colour, y in lanes:
        p.append(f'  <rect x="{x0}" y="{y}" width="{x1 - x0}" height="44" rx="10" '
                 f'fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1.2"/>')
        p.append(txt(96, y + 28, name, cls="b"))
        p.append(f'  <rect x="{tx(onset):.0f}" y="{y}" '
                 f'width="{x1 - tx(onset):.0f}" height="44" rx="10" '
                 f'fill="{colour}" opacity="0.14"/>')
        p.append(f'  <path d="M{tx(onset):.0f} {y}V{y + 44}" stroke="{colour}" '
                 f'stroke-width="3"/>')
        p.append(txt(tx(onset) + 12, y + 28, f"{onset:.0f} 秒  {cond}", cls="b"))

    # lead_time 标注
    lead = READING["lead_time"]
    p.append(f'  <path class="bracket" d="M{tx(READING["saturation_onset"]):.0f} 438'
             f'V452H{tx(READING["queue_onset"]):.0f}V438"/>')
    p.append(txt((tx(READING["saturation_onset"]) + tx(READING["queue_onset"])) / 2,
                 474, f"lead_time = {lead:.0f} 秒", cls="b", anchor="middle"))
    p.append(txt(tx(READING["queue_onset"]) + 16, 474,
                 "这段就是你能拿到的预警时间，告警该配在第一个信号上", cls="s"))

    for t in range(0, int(duration) + 1, 10):
        p.append(txt(tx(t), 228, f"{t}s", cls="s", anchor="middle"))

    p.append(card(72, 520, 552, 108, cls="goodfill", rx=14))
    p.append(txt(92, 552, "lead_time 大于零", cls="b"))
    p.append(txt(92, 580, "饱和到排队之间有余地，告警配在 running_ratio 上来得及",
                 cls="s"))
    p.append(txt(92, 606, f"这段 trace 判的是 {READING['verdict']}，"
                          f"窗口内抢占 {READING['preemptions_in_window']} 次",
                 cls="s"))

    p.append(card(656, 520, 552, 108, cls="badfill", rx=14))
    p.append(txt(676, 552, "lead_time 小于或等于零", cls="b"))
    p.append(txt(676, 580, "排队不晚于饱和，说明 max_num_seqs 不是当前的约束",
                 cls="s"))
    p.append(txt(676, 606, "这时把告警配在 running_ratio 上会完全失灵", cls="s"))

    return page(
        system=SYSTEM,
        title="三个调度信号的先后顺序，以及它们之间的预警时间",
        desc="三条并列的时间轴泳道，横轴是 0 到 60 秒。第一条是槽位占用率，在第 15 秒"
             "开始持续接近 1；第二条是 Waiting 队列长度，在第 25 秒开始持续大于 0；第三条是"
             "抢占计数，在第 40 秒开始上涨。第一条和第二条之间用括号标出 lead_time 等于 10 "
             "秒。下方两块分别说明 lead_time 大于零和小于等于零时的不同结论。",
        kicker="第 20 章 · 20.7、20.8",
        heading="第一个信号最早动，第三个最晚但最严重",
        sub="告警配在第一个上；等第二、三个动起来，用户已经在投诉了",
        body="\n".join(p),
        takeaway="lead_time 量化了饱和到排队之间的预警时间，它直接决定告警配在哪个指标上",
    )


FIGS = [
    ("fig20-01_three_states", fig1,
     dict(title="图20-1 三个状态，一条路径，两条非常规边",
          source="20.2、20.3",
          order="先沿实线箭头读三个状态，再看两条虚线的非常规边，然后看下方每一步做的五件事，最后看右侧第 4 步带来的三个后果",
          takeaway="进了 Running，这条请求的节奏就和同批其他请求绑在一起，ITL 抖动由此而来",
          boundary="这是简化到三个状态的模型，真实引擎的内部状态更多；两条非常规边各自的完整机制在第 21 章和第 16 章")),
    ("fig20-02_queue_amplification", fig2,
     dict(title="图20-2 接近饱和时排队时间对负载的敏感度急剧上升",
          source="20.6",
          order="先看曲线在 0.5 到 0.8 之间有多平，再看 0.9 之后有多陡，然后读四个标出的点，最后看右侧那三处与 M/M/1 前提的不符",
          takeaway="70% 负载率下加 5% 流量排队涨约两成，90% 下加同样的 5% 接近翻倍",
          boundary="M/M/1 只在 ρ < 1 的稳态下成立，给的是形状和量级不是预测值；横轴的负载率指到达量占处理能力的比例，不是监控面板上的 GPU 利用率")),
    ("fig20-03_three_signals", fig3,
     dict(title="图20-3 三个调度信号的先后顺序与 lead_time",
          source="20.7、20.8",
          order="从上往下读三条泳道各自在第几秒变色，再看第一条和第二条之间那个括号，最后看下方两块里 lead_time 正负两种情形的不同结论",
          takeaway="lead_time 量化了饱和到排队之间的预警时间，它直接决定告警配在哪个指标上",
          boundary="数据出自 content/ch20/evidence/scheduler-trace-sample.json，是合成 trace 不是真机采集；三个 onset 都要求连续三个样本才算，单个样本越线按噪声处理")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
