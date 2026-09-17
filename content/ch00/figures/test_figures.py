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


if __name__ == "__main__":
    unittest.main()
