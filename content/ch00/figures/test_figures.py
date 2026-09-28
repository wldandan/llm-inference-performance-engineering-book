import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


CHAPTER_DIR = Path(__file__).parent.parent
FIGURE_DIR = CHAPTER_DIR / "figures"
SVG_NS = "http://www.w3.org/2000/svg"
EXPECTED_FIGURES = {
    "fig00-01_naive_generation_loop.svg": "朴素的四步生成循环",
    "fig00-02_read_once_write_many.svg": "读题搬一次，答题搬 N 次",
    "fig00-03_batching_and_queueing.svg": "批量摊薄搬运，满载拉长等待",
}
# 这些术语各有首现章节，第 0 章正文与插图都不得出现。
FORBIDDEN_TERMS = [
    "Attention", "KV Cache", "Prefix Cache", "Prefill", "Decode",
    "TTFT", "TPOT", "ITL", "SLO", "Goodput", "带宽", "算力受限",
    "Continuous Batching", "张量",
]


class ChapterZeroFigureTests(unittest.TestCase):
    def test_figure_set_matches_approved_storyboard(self):
        self.assertEqual(
            set(EXPECTED_FIGURES),
            {path.name for path in FIGURE_DIR.glob("*.svg")},
        )

    def test_every_figure_uses_visual_contract(self):
        for filename, expected_title in EXPECTED_FIGURES.items():
            with self.subTest(filename=filename):
                path = FIGURE_DIR / filename
                source = path.read_text(encoding="utf-8")
                root = ET.fromstring(source)
                self.assertEqual(root.attrib.get("width"), "1280")
                self.assertEqual(root.attrib.get("height"), "720")
                self.assertEqual(root.attrib.get("viewBox"), "0 0 1280 720")
                self.assertEqual(root.attrib.get("data-figure-system"), "chapter00-v2")
                self.assertIn("aria-labelledby", root.attrib)
                title = root.find(f"{{{SVG_NS}}}title")
                description = root.find(f"{{{SVG_NS}}}desc")
                self.assertIsNotNone(title)
                self.assertIsNotNone(description)
                self.assertIn(expected_title, title.text or "")
                self.assertGreater(len((description.text or "").strip()), 20)
                self.assertIn("PingFang SC", source)
                self.assertIn("关键结论", source)
                self.assertNotIn("Key Takeaway", source)
                self.assertIn("marker-end", source)
                font_sizes = [int(value) for value in re.findall(r"font-size:\s*(\d+)px", source)]
                self.assertTrue(font_sizes)
                self.assertGreaterEqual(min(font_sizes), 14)
                for term in FORBIDDEN_TERMS:
                    self.assertNotIn(term, source)
                note = path.with_suffix(".figure-note.md")
                self.assertTrue(note.exists())
                note_source = note.read_text(encoding="utf-8")
                self.assertIn("来源段落", note_source)
                self.assertIn("关键结论", note_source)

    def test_naive_loop_is_labelled_and_shows_repeated_history(self):
        source = (FIGURE_DIR / "fig00-01_naive_generation_loop.svg").read_text(encoding="utf-8")
        for label in ["朴素模型", "已写出的全部 token", "第 500 圈"]:
            self.assertIn(label, source)

    def test_chapter_links_three_continuous_figures(self):
        source = (CHAPTER_DIR / "ch00.md").read_text(encoding="utf-8")
        links = re.findall(r"!\[[^\]]*\]\((figures/[^)]+\.svg)\)", source)
        self.assertEqual(links, [f"figures/{name}" for name in EXPECTED_FIGURES])
        self.assertEqual(re.findall(r"图0-(\d+)[：:]", source), ["1", "2", "3"])

    def test_chapter_respects_boundaries(self):
        source = (CHAPTER_DIR / "ch00.md").read_text(encoding="utf-8")
        for term in FORBIDDEN_TERMS + ["盈亏平衡"]:
            self.assertNotIn(term, source)
        self.assertEqual(len(re.findall(r"(?m)^> \*\*", source)), 3)
        self.assertEqual(source.count("——"), 0)
        self.assertIn("默认指稠密模型", source)
        self.assertIn("先用最朴素的方式想象", source)
        self.assertIn("真实系统已经绕开了", source)
        for ordinal in ["第一条规律", "第二条规律", "第三条规律"]:
            self.assertIn(ordinal, source)
        # 只有 0.7 的案例和误区使用三级标题，节内不再切带编号的小节。
        self.assertEqual(re.findall(r"(?m)^### \d", source), [])
        self.assertLessEqual(len(re.findall(r"(?m)^### ", source)), 5)
        self.assertNotIn("## 延伸阅读", source)
        self.assertIn("29.64 ms", source)

    def test_price_table_matches_what_was_actually_checked(self):
        source = (CHAPTER_DIR / "ch00.md").read_text(encoding="utf-8")
        # 0.1 那张表只引用核对过的一家价目表，并写出查询日期与模型数。
        self.assertIn("2026 年 9 月 24 日查询", source)
        self.assertIn("18 个模型", source)
        self.assertIn("输出单价恰好是输入的 5 倍", source)
        self.assertIn("十分之一，最深的到四十分之一", source)
        # 缓存写入溢价必须出现，否则 0.3 那句“便宜得多”没有代价。
        self.assertIn("1.25 倍", source)
        # 两条核对不到的说法不许再出现。
        self.assertNotIn("3 到 5 倍", source)
        self.assertNotIn("五十分之一", source)
        self.assertNotIn("错峰", source)
        self.assertNotIn("几乎不要钱", source)
        # 0.7 案例二用的倍数必须和表里一致。
        self.assertIn("输出单价是输入的 5 倍", source)

    def test_main_line_is_handed_over_explicitly(self):
        source = (CHAPTER_DIR / "ch00.md").read_text(encoding="utf-8")
        self.assertIn("运行 → 测量 → 诊断 → 优化 → 验证 → 上线守护", source)
        self.assertIn("往后每一篇开头都会告诉你走到了主线的哪一步", source)

    def test_every_part_opener_locates_itself_on_the_main_line(self):
        content_dir = CHAPTER_DIR.parent
        openers = sorted(content_dir.glob("part0*.md"))
        self.assertEqual(len(openers), 7)
        for path in openers:
            with self.subTest(part=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("主线位置：", text)
                self.assertIn("和第 0 章的关系：", text)
        # Part 1 还要显式接过第 0 章交出来的那条主线。
        first = (content_dir / "part01.md").read_text(encoding="utf-8")
        self.assertIn("第 0 章交出了一条主线", first)
        self.assertIn("运行 → 测量 → 诊断 → 优化 → 验证 → 上线守护", first)

    def test_part_openers_keep_one_bold_per_paragraph(self):
        content_dir = CHAPTER_DIR.parent
        for path in sorted(content_dir.glob("part0*.md")):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").split("\n"), start=1
            ):
                with self.subTest(part=path.name, line=number):
                    self.assertLessEqual(len(re.findall(r"\*\*[^*]+\*\*", line)), 1)

    def test_every_case_declares_its_provenance(self):
        source = (CHAPTER_DIR / "ch00.md").read_text(encoding="utf-8")
        for case in ["### 案例一", "### 案例二", "### 案例三"]:
            start = source.index(case)
            with self.subTest(case=case):
                self.assertIn("合成设定", source[start : start + 200])

    def test_reading_cost_claim_stays_an_upper_bound(self):
        source = (CHAPTER_DIR / "ch00.md").read_text(encoding="utf-8")
        # 29.64 ms 里还含着写出首 token 和网络，不能整段记在“读 30 个 token”头上。
        self.assertIn("读 30 个 token 连同写出第一个 token", source)
        self.assertNotIn("读 30 个 token，只相当于写三段的时间", source)
        self.assertIn("29.64 ÷ 9.15 ≈ 3.2", source)

    def test_fixed_components_match_the_rest_of_the_book(self):
        content_dir = CHAPTER_DIR.parent
        counts = {}
        for number in range(0, 31):
            path = content_dir / f"ch{number:02d}" / f"ch{number:02d}.md"
            text = path.read_text(encoding="utf-8")
            with self.subTest(chapter=number):
                # 延伸方向是只剩两章在用的旧模板，全书已统一去掉。
                self.assertNotIn("### 延伸方向", text)
            tail = text.split("## 课后练习")[-1]
            counts[number] = len(re.findall(r"(?m)^\d+\. ", tail))
        # 课后练习全书一律 8 题。
        self.assertEqual(sorted(set(counts.values())), [8], counts)
        checklist = re.search(
            r"### 本章 Checklist\n(.*?)(?=\n## |\Z)",
            (CHAPTER_DIR / "ch00.md").read_text(encoding="utf-8"),
            re.S,
        )
        self.assertEqual(len(re.findall(r"(?m)^- \[ \]", checklist.group(1))), 8)



if __name__ == "__main__":
    unittest.main()
