#!/usr/bin/env python3
"""Figure tests for Chapter 07.

They check the visual contract and the things this chapter's figures must not
say, not that the pictures look nice.
"""

from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch07.md"

FIGURES = {
    "fig07-01_three_runs_and_the_line.svg": "三轮结果与可识别线",
    "fig07-02_measurement_window.svg": "测量窗口的两端与窗外那几段",
    "fig07-03_cache_inflated_baseline.svg": "被缓存抬高的 Baseline",
    "fig07-04_baseline_four_blocks.svg": "Baseline 报告的四块与缺一块的后果"
}

FORBIDDEN = {
    "fig07-01_three_runs_and_the_line.svg": ["置信区间"],
    "fig07-02_measurement_window.svg": ["Decode", "KV Cache"]
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
                title = root.find(f"{ns}title")
                desc = root.find(f"{ns}desc")
                self.assertIsNotNone(title)
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


class TestChapterIntegration(unittest.TestCase):
    def setUp(self):
        self.text = CHAPTER.read_text(encoding="utf-8")

    def test_chapter_links_every_figure_in_order(self):
        refs = re.findall(r"!\[[^\]]*\]\((figures/[^)]+)\)", self.text)
        self.assertEqual(refs, [f"figures/{name}" for name in FIGURES])

    def test_captions_are_numbered_in_order(self):
        caps = re.findall(r"^图7-(\d+)[：:]", self.text, re.M)
        self.assertEqual(caps, [str(i + 1) for i in range(len(FIGURES))])

    def test_no_placeholder_left(self):
        self.assertNotIn("插图占位", self.text)
