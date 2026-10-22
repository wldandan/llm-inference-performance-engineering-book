"""Build the Chapter 25 figure set defined in strategy/reviews/ch25/storyboard.md.

  fig25-01  25.2's decomposition and the assumption it overturns: the model
            service is the biggest layer, but two thirds of it is queueing, so
            cutting the per-call compute from 480 to 260 ms moves the
            end-to-end number by about 7%.
  fig25-02  25.3's budget split, drawn as the two attempts: the first draft at
            today's load (ρ 0.9) that code/ch25/e2e_experiment.py refuses because
            the queue does not fit, and the adjusted one (10 steps, ρ ≤ 0.69) it
            accepts.

The budget numbers are produced by `build_budget` at build time, and the
infeasible one is produced by catching its refusal, so the figure cannot claim a
split the checker would reject.

Run from the repository root:

    python3 content/ch25/figures/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch25"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, WARN, card, dashed, note, page, txt, write, write_note,
)
import e2e_experiment as ee  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"
MUTED_LINE = "#94A3B8"

BUDGET_KW = dict(total_ms=8000.0, per_step_orchestration_ms=50.0,
                 retrieval_ms=1200.0, model_serving_ms=5000.0,
                 tools_ms=1000.0, measured_call_compute_ms=480.0,
                 model_calls_p95=7, service_time_ms=103.0)
RHO_NOW = 0.9
FEASIBLE = ee.build_budget(steps_p95=10, rho=0.69, **BUDGET_KW)

try:
    ee.build_budget(steps_p95=15, rho=RHO_NOW, **BUDGET_KW)
except ee.ExperimentError as exc:
    REFUSAL = str(exc)
else:  # pragma: no cover - 这里不该走到
    raise SystemExit("负载率 0.9 那份预算居然通过了，图和检查器对不上")

FIRST = ee.build_budget(steps_p95=15, **BUDGET_KW)  # 不带 ρ，取它的拆分画左栏
# 25.2 实测：模型服务里排队占 31%，21 秒 × 31% ÷ 7 次调用 ≈ 930 ms。正文用的是
# 这个实测值；式子那一侧 9 × 103 给 927，同一个量两个数会让读者以为是两件事。
QUEUE_NOW = 6510 / 7
QUEUE_FROM_MODEL = ee.queue_ms(BUDGET_KW["service_time_ms"], RHO_NOW)
COMPUTE_CUT = (480 - 260) / 480

# 25.2 那张全链路时间表。
LAYERS_25_2 = [
    ("编排层", 0.18, "步数 P95 = 34（模型调用约 7 次）", WARN),
    ("检索层", 0.22, "重排候选 200，冷查询占比高", COOL),
    ("模型服务", 0.47, "排队 31%，GPU 计算 16%", BAD),
    ("工具", 0.13, "代码执行", MUTED_LINE),
]
QUEUE_SHARE = 0.31
GPU_SHARE = 0.16
LAYER_LABEL = {"orchestration": "编排层", "retrieval": "检索层",
               "model_serving": "模型服务", "tools": "工具"}


# --- 图25-1 分层定位推翻的那个默认假设 --------------------------------------

def fig1() -> str:
    p = [card(72, 176, 700, 396, cls="card", rx=16)]
    p.append(txt(96, 208, "压测下的全链路时间分解（合成设定）", cls="b"))

    x0, x1 = 232, 744
    y = 236
    # 行距收到 70，最后一行的说明落在 506，不压底下那条拆开的细条
    for name, share, why, colour in LAYERS_25_2:
        w = share * (x1 - x0)
        p.append(f'  <rect x="{x0}" y="{y}" width="{w:.0f}" height="34" rx="8" '
                 f'fill="{colour}" opacity="0.20" stroke="{colour}" '
                 f'stroke-width="1.6"/>')
        p.append(txt(96, y + 23, name, cls="b"))
        p.append(f'  <text class="b" x="{x0 + w + 12:.0f}" y="{y + 23}" '
                 f'fill="{colour}">{share:.0%}</text>')
        p.append(txt(232, y + 56, why, cls="s"))
        y += 70

    # 把模型服务那一层拆开：排队 31%，GPU 计算 16%
    p.append(txt(96, 556, "模型服务那 47% 里，三分之二是排队", cls="b"))
    sx = 380
    seg_w = (x1 - sx)
    p.append(f'  <rect x="{sx}" y="536" width="{seg_w * QUEUE_SHARE / 0.47:.0f}" '
             f'height="28" rx="6" fill="{BAD}" opacity="0.35"/>')
    p.append(f'  <rect x="{sx + seg_w * QUEUE_SHARE / 0.47:.0f}" y="536" '
             f'width="{seg_w * GPU_SHARE / 0.47:.0f}" height="28" rx="6" '
             f'fill="{GOOD}" opacity="0.35"/>')
    p.append(txt(sx + 12, 555, f"排队 {QUEUE_SHARE:.0%}", cls="s"))
    p.append(txt(sx + seg_w * QUEUE_SHARE / 0.47 + 12, 555,
                 f"GPU {GPU_SHARE:.0%}", cls="s"))

    p.append(card(796, 176, 412, 396, cls="card", rx=16))
    p.append(txt(820, 208, "这张表立刻推翻的那个假设", cls="b"))
    p.append(note(812, 228, 380, [
        "默认假设：模型服务占 47%，",
        "所以先去优化推理",
    ], cls="badfill"))
    p.append(note(812, 316, 380, [
        f"真正的 GPU 计算只占 {GPU_SHARE:.0%}",
        "单次计算从 480 降到 260 ms，",
        f"端到端只改善约 {GPU_SHARE * COMPUTE_CUT:.0%}",
    ], cls="warnfill"))
    p.append(note(812, 430, 380, [
        "排队高，先问负载率为什么高：",
        "容量、准入、满载吞吐（第 20、21 章）；",
        "满载吞吐上去了，排队才会塌下去",
    ], cls="goodfill"))

    p.append(note(72, 588, 1136, [
        "分解要在压测下做，不是在空闲时做。空闲时排队为零，这张表会完全是另一个样子，"
        "然后你会去优化一个在高峰期根本不是瓶颈的环节。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="分层定位，不是分层优化",
        desc="左侧四条横条按占比画出编排层 18%、检索层 22%、模型服务 47%、工具 13%，"
             "每条下方写明主要构成。最下方把模型服务那一层再拆成排队 31% 和 GPU 计算 16% "
             "两段。右侧三块依次是：默认假设是先去优化推理；真正的 GPU 计算只占 16%，单次"
             "计算从 480 降到 260 毫秒，端到端只改善约 7%；排队高先问负载率为什么高，"
             "答案在容量、准入和满载吞吐上。",
        kicker="第 25 章 · 25.2",
        heading="最大的那一层，未必是该先动的那一层",
        sub="模型服务占 47%，但其中三分之二是排队",
        body="\n".join(p),
        takeaway="单次计算快了将近一半，端到端只改善约 7%：先分解，再决定动哪一层",
    )


# --- 图25-2 拆预算会立刻暴露不可能的目标 ------------------------------------

def fig2() -> str:
    p = []

    # 左：按现状负载率 0.9 拆的第一版，被拒
    p.append(card(72, 176, 552, 396, cls="badfill", rx=16))
    p.append(txt(96, 208, f"第一版：步数 P95 = 15，负载率按现状 {RHO_NOW}", cls="h"))
    y = 248
    for key in ee.LAYERS:
        row = FIRST["layers"][key]
        p.append(txt(120, y, LAYER_LABEL[key], cls="b"))
        p.append(txt(252, y, f"{row['ms']:.0f} ms", cls="m"))
        p.append(txt(384, y, row["basis"].split("，")[0], cls="s"))
        y += 36
    p.append(f'  <path d="M104 {y - 18}H600" class="divider"/>')
    p.append(txt(120, y + 16, "合计", cls="b"))
    total_first = sum(r["ms"] for r in FIRST["layers"].values())
    p.append(txt(252, y + 16, f"{total_first:.0f} ms", cls="m"))
    p.append(txt(120, y + 58,
                 f"每次调用 {FIRST['per_call_model_serving_ms']:.0f} ms，"
                 f"扣掉纯计算 480，排队只占得到 "
                 f"{FIRST['queue_allowance_per_call_ms']:.0f} ms", cls="b"))
    p.append(f'  <text class="b" x="120" y="{y + 88}" fill="{BAD}">'
             f'负载率 {RHO_NOW} 时实测每次排队约 {QUEUE_NOW:.0f} ms</text>')
    p.append(txt(120, y + 118, "这份预算不成立，脚本直接报错", cls="s"))

    # 右：调整后，成立
    p.append(card(656, 176, 552, 396, cls="goodfill", rx=16))
    p.append(txt(680, 208,
                 f"调整后：步数 P95 = {FEASIBLE['steps_p95']}，"
                 f"负载率 ≤ {FEASIBLE['rho_max']:.2f}", cls="h"))
    y = 248
    for key in ee.LAYERS:
        row = FEASIBLE["layers"][key]
        p.append(txt(704, y, LAYER_LABEL[key], cls="b"))
        p.append(txt(836, y, f"{row['ms']:.0f} ms", cls="m"))
        p.append(txt(968, y, row["basis"].split("，")[0], cls="s"))
        y += 36
    p.append(txt(704, y, "未分配余量", cls="b"))
    p.append(txt(836, y, f"{FEASIBLE['unallocated_ms']:.0f} ms", cls="m"))
    p.append(txt(968, y, "给串行等待和抖动", cls="s"))
    y += 36
    p.append(f'  <path d="M688 {y - 18}H1192" class="divider"/>')
    p.append(txt(704, y + 16, "合计", cls="b"))
    p.append(txt(836, y + 16, f"{FEASIBLE['total_ms']:.0f} ms", cls="m"))
    allow = FEASIBLE["queue_allowance_per_call_ms"]
    s_ms = FEASIBLE["service_time_ms"]
    p.append(f'  <text class="b" x="704" y="{y + 58}" fill="{GOOD}">'
             f'每次 {FEASIBLE["per_call_model_serving_ms"]:.0f} ms = '
             f'纯计算 480 + 排队 ≤ {allow:.0f}</text>')
    p.append(txt(704, y + 88,
                 f"负载率上限 {allow:.0f} ÷ ({s_ms:.0f} + {allow:.0f}) ≈ "
                 f"{FEASIBLE['rho_max']:.2f}，交给准入和容量去守",
                 cls="s"))

    p.append(f'  <path class="flow" d="M628 372H648"/>')

    p.append(note(72, 588, 1136, [
        "拆预算的价值就在于它会报错。一个总能返回结果的函数，正是让这个矛盾"
        "在优化到一半才被发现的那个东西；这个矛盾必须在动手之前解决。",
    ], cls="soft"))

    return page(
        system=SYSTEM,
        title="拆预算会立刻暴露不可能的目标",
        desc="两栏对照。左栏是第一版：步数 P95 等于 15，编排层 750、检索层 1200、模型服务 "
             "5000、工具 1000；模型服务按 7 次模型调用拆，每次 714 毫秒，扣掉 480 毫秒纯计算，"
             "排队只占得到 234 毫秒，而现状实测每次排队约 930 毫秒，所以这份预算"
             "不成立。右栏是调整后的版本：步数降到 10，编排层 500、检索层 1200、模型服务 "
             "5000、工具 1000、未分配余量 300，合计 8000；负载率要守在 0.69 以下，排队才放得进"
             "每次调用的预算。",
        kicker="第 25 章 · 25.3、25.8",
        heading="预算算不下来时，该改的是负载率、步数或者 SLO，不是预算表",
        sub="按调用拆，每次调用里排队只占得到 234 ms，负载率要守在 0.69 以下",
        body="\n".join(p),
        takeaway="这个矛盾必须在动手之前解决，而不是优化到一半才发现做不到",
    )


FIGS = [
    ("fig25-01_layer_breakdown", fig1,
     dict(title="图25-1 分层定位，不是分层优化",
          source="25.2",
          order="先看四条横条里哪一条最长，再看最下面那条把模型服务拆成排队和 GPU 计算的细条，最后读右侧三块",
          takeaway="单次计算快了将近一半，端到端只改善约 7%：先分解，再决定动哪一层",
          boundary="合成设定，不是某个真实服务的分解；各层占比随链路结构和负载变化很大，要看的是先分解再决定这件事，不是这几个具体百分比。分解必须在压测下做，空闲时采的表不能用于决策")),
    ("fig25-02_budget_split", fig2,
     dict(title="图25-2 拆预算会立刻暴露不可能的目标",
          source="25.3、25.8",
          order="先看左栏那几行和下面每次调用的拆法，再看现状负载率下排队要多少，然后看右栏调整后的步数和负载率上限",
          takeaway="这个矛盾必须在动手之前解决，而不是优化到一半才发现做不到",
          boundary="两份预算都由 code/ch25/e2e_experiment.py 的 build_budget 生成，左栏那一版是捕获它的报错画出来的；480 ms 的单次纯计算、7 次调用和 103 ms 的 S 是合成设定，排队按第 20.6 节的单服务台式子算，是上界；换一条链路两栏的数都会变，不变的是拆预算会报错这件事")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
