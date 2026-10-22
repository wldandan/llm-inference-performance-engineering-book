"""List the sections whose term annotations suggest a missing relation paragraph.

写作规则 4 说，一段里出现两条以上注释，通常说明这段引入了太多新概念；写作规则 9 说，
几个概念一起出场时，先用一段话讲清它们的关系。这个脚本按小节数注释，报两类：

    stacked  同一个引用块里连着两条以上注释。读者拿到的是一串并列定义，几乎总该拆开，
             或者改成一段关系说明加各自展开处的注释
    dense    一个小节里有两条以上注释。不一定有错，提示去看这一节是不是缺了关系段

用法：

    python3 tools/check_annotations.py            # 列出两类
    python3 tools/check_annotations.py --strict   # 有 stacked 时返回 1，CI 用
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_glossary import SECTION, TERM, reading_order, split_term  # noqa: E402


def scan() -> tuple[list[dict], list[dict]]:
    stacked: list[dict] = []
    sections: dict[tuple[str, str], list[str]] = {}
    order: list[tuple[str, str]] = []
    for label, path in reading_order():
        section = label
        block_terms: list[str] = []
        block_start = 0
        in_code = False
        lines = path.read_text(encoding="utf-8").split("\n") + [""]
        for i, line in enumerate(lines, 1):
            if line.startswith("```"):
                in_code = not in_code
            if in_code:
                continue
            if not line.startswith(">"):
                if len(block_terms) >= 2:
                    stacked.append({"where": label, "section": section,
                                    "line": block_start, "terms": block_terms})
                block_terms = []
            m = SECTION.match(line)
            if m:
                section = m.group("num")
                continue
            m = TERM.match(line)
            if not m:
                continue
            term, _ = split_term(m.group("term").strip(), (m.group("en") or "").strip())
            if not block_terms:
                block_start = i
            block_terms.append(term)
            key = (label, section)
            if key not in sections:
                sections[key] = []
                order.append(key)
            sections[key].append(term)
    dense = [{"where": k[0], "section": k[1], "terms": sections[k]}
             for k in order if len(sections[k]) >= 2]
    return stacked, dense


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--strict", action="store_true",
                        help="有 stacked 时返回 1")
    args = parser.parse_args(argv)
    stacked, dense = scan()
    for s in stacked:
        print(f"stacked  {s['where']}  {s['section']}  第 {s['line']} 行  "
              f"{'、'.join(s['terms'])}")
    for d in dense:
        print(f"dense    {d['where']}  {d['section']}  {len(d['terms'])} 条  "
              f"{'、'.join(d['terms'])}")
    print(f"stacked {len(stacked)} 处，dense {len(dense)} 节")
    return 1 if args.strict and stacked else 0


if __name__ == "__main__":
    sys.exit(main())
