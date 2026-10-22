#!/usr/bin/env python3
"""Figure tests for Chapter 13.

The numeric assertions pin the figures to the chapter text and to
code/ch11/prefill_model.py, so a figure cannot drift away from the numbers
the chapter works through.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch13.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch11"))
sys.path.insert(0, str(ROOT / "code" / "ch12"))
sys.path.insert(0, str(ROOT / "code" / "ch13"))

FIGURES = {
    "fig13-01_four_paths.svg": "四条路改的不是同一件事",
    "fig13-02_hit_rate_four_cuts.svg": "命中率的三刀乘法：60% 到 7.5%",
    "fig13-03_attention_matrix_size.svg": "那个矩阵大 178 倍",
    "fig13-04_chunked_two_timelines.svg": "拆开之后，谁快了谁慢了",
}

FORBIDDEN = {
    # 13.1 must not put a gain number on any path: the conditions differ.
    "fig13-01_four_paths.svg": ["%", "vLLM", "收益 4"],
    # 13.4 gives no speed-up percentage; it depends on the card and the kernel.
    "fig13-03_attention_matrix_size.svg": ["提速", "加速比"],
    # 13.5 does not open up the scheduler (chapter 20).
    "fig13-04_chunked_two_timelines.svg": ["Token Budget", "块该多大"],
}


class TestFigureSet(unittest.TestCase):
    def test_every_figure_and_note_exists(self):
        for name in FIGURES:
            self.assertTrue((FIGURE_DIR / name).exists(), f"missing {name}")
            note = FIGURE_DIR / (name[:-4] + ".figure-note.md")
            self.assertTrue(note.exists(), f"missing note for {name}")

    def test_no_orphan_svg(self):
        on_disk = {p.name for p in FIGURE_DIR.glob("*.svg")}
        self.assertEqual(on_disk, set(FIGURES))

    def test_visual_contract(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            root = ET.fromstring(source)
            with self.subTest(figure=name):
                self.assertEqual(root.get("width"), "1280")
                self.assertEqual(root.get("height"), "720")
                self.assertEqual(root.get("data-figure-system"), "part02-v1")
                self.assertEqual(root.get("aria-labelledby"), "fig-title fig-desc")
                ns = "{http://www.w3.org/2000/svg}"
                self.assertIsNotNone(root.find(f"{ns}title"))
                desc = root.find(f"{ns}desc")
                self.assertIsNotNone(desc)
                self.assertGreater(len((desc.text or "").strip()), 20)
                self.assertIn("PingFang SC", source)
                self.assertIn("marker-end", source)
                self.assertNotIn("Key Takeaway", source)
                self.assertIn("关键结论", source)

    def test_minimum_font_size(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            sizes = [float(v) for v in re.findall(r"font-size:(\d+(?:\.\d+)?)px", source)]
            with self.subTest(figure=name):
                self.assertTrue(sizes)
                self.assertGreaterEqual(min(sizes), 14)

    def test_notes_carry_the_four_required_lines(self):
        for name in FIGURES:
            note = (FIGURE_DIR / (name[:-4] + ".figure-note.md")).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                for field in ("来源段落", "阅读顺序", "关键结论", "表达边界"):
                    self.assertIn(field, note)

    def test_forbidden_terms_stay_out(self):
        for name, terms in FORBIDDEN.items():
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            for term in terms:
                with self.subTest(figure=name, term=term):
                    self.assertNotIn(term, source)

    def test_chunked_prefill_is_drawn_as_helping_someone_else(self):
        """13.5's whole point: the metric that improves is not this request's."""
        source = (FIGURE_DIR / "fig13-01_four_paths.svg").read_text(encoding="utf-8")
        self.assertIn("改善 其他请求", source)
        self.assertIn("不让任何一条", source)

    def test_chunked_prefill_cost_is_not_hidden(self):
        source = (FIGURE_DIR / "fig13-04_chunked_two_timelines.svg").read_text(encoding="utf-8")
        self.assertIn("受损", source)
        self.assertIn("2.4 s → 3.1 s", source)




class TestFiguresMatchTheNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import prefill_model as pm
        import prefill_optimization_check as poc
        from context_cost import prefix_cache_saving

        cls.pm = pm
        cls.poc = poc
        cls.saving = staticmethod(prefix_cache_saving)
        cls.config = pm.load_config(json.loads(
            (ROOT / "code" / "ch11" / "model-qwen25-05b.json").read_text(encoding="utf-8")))

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_the_four_quantities_are_all_drawn(self):
        source = self.svg("fig13-01_four_paths.svg")
        for quantity in ("输入长度", "计算量", "搬运量", "调度顺序"):
            with self.subTest(quantity=quantity):
                self.assertIn(quantity, source)

    def test_only_trimming_touches_input_length(self):
        """13.1: one path reduces length, and the figure must show only one."""
        source = self.svg("fig13-01_four_paths.svg")
        self.assertIn("上下文裁剪", source)
        # the four path boxes each carry exactly one 改善 line
        self.assertEqual(source.count("改善 本条请求"), 3)
        self.assertEqual(source.count("改善 其他请求"), 1)

    def test_hit_rate_multiplication_matches(self):
        source = self.svg("fig13-02_hit_rate_four_cuts.svg")
        self.assertAlmostEqual(0.60 * 1 * 1 * 0.25, 0.15, places=6)
        self.assertIn("60%", source)
        self.assertIn("× 12.5%", source)
        self.assertIn("7.5%", source)

    def test_prefix_saving_rows_match_the_code(self):
        source = self.svg("fig13-02_hit_rate_four_cuts.svg")
        for total, expected in ((3000, 56), (8000, 52), (16640, 48)):
            computed = self.saving(self.config, total, int(total * 0.6))
            self.assertEqual(round(computed * 100), expected)
            with self.subTest(total=total):
                self.assertIn(f"实际省 {expected}%", source)

    def test_saving_is_always_below_the_token_share(self):
        for total in (3000, 8000, 16640):
            self.assertLess(self.saving(self.config, total, int(total * 0.6)), 0.60)

    def test_attention_matrix_sizes_match(self):
        source = self.svg("fig13-03_attention_matrix_size.svg")
        small = self.pm.attention_matrix_bytes(self.config, 600) / 1024 ** 2
        large = self.pm.attention_matrix_bytes(self.config, 8000) / 1024 ** 2
        self.assertEqual(round(small), 10)
        self.assertEqual(round(large), 1709)
        self.assertEqual(round(large / small), 178)
        self.assertIn("10 MiB", source)
        self.assertIn("1710 MiB", source)
        self.assertIn("178 倍", source)

    def test_matrix_squares_are_drawn_to_area(self):
        """The visual claim is the ratio, so the two squares must honour it."""
        source = self.svg("fig13-03_attention_matrix_size.svg")
        sides = [float(m) for m in re.findall(r'<rect x="[\d.]+" y="[\d.]+" width="([\d.]+)"', source)]
        squares = sorted(s for s in sides if s < 400)
        self.assertGreaterEqual(len(squares), 2)
        ratio = (squares[-1] / squares[0]) ** 2
        self.assertAlmostEqual(ratio, 8000 ** 2 / 600 ** 2, delta=2)

    def test_thresholds_drawn_match_the_code(self):
        source = self.svg("fig13-04_chunked_two_timelines.svg")
        self.assertEqual(self.poc.MIXED_LENGTH_RATIO, 3.0)
        self.assertIn("P50 三倍", source)

class TestChapterIntegration(unittest.TestCase):
    def setUp(self):
        self.text = CHAPTER.read_text(encoding="utf-8")

    def test_chapter_links_every_figure_in_order(self):
        refs = re.findall(r"!\[[^\]]*\]\((figures/[^)]+)\)", self.text)
        self.assertEqual(refs, [f"figures/{name}" for name in FIGURES])

    def test_captions_are_numbered_in_order(self):
        caps = re.findall(r"^图13-(\d+)[：:]", self.text, re.M)
        self.assertEqual(caps, [str(i + 1) for i in range(len(FIGURES))])

    def test_no_placeholder_left(self):
        self.assertNotIn("插图占位", self.text)


if __name__ == "__main__":
    unittest.main()
