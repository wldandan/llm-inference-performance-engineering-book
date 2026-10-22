#!/usr/bin/env python3
"""Figure tests for Chapter 12.

The numeric assertions pin the figures to code/ch12/context_cost.py, so a
figure cannot drift away from the bill the chapter computes.
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
CHAPTER = FIGURE_DIR.parent / "ch12.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch11"))
sys.path.insert(0, str(ROOT / "code" / "ch12"))

FIGURES = {
    "fig12-01_prompt_segments.svg": "prompt 的五段各由谁决定",
    "fig12-02_quality_vs_cost.svg": "拐点在 5，不在质量最高的 10",
    "fig12-03_agent_ladder.svg": "Agent 的上下文是一条阶梯",
}

FORBIDDEN = {
    # 12.2 draws the cost side only.
    "fig12-01_prompt_segments.svg": ["质量分", "命中率"],
    # 12.5 does not open up compression strategy (chapter 24) or memory (16).
    "fig12-03_agent_ladder.svg": ["摘要策略", "显存", "KV Cache"],
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

    def test_quality_scores_are_marked_as_illustrative(self):
        """12.4: quality must never be presented as a measured result."""
        source = (FIGURE_DIR / "fig12-02_quality_vs_cost.svg").read_text(encoding="utf-8")
        self.assertIn("示意值", source)


class TestFiguresMatchTheBill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import context_cost as cc
        from prefill_model import load_config

        cls.cc = cc
        cls.config = load_config(json.loads(
            (ROOT / "code" / "ch11" / "model-qwen25-05b.json").read_text(encoding="utf-8")))
        cls.spec = json.loads(
            (ROOT / "code" / "ch12" / "rag-prompt.json").read_text(encoding="utf-8"))

    def bill(self, items: int):
        doc = copy.deepcopy(self.spec)
        doc["segments"][2]["items"] = items
        return self.cc.build_bill(doc, self.config)

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_segment_tokens_drawn_match(self):
        source = self.svg("fig12-01_prompt_segments.svg")
        bill = self.bill(10)
        self.assertEqual(bill["totals"]["input_tokens"], 2630)
        self.assertIn("2630 token", source)
        for row in bill["segments"]:
            if row["tokens"]:
                with self.subTest(segment=row["name"]):
                    self.assertIn(f"{row['tokens']} token", source)

    def test_cacheable_prefix_drawn_matches(self):
        source = self.svg("fig12-01_prompt_segments.svg")
        for items, share in ((3, 49), (10, 23)):
            bill = self.bill(items)
            self.assertEqual(bill["cacheable"]["prefix_tokens"], 600)
            self.assertEqual(round(bill["cacheable"]["prefix_share_of_tokens"] * 100), share)
            self.assertIn(f"{share}%", source)
        self.assertIn("可缓存前缀 600 token", source)

    def test_the_630_vs_600_distinction_is_drawn(self):
        """The trap 12.2 warns about must be visible in the picture."""
        source = self.svg("fig12-01_prompt_segments.svg")
        self.assertIn("630", source)
        self.assertIn("600", source)
        self.assertIn("前缀", source)

    def test_top_k_table_drawn_matches(self):
        source = self.svg("fig12-02_quality_vs_cost.svg")
        for items, ms in ((3, "320"), (5, "434"), (10, "738"), (20, "1434")):
            bill = self.bill(items)
            self.assertEqual(f"{bill['totals']['estimated_ttft_ms']:.0f}", ms)
            with self.subTest(items=items):
                self.assertIn(f"{ms} ms", source)
                self.assertIn(f"{bill['totals']['input_tokens']} token", source)

    def test_knee_is_drawn_at_five_not_ten(self):
        source = self.svg("fig12-02_quality_vs_cost.svg")
        self.assertIn("拐点", source)
        self.assertIn("K = 5", source)
        self.assertIn("17.5", source)

    def test_agent_ladder_sums_to_14500(self):
        source = self.svg("fig12-03_agent_ladder.svg")
        steps = [600, 1400, 2600, 4100, 5800]
        self.assertEqual(sum(steps), 14500)
        for tok in steps:
            self.assertIn(f"{tok} token", source)
        self.assertIn("14500 token", source)
        self.assertIn("3000 token", source)
        self.assertEqual(round(14500 / 3000, 1), 4.8)
        self.assertIn("4.8 倍", source)


class TestChapterIntegration(unittest.TestCase):
    def setUp(self):
        self.text = CHAPTER.read_text(encoding="utf-8")

    def test_chapter_links_every_figure_in_order(self):
        refs = re.findall(r"!\[[^\]]*\]\((figures/[^)]+)\)", self.text)
        self.assertEqual(refs, [f"figures/{name}" for name in FIGURES])

    def test_captions_are_numbered_in_order(self):
        caps = re.findall(r"^图12-(\d+)[：:]", self.text, re.M)
        self.assertEqual(caps, [str(i + 1) for i in range(len(FIGURES))])

    def test_no_placeholder_left(self):
        self.assertNotIn("插图占位", self.text)


if __name__ == "__main__":
    unittest.main()
