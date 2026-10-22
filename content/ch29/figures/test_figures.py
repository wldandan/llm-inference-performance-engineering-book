#!/usr/bin/env python3
"""Figure tests for Chapter 29.

图29-1 两栏的内容都来自 code/ch29/release_check.py 跑 release-docs-seam.json 的结果。
所以这里核对的是：图上画着九项全绿、结论不通过，而脚本给出的正是这个结论。图和
脚本对不上时，坏的是图。
"""

from __future__ import annotations

import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch29.md"
EV = FIGURE_DIR.parent / "evidence"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch29"))

FIGURES = {
    "fig29-01_seams.svg": "九项全绿，评审仍然不通过",
}

FORBIDDEN = {
    # 29.1 说评审的价值在交叉检查，图里不该把清单说成充分条件
    "fig29-01_seams.svg": ["九项齐全即可上线", "完备清单", "覆盖所有接缝"],
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
                caption = f"图29-{i}："
                self.assertIn(caption, text)
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions))

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图29-(\d+)：", text))
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
        import release_check as rc
        cls.rc = rc
        cls.docs = json.loads(
            (EV / "release-docs-seam.json").read_text(encoding="utf-8"))
        cls.result = rc.review(cls.docs)
        cls.svg = (FIGURE_DIR / "fig29-01_seams.svg").read_text(
            encoding="utf-8")

    def test_all_nine_labels_are_drawn(self):
        for _, label in self.rc.CHECKLIST:
            with self.subTest(item=label):
                self.assertIn(label, self.svg)

    def test_the_checklist_really_is_all_green(self):
        self.assertEqual(self.result["checklist"]["missing"], [])
        self.assertIn("全绿", self.svg)
        self.assertNotIn("×", self.svg)

    def test_all_five_seams_are_drawn(self):
        for _, left, right in self.rc.CROSS_CHECKS:
            with self.subTest(seam=left):
                self.assertIn(left, self.svg)
                self.assertIn(right, self.svg)

    def test_exactly_one_seam_is_marked_mismatched(self):
        self.assertEqual(self.result["cross_check"]["mismatched"],
                         ["context_length"])
        self.assertEqual(self.svg.count(">不一致</text>"), 1)
        self.assertEqual(self.svg.count(">一致</text>"), 4)

    def test_the_two_lengths_are_drawn(self):
        row = next(r for r in self.result["cross_check"]["rows"]
                   if r["key"] == "context_length")
        self.assertIn(f"{row['left_value']:.0f} 对 {row['right_value']:.0f}",
                      self.svg)

    def test_the_consequence_is_drawn_not_just_the_mismatch(self):
        """29.8 案例一的教训是「多要三张卡」，不是「两个数不一样」。"""
        row = next(r for r in self.result["cross_check"]["rows"]
                   if r["key"] == "context_length")
        c = row["consequence"]
        self.assertEqual(c["instances_needed"], 11)
        self.assertIn(f"{c['instances_in_model']} 张卡实际要 "
                      f"{c['instances_needed']} 张", self.svg)

    def test_the_verdict_drawn_is_the_one_the_script_gives(self):
        self.assertEqual(self.result["verdict"], "不通过")
        self.assertIn(f"结论是{self.result['verdict']}", self.svg)

    def test_it_names_the_blind_spot_29_8_names(self):
        self.assertIn("接缝处正好是所有人的盲区", self.svg)

    def test_synthetic_setting_is_labelled_in_the_source_document(self):
        self.assertIn("合成设定", self.docs["_note"])

    def test_the_chapter_states_the_same_two_lengths(self):
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("平均上下文是 12000", chapter)
        self.assertIn("平均上下文实际是 16000", chapter)


if __name__ == "__main__":
    unittest.main()
