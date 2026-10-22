"""Build the Chapter 8 figure set defined in strategy/reviews/ch08/storyboard.md.

Run from the repository root:

    python3 content/ch08/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    arrow, bar, card, dashed, hpath, note, page, txt, vpath, write, write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"


def fig1() -> str:
    p = []
    cols = [
        ("指标 Metrics", "按时间聚合的数值",
         ["现在是否异常", "趋势如何", "容量还剩多少"],
         ["具体是哪条请求", "为什么慢"]),
        ("日志 Logs", "单条事件记录",
         ["这一条发生了什么", "报了什么错"],
         ["整体趋势", "跨组件的先后关系"]),
        ("链路 Traces", "一次调用跨组件的时间线",
         ["时间花在哪一段", "哪个下游拖慢了"],
         ["长期趋势", "罕见事件的统计"]),
    ]
    x = 72
    for name, what, good, bad in cols:
        p.append(card(x, 172, 356, 282, cls="card", rx=16))
        p.append(txt(x + 24, 210, name, cls="h"))
        p.append(txt(x + 24, 238, what, cls="s"))
        p.append(f'  <path d="M{x + 12} 256H{x + 344}" class="divider"/>')
        p.append(txt(x + 24, 286, "擅长回答", cls="b"))
        for i, g in enumerate(good):
            p.append(txt(x + 24, 314 + 26 * i, "· " + g, cls="good"))
        p.append(txt(x + 24, 396, "回答不了", cls="b"))
        for i, b in enumerate(bad):
            p.append(txt(x + 24, 424 + 26 * i, "· " + b, cls="bad"))
        x += 380

    # forbidden label on the metrics column
    p.append(card(72, 476, 356, 52, cls="badfill", rx=12))
    p.append(txt(96, 508, "不要把高基数字段放进标签", cls="bad"))

    # relay at the bottom
    p.append(txt(72, 570, "三者是接力，不是三选一", cls="b"))
    steps = [("用指标确认问题与范围", 300), ("用日志或 Trace 定位具体请求", 360), ("回到指标验证修复", 280)]
    x = 72
    for i, (label, w) in enumerate(steps):
        p.append(bar(x, 586, w, 42, cls="soft"))
        p.append(txt(x + w / 2, 613, label, cls="s", anchor="middle"))
        if i < len(steps) - 1:
            p.append(hpath(x + w + 4, 607, x + w + 36))
        x += w + 40
    return page(
        system=SYSTEM,
        title="图 8-1 三种数据各自能回答什么",
        desc="指标、日志与链路三列并置，各自列出擅长回答与回答不了的问题；底部一条接力箭头串起指标确认范围、日志或 Trace 定位请求、回到指标验证修复。",
        kicker="THREE DATA KINDS · 08",
        heading="三种数据各自能回答什么",
        sub="搞混了就会拿错工具：只看日志把个例当普遍，只看指标永远停在“确实慢了”",
        body="\n".join(p),
        takeaway="三者是接力，不是三选一。",
    )


def fig2() -> str:
    p = []
    p.append(card(72, 196, 300, 168, cls="card", rx=16))
    p.append(txt(222, 236, "客户端", cls="h", anchor="middle"))
    p.append(txt(222, 272, "生成 req-8a3f", cls="m", anchor="middle"))
    p.append(txt(222, 304, "记录它", cls="s", anchor="middle"))
    p.append(txt(222, 336, "投诉时能直接报出来", cls="s", anchor="middle"))

    p.append(card(756, 196, 300, 168, cls="card", rx=16))
    p.append(txt(906, 236, "服务端", cls="h", anchor="middle"))
    p.append(txt(906, 272, "读到就沿用", cls="s", anchor="middle"))
    p.append(txt(906, 304, "读不到才自己生成", cls="s", anchor="middle"))
    p.append(txt(906, 336, "并校验格式与重复", cls="s", anchor="middle"))

    p.append(hpath(372, 248, 748))
    p.append(txt(560, 232, "请求头带 req-8a3f", cls="m", anchor="middle"))
    p.append(f'  <path class="flow" d="M756 316H376"/>')
    p.append(txt(560, 300, "响应头回带同一个 ID", cls="m", anchor="middle"))

    # five landing points
    p.append(txt(72, 420, "这个 ID 要出现在五个地方", cls="b"))
    spots = [
        ("客户端调用记录", "goodfill"),
        ("服务端入口日志", "goodfill"),
        ("引擎请求级指标", "goodfill"),
        ("出错时的错误日志", "goodfill"),
        ("Trace 里对应的 Span", "goodfill"),
    ]
    x = 72
    for name, cls in spots:
        p.append(card(x, 442, 212, 62, cls=cls, rx=14))
        p.append(txt(x + 106, 480, name, cls="s", anchor="middle"))
        x += 232

    p.append(card(72, 528, 668, 76, cls="badfill", rx=14))
    p.append(txt(96, 562, "第六个地方：指标标签", cls="bad"))
    p.append(txt(96, 590, "不要放。每条请求一条新时间序列，监控系统会被打垮", cls="s"))
    p.append(note(764, 528, 444, [
        "判据：会不会出现“没有响应但需要追踪”",
        "会就客户端生成，不会就服务端生成",
    ]))
    return page(
        system=SYSTEM,
        title="图 8-2 一个 ID 要出现在哪五个地方",
        desc="客户端生成 ID 经请求头传给服务端、服务端沿用并在响应头回带；这个 ID 要出现在客户端记录、入口日志、请求级指标、错误日志与 Trace 里对应的 Span 五处，唯独不能进指标标签。",
        kicker="REQUEST ID · 08",
        heading="一个 ID 要出现在哪五个地方",
        sub="三种数据要能互相走通，前提是它们记的是同一条请求",
        body="\n".join(p),
        takeaway="客户端必须最终拿到并记下这个 ID，否则投诉时无从查起。",
    )


def fig3() -> str:
    p = []
    p.append(txt(72, 186, "Trace: rag-query-7c2e", cls="mb"))
    total = 2400
    x0, wmax = 360, 760

    def w(ms):
        return ms / total * wmax

    rows = [
        (0, "assemble-prompt", 10, 0, "soft"),
        (0, "retrieve", 180, 10, "coolfill"),
        (0, "rerank", 90, 190, "coolfill"),
        (0, "llm-call", 2120, 280, "coolfill"),
        (1, "queue", 900, 280, "badfill"),
        (1, "scheduled-to-first-token", 140, 1180, "coolfill"),
        (1, "generation", 1080, 1320, "coolfill"),
    ]
    y = 216
    for depth, name, ms, start, cls in rows:
        indent = 0 if depth == 0 else 28
        p.append(txt(96 + indent, y + 26, name, cls="m"))
        p.append(bar(x0 + w(start), y + 6, max(w(ms), 3), 30, cls=cls))
        p.append(txt(x0 + w(start) + max(w(ms), 3) + 12, y + 27, f"{ms} ms", cls="m"))
        if name == "queue":
            p.append(txt(x0 + w(start) + w(ms) / 2, y + 27, "时间在这", cls="bad", anchor="middle"))
        y += 46
    # total bracket
    p.append(f'  <path class="bracket" d="M{x0} 202H{x0 + wmax}"/>')
    p.append(f'  <path class="bracket" d="M{x0} 202V210"/>')
    p.append(f'  <path class="bracket" d="M{x0 + wmax} 202V210"/>')
    p.append(txt(x0 + wmax / 2, 196, "总计 2400 ms", cls="b", anchor="middle"))

    p.append(note(72, 546, 1136, [
        "只看总时长 2400 ms 得不出“在排队”这个结论；只看 LLM 服务的指标也得不出来，因为那里看不到检索和重排",
        "span 的边界同样取决于埋点位置：Trace 让时间线直观，不会自动让边界可信",
    ]))
    return page(
        system=SYSTEM,
        title="图 8-3 一次 RAG 调用的 Trace 树",
        desc="一棵 Trace 树：总计 2400 ms，assemble-prompt 10、retrieve 180、rerank 90、llm-call 2120，其中 queue 900、scheduled-to-first-token 140、generation 1080，排队那一段被标出。",
        kicker="TRACE TREE · 08",
        heading="一次 RAG 调用的 Trace 树",
        sub="慢不在检索，也不在模型计算，而在排队",
        body="\n".join(p),
        takeaway="只看总时长 2400 ms 得不出“在排队”这个结论。",
    )


def fig4() -> str:
    p = []
    x0, wmax = 200, 900
    span = 9.6

    def px(sec):
        return x0 + sec / span * wmax

    # client timeline
    p.append(txt(72, 190, "客户端一次操作", cls="b"))
    p.append(txt(72, 216, "9.48 s", cls="mb"))
    segs = [
        (0.0, 3.0, "尝试 1 · 被取消", "badfill"),
        (3.0, 1.0, "退避", "warnfill"),
        (4.0, 3.0, "尝试 2 · 被取消", "badfill"),
        (7.0, 2.0, "退避", "warnfill"),
        (9.0, 0.48, "尝试 3 · 成功", "goodfill"),
    ]
    for start, dur, label, cls in segs:
        p.append(bar(px(start), 236, px(start + dur) - px(start), 48, cls=cls))
        if dur >= 0.9:
            p.append(txt((px(start) + px(start + dur)) / 2, 266, label, cls="s", anchor="middle"))
    p.append(txt(px(9.24), 310, "尝试 3", cls="s", anchor="middle"))
    p.append(txt(px(9.24), 332, "成功 480 ms", cls="s", anchor="middle"))
    # shared wall-clock axis
    p.append(f'  <path d="M{x0} 352H{x0 + wmax}" stroke="#94A3B8" stroke-width="1.4" fill="none"/>')
    for sec in (0, 3, 6, 9):
        p.append(f'  <path d="M{px(sec)} 352V358" stroke="#94A3B8" stroke-width="1.4"/>')
        p.append(txt(px(sec), 374, f"{sec} s", cls="s", anchor="middle"))

    # server records
    p.append(txt(72, 412, "服务端记录", cls="b"))
    p.append(txt(72, 438, "三条", cls="s"))
    recs = [
        (0.0, 3.0, "cancelled", "badfill"),
        (4.0, 3.0, "cancelled", "badfill"),
        (9.0, 0.48, "finished 480 ms", "goodfill"),
    ]
    for start, dur, label, cls in recs:
        p.append(bar(px(start), 400, px(start + dur) - px(start), 44, cls=cls))
        if dur >= 0.9:
            p.append(txt((px(start) + px(start + dur)) / 2, 428, label, cls="s", anchor="middle"))
    p.append(txt(px(9.24), 466, "finished", cls="s", anchor="middle"))
    p.append(txt(px(0.0) + 6, 466, "按“成功返回耗时”筛日志，只有最右边那条会出现", cls="s"))

    # decomposition
    p.append(card(72, 482, 1136, 124, cls="card", rx=16))
    p.append(txt(96, 518, "差值 9.00 s 拆开", cls="b"))
    items = [
        ("两次被取消的尝试", "3.0 + 3.0 = 6.0 s", "服务端有记录，终态是 cancelled", "badfill"),
        ("两次退避等待", "1.0 + 2.0 = 3.0 s", "只有客户端有记录", "warnfill"),
        ("余下", "0 s", "拆完一分不剩，痕迹是齐的", "goodfill"),
    ]
    x = 300
    for name, value, why, cls in items:
        p.append(card(x, 498, 290, 92, cls=cls, rx=12))
        p.append(txt(x + 16, 528, name, cls="b"))
        p.append(txt(x + 16, 556, value, cls="m"))
        p.append(txt(x + 16, 580, why, cls="s"))
        x += 304
    p.append(txt(96, 552, "客户端 9.48 s", cls="m"))
    p.append(txt(96, 578, "服务端 0.48 s", cls="m"))
    return page(
        system=SYSTEM,
        title="图 8-4 客户端与服务端的差值要拆，不要命名",
        desc="客户端一次 9.48 秒的操作对应服务端三条请求（两条 cancelled、一条 480 ms 成功），9.00 秒的差值拆成两次取消尝试 6.0 秒与两次退避 3.0 秒，余下为零。",
        kicker="CLIENT VS SERVER · 08",
        heading="客户端与服务端的差值要拆，不要命名",
        sub="差值不是一个待命名的数，是一个待拆的数",
        body="\n".join(p),
        takeaway="拆不完时剩下的写未归因，不写网络耗时。",
    )


FIGURES = {
    "fig08-01_three_data_kinds.svg": (
        fig1,
        dict(title="图 8-1 制作说明：三种数据各自能回答什么",
             source="第 8.2 节。",
             order="先横着读三列的“擅长回答”，再读“回答不了”，最后读底部那条接力箭头。",
             takeaway="三者是接力，不是三选一。",
             boundary="不出现具体监控产品名；高基数的序列数算例在正文，图上只留一句禁止。"),
    ),
    "fig08-02_request_id_path.svg": (
        fig2,
        dict(title="图 8-2 制作说明：一个 ID 要出现在哪五个地方",
             source="第 8.3 节。",
             order="先看上方客户端与服务端之间一来一回的两条箭头，再看中间那五个落点，最后读左下角被标红的第六个地方。",
             takeaway="客户端必须最终拿到并记下这个 ID，否则投诉时无从查起。",
             boundary="不画引擎内部的请求状态机（属于第 2 章）。"),
    ),
    "fig08-03_trace_tree.svg": (
        fig3,
        dict(title="图 8-3 制作说明：一次 RAG 调用的 Trace 树",
             source="第 8.4 节。",
             order="先看顶部总计 2400 ms 的括号，再从上到下读四个一级 span，最后展开 llm-call 里那三段，注意被标红的 queue。",
             takeaway="只看总时长 2400 ms 得不出“在排队”这个结论。",
             boundary="不把 scheduled-to-first-token 写成 TTFT；不暗示 span 边界天然可信。"),
    ),
    "fig08-04_client_server_gap.svg": (
        fig4,
        dict(title="图 8-4 制作说明：客户端与服务端的差值要拆，不要命名",
             source="第 8.6 节与 8.8 案例一。",
             order="先读上面客户端那条 9.48 秒的时间线，再看下面服务端只有三条记录且两条是 cancelled，最后读底部差值的三段拆解。",
             takeaway="拆不完时剩下的写未归因，不写网络耗时。",
             boundary="不给未归因那一段起任何名字。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
