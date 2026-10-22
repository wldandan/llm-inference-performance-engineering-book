"""Build content/reference/glossary.md from the term annotations in the chapters.

全书的术语注释都写成引用块：

    > **术语**（English）：定义。补充说明……

这个脚本按阅读顺序（第 0 章、Part 1 开篇、第 1 至 5 章、Part 2 开篇……附录 A）扫一遍，
每条注释取首选写法、英文、定义的第一句、定义所在的小节，再找这个写法在全书第一次出现
的位置。两个位置不同时，说明读者在读到定义之前已经见过它。

另有几条全书没有写成注释、但正文反复出现的术语，在 EXTRA 里手写定义。GEMM 之类正文
从不单独解释的，定义所在一栏写“本表”；Request ID、槽位占用率这类在关系段或关系表里
说清、按写作规则 9 不再挂注释的，写它们所在的那一节，按小节顺序插回表里。

“同族”一列来自 FAMILIES：容易混用的几组词，各自在一节里放了一张对照表（写作规则 9），
括号里就是那一节。

术语表是索引，不手工维护。改了正文里的注释就重跑：

    python3 tools/build_glossary.py           # 重写 glossary.md
    python3 tools/build_glossary.py --check   # 只检查是否最新，CI 用
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
OUT = CONTENT / "reference" / "glossary.md"

TERM = re.compile(r"^> \*\*(?P<term>[^*]+)\*\*(?:（(?P<en>[^）]+)）)?[：:](?P<body>.*)$")
SECTION = re.compile(r"^## (?P<num>\d+\.\d+|[A-Z]\.\d+) ")

# 全书没有写成注释、但正文反复用到的几条。第四项是定义所在的小节，"本表" 表示正文
# 没有单独解释它。
EXTRA = [
    ("GEMM", "general matrix multiply",
     "通用矩阵乘法。投影层和 MLP 的计算都是它，Prefill 的运算量主要花在这里", "本表"),
    ("logits", "logits",
     "模型最后一层对词表里每个 token 打出的原始分数，经过 softmax 才变成概率", "本表"),
    ("SM", "streaming multiprocessor",
     "GPU 上执行计算的基本单元，一张卡有几十到上百个", "本表"),
    ("Request ID", "request ID",
     "从客户端贯通到引擎的那个 ID，一条推理请求一个。它不是引擎内部的 request_id，"
     "也不是标识整次调用的 Trace ID", "8.3"),
    ("在途", "in-flight",
     "已到达、还没结束的请求条数，由 Little's Law 决定。引擎里的 Waiting 和 Running "
     "都是它的一部分", "20.3"),
    ("并发上限", "concurrency limit",
     "全书有两种用法：第 16 章指 KV 池按平均上下文放得下的条数，第 7、10 章指配置里给的"
     "上限，例如 max_num_seqs。两者都是 Running 的上限，实际取较小的那个", "20.3"),
    ("GPU 利用率", "GPU utilization",
     "采样时间里有 kernel 在跑的时间占比。它只说明 GPU 在忙，不说明还有没有余量", "20.7"),
    ("槽位占用率", "Slot Occupancy",
     "Running 条数除以槽位上限 max_num_seqs，回答还能不能再收一条请求，"
     "是三个调度信号里最早动的", "20.7"),
    ("灰度发布", "gradual rollout",
     "让新版本先只接一部分流量、再逐步放大。Canary 是它的一种做法，"
     "滚动升级换的是实例，不是灰度", "28.5"),
    ("Canary", "canary release",
     "灰度的一种：把一小份真实流量切给新版本，响应真的返回给用户，"
     "出问题时受影响的就是这一小份人", "28.5"),
    ("Shadow", "shadow traffic",
     "把生产流量复制一份发给新版本，响应丢弃、不返回给用户。它不是灰度，"
     "因为没有用户承担风险；代价是新版本要有独立资源", "28.5"),
]

# 容易混用的几组词，各自在哪一节放了对照表。键是术语表里的首选写法。
FAMILIES = {
    "ID（8.3）": ["Request ID", "Trace 与 Span"],
    "缓存（13.3）": ["KV Cache", "Prefix Cache"],
    "数量（20.3）": ["在途", "并发上限"],
    "比例（20.7）": ["GPU 利用率", "负载率", "槽位占用率"],
    "任务层级（24.1）": ["Agent", "编排层", "步数放大"],
    "发布方式（28.5）": ["灰度发布", "Shadow", "Canary"],
}


def reading_order() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = [("第 0 章", CONTENT / "ch00" / "ch00.md")]
    parts = {1: range(1, 6), 2: range(6, 11), 3: range(11, 15), 4: range(15, 20),
             5: range(20, 26), 6: range(26, 30), 7: range(30, 31)}
    for part, chapters in parts.items():
        files.append((f"Part {part} 开篇", CONTENT / f"part0{part}.md"))
        for n in chapters:
            files.append((f"第 {n} 章", CONTENT / f"ch{n:02d}" / f"ch{n:02d}.md"))
    files.append(("附录 A", CONTENT / "advanced" / "appendix-a-gpu-architecture"
                  / "appendix-a.md"))
    return files


def first_sentence(text: str) -> str:
    """定义的第一句；太短（只是引子）时再接一句。"""
    parts = [x.strip() for x in re.split(r"[。；]", text.strip()) if x.strip()]
    if not parts:
        return ""
    s = parts[0]
    if len(s) < 28 and len(parts) > 1 and not re.match(r"(这里|上面|比如|例如)", parts[1]):
        s = s + "。" + parts[1]
    # 去掉只在原文语境里成立的指代，比如“即上表最后一列”。
    s = re.sub(r"，[^，]*(上表|下表|上面|下面)[^，]*$", "", s)
    return s.replace("|", "\\|").strip()


def split_term(term: str, en: str) -> tuple[str, str]:
    """“变异系数（CV, coefficient of variation）”这类把英文写进加粗里的，拆开。"""
    m = re.match(r"^([^（]+)（([^（）]+)）$", term)
    if not en and m and re.search(r"[A-Za-z]", m.group(2)):
        return m.group(1).strip(), m.group(2).strip()
    return term, en


def collect() -> tuple[list[dict], dict[str, str]]:
    entries: list[dict] = []
    seen: set[str] = set()
    texts: list[tuple[str, str]] = []
    sections: list[str] = []
    for label, path in reading_order():
        text = path.read_text(encoding="utf-8")
        texts.append((label, text))
        section = label
        for line in text.split("\n"):
            m = SECTION.match(line)
            if m:
                section = (f"附录 {m.group('num')}" if label.startswith("附录")
                           else f"{m.group('num')}")
                sections.append(section)
                continue
            m = TERM.match(line)
            if not m:
                continue
            term, en = split_term(m.group("term").strip(),
                                  (m.group("en") or "").strip())
            if term in seen:
                continue
            seen.add(term)
            entries.append({
                "term": term,
                "en": en,
                "definition": first_sentence(m.group("body")),
                "where": section,
            })
    rank = {s: i for i, s in enumerate(sections)}
    tail: list[dict] = []
    for term, en, definition, where in EXTRA:
        if term in seen:
            continue
        entry = {"term": term, "en": en, "definition": definition, "where": where}
        if where not in rank:
            if where != "本表":
                raise SystemExit(f"EXTRA 里 {term} 的小节 {where} 在正文里不存在")
            tail.append(entry)
            continue
        # 插到同一节已有条目之后、下一节之前，保持“按定义所在的先后排列”。
        at = next((i for i, e in enumerate(entries)
                   if rank.get(e["where"], -1) > rank[where]), len(entries))
        entries.insert(at, entry)
    entries.extend(tail)
    family = {term: name for name, terms in FAMILIES.items() for term in terms}
    known = {e["term"] for e in entries}
    for term in family:
        if term not in known:
            raise SystemExit(f"FAMILIES 里的 {term} 不在术语表里")
    for e in entries:
        e["family"] = family.get(e["term"], "")
    first: dict[str, str] = {}
    for e in entries:
        key = e["term"].split("（")[0]
        for label, text in texts:
            if key in text:
                first[e["term"]] = label
                break
    return entries, first


def render(entries: list[dict], first: dict[str, str]) -> str:
    lines = [
        "# 术语表",
        "",
        "全书的术语注释按定义所在的先后排列，所以这张表也可以当作一份概念出场顺序来读。"
        "“定义所在”是注释写在哪一节；“首次出现”是这个写法在全书第一次出现的位置，"
        "两者不同，说明读到定义之前已经见过它，回查时先去定义所在那一节。",
        "",
        "“同族”一列标出容易混用的几组词，括号里是把它们放在一起对照的那一节，"
        "分不清同一族里的两个词时先去那里。",
        "",
        "这张表由 `tools/build_glossary.py` 从正文的注释生成，不手工维护。"
        "公式和它们的前提见附录 F。",
        "",
        "| 首选写法 | 英文 | 一句话定义 | 定义所在 | 首次出现 | 同族 |",
        "|---|---|---|---|---|---|",
    ]
    for e in entries:
        lines.append(f"| {e['term']} | {e['en'] or '—'} | {e['definition']} | "
                     f"{e['where']} | {first.get(e['term'], '—')} | "
                     f"{e['family'] or '—'} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    entries, first = collect()
    text = render(entries, first)
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("glossary.md 不是最新的，重跑 python3 tools/build_glossary.py")
            return 1
        print(f"glossary.md 最新，{len(entries)} 条")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {len(entries)} terms to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
