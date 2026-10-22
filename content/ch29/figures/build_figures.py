"""Build the Chapter 29 figure set defined in strategy/reviews/ch29/storyboard.md.

  fig29-01  29.1 那句话的图：九项清单全绿，评审仍然不通过，因为五处接缝里有一处
            对不上。左栏是九项，右栏是五处接缝，唯一那处不一致带着它换算出来的
            后果（8 张卡实际要 11 张）。

两栏的内容都由 code/ch29/release_check.py 跑仓库里那份 release-docs-seam.json 得到，
所以图上说的通过和不通过，就是脚本会给出的那个结论。

Run from the repository root:

    python3 content/ch29/figures/build_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "code" / "ch29"))
from figkit import (  # noqa: E402
    BAD, COOL, GOOD, MUTED, WARN, card, dashed, note, page, txt, write,
    write_note,
)
import release_check as rc  # noqa: E402

OUT = Path(__file__).parent
SYSTEM = "part02-v1"

DOCS = json.loads(
    (ROOT / "content" / "ch29" / "evidence" / "release-docs-seam.json")
    .read_text(encoding="utf-8"))
RESULT = rc.review(DOCS)
SEAM = next(r for r in RESULT["cross_check"]["rows"]
            if r["key"] == "context_length")


def fig1() -> str:
    p = []

    # 左：九项清单
    p.append(card(56, 158, 460, 416, cls="goodfill", rx=16))
    p.append(txt(80, 190, "九项清单", cls="h"))
    p.append(f'  <text class="b" x="492" y="190" text-anchor="end" '
             f'fill="{GOOD}">全绿</text>')
    y = 218
    for key, label in rc.CHECKLIST:
        item = RESULT["checklist"]["items"][key]
        mark = "✓" if item["ok"] else "×"
        colour = GOOD if item["ok"] else BAD
        p.append(f'  <text class="b" x="80" y="{y + 18}" fill="{colour}">'
                 f'{mark}</text>')
        p.append(txt(106, y + 18, label, cls="s"))
        y += 38

    # 右：五处接缝
    p.append(card(540, 158, 684, 416, cls="card", rx=16))
    p.append(txt(564, 190, "五处接缝", cls="h"))
    p.append(f'  <text class="b" x="1200" y="190" text-anchor="end" '
             f'fill="{BAD}">一处对不上</text>')

    y = 218
    for row in RESULT["cross_check"]["rows"]:
        bad = row["status"] == "不一致"
        colour = BAD if bad else GOOD
        h = 126 if bad else 48
        p.append(f'  <rect x="556" y="{y}" width="652" height="{h}" rx="12" '
                 f'fill="{"#FEF2F2" if bad else "#FFFFFF"}" '
                 f'stroke="{colour}" stroke-width="{1.8 if bad else 1.2}"/>')
        p.append(txt(576, y + 30, row["left"], cls="b"))
        p.append(f'  <text class="s" x="860" y="{y + 30}" '
                 f'text-anchor="middle">对</text>')
        p.append(txt(896, y + 30, row["right"], cls="b"))
        p.append(f'  <text class="b" x="1192" y="{y + 30}" '
                 f'text-anchor="end" fill="{colour}">{row["status"]}</text>')
        if bad:
            p.append(f'  <path d="M572 {y + 48}H1192" class="divider"/>')
            p.append(f'  <text class="mb" x="576" y="{y + 76}" fill="{BAD}">'
                     f'{row["left_value"]:.0f} 对 {row["right_value"]:.0f}'
                     f'</text>')
            c = row["consequence"]
            p.append(txt(760, y + 76,
                         "新版本把检索片段从 Top-5 加到了 Top-8",
                         cls="s"))
            p.append(f'  <text class="b" x="576" y="{y + 106}" fill="{BAD}">'
                     f'并发上限折算为原来的 {c["concurrency_ratio"]:.0%}，'
                     f'{c["instances_in_model"]} 张卡实际要 '
                     f'{c["instances_needed"]} 张</text>')
        y += h + 8

    p.append(note(56, 588, 1168, [
        f"结论是{RESULT['verdict']}。每一份材料单看都没错，"
        f"而没有任何一个单独的角色会去比这五对数：性能工程师看性能证据，"
        f"运维看容量，开发看变更说明，接缝处正好是所有人的盲区。",
    ], cls="badfill"))

    return page(
        system=SYSTEM,
        title="九项全绿，评审仍然不通过",
        desc="左栏是九项上线检查清单，SLO、Baseline、容量核算、门禁、监控、流量治理、"
             "冷启动、回滚预案、责任人，九项全部打勾。右栏是五处接缝的核对结果："
             "门禁批量对生产批量、Baseline 框架版本对镜像版本、容量模型的峰值与下限卡数"
             "对扩缩容的实例数区间、SLO 阈值对门禁绝对阈值，四处一致；"
             "容量模型的上下文长度 12000 对当前 prompt 模板的实际长度 16000，这一处不一致，"
             "原因是新版本把检索片段从 Top-5 加到 Top-8，"
             "并发上限折算为原来的 75%，容量模型算出的 8 张卡实际要 11 张。"
             "底部写明结论是不通过。",
        kicker="第 29 章 · 29.1、29.8",
        heading="评审的价值不在重审每一份材料，在交叉检查那些接缝",
        sub="九项清单一项不缺，唯一的问题是两份材料里的上下文长度对不上",
        body="\n".join(p),
        takeaway="接缝对不上要换算成卡数：不然它看着像格式问题，其实是容量问题",
    )


FIGS = [
    ("fig29-01_seams", fig1,
     dict(title="图29-1 九项全绿，评审仍然不通过",
          source="29.1、29.8",
          order="先扫一遍左栏确认九项都打了勾，再看右栏哪一行是红的，最后读那一行下面换算出来的卡数",
          takeaway="接缝对不上要换算成卡数：不然它看着像格式问题，其实是容量问题",
          boundary="合成设定，材料来自 content/ch29/evidence/release-docs-seam.json，两栏的结论由 code/ch29/release_check.py 跑出来。五处接缝是这本书里反复出过事的那五处，不是一份完备清单；每个团队都该按自己出过的事故往上加")),
]


def main() -> None:
    for stem, fn, meta in FIGS:
        write(OUT, f"{stem}.svg", fn())
        write_note(OUT, stem, **meta)
    print(f"wrote {len(FIGS)} figures to {OUT}")


if __name__ == "__main__":
    main()
