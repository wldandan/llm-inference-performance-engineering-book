"""Build the Chapter 6 figure set defined in strategy/reviews/ch06/storyboard.md.

Run from the repository root:

    python3 content/ch06/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from figkit import (  # noqa: E402
    arrow, bar, card, curve, dashed, hpath, lane, note, page, table, txt,
    vpath, write, write_note,
)

OUT = Path(__file__).parent
SYSTEM = "part02-v1"


def fig1() -> str:
    p = []
    # centre "负载" block
    p.append(card(514, 176, 252, 76, cls="dark", rx=18))
    p.append(txt(640, 212, "负载", cls="hw", anchor="middle"))
    p.append(txt(640, 238, "一个没有定义的词", cls="sw", anchor="middle"))

    groups = [
        (72, "identity", ["名称", "类型 chat / rag / agent", "数据来源"]),
        (368, "length", ["prompt P50 / P90 / P99 / max", "output P50 / P90 / P99 / max", "两侧分开写"]),
        (664, "arrival", ["模式", "速率或并发数", "持续时间与随机种子"]),
        (960, "slo", ["指标", "分位数", "阈值"]),
    ]
    for x, name, items in groups:
        cx = x + 124
        p.append(arrow(640, 252, cx, 316))
        p.append(card(x, 320, 248, 172, cls="card", rx=16))
        p.append(txt(cx, 356, name, cls="mb", anchor="middle"))
        for i, it in enumerate(items):
            p.append(txt(x + 20, 392 + 28 * i, it, cls="s"))

    # agent extra
    p.append(vpath(492, 492, 528, cls="flowb"))
    p.append(card(368, 532, 248, 62, cls="coolfill", rx=14))
    p.append(txt(492, 558, "steps", cls="mb", anchor="middle"))
    p.append(txt(492, 582, "类型是 agent 时必填", cls="s", anchor="middle"))

    # description side vs results side, the latter deliberately empty
    p.append(card(648, 532, 220, 62, cls="soft", rx=14))
    p.append(txt(758, 558, "描述侧", cls="b", anchor="middle"))
    p.append(txt(758, 582, "本章的全部产出", cls="s", anchor="middle"))
    p.append(dashed(888, 528, 888, 598))
    p.append(card(908, 532, 300, 62, cls="soft", rx=14))
    p.append(txt(1058, 558, "结果侧", cls="b", anchor="middle"))
    p.append(txt(1058, 582, "本章不产生任何性能数字", cls="s", anchor="middle"))

    return page(
        system=SYSTEM,
        title="图 6-1 负载要拆成四组字段",
        desc="把“负载”这个词拆成 identity、length、arrival、slo 四组可以写下来的字段，agent 类型另加 steps；右侧标出本章不产生性能数字。",
        kicker="WORKLOAD FIELDS · 06",
        heading="负载要拆成四组字段",
        sub="说“我们的负载是 Chat”只说清了应用形态，四组字段才是能被复现的东西",
        body="\n".join(p),
        takeaway="负载不是一个形容词，是四组能写下来的字段。",
    )


def fig2() -> str:
    p = []
    # closed loop lane
    p.append(lane(72, 168, 1136, 196, "闭环　64 个并发循环发送"))
    p.append(card(104, 214, 168, 66, cls="card", rx=14))
    p.append(txt(188, 244, "客户端", cls="b", anchor="middle"))
    p.append(txt(188, 268, "并发固定 64", cls="s", anchor="middle"))
    p.append(hpath(272, 247, 344))
    p.append(card(344, 214, 150, 66, cls="soft", rx=14))
    p.append(txt(419, 252, "队列 稳定", cls="b", anchor="middle"))
    p.append(hpath(494, 247, 566))
    p.append(card(566, 214, 150, 66, cls="card", rx=14))
    p.append(txt(641, 252, "服务端", cls="b", anchor="middle"))
    p.append(curve(641, 288, 188, 288, 56))
    p.append(txt(415, 344, "响应返回后才发下一个：服务变慢时压力自动变小", cls="s", anchor="middle"))
    p.append(card(792, 206, 384, 84, cls="goodfill", rx=14))
    p.append(txt(816, 240, "TTFT P99 约 300 ms", cls="mb"))
    p.append(txt(816, 268, "五分钟内稳定", cls="s"))

    # open loop lane
    p.append(lane(72, 392, 1136, 218, "开环　固定每秒 40 个"))
    p.append(card(104, 440, 168, 66, cls="card", rx=14))
    p.append(txt(188, 470, "客户端", cls="b", anchor="middle"))
    p.append(txt(188, 494, "速率固定 40/s", cls="s", anchor="middle"))
    p.append(hpath(272, 473, 344))
    qx = 344
    for i, h in enumerate((34, 52, 70, 88)):
        p.append(bar(qx + i * 44, 506 - h, 34, h, cls="badfill"))
    p.append(txt(432, 534, "队列越堆越长", cls="s", anchor="middle"))
    p.append(hpath(528, 473, 566))
    p.append(card(566, 440, 150, 66, cls="card", rx=14))
    p.append(txt(641, 478, "服务端", cls="b", anchor="middle"))
    p.append(txt(641, 572, "没有反馈：请求继续以原速率涌入", cls="s", anchor="middle"))
    p.append(card(792, 432, 384, 84, cls="badfill", rx=14))
    p.append(txt(816, 466, "TTFT P99 约 9 s", cls="mb"))
    p.append(txt(816, 494, "五分钟内升到这里，而且还在涨", cls="s"))
    p.append(txt(984, 556, "漏掉的是最慢的那批：协调遗漏", cls="s", anchor="middle"))
    p.append('  <path class="bracket" d="M1196 290V432"/>')
    p.append('  <path class="bracket" d="M1188 290H1196"/>')
    p.append('  <path class="bracket" d="M1188 432H1196"/>')
    p.append(f'  <text class="b" x="1204" y="366" transform="rotate(90 1204 366)" text-anchor="middle">约 30 倍</text>')

    return page(
        system=SYSTEM,
        title="图 6-3 闭环与开环压的不是同一件事",
        desc="同一个服务、同一份长度分布，闭环 64 并发测出 TTFT P99 约 300 ms，开环每秒 40 个五分钟内升到约 9 秒；闭环有一条从响应返回指回发送的反馈，开环没有。",
        kicker="CLOSED VS OPEN · 06",
        heading="闭环与开环压的不是同一件事",
        sub="两组数字都没错，只是回答了不同的问题（合成设定）；真实用户按自己的节奏提问，对应下面那一行",
        body="\n".join(p),
        takeaway="真实用户是开环的，闭环测不出排队崩溃。",
    )


def fig3() -> str:
    p = []
    base_y = 512
    p.append(txt(72, 186, "prompt token 长度分布", cls="b"))
    # axis
    p.append(f'  <path d="M104 {base_y}H1004" stroke="#94A3B8" stroke-width="1.6" fill="none"/>')
    # right-skewed curve
    p.append(
        '  <path d="M104 512 C 196 512 236 250 320 250 C 404 250 452 400 556 452 '
        'C 660 500 780 504 1004 508" fill="none" stroke="#1D4ED8" stroke-width="2.6"/>'
    )
    marks = [(320, "P50", "180"), (556, "P90", "640"), (836, "P99", "7200"), (972, "max", "12000")]
    for x, label, value in marks:
        p.append(dashed(x, 250 if label == "P50" else 300, x, base_y))
        p.append(txt(x, base_y + 26, label, cls="b", anchor="middle"))
        p.append(txt(x, base_y + 50, value, cls="m", anchor="middle"))
    # mean marker
    p.append(f'  <circle cx="404" cy="{base_y}" r="7" fill="#B45309"/>')
    p.append(txt(404, base_y - 46, "平均值", cls="warn", anchor="middle"))
    p.append(txt(404, base_y - 24, "落在 P50 右边", cls="warn", anchor="middle"))

    # consequences from the tail
    p.append(arrow(880, 300, 1040, 250))
    p.append(card(1040, 214, 168, 72, cls="badfill", rx=14))
    p.append(txt(1124, 246, "显存峰值", cls="b", anchor="middle"))
    p.append(txt(1124, 270, "由这一段决定", cls="s", anchor="middle"))
    p.append(arrow(880, 340, 1040, 380))
    p.append(card(1040, 344, 168, 72, cls="badfill", rx=14))
    p.append(txt(1124, 376, "TTFT 尾部", cls="b", anchor="middle"))
    p.append(txt(1124, 400, "也由这一段决定", cls="s", anchor="middle"))

    p.append(note(72, 574, 700, [
        "只报 P50=180 会得出“上下文很短、没什么压力”；让服务在早高峰 OOM 的是那 1% 的 7200 token",
    ]))
    return page(
        system=SYSTEM,
        title="图 6-2 长度分布的尾巴决定了什么",
        desc="右偏的 prompt 长度分布上标出 P50 180、P90 640、P99 7200、max 12000，平均值落在 P50 右边，显存峰值与 TTFT 尾部都由 P99 那一段决定。",
        kicker="LENGTH TAIL · 06",
        heading="长度分布的尾巴决定了什么",
        sub="长度至少要写四个数：P50、P90、P99 和最大值",
        body="\n".join(p),
        takeaway="决定显存峰值和尾延迟的是 P99，不是平均值。",
    )


def fig4() -> str:
    p = []
    rows = [
        (172, "Chat", "1 次", [("用户输入", 110), ("→ LLM 调用", 118)],
         "对话历史轮次", "平均轮次、每轮增量"),
        (322, "RAG", "1 次", [("用户问题", 110), ("→ 检索", 100), ("→ LLM 调用", 118)],
         "Top-K × 每段长度", "Top-K、片段长度、是否重排"),
        (472, "Agent", "多次，不固定",
         [("任务", 88), ("→ 调用 1", 104), ("→ 调用 2", 120), ("→ …", 136)],
         "累积的工具结果", "步数分布、工具调用比例、重试率"),
    ]
    for y, name, calls, chain, driver, fields in rows:
        p.append(card(72, y, 1136, 124, cls="card", rx=16))
        p.append(txt(96, y + 40, name, cls="h"))
        p.append(txt(96, y + 70, f"一次任务 {calls}", cls="s"))
        p.append(txt(96, y + 96, "LLM 调用", cls="s"))
        x = 272
        for step, w in chain:
            p.append(bar(x, y + 42, w, 40, cls="coolfill"))
            p.append(txt(x + w / 2, y + 68, step, cls="s", anchor="middle"))
            x += w + 14
        p.append(txt(800, y + 38, "输入长度由什么决定", cls="s"))
        p.append(txt(800, y + 66, driver, cls="b"))
        p.append(txt(800, y + 98, f"特有字段　{fields}", cls="s"))
    p.append(txt(640, 618, "Agent 那一行的方块逐级变宽，表示上下文在累积", cls="s", anchor="middle"))
    return page(
        system=SYSTEM,
        title="图 6-4 Chat、RAG、Agent 是三种形状",
        desc="三行对照 Chat、RAG 与 Agent 的调用数、输入长度由什么决定，以及各自的特有字段；Agent 行的输入方块逐级变宽表示上下文累积。",
        kicker="WORKLOAD SHAPES · 06",
        heading="Chat、RAG、Agent 是三种形状",
        sub="前面几节的字段适用于任何负载，但填进去之后三类应用的形状很不一样",
        body="\n".join(p),
        takeaway="Agent 必须在任务层描述，否则连调用数都说不清。",
    )


FIGURES = {
    "fig06-01_workload_fields.svg": (
        fig1,
        dict(title="图 6-1 制作说明：负载要拆成四组字段",
             source="第 6.1 节与 6.7 节。",
             order="先读中间“负载”那个黑块，再顺四条箭头读出四组字段，最后看右下角空着的结果侧。",
             takeaway="负载不是一个形容词，是四组能写下来的字段。",
             boundary="不出现 Queue、Prefill、Decode 等服务端阶段，也不出现任何 TTFT 或吞吐数值。"),
    ),
    "fig06-03_closed_vs_open_loop.svg": (
        fig2,
        dict(title="图 6-3 制作说明：闭环与开环压的不是同一件事",
             source="第 6.3 节，数字与 6.8 案例一同源。",
             order="先读上面闭环那条泳道，注意那条从响应指回发送的反馈线；再读下面开环那条，队列方块逐格变高；最后对比右侧两个结果。",
             takeaway="真实用户是开环的，闭环测不出排队崩溃。",
             boundary="不画引擎内部的调度机制（属于第 20 章）；协调遗漏只标一句“漏掉的是最慢的那批”，完整解释在正文引用块。"),
    ),
    "fig06-02_length_tail.svg": (
        fig3,
        dict(title="图 6-2 制作说明：长度分布的尾巴决定了什么",
             source="第 6.2 节。",
             order="先看曲线的右偏形状，再读四个分位数标记，然后注意平均值那个点落在 P50 右边，最后顺两条箭头读尾部的两个后果。",
             takeaway="决定显存峰值和尾延迟的是 P99，不是平均值。",
             boundary="不给显存数值，也不展开 KV Cache 的容量算法（属于第 16 章）。"),
    ),
    "fig06-04_three_workload_shapes.svg": (
        fig4,
        dict(title="图 6-4 制作说明：Chat、RAG、Agent 是三种形状",
             source="第 6.5 节。",
             order="逐行读，每行从左到右是名称、调用链、输入长度的决定因素与特有字段；注意 Agent 行方块宽度递增。",
             takeaway="Agent 必须在任务层描述，否则连调用数都说不清。",
             boundary="不讲检索算法与 Agent 规划机制，也不给第 12、23、24 章的成本公式。"),
    ),
}


def main() -> None:
    for name, (fn, meta) in FIGURES.items():
        write(OUT, name, fn())
        write_note(OUT, name[:-4], **meta)
        print("wrote", name)


if __name__ == "__main__":
    main()
