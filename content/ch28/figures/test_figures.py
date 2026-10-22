#!/usr/bin/env python3
"""Figure tests for Chapter 28.

图28-1 的两条曲线、两个落点和右上那组阈值建议，都由 code/ch28/perf_gate.py 在构建
时算出来。这里最要紧的一组是把 1.26 倍和 1.89 倍分开核对：正文的论证靠的正是这
两个数不是同一个数。
"""

from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch28.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch28"))

FIGURES = {
    "fig28-01_compounding.svg": "每一次都在阈值下面，累积起来不在",
}

FORBIDDEN = {
    # 28.3 说阈值要从自己的变异系数推，图里不该给一个通用推荐值
    "fig28-01_compounding.svg": ["推荐阈值统一", "行业标准阈值",
                                 "半年必然翻倍"],
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
                self.assertEqual(root.get("aria-labelledby"),
                                 "fig-title fig-desc")
                ns = "{http://www.w3.org/2000/svg}"
                self.assertIsNotNone(root.find(f"{ns}title"))
                desc = root.find(f"{ns}desc")
                self.assertIsNotNone(desc)
                self.assertGreater(len((desc.text or "").strip()), 20)
                self.assertIn("PingFang SC", source)
                self.assertIn("关键结论", source)

    def test_minimum_font_size(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            sizes = [float(v) for v in
                     re.findall(r"font-size:(\d+(?:\.\d+)?)px", source)]
            with self.subTest(figure=name):
                self.assertGreaterEqual(min(sizes), 14)

    def test_notes_carry_the_four_required_lines(self):
        for name in FIGURES:
            note = (FIGURE_DIR / (name[:-4] + ".figure-note.md")).read_text(
                encoding="utf-8")
            for field in ("来源段落", "阅读顺序", "关键结论", "表达边界"):
                with self.subTest(figure=name, field=field):
                    self.assertIn(field, note)

    def test_forbidden_terms_stay_out(self):
        for name, terms in FORBIDDEN.items():
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            for term in terms:
                with self.subTest(figure=name, term=term):
                    self.assertNotIn(term, source)

    def test_every_figure_is_referenced_and_numbered_in_order(self):
        text = CHAPTER.read_text(encoding="utf-8")
        positions = []
        for i, name in enumerate(FIGURES, 1):
            with self.subTest(figure=name):
                self.assertIn(name, text)
                caption = f"图28-{i}："
                self.assertIn(caption, text)
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions))

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图28-(\d+)：", text))
        self.assertEqual(found, list(range(1, len(FIGURES) + 1)))

    def test_no_em_dash_and_no_corner_quotes(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertNotIn("——", source)
                self.assertNotIn("「", source)
                self.assertNotIn("」", source)


class TestFigureMatchesTheCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import perf_gate as pg
        cls.pg = pg
        cls.five = pg.drift([0.05, 0.04, 0.06, 0.05, 0.04], threshold=0.08)
        cls.half_year = pg.drift([0.05] * 13, threshold=0.08)
        cls.svg = (FIGURE_DIR / "fig28-01_compounding.svg").read_text(
            encoding="utf-8")

    def test_the_five_steps_are_all_under_the_gate_threshold(self):
        self.assertTrue(self.five["all_within_threshold"])
        self.assertEqual(self.five["steps_over_threshold"], [])
        for step in (0.05, 0.04, 0.06):
            with self.subTest(step=step):
                self.assertIn(f"{step:.0%}", self.svg)

    def test_the_five_step_product_is_drawn(self):
        self.assertAlmostEqual(self.five["cumulative"], 1.2637, places=3)
        self.assertIn(f"5 次 = {self.five['cumulative']:.2f} 倍", self.svg)

    def test_the_thirteen_step_product_is_drawn(self):
        """两周一次发布，26 周是 13 次：1.05^13 ≈ 1.89。"""
        self.assertAlmostEqual(self.half_year["cumulative"], 1.886, places=3)
        self.assertIn(f"13 次 = {self.half_year['cumulative']:.2f} 倍", self.svg)

    def test_the_two_numbers_are_kept_apart(self):
        """正文的论证靠的是 1.26 和 1.89 不是同一个数。"""
        self.assertNotAlmostEqual(self.five["cumulative"],
                                  self.half_year["cumulative"], places=1)
        self.assertIn("两个数不能混", self.svg)

    def test_the_half_year_one_approaches_the_doubling_line(self):
        self.assertLess(self.five["cumulative"], 1.3)
        self.assertGreater(self.half_year["cumulative"], 1.85)
        self.assertIn("翻倍线", self.svg)

    def test_the_steps_to_double_match(self):
        self.assertIn(f"{self.pg.steps_to_double(0.05):.1f} 次", self.svg)
        self.assertIn(f"{self.pg.steps_to_double(0.08):.1f} 次", self.svg)

    def test_the_threshold_rule_is_the_one_from_28_3(self):
        bad = self.pg.threshold_advice(0.09)
        good = self.pg.threshold_advice(0.026)
        self.assertGreater(bad["min_usable"], 0.05)
        self.assertLessEqual(good["min_usable"], 0.08)
        self.assertIn(f"推荐 {good['recommended']:.0%}", self.svg)
        self.assertIn("单指标误报约 1.5%", self.svg)
        self.assertIn("10% 回归检出约 83%", self.svg)

    def test_the_default_p95_threshold_is_above_the_five_steps(self):
        """图里那条 8% 的线不是随手画的：它高于五步里的每一步。"""
        self.assertTrue(all(s < 0.08 for s in (0.05, 0.04, 0.06)))
        self.assertIn("门禁阈值 8%", self.svg)

    def test_synthetic_setting_is_labelled(self):
        self.assertIn("合成设定", self.svg)

    def test_the_chapter_states_the_same_numbers(self):
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("1.05 × 1.04 × 1.06 × 1.05 × 1.04 = 1.26", chapter)
        self.assertIn("1.05^13 ≈ 1.89", chapter)


if __name__ == "__main__":
    unittest.main()
