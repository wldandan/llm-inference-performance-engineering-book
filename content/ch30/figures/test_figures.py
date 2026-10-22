#!/usr/bin/env python3
"""Figure tests for Chapter 30.

图30-1 画的是 30.2 那七个阶段和它们之间的依赖。这里核对的是图、正文和
code/ch30/project/verify.py 三者说的是同一套东西：七个阶段名、七个目录、
五项交付物，以及第 0 章那三条规律落在哪个阶段。
"""

from __future__ import annotations

import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch30.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch30" / "project"))

FIGURES = {
    "fig30-01_seven_stages.svg": "七个阶段，以及为什么这个顺序不能打乱",
}

FORBIDDEN = {
    # 30.1 说规模不重要完整性重要，图里不该给一个规模门槛
    "fig30-01_seven_stages.svg": ["至少需要多卡", "推荐模型规模", "唯一顺序"],
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
                caption = f"图30-{i}："
                self.assertIn(caption, text)
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions))

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图30-(\d+)：", text))
        self.assertEqual(found, list(range(1, len(FIGURES) + 1)))

    def test_no_em_dash_and_no_corner_quotes(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertNotIn("——", source)
                self.assertNotIn("「", source)
                self.assertNotIn("」", source)


class TestFigureMatchesTheChapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import verify as vf
        cls.vf = vf
        cls.svg = (FIGURE_DIR / "fig30-01_seven_stages.svg").read_text(
            encoding="utf-8")
        cls.chapter = CHAPTER.read_text(encoding="utf-8")

    def test_seven_stages_are_drawn(self):
        for num in ("一", "二", "三", "四", "五", "六", "七"):
            with self.subTest(stage=num):
                self.assertIn(f">{num}</text>", self.svg)

    def test_the_chapter_ranges_cover_ch0_to_ch29_without_a_gap(self):
        """七个阶段要把 Ch0 到 Ch29 铺满，中间不能有断档。"""
        ranges = re.findall(r"Ch(\d+)–Ch(\d+)", self.svg)
        self.assertEqual(len(ranges), 7)
        bounds = [(int(a), int(b)) for a, b in ranges]
        self.assertEqual(bounds[0][0], 0)
        self.assertEqual(bounds[-1][1], 29)
        for (_, end), (start, _) in zip(bounds, bounds[1:]):
            with self.subTest(after=end):
                self.assertEqual(start, end + 1)

    def test_every_stage_carries_an_acceptance_criterion(self):
        for criterion in ("能说出每个阶段的时间戳来自哪里",
                          "同事拿着这两份文件能重跑出同一批请求",
                          "随便指一条慢请求，能说出它慢在哪一段",
                          "每个收益数字都标注了对应的批量",
                          "门禁能真的拦住一次人为制造的回归"):
            with self.subTest(criterion=criterion):
                self.assertIn(criterion, self.svg)
                self.assertIn(criterion, self.chapter)

    def test_the_three_dependencies_are_the_ones_the_chapter_states(self):
        for line in ("没有 workload 就没有 Baseline",
                     "没有 Baseline 就没有门禁",
                     "没有容量模型就没有成本讨论"):
            with self.subTest(line=line):
                self.assertIn(line, self.svg)
                self.assertIn(line, self.chapter)

    def test_the_three_laws_are_chapter_zero_s_own_words(self):
        """P0-1：三条规律用第 0 章的原话，规律三不能漏，Part 4–6 的锚名不能顶替。"""
        for law, stages in (("写比读贵", "阶段四、五"),
                            ("批量摊薄搬运，满载拉长等待", "阶段五、六、七"),
                            ("只有有用的产出才算数", "阶段六、七与报告")):
            with self.subTest(law=law):
                self.assertIn(law, self.svg)
                self.assertIn(stages, self.svg)
                self.assertIn(law, self.chapter)
                self.assertIn(stages, self.chapter)
        # 搬运下限会作为规律一的判据出现（TPOT 实测与它之比），另外两个锚名
        # 不该出现在规律那一栏里。
        for anchor in ("排队与放大", "稳态与余量"):
            with self.subTest(anchor=anchor):
                self.assertNotIn(anchor, self.svg)

    def test_the_seven_stage_directories_exist_in_the_scaffold(self):
        """图里画七个阶段，脚手架就得有七个目录，否则图是空的。"""
        self.assertEqual(len(self.vf.PROJECT_FILES), 7)
        project = ROOT / "code" / "ch30" / "project"
        for name in self.vf.PROJECT_FILES:
            with self.subTest(stage=name):
                self.assertTrue((project / name).is_dir())

    def test_it_names_the_deliverable_that_gets_underestimated(self):
        self.assertIn("可解释", self.svg)
        self.assertIn("第三项是最容易被低估的", self.chapter)

    def test_it_does_not_promise_a_scale(self):
        """30.1：规模不重要，完整性重要。"""
        self.assertNotIn("至少需要", self.svg)


if __name__ == "__main__":
    unittest.main()
