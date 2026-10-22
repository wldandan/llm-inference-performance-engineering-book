#!/usr/bin/env python3
"""Figure tests for Chapter 06.

They check the visual contract and the things this chapter's figures must not
say, not that the pictures look nice.
"""

from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch06.md"

FIGURES = {
    "fig06-01_workload_fields.svg": "负载要拆成四组字段",
    "fig06-02_length_tail.svg": "长度分布的尾巴决定了什么",
    "fig06-03_closed_vs_open_loop.svg": "闭环与开环压的不是同一件事",
    "fig06-04_three_workload_shapes.svg": "Chat、RAG、Agent 是三种形状"
}

FORBIDDEN = {
    "fig06-01_workload_fields.svg": ["Prefill", "Decode", "TTFT"],
    "fig06-02_length_tail.svg": ["KV Cache", "GB"],
    "fig06-04_three_workload_shapes.svg": ["Prefill", "显存"]
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
        caps = re.findall(r"^图6-(\d+)[：:]", self.text, re.M)
        self.assertEqual(caps, [str(i + 1) for i in range(len(FIGURES))])

    def test_no_placeholder_left(self):
        self.assertNotIn("插图占位", self.text)

    def test_every_case_number_declares_its_provenance(self):
        # 6.3 与 6.8 的三个案例是全书“闭环测不出排队崩溃”论证的全部数字依据，
        # 按 Part 1 纪律二，没有来源就要写明是合成设定。
        # 6.3 正文一处、6.3 代码块里的标签一处、6.4 闭环吞吐算例一处、
        # 6.5 Agent 累积系数一处、6.8 三个案例各一处。
        self.assertEqual(self.text.count("合成设定"), 7)
        for case in ["### 案例一", "### 案例二", "### 案例三"]:
            start = self.text.index(case)
            body = self.text[start : start + 220]
            self.assertIn("合成设定", body, msg=f"{case} 缺来源标注")
        self.assertIn("不是任何一台机器的实测记录", self.text)
        # 机理不许再挂在那两个数上。
        self.assertIn("由定义就能推出来", self.text)
        self.assertNotIn("很多“压测通过、上线就炸”的案例，根子就在这里", self.text)
