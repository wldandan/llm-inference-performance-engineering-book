"""Build the Chapter 1 figure set defined in strategy/reviews/ch01/storyboard.md.

The script only emits SVG text; it does not fetch anything and does not embed
performance conclusions. Run it from the repository root:

    python3 content/ch01/figures/build_figures.py
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).parent

STYLE = """
    text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
    .k{font-size:14px;font-weight:700;letter-spacing:2px;fill:#64748B}
    .t{font-size:32px;font-weight:750}
    .sub{font-size:16px;fill:#64748B}
    .card{fill:#FFFFFF;stroke:#CBD5E1;stroke-width:1.8}
    .soft{fill:#F1F5F9;stroke:#CBD5E1;stroke-width:1.3}
    .dark{fill:#0F172A}
    .h{font-size:20px;font-weight:750}
    .hw{font-size:20px;font-weight:750;fill:#FFFFFF}
    .s{font-size:15px;fill:#64748B}
    .sw{font-size:15px;fill:#CBD5E1}
    .b{font-size:17px;font-weight:700}
    .m{font-size:15px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
    .flow{fill:none;stroke:#334155;stroke-width:2.5;marker-end:url(#arrow)}
    .bracket{fill:none;stroke:#64748B;stroke-width:2}
    .divider{stroke:#E2E8F0;stroke-width:1.5}
    .take{fill:#0F172A}
    .tl{font-size:14px;font-weight:700;letter-spacing:1px;fill:#CBD5E1}
    .tv{font-size:19px;font-weight:650;fill:#FFFFFF}
"""


def page(title: str, desc: str, kicker: str, heading: str, sub: str, body: str, takeaway: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720" role="img" aria-labelledby="fig-title fig-desc" data-figure-system="chapter01-v2" fill="#0F172A">
  <title id="fig-title">{title}</title><desc id="fig-desc">{desc}</desc>
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0L10 5L0 10Z" fill="#334155"/></marker><style>{STYLE}</style></defs>
  <rect width="1280" height="720" fill="#F8FAFC"/>
  <text class="k" x="56" y="46">{kicker}</text><text class="t" x="56" y="84">{heading}</text><text class="sub" x="56" y="114">{sub}</text>
{body}
  <rect class="take" x="56" y="642" width="1168" height="54" rx="14"/><text class="tl" x="80" y="675">关键结论</text><text class="tv" x="184" y="676">{takeaway}</text>
</svg>
"""


def fig1() -> str:
    boxes = [
        ("客户端", "curl 或 streaming_client.py"),
        ("vLLM API", "/v1/chat/completions"),
        ("模型", "Qwen2.5-0.5B-Instruct"),
        ("GPU", "加载权重并执行计算"),
    ]
    parts = ['  <text class="b" x="640" y="214" text-anchor="middle">同一台主机 · 127.0.0.1:8000</text>']
    x = 90
    for index, (name, note) in enumerate(boxes):
        parts.append(
            f'  <g transform="translate({x} 250)"><rect class="card" width="230" height="140" rx="20"/>'
            f'<text class="h" x="115" y="62" text-anchor="middle">{name}</text>'
            f'<text class="s" x="115" y="96" text-anchor="middle">{note}</text></g>'
        )
        if index < len(boxes) - 1:
            parts.append(f'  <path class="flow" d="M{x + 230} 320H{x + 284}"/>')
        x += 290
    parts.append(
        '  <g transform="translate(90 452)"><rect class="soft" width="1100" height="104" rx="18"/>'
        '<text class="b" x="36" y="44">环境前提</text>'
        '<text class="s" x="180" y="44">Python / vLLM / Driver / GPU / Model，五项都记实际输出</text>'
        '<text class="s" x="36" y="80">先在本机跑通这条链路，再从开发机或别的服务访问；那时调用失败才能判定是网络路径问题</text></g>'
    )
    return page(
        "图 1-1 第一个 LLM 服务的最小运行链路",
        "客户端、vLLM API、模型与 GPU 四个环节串成一条本机链路，并标出这次运行的环境前提。",
        "MINIMAL PATH · 01",
        "第一个 LLM 服务的最小运行链路",
        "本章只跑这一条链路：客户端与服务端同机，先排除防火墙、端口转发和跨机网络",
        "\n".join(parts),
        "先跑通本机最短链路，再考虑跨机访问和内部结构。",
    )


def fig2() -> str:
    rows = [
        ("第三层 · 真实生成", "发送 Chat Completions（1.4 动手做）", "请求、模型执行和响应链路完整可用", "性能是否稳定、容量是否足够"),
        ("第二层 · 模型列表", "请求 /v1/models", "API 可访问，目标模型名可发现", "模型能否完成一次生成"),
        ("第一层 · 进程", "查看启动终端或进程状态", "vLLM 进程已经创建", "模型是否加载完成"),
    ]
    parts = [
        '  <text class="b" x="404" y="168">能证明什么</text>',
        '  <text class="b" x="838" y="168">仍不能证明什么</text>',
    ]
    y = 182
    for index, (layer, how, can, cannot) in enumerate(rows):
        parts.append(
            f'  <g transform="translate(56 {y})"><rect class="card" width="1168" height="112" rx="20"/>'
            f'<text class="h" x="32" y="52">{layer}</text>'
            f'<text class="s" x="32" y="84">{how}</text>'
            f'<line class="divider" x1="330" y1="18" x2="330" y2="94"/>'
            f'<text class="s" x="362" y="64" fill="#0F172A">{can}</text>'
            f'<line class="divider" x1="764" y1="18" x2="764" y2="94"/>'
            f'<text class="s" x="796" y="64">{cannot}</text></g>'
        )
        if index < len(rows) - 1:
            arrow_bottom = y + 112 + 24
            parts.append(f'  <path class="flow" d="M200 {arrow_bottom}V{y + 118}"/>')
        y += 140
    parts.append(
        '  <g transform="translate(56 590)"><rect class="soft" width="1168" height="36" rx="12"/>'
        '<text class="s" x="24" y="24" fill="#0F172A">排查失败时沿这三层从前往后找，停在最早失败的那一层</text></g>'
    )
    return page(
        "图 1-2 三层就绪证据",
        "进程、模型列表和真实生成三层证据自下而上排列，每层写出能证明什么与仍不能证明什么。",
        "READINESS EVIDENCE · 02",
        "三层就绪证据",
        "“服务已启动”至少有三种含义，上一层通过不代表下一层通过",
        "\n".join(parts),
        "进程存在只是第一层证据，三层都通过才算服务可交付。",
    )


def fig3() -> str:
    fields = [
        ("model", "必需", "服务公开的模型名"),
        ("messages", "必需", "对话消息与角色"),
        ("max_tokens", "可选", "限制最大输出长度"),
        ("temperature", "可选", "控制采样随机性"),
        ("stream", "可选", "false 一次性返回"),
    ]
    checks = [
        ("1", "model 是否为目标服务公开的模型名"),
        ("2", "choices[0].message.role 是否为 assistant"),
        ("3", "content 是否包含非空正文"),
        ("4", "finish_reason 是否说明正常结束"),
        ("5", "usage 是否给出 token 数，缺失则留空"),
    ]
    parts = [
        '  <g transform="translate(72 170)"><rect class="card" width="440" height="404" rx="20"/>'
        '<text class="h" x="32" y="52">请求 · stream=false</text>'
    ]
    y = 88
    for name, need, note in fields:
        parts.append(
            f'<g transform="translate(32 {y})"><rect class="soft" width="376" height="56" rx="12"/>'
            f'<text class="m" x="20" y="34">{name}</text>'
            f'<text class="s" x="170" y="34" fill="#0F172A">{need}</text>'
            f'<text class="s" x="230" y="34">{note}</text></g>'
        )
        y += 64
    parts.append("</g>")
    parts.append('  <path class="flow" d="M512 372H620"/>')
    parts.append('  <text class="s" x="566" y="352" text-anchor="middle" fill="#0F172A">返回</text>')
    parts.append('  <text class="s" x="566" y="404" text-anchor="middle">HTTP 200</text>')
    parts.append('  <text class="s" x="566" y="428" text-anchor="middle">不是验收项</text>')
    parts.append(
        '  <g transform="translate(624 170)"><rect class="card" width="584" height="404" rx="20"/>'
        '<text class="h" x="32" y="52">一次性完整响应：五项逐条检查</text>'
    )
    y = 88
    for index, text in checks:
        parts.append(
            f'<g transform="translate(32 {y})"><rect class="soft" width="520" height="56" rx="12"/>'
            f'<text class="b" x="20" y="35">{index}</text>'
            f'<text class="s" x="56" y="34" fill="#0F172A">{text}</text></g>'
        )
        y += 64
    parts.append("</g>")
    return page(
        "图 1-3 同步请求字段与响应验收项",
        "左侧列出同步请求的五个字段与必需性，右侧按正文顺序列出响应的五个验收项，并标明 HTTP 200 不在其中。",
        "REQUEST CONTRACT · 03",
        "同步请求字段与响应验收项",
        "两个必需字段加三个显式写出的可选字段，换来一份要逐项验收的完整响应",
        "\n".join(parts),
        "HTTP 200 不等于验收通过；usage 缺失时留空，不用字符数折算。",
    )


def fig4() -> str:
    lines = [
        ('data: {"choices":[{"delta":{"role":"assistant"}}]}', "流开始"),
        ('data: {"choices":[{"delta":{"content":"…"}}]}', "正文增量，客户端在这里计时"),
        ('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}', "结束原因单独一片"),
        ('data: {"usage":{"prompt_tokens":…,"completion_tokens":…}}', "只有 include_usage 才有"),
        ("data: [DONE]", "这一行不是 JSON"),
    ]
    parts = [
        '  <g transform="translate(56 148)"><rect class="card" width="1168" height="212" rx="20"/>'
        '<text class="h" x="28" y="44">SSE 流：一串 data: 行，不是一个 JSON 对象</text>'
    ]
    y = 74
    for code, note in lines:
        parts.append(
            f'<text class="m" x="28" y="{y + 20}">{code}</text>'
            f'<text class="s" x="700" y="{y + 20}">{note}</text>'
        )
        y += 28
    parts.append("</g>")

    marks = [
        (150, "请求发出", "计时起点"),
        (330, "首个内容分片", "第一段正文到达"),
        (620, "后续分片", "相邻两片的间隔"),
        (980, "收到 [DONE]", "流正常结束"),
    ]
    parts.append('  <text class="b" x="56" y="386">客户端时间线</text>')
    parts.append('  <path class="flow" d="M120 440H1080"/>')
    for x, name, note in marks:
        parts.append(f'  <circle cx="{x}" cy="440" r="9" fill="#0F172A"/>')
        parts.append(f'  <text class="b" x="{x}" y="418" text-anchor="middle">{name}</text>')
        parts.append(f'  <text class="s" x="{x}" y="472" text-anchor="middle">{note}</text>')
    for x in (540, 700, 800):
        parts.append(f'  <circle cx="{x}" cy="440" r="6" fill="#94A3B8"/>')
    parts.append('  <path class="bracket" d="M150 496V516H330V496"/>')
    parts.append('  <text class="s" x="240" y="540" text-anchor="middle" fill="#0F172A">首个内容分片等待</text>')
    parts.append('  <path class="bracket" d="M150 556V576H980V556"/>')
    parts.append('  <text class="s" x="565" y="600" text-anchor="middle" fill="#0F172A">整次调用时长</text>')
    parts.append(
        '  <g transform="translate(1000 496)"><rect class="soft" width="224" height="112" rx="16"/>'
        '<text class="s" x="20" y="34" fill="#0F172A">两种计数分开记</text>'
        '<text class="s" x="20" y="62">stream_chunks 客户端数</text>'
        '<text class="s" x="20" y="90">output_tokens 服务端给</text></g>'
    )
    return page(
        "图 1-4 流式调用里客户端能记下的四个时刻",
        "上方是 SSE 流的五类行，下方把请求发出、首个内容分片、后续分片与流结束落在同一条客户端时间线上，并闭合两段区间。",
        "CLIENT EVENTS · 04",
        "流式调用里客户端能记下的四个时刻",
        "分片陆续到达，一次调用于是从一个数字变成一串可以打时间戳的事件",
        "\n".join(parts),
        "客户端能记下四个时刻、闭合两段区间；分片数与 token 数必须分开记。",
    )


def fig5() -> str:
    parts = [
        '  <g transform="translate(72 162)"><rect class="card" width="420" height="188" rx="20"/>'
        '<text class="h" x="32" y="50">同步 stream=false</text>'
        '<text class="b" x="32" y="96">只有一个数字：time_total</text>'
        '<text class="s" x="32" y="130">答案要么没出来，要么全出来了</text>'
        '<text class="s" x="32" y="158">中间没有可记录的事件</text></g>',
        '  <path class="flow" d="M492 256H600"/>',
        '  <text class="s" x="546" y="236" text-anchor="middle" fill="#0F172A">换成流式</text>',
        '  <g transform="translate(604 162)"><rect class="card" width="604" height="188" rx="20"/>'
        '<text class="h" x="32" y="50">流式 stream=true</text>'
        '<text class="b" x="32" y="92">开口：首个内容分片 29.64 ms</text>'
        '<text class="b" x="32" y="126">之后：254 个分片，平均间隔 9.15 ms</text>'
        '<text class="b" x="32" y="160">答完：整次调用 2345.26 ms</text></g>',
        '  <path class="flow" d="M282 350V424"/>',
        '  <g transform="translate(72 428)"><rect class="soft" width="420" height="96" rx="18"/>'
        '<text class="b" x="32" y="42">只能问“多久答完”</text>'
        '<text class="s" x="32" y="72">用户感受被压进一个总时长里</text></g>',
        '  <path class="flow" d="M744 350V424"/>',
        '  <path class="flow" d="M1060 350V424"/>',
        '  <g transform="translate(604 428)"><rect class="dark" width="280" height="96" rx="18"/>'
        '<text class="hw" x="140" y="44" text-anchor="middle">多久开口</text>'
        '<text class="sw" x="140" y="74" text-anchor="middle">对着空白等多久</text></g>',
        '  <g transform="translate(920 428)"><rect class="dark" width="288" height="96" rx="18"/>'
        '<text class="hw" x="144" y="44" text-anchor="middle">后面出得稳不稳</text>'
        '<text class="sw" x="144" y="74" text-anchor="middle">读起来顺不顺</text></g>',
        '  <path class="flow" d="M744 524V566"/>',
        '  <path class="flow" d="M1064 524V566"/>',
        '  <text class="b" x="744" y="592" text-anchor="middle">第 5 章 TTFT</text>',
        '  <text class="b" x="1064" y="592" text-anchor="middle">第 5 章 ITL</text>',
        '  <text class="s" x="72" y="592">两个量互相独立：开口快也可能输出结巴</text>',
        '  <text class="s" x="72" y="618">右侧三个数字来自 GX10 一次真实调用的客户端观测，不是性能结论</text>',
    ]
    return page(
        "图 1-5 一个总时长，两个独立的问题",
        "左侧同步记录只剩一个总时长，右侧流式记录给出开口、节奏与答完三个数字，并引出多久开口与出得稳不稳两个问题。",
        "ONE NUMBER, TWO QUESTIONS · 05",
        "一个总时长，两个独立的问题",
        "交付方式一变，“快”的含义也跟着变：用户在第一个字出现时就开始读了",
        "\n".join(parts),
        "流式让客户端第一次测得到这两个量，它们的正式名字在第 5 章。",
    )


FIGURES = {
    "fig01-01_minimal_service_path.svg": fig1,
    "fig01-02_readiness_evidence.svg": fig2,
    "fig01-03_sync_request_acceptance.svg": fig3,
    "fig01-04_streaming_client_events.svg": fig4,
    "fig01-05_one_number_two_questions.svg": fig5,
}


def main() -> None:
    for name, builder in FIGURES.items():
        (OUT / name).write_text(builder(), encoding="utf-8")
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
