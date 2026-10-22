"""Build the Chapter 26 figure set defined in strategy/reviews/ch26/storyboard.md.

  fig26-01  26.2 到 26.3 那条链，画成一条从日活到卡数的阶梯，中间那一步
            「按平均总长度折算并发」单独标出来，因为 29.8 案例一就是它被跳过。
            末端两个约束取更紧的一个，并把 Prefill 占时那一项补上之后的数
            和只看两个静态约束的数并排。
  fig26-02  26.3 的余量：一分钟三倍突发的消化时间随卡数怎么变，以及排队
            那一项在“钉在副本上”和“按负载派发”两种派发下差多少。

链上每一个数都由 code/ch26/capacity_cost.py 在构建时算出来，所以图不可能报出
一个模型给不出的数。

Run from the repository root:

    python3 content/ch26/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch26"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, MUTED, WARN, card, dashed, note, page, txt, write,
    write_note,
)
import capacity_cost as cc  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

PARAMS = dict(dau=500000, sessions_per_user=3.2, peak_to_mean=3.0,
              calls_per_session=2.4, input_tokens=2600, output_tokens=220,
              request_duration=4.2, gpu_concurrency=130,
              concurrency_at_tokens=2300, gpu_output_tps=1560,
              prefill_share=cc.DEFAULT_PREFILL_SHARE,
              measured_io_ratio=cc.DEFAULT_MEASURED_IO_RATIO,
              gpu_monthly=12000, headroom=0.3,
              api_input_price=0.0008, api_output_price=0.002)

MODEL = cc.build_model(PARAMS)
STATIC = cc.build_model(dict(PARAMS, ignore_prefill=True))
D = MODEL["demand"]
S = MODEL["sizing"]
TPS = MODEL["gpu_output_tps_used"]
SCALED_CONC = MODEL["gpu_concurrency_used"]
MINIMUM = S["gpus_minimum_exact"]
MARGIN_OPTIONS = [36, 42, 45, 48]
MARGIN = cc.margin_table(MINIMUM, MARGIN_OPTIONS)


# --- 图26-1 从日活到卡数，中间那一步不能省 -----------------------------------

def fig1() -> str:
    p = []

    # 左：六级阶梯
    p.append(card(56, 158, 620, 416, cls="card", rx=16))
    p.append(txt(80, 190, "26.2 那条链（合成设定）", cls="b"))

    steps = [
        ("日活 × 每人对话数", f"{PARAMS['dau']:.0f} × {PARAMS['sessions_per_user']}",
         f"{D['daily_sessions']:.0f} 次对话/天", MUTED),
        ("÷ 86400", "摊到每秒", f"{D['mean_session_qps']:.1f} 对话/s", MUTED),
        ("× 峰均比", f"× {PARAMS['peak_to_mean']:.0f}",
         f"{D['peak_session_qps']:.1f} 对话/s", WARN),
        ("× 每次对话的调用数", f"× {PARAMS['calls_per_session']}",
         f"{D['peak_call_qps']:.0f} 调用/s", WARN),
        ("× 平均输出长度", f"× {PARAMS['output_tokens']:.0f}",
         f"{D['peak_output_tps']:.0f} token/s", COOL),
        # 这一级不接在 token/s 那一级后面：在途条数是「调用/s × 平均请求时长」，
        # 顺着阶梯往下乘会得到 29333 × 4.2，差两个量级（Part 6 审阅 P1-8）。
        ("调用/s × 平均请求时长",
         f"{D['peak_call_qps']:.0f} × {PARAMS['request_duration']} s",
         f"在途 {MODEL['inflight']:.0f} 条", COOL),
    ]
    y = 222
    for label, how, out, colour in steps:
        p.append(txt(80, y + 20, label, cls="b"))
        p.append(txt(332, y + 20, how, cls="m"))
        p.append(f'  <text class="mb" x="456" y="{y + 20}" fill="{colour}">'
                 f'{out}</text>')
        if y < 222 + 58 * 5:
            p.append(f'  <path d="M72 {y + 36}H660" class="divider"/>')
        y += 58

    p.append(note(56, 588, 620, [
        f"第二步和第四步之间差 {PARAMS['peak_to_mean']:.0f} × "
        f"{PARAMS['calls_per_session']} = "
        f"{PARAMS['peak_to_mean'] * PARAMS['calls_per_session']:.1f} 倍，"
        "26.8 案例一把它们当成了同一个数",
    ], cls="warnfill"))

    # 右上：折算那一步
    p.append(card(700, 158, 524, 196, cls="badfill", rx=16))
    p.append(txt(724, 190, "不能省的那一步：按总长度折算并发", cls="h"))
    p.append(txt(724, 224,
                 f"第 16 章给的 {PARAMS['gpu_concurrency']:.0f} 条，是在总长度 "
                 f"{PARAMS['concurrency_at_tokens']:.0f} token 下测的",
                 cls="s"))
    p.append(txt(724, 252,
                 f"本例 {PARAMS['input_tokens']:.0f} + "
                 f"{PARAMS['output_tokens']:.0f} = "
                 f"{PARAMS['input_tokens'] + PARAMS['output_tokens']:.0f} token",
                 cls="s"))
    p.append(f'  <text class="mb" x="724" y="286" fill="{BAD}">'
             f'{PARAMS["gpu_concurrency"]:.0f} × '
             f'{PARAMS["concurrency_at_tokens"]:.0f} ÷ '
             f'{PARAMS["input_tokens"] + PARAMS["output_tokens"]:.0f} ≈ '
             f'{SCALED_CONC:.0f} 条</text>')
    p.append(txt(724, 320,
                 "跳过它，等于用另一个负载的容量给这个负载配卡", cls="s"))

    # 右中：两个约束取更紧
    p.append(card(700, 374, 524, 200, cls="card", rx=16))
    p.append(txt(724, 406, "两个约束，取更紧的", cls="h"))
    rows = [
        ("只看静态吞吐", f"{D['peak_output_tps']:.0f} ÷ "
                     f"{PARAMS['gpu_output_tps']:.0f}",
         f"{STATIC['sizing']['gpus_by_throughput']:.1f} 张", MUTED),
        ("补上 Prefill 占时", f"{D['peak_output_tps']:.0f} ÷ "
                          f"{TPS['output_tps']:.0f}",
         f"{S['gpus_by_throughput']:.1f} 张", BAD),
        ("按显存并发", f"{MODEL['inflight']:.0f} ÷ {SCALED_CONC:.0f}",
         f"{S['gpus_by_memory']:.1f} 张", GOOD),
    ]
    yy = 426
    for label, how, out, colour in rows:
        p.append(txt(724, yy + 20, label, cls="b"))
        p.append(txt(904, yy + 20, how, cls="m"))
        p.append(f'  <text class="mb" x="1084" y="{yy + 20}" fill="{colour}">'
                 f'{out}</text>')
        yy += 36
    p.append(f'  <path d="M716 {yy + 4}H1208" class="divider"/>')
    p.append(f'  <text class="b" x="724" y="{yy + 34}" fill="{BAD}">'
             f'吞吐先满，刚好够 {S["gpus_minimum"]} 张，加 '
             f'{PARAMS["headroom"]:.0%} 余量 {S["gpus_required"]} 张</text>')

    p.append(note(700, 588, 524, [
        f"Prefill 占时 {TPS['prefill_share_measured']:.0%} → "
        f"{TPS['prefill_share_actual']:.0%}，单卡输出 "
        f"{PARAMS['gpu_output_tps']:.0f} → {TPS['output_tps']:.0f} token/s",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="从日活到卡数，中间那一步不能省",
        desc="左栏是六级阶梯：日活五十万乘每人 3.2 次对话得到每天一百六十万次，"
             "除以 86400 得到每秒 18.5 次对话，乘峰均比 3 得到 55.6，"
             "再乘每次对话 2.4 次模型调用得到每秒 133 次调用，"
             "乘平均输出长度 220 得到每秒 29333 个输出 token；"
             "最后一级回到每秒 133 次调用，乘平均请求时长 4.2 秒得到在途 560 条。"
             "右上一块讲不能省的那一步：第 16 章给的单卡并发 130 条是在总长度 2300 "
             "token 下测的，本例负载 2820 token，折算后是 106 条。"
             "右中一块把约束并排：只看静态吞吐是 18.6 张，补上 Prefill 占时后单卡输出"
             "从 1560 降到 924 token/s，变成 31.7 张；按显存并发只要 5.3 张。"
             "吞吐先满，刚好够 32 张，加 30% 余量 42 张。",
        kicker="第 26 章 · 26.2、26.3",
        heading="搬数字的时候，要把产生它的条件一起搬",
        sub="130 条是在 2300 token 下测的，本例 2820 token，折算后是 106 条",
        body="\n".join(p),
        takeaway="链上少一步折算，配出来的卡数就是另一个负载的答案",
    )


# --- 图26-2 余量买的是排队时间 -----------------------------------------------

def fig2() -> str:
    p = []
    p.append(card(56, 158, 744, 416, cls="card", rx=16))
    p.append(txt(80, 190, "一分钟三倍突发要多久才消化完（按卡数）", cls="b"))

    x0, x1 = 160, 760
    y0, y1 = 232, 506
    lo, hi = 33, 53
    top = 30.0

    def px(cards):
        return x0 + (cards - lo) / (hi - lo) * (x1 - x0)

    def py(minutes):
        return y1 - min(minutes, top) / top * (y1 - y0)

    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" stroke="#94A3B8" '
             f'stroke-width="1.8"/>')
    pts = []
    c = lo
    while c <= hi + 1e-9:
        rho = MINIMUM / c
        pts.append(f"{px(c):.1f} {py(cc.drain_minutes(rho)):.1f}")
        c += 0.1
    p.append(f'  <path d="M{"L".join(pts)}" fill="none" stroke="{COOL}" '
             f'stroke-width="2.6"/>')
    for m in (5, 10, 15, 20, 25, 30):
        yy = py(m)
        p.append(f'  <path d="M{x0 - 6} {yy:.1f}H{x0}" stroke="#94A3B8" '
                 f'stroke-width="1.4"/>')
        p.append(txt(x0 - 14, yy + 5, f"{m} 分", cls="s", anchor="end"))
    for c in (33, 38, 43, 48, 53):
        xx = px(c)
        p.append(f'  <path d="M{xx:.1f} {y1}V{y1 + 6}" stroke="#94A3B8" '
                 f'stroke-width="1.4"/>')
        p.append(txt(xx, y1 + 26, f"{c} 张", cls="s", anchor="middle"))

    # 四个落点挤在曲线平缓的那一段，标注改成右上角的一张小表，点下面只标卡数
    colours = {36: WARN, 42: GOOD, 45: GOOD, 48: GOOD}
    ly = 262
    for row in MARGIN:
        cards = row["cards"]
        cx, cy = px(cards), py(row["drain_minutes"])
        p.append(f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" '
                 f'fill="{colours[cards]}"/>')
        p.append(f'  <text class="s" x="{cx:.1f}" y="{cy + 26:.1f}" '
                 f'text-anchor="middle" fill="{colours[cards]}">{cards}</text>')
        p.append(f'  <circle cx="452" cy="{ly - 5}" r="6" fill="{colours[cards]}"/>')
        p.append(f'  <text class="b" x="468" y="{ly}" fill="{colours[cards]}">'
                 f'{cards} 张　负载率 {row["rho"]:.2f}　'
                 f'{row["drain_minutes"]:.1f} 分钟</text>')
        ly += 30
    p.append(txt(x0, y1 + 52,
                 f"刚好够是 {MINIMUM:.1f} 张；故障、升级、预测误差三项约要加 25% 到 30%",
                 cls="s"))

    # 右栏：排队那一项按派发方式差多少
    p.append(card(824, 158, 400, 248, cls="card", rx=16))
    p.append(txt(848, 190, "排队那一项看怎么派发（单位 S）", cls="h"))
    p.append(txt(848, 222, "卡数", cls="b"))
    p.append(txt(920, 222, "钉在副本上", cls="b"))
    p.append(txt(1072, 222, "按负载派发", cls="b"))
    yy = 256
    for row in MARGIN:
        if row["cards"] == 45:
            continue
        p.append(txt(848, yy, f"{row['cards']} 张", cls="m"))
        p.append(f'  <text class="mb" x="920" y="{yy}" fill="{WARN}">'
                 f'{row["amplification"]:.1f}</text>')
        p.append(f'  <text class="mb" x="1072" y="{yy}" fill="{GOOD}">'
                 f'{row["erlang_c_wait"]:.3f}</text>')
        yy += 30
    p.append(txt(848, yy + 4, "左列是单副本上界（M/M/1），", cls="s"))
    p.append(txt(848, yy + 30, "右列是全部卡按负载派发（Erlang C）", cls="s"))

    p.append(card(824, 422, 400, 152, cls="warnfill", rx=16))
    p.append(txt(848, 454, "这张图只给量级", cls="h"))
    p.append(txt(848, 484, "真实部署落在两列之间；单卡里还有几十个", cls="s"))
    p.append(txt(848, 510, "槽位，比左列更平缓。", cls="s"))
    p.append(f'  <text class="b" x="848" y="548" fill="{WARN}">'
             f'用它定档位，不要用它承诺毫秒数</text>')

    p.append(note(56, 588, 1168, [
        "按负载派发时平均排队几乎为零，余量主要买的是故障、升级、预测误差和突发；"
        "请求被前缀亲和钉在副本上时，排队才回到左列那么陡。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="余量买的是什么",
        desc="左边是一条曲线，横轴卡数从 29 到 45 张，纵轴是一分钟三倍突发的消化时间。"
             "刚好够是 31.7 张，36 张时负载率 0.88、约 13.7 分钟消化完；42 张时 0.76、约 5.2 分钟；"
             "45 张时 0.70、约 3.8 分钟；48 张时 0.66、约 2.9 分钟。右上一张小表对比排队："
             "36、42、48 张时，请求钉在副本上的单副本上界分别是 7.4、3.1、1.9 个 S，"
             "全部卡按负载派发的 Erlang C 只有 0.083、0.005、0.0003 个 S。"
             "右下一块写明这张图只给量级，不承诺毫秒数。",
        kicker="第 26 章 · 26.3",
        heading="加 30% 到 50% 不是口诀，由四件事各要一份",
        sub=f"刚好够 {MINIMUM:.1f} 张；42 张时负载率 0.76，一次突发约 5 分钟消化完",
        body="\n".join(p),
        takeaway="余量买的是出事时少难受一截：故障、升级、预测误差、突发；按负载派发时排队很便宜",
    )


FIGS = [
    ("fig26-01_demand_chain", fig1,
     dict(title="图26-1 从日活到卡数，中间那一步不能省",
          source="26.2、26.3",
          order="先从左栏最上一级往下读到在途条数，再看右上那一步折算，最后看右中两个约束哪个更紧",
          takeaway="链上少一步折算，配出来的卡数就是另一个负载的答案",
          boundary="合成设定，六个乘数和第 19 章那次压测里 10% 的 Prefill 占时都是设定值；链上每一个数由 code/ch26/capacity_cost.py 在构建时算出。换一份负载画像，吞吐和显存哪个先满会反过来，这张图要看的是链的结构和那两步折算，不是这几个具体数字")),
    ("fig26-02_headroom_curve", fig2,
     dict(title="图26-2 余量买的是什么",
          source="26.3",
          order="先看曲线在卡数少时怎么翘起来，再看 31、36、39、41 四个点各要多少分钟消化一次突发，然后读右上那张排队对比，最后读右下那条边界",
          takeaway="余量买的是出事时少难受一截：故障、升级、预测误差、突发；按负载派发时排队很便宜",
          boundary="消化时间按第 20.6 节的积压 ÷ ((1 − ρ) × 满载吞吐) 算；排队两列一个是单副本上界、一个是多服务台下界，真实部署落在中间。落点由 code/ch26/capacity_cost.py 的 margin_table 算出，基数 31.7 张来自 26.3 补上 Prefill 占时之后的那一步")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
