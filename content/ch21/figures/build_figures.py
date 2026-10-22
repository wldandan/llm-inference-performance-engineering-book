"""Build the Chapter 21 figure set defined in strategy/reviews/ch21/storyboard.md.

Every number drawn here is recomputed at build time from
code/ch21/overload_drill.py and the two synthetic drills in
content/ch21/evidence/, so the figures cannot drift away from the text.

  fig21-01  21.1's two shapes, drawn as the two goodput curves the repository's
            pair of drills actually produced.
  fig21-02  21.1's map: where the five controls sit on one request's path, and
            the three constraints between them.
  fig21-03  21.3's four timeout layers, placed on the request timeline.
  fig21-04  21.5's amplifier, walked four rounds the way 案例一 does.

Run from the repository root:

    python3 content/ch21/figures/build_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch21"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, card, curve, dashed, hpath, lane, note, page, txt,
    write, write_note,
)
import overload_drill as od  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"
MUTED_LINE = "#94A3B8"

EVIDENCE = ROOT / "content" / "ch21" / "evidence"
NO_ADM = json.loads((EVIDENCE / "overload-drill-no-admission.json")
                    .read_text(encoding="utf-8"))
WITH_ADM = json.loads((EVIDENCE / "overload-drill-with-admission.json")
                      .read_text(encoding="utf-8"))
READ_NO = od.analyze(NO_ADM)
READ_WITH = od.analyze(WITH_ADM)

# 案例一 那四轮：失败率是设定，放大系数和可用性由代码算。
LOOP = od.retry_loop([0.04, 0.15, 0.40, 0.73], retries=3)


# --- 图21-1 两种垮法 --------------------------------------------------------

def fig1() -> str:
    p = [card(72, 176, 1136, 372, cls="card", rx=16)]
    p.append(txt(96, 208, "同一份负载、同一个容量，只差有没有准入（合成演练）",
                 cls="b"))

    offered = [s["offered_qps"] for s in NO_ADM["steps"]]
    capacity = NO_ADM["capacity_qps"]
    x0, x1 = 216, 700
    y0, y1 = 250, 466
    top = 14.0

    def gx(q: float) -> float:
        return x0 + (q - offered[0]) / (offered[-1] - offered[0]) * (x1 - x0)

    def gy(v: float) -> float:
        return y1 - min(v, top) / top * (y1 - y0)

    p.append(f'  <path d="M{x0} {y0}V{y1}H{x1}" fill="none" '
             f'stroke="{MUTED_LINE}" stroke-width="1.6"/>')
    p.append(txt(x0 - 12, gy(12) + 5, "12", cls="s", anchor="end"))
    p.append(txt(x0 - 12, gy(6) + 5, "6", cls="s", anchor="end"))
    p.append(txt(120, 240, "Goodput（QPS）", cls="b"))

    # 容量那条线
    p.append(dashed(gx(capacity), y0, gx(capacity), y1))
    p.append(txt(gx(capacity) + 8, y0 + 18, f"容量 {capacity:.0f} QPS", cls="s"))

    for doc, reading, colour, label, dy in (
            (WITH_ADM, READ_WITH, GOOD, "有准入", -16),
            (NO_ADM, READ_NO, BAD, "没有准入", 24)):
        pts = " ".join(
            f"{gx(s['offered_qps']):.0f},{gy(s['goodput']):.0f}"
            for s in doc["steps"])
        p.append(f'  <polyline points="{pts}" fill="none" stroke="{colour}" '
                 f'stroke-width="3.2"/>')
        for s in doc["steps"]:
            p.append(f'  <circle cx="{gx(s["offered_qps"]):.0f}" '
                     f'cy="{gy(s["goodput"]):.0f}" r="5" fill="{colour}"/>')
        last = doc["steps"][-1]
        p.append(txt(gx(last["offered_qps"]) + 4, gy(last["goodput"]) + dy,
                     f"{label} {last['goodput']:.1f}", cls="b", anchor="end"))

    for s in NO_ADM["steps"]:
        p.append(txt(gx(s["offered_qps"]), y1 + 26,
                     f"{s['offered_qps']:.0f}", cls="s", anchor="middle"))
    p.append(txt(112, y1 + 26, "施加的 QPS", cls="s"))
    p.append(txt(120, y1 + 52,
                 f"末档 36 QPS：有准入保住峰值的 "
                 f"{READ_WITH['goodput_retained'] * 100:.1f}%，"
                 f"没有准入只剩 {READ_NO['goodput_retained'] * 100:.1f}%", cls="b"))

    p.append(card(744, 240, 440, 120, cls="goodfill", rx=14))
    p.append(txt(766, 272, "B  部分拒绝", cls="h"))
    p.append(txt(766, 302, "超出容量的请求立即被拒", cls="s"))
    p.append(txt(766, 328,
                 f"被接受的请求延迟正常，末档拒掉 "
                 f"{READ_WITH['rejected_final_qps']:.1f} QPS", cls="s"))

    p.append(card(744, 380, 440, 140, cls="badfill", rx=14))
    p.append(txt(766, 412, "A  全部接受", cls="h"))
    p.append(txt(766, 442, "队列越堆越长，延迟一起劣化", cls="s"))
    p.append(txt(766, 468, "最终全员超时，一个都没成功", cls="s"))
    p.append(txt(766, 494, "而且失败得很慢，用户要等到超时才知道", cls="s"))

    p.append(note(72, 564, 1136, [
        "数据出自 content/ch21/evidence/ 那两份合成演练，不是真机结果。"
        "要看的是两条曲线在过容量之后分道扬镳这件事，不是这几个具体数字。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="过载时的两种垮法：部分拒绝与全员失败",
        desc="一张折线图，横轴是施加的请求速率从 6 到 36 QPS，纵轴是 Goodput。竖虚线标出 "
             "12 QPS 的容量。绿色曲线是有准入的那一版，过容量之后一直保持在 11 QPS 上下；"
             "红色曲线是没有准入的那一版，过容量后一路掉到 2.1。右侧两块分别说明这两种"
             "形状对应 21.1 里的 B 和 A。",
        kicker="第 21 章 · 21.1、21.8",
        heading="容量总有被超过的一天，问题是超过之后什么样",
        sub="A 把“一部分用户失败”变成了“所有用户失败”，而且失败得很慢",
        body="\n".join(p),
        takeaway="健康的形状是过容量后 Goodput 保持平稳、多余流量被拒，不是一起掉下去",
    )


# --- 图21-2 五项治理的位置和约束 ---------------------------------------------

def fig_controls() -> str:
    p = [lane(72, 150, 236, 320, "上游"), lane(324, 150, 884, 320, "服务端")]

    # 一条请求的去路
    y, h = 248, 60
    stations = [
        (96, 200, "客户端 / 编排层", "card", "h"),
        (360, 200, "网关入口", "card", "h"),
        (624, 200, "Waiting 队列", "card", "h"),
        (888, 296, "Running：在 GPU 上生成", "dark", "hw"),
    ]
    for x, w, label, cls, tcls in stations:
        p.append(card(x, y, w, h, cls=cls, rx=14))
        p.append(txt(x + w / 2, y + 37, label, cls=tcls, anchor="middle"))
    for xa, xb in ((296, 360), (560, 624), (824, 888)):
        p.append(hpath(xa, y + h / 2, xb - 4))

    # 两条往回走的信号：失败回到上游，余量告诉上游
    p.append(curve(1036, y, 156, y, -136))
    p.append(txt(600, 216, "余量信号：服务端把还剩多少告诉上游", cls="s",
                 anchor="middle"))
    p.append(curve(452, y, 236, y, -60))
    p.append(txt(374, 242, "失败或 429", cls="s", anchor="middle"))

    # 五项各挂在哪
    def chip(x, w, top, cls, name, line):
        p.append(card(x, top, w, 64, cls=cls, rx=12))
        p.append(txt(x + 16, top + 27, name, cls="b"))
        p.append(txt(x + 16, top + 51, line, cls="s"))

    chip(96, 200, 324, "badfill", "④ 重试", "把失败变成新的到达")
    chip(96, 200, 396, "soft", "⑤ 背压", "按余量信号自己降速")
    chip(360, 200, 324, "goodfill", "① 准入", "没余量就当场 429")
    chip(624, 560, 324, "coolfill", "② 超时",
         "排队、首包、流间隔，每段等待各有上限（细分见图 21-3）")
    chip(888, 296, 396, "warnfill", "③ 取消", "断开信号传到引擎，KV 立即释放")

    # 三条约束
    rules = [
        (72, "warnfill", "② 超时 + ③ 取消", "超时不配取消",
         ["请求在客户端那边已经放弃了", "GPU 还在替它算，KV 也不释放"]),
        (460, "badfill", "② 超时 + ④ 重试", "超时配上不加约束的重试",
         ["每次超时都变成一次新的到达", "到达按 1 + p + p² + … 放大"]),
        (848, "coolfill", "① 准入 和 ⑤ 背压", "用错对象",
         ["准入拒绝一部分，背压让所有请求慢一点", "对能降速的上游硬拒，会触发它的重试"]),
    ]
    for x, cls, tag, head, lines in rules:
        p.append(card(x, 486, 360, 142, cls=cls, rx=14))
        p.append(txt(x + 20, 514, tag, cls="s"))
        p.append(txt(x + 20, 546, head, cls="h"))
        for i, line in enumerate(lines):
            p.append(txt(x + 20, 580 + 28 * i, line, cls="s"))

    return page(
        system=SYSTEM,
        title="五项治理在请求路径上的位置和三条约束",
        desc="上半部分是一条请求从上游经过网关入口、Waiting 队列，到 GPU 上 Running "
             "的路径。准入挂在入口，超时覆盖排队和生成的每一段，取消在 GPU 上释放 KV，"
             "重试和背压都在上游：两条虚线弧从服务端绕回上游，一条是失败或 429，一条是"
             "余量信号。下半部分三块写出它们之间的约束：超时不配取消、超时配上不加约束的"
             "重试、准入和背压用错对象。",
        kicker="第 21 章 · 21.1 至 21.6",
        heading="五项治理挂在一条请求路径的不同位置",
        sub="单独调好任何一项都不够，它们之间有三条约束",
        body="\n".join(p),
        takeaway="超时要配取消，重试要有纪律，准入和背压要认清对象",
    )


# --- 图21-4 重试回路 --------------------------------------------------------

def fig2() -> str:
    p = [card(72, 176, 700, 372, cls="card", rx=16)]
    p.append(txt(96, 208, "三次重试，四轮把 4% 推成 73%", cls="b"))

    rows = LOOP["rounds"]
    x0 = 120
    col = [0, 150, 320, 500]
    heads = ["轮次", "这一轮的 p", "放大 1+p+p²+p³", "下一轮的负载"]
    for cx, head in zip(col, heads):
        p.append(txt(x0 + cx, 246, head, cls="b"))
    p.append(f'  <path d="M{x0} 258H740" class="divider"/>')
    y = 288
    for i, row in enumerate(rows):
        colour = (GOOD, WARN, WARN, BAD)[i]
        p.append(f'  <rect x="{x0 - 16}" y="{y - 24}" width="656" height="46" '
                 f'rx="10" fill="{colour}" opacity="0.07"/>')
        p.append(txt(x0 + col[0], y + 6, f"第 {row['round']} 轮", cls="b"))
        p.append(f'  <text class="b" x="{x0 + col[1]}" y="{y + 6}" '
                 f'fill="{colour}">{row["failure_rate"] * 100:.0f}%</text>')
        p.append(txt(x0 + col[2], y + 6, f"{row['amplification']:.2f}", cls="m"))
        p.append(txt(x0 + col[3], y + 6, f"{row['next_load']:.2f} 倍", cls="m"))
        y += 56
    p.append(txt(96, 516, "没有任何一轮是负载翻了三倍，是四轮叠出来的", cls="b"))

    # 回路示意
    p.append(card(796, 176, 412, 372, cls="card", rx=16))
    p.append(txt(820, 208, "回路是这样转起来的", cls="b"))
    nodes = [
        (836, 236, "系统过载", "warnfill"),
        (836, 306, "请求超时", "warnfill"),
        (836, 376, "客户端重试", "badfill"),
        (836, 446, "负载上升，p 更高", "badfill"),
    ]
    for x, y2, label, cls in nodes:
        p.append(card(x, y2, 250, 52, cls=cls, rx=12))
        p.append(txt(x + 18, y2 + 32, label, cls="b"))
    for y2 in (288, 358, 428):
        p.append(f'  <path class="flow" d="M961 {y2}V{y2 + 14}"/>')
    p.append('  <path class="feedback" d="M1086 472Q1156 472 1156 262'
             'Q1156 236 1110 236"/>')
    p.append(txt(820, 530, "p 不是常数，它是负载的函数", cls="good"))

    p.append(card(72, 564, 1136, 64, cls="badfill", rx=14))
    p.append(txt(96, 600,
                 f"终点那个 {LOOP['final_failure_rate'] * 100:.0f}% 和开头那个 "
                 f"99.5% 掉到 71% 对得上："
                 f"一条请求最多试 {LOOP['attempts_per_request']} 次，"
                 f"{LOOP['final_failure_rate']:.2f} 的 "
                 f"{LOOP['attempts_per_request']} 次方是 "
                 f"{LOOP['user_visible_failure_rate'] * 100:.1f}%，"
                 f"可用性 {LOOP['availability'] * 100:.1f}%", cls="b"))

    return page(
        system=SYSTEM,
        title="重试把 4% 的失败推成 73%",
        desc="左边是一张四行的表，第 0 轮失败率 4%、放大系数 1.04，第 1 轮 15%、1.18，"
             "第 2 轮 40%、1.62，第 3 轮 73%、2.65，行的底色从绿到红。右边是一个四节点的"
             "环：系统过载、请求超时、客户端重试、负载上升，一条虚线从最后一个节点绕回第一个，"
             "标注“p 不是常数，它是负载的函数”。底部说明终点的 73% 与案例里 71% 的可用性"
             "是同一个数的两种表现。",
        kicker="第 21 章 · 21.5、21.9",
        heading="雪崩不是某个组件坏了，是这个回路自己跑起来了",
        sub="放大系数 1 + p + … + p^r，而 p 每一轮都被上一轮推上去",
        body="\n".join(p),
        takeaway="第 0 轮那 4% 的额外流量看起来完全无害，而它正是把 p 从 4% 推到 15% 的那一下",
    )


# --- 图21-3 分层超时 --------------------------------------------------------

def fig3() -> str:
    p = [card(72, 176, 1136, 340, cls="card", rx=16)]
    p.append(txt(96, 208, "一条请求的时间线，和管着它的四个超时", cls="b"))

    x0, x1 = 176, 872
    segs = [
        ("排队", 0.16, "soft"),
        ("Prefill", 0.14, "coolfill"),
        ("生成第 1 个 token 之后逐个吐", 0.70, "goodfill"),
    ]
    x = x0
    for label, frac, cls in segs:
        w = (x1 - x0) * frac
        p.append(card(x, 240, w, 56, cls=cls, rx=12))
        p.append(txt(x + 16, 274, label, cls="b"))
        x += w
    p.append(txt(x0, 322, "到达", cls="s"))
    p.append(txt(x0 + (x1 - x0) * 0.16, 322, "进 Running", cls="s"))
    p.append(txt(x0 + (x1 - x0) * 0.30, 322, "第 1 个 token", cls="s"))
    p.append(txt(x1, 322, "结束", cls="s", anchor="end"))

    bars = [
        ("排队超时", 0.0, 0.16, "超了说明系统过载，该拒绝", COOL, 356),
        ("首包超时", 0.16, 0.30, "超了说明 Prefill 异常", GOOD, 392),
        ("流间隔超时", 0.30, 1.0, "超了说明卡住或被抢占", WARN, 428),
        ("总超时", 0.0, 1.0, "兜底，设得很宽松", MUTED_LINE, 464),
    ]
    for name, a, b, why, colour, y in bars:
        xa = x0 + (x1 - x0) * a
        xb = x0 + (x1 - x0) * b
        p.append(f'  <rect x="{xa:.0f}" y="{y - 12}" width="{xb - xa:.0f}" '
                 f'height="18" rx="6" fill="{colour}" opacity="0.30"/>')
        p.append(f'  <path d="M{xa:.0f} {y - 16}V{y + 10}" stroke="{colour}" '
                 f'stroke-width="2.4"/>')
        p.append(f'  <path d="M{xb:.0f} {y - 16}V{y + 10}" stroke="{colour}" '
                 f'stroke-width="2.4"/>')
        p.append(txt(96, y + 3, name, cls="b"))
        p.append(txt(x1 + 24, y + 3, why, cls="s"))
    p.append(txt(96, 502, "前三个才是真正有用的：各自能定位到一个原因，"
                          "而总超时只能告诉你“慢”", cls="b"))

    p.append(card(72, 524, 552, 104, cls="warnfill", rx=14))
    p.append(txt(92, 556, "为什么不能照搬普通 HTTP 服务那一套", cls="b"))
    p.append(txt(92, 584, "生成 50 个和 2000 个 token，耗时差四十倍", cls="s"))
    p.append(txt(92, 610, "一个固定的总超时要么砍长请求，要么对短请求形同虚设",
                 cls="s"))

    p.append(card(656, 524, 552, 104, cls="coolfill", rx=14))
    p.append(txt(676, 556, "流间隔超时的阈值参考抢占的恢复时间", cls="b"))
    p.append(txt(676, 584, "第 16 章说过抢占后要重算 Prefill，可能是几秒", cls="s"))
    p.append(txt(676, 610, "阈值设得比它短，会把正常恢复中的请求误杀", cls="s"))

    return page(
        system=SYSTEM,
        title="LLM 服务需要分层的超时，不是一个总超时",
        desc="上方是一条请求的时间线，分成排队、Prefill、逐个吐 token 三段。下方四条横杠"
             "分别覆盖时间线的不同区间：排队超时只覆盖排队段，首包超时覆盖到第一个 token，"
             "流间隔超时覆盖生成段，总超时覆盖全程。每条横杠旁写明它超了意味着什么。下方"
             "两块分别说明为什么不能照搬普通服务的做法，以及流间隔超时的阈值怎么定。",
        kicker="第 21 章 · 21.3",
        heading="四个超时各管一段，各自对应一个原因",
        sub="总超时只能告诉你“慢”，不能告诉你慢在哪",
        body="\n".join(p),
        takeaway="排队超时对应准入，首包超时对应 Prefill 异常，流间隔超时对应抢占；前三个才真正有用",
    )


FIGS = [
    ("fig21-01_two_collapse_shapes", fig1,
     dict(title="图21-1 过载时的两种垮法：部分拒绝与全员失败",
          source="21.1、21.8",
          order="先找到那条竖虚线标的容量，再看两条曲线过了它之后分别往哪走，最后看右侧两块对应 21.1 里的 A 和 B",
          takeaway="健康的形状是过容量后 Goodput 保持平稳、多余流量被拒，不是一起掉下去",
          boundary="数据出自 content/ch21/evidence/ 那两份合成演练，不是真机结果；两份的 offered_qps、容量和 SLO 逐项相同，只差有没有准入，否则这个对比不成立")),
    ("fig21-02_five_controls_on_path", fig_controls,
     dict(title="图21-2 五项治理在请求路径上的位置",
          source="21.1",
          order="先沿上方的路径从左往右走一遍，再看下面五块各挂在哪一站，然后看两条虚线弧怎样从服务端绕回上游，最后读下方三条约束各牵涉哪两项",
          takeaway="超时要配取消，重试要有纪律，准入和背压要认清对象",
          boundary="这是位置示意，不画时间比例，也不给任何阈值；五项各自的取值和验证在 21.2 至 21.6，过载演练在 21.8")),
    ("fig21-03_layered_timeouts", fig3,
     dict(title="图21-3 LLM 服务需要分层的超时",
          source="21.3",
          order="先看上方时间线的三段，再看下方四条横杠各自覆盖哪一段，然后读每条超了意味着什么，最后看下方两块的前提和阈值来源",
          takeaway="排队超时对应准入，首包超时对应 Prefill 异常，流间隔超时对应抢占；前三个才真正有用",
          boundary="时间线各段的宽度是示意，不是某次实测的比例；四个超时的具体阈值取决于负载的长度分布，这张图只给它们各自管哪一段")),
    ("fig21-04_retry_loop", fig2,
     dict(title="图21-4 重试把 4% 的失败推成 73%",
          source="21.5、21.9 案例一",
          order="先从上往下读左边那四行，注意第 0 轮的放大系数只有 1.04，再看右边那个环怎么把上一轮的结果变成下一轮的输入，最后看底部那句把 73% 和 71% 连起来的话",
          takeaway="第 0 轮那 4% 的额外流量看起来完全无害，而它正是把 p 从 4% 推到 15% 的那一下",
          boundary="四轮的失败率是合成设定，放大系数和可用性由 code/ch21/overload_drill.py 算出；放大系数按各次独立失败的精确式算，速记的 1 + p·r 是它的上界；单看一轮的式子会低估雪崩，因为它漏掉的是 p 被负载一轮轮推高的回路，这张表走的正是这个回路")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
