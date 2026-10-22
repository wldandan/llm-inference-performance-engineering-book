#!/usr/bin/env python3
"""Figure tests for Chapter 18.

Beyond the shared visual contract, the numeric assertions pin every number drawn
in these figures to code/ch18/decode_optimization_check.py 与那份合成的接受率样例, so the pictures and the code cannot drift apart. That
is what caught two wrong numbers in Chapter 11 during the 2026-09-22 review.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch18.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch15"))
sys.path.insert(0, str(ROOT / "code" / "ch18"))
CONFIG = json.loads((ROOT / "code" / "ch15" / "model-7b-generic.json")
                    .read_text(encoding="utf-8"))

FIGURES = {
    "fig18-01_acceptance_breakeven.svg": "投机解码的收益比与盈亏线",
    "fig18-02_cuda_graph_timeline.svg": "CUDA Graph 让 kernel 空隙消失",
}

FORBIDDEN = {
    # 18.3 不给行业平均接受率，那个数不可迁移
    "fig18-01_acceptance_breakeven.svg": ["行业平均", "通常在 2 到 3"],
    # 18.4 那条线是算出来的，不该出现写死的 30B
    "fig18-02_cuda_graph_timeline.svg": ["写死 30B", "分界在 30B"],
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

    def test_every_figure_is_referenced_in_the_chapter(self):
        text = CHAPTER.read_text(encoding="utf-8")
        for i, name in enumerate(FIGURES, 1):
            with self.subTest(figure=name):
                self.assertTrue(name in text, f"{name} 没有出现在正文里")
                caption = f"图18-{i}："
                self.assertTrue(caption in text, f"正文缺少图注 {caption}")

    def test_no_em_dash_in_any_figure(self):
        """全书体例：不用破折号。"""
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertNotIn("——", source)


class TestNumbersMatchTheChecker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import decode_optimization_check as dc
        cls.dc = dc
        cls.acceptance = json.loads(
            (ROOT / "content" / "ch18" / "evidence"
             / "draft-acceptance-sample.json").read_text(encoding="utf-8"))

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    # --- 图18-1 ---
    def test_the_break_even_line_drawn_matches_the_formula(self):
        source = self.svg("fig18-01_acceptance_breakeven.svg")
        line = self.dc.spec_break_even(4, 0.1)
        self.assertAlmostEqual(line, 1.4, places=6)
        self.assertTrue("盈亏线 a = 1 + k×c = 1.4" in source, "图里缺少这段文字")

    def test_all_four_plotted_gains_match_the_formula(self):
        source = self.svg("fig18-01_acceptance_breakeven.svg")
        for a in (1.1, 1.3, 3.2, 3.6):
            drawn = f"{a} → {self.dc.spec_gain(a, 4, 0.1):.2f} 倍"
            with self.subTest(a=a):
                self.assertTrue(drawn in source, f"图里缺少 {drawn}")

    def test_the_two_real_scenarios_come_from_the_sample(self):
        source = self.svg("fig18-01_acceptance_breakeven.svg")
        chat = next(s for s in self.acceptance["other_scenarios"]
                    if s["scenario"] == "customer-service-chat")
        self.assertEqual(chat["mean_accepted"], 1.3)
        self.assertEqual(self.acceptance["mean_accepted"], 3.6)
        self.assertTrue("客服对话（18.8 案例一）" in source, "图里缺少这段文字")
        self.assertTrue("代码补全（18.8 案例一）" in source, "图里缺少这段文字")

    def test_the_two_scenarios_land_on_opposite_sides_of_the_line(self):
        line = self.dc.spec_break_even(self.acceptance["k"],
                                       self.acceptance["draft_cost_ratio"])
        chat = next(s for s in self.acceptance["other_scenarios"]
                    if s["scenario"] == "customer-service-chat")
        self.assertLess(chat["mean_accepted"], line)
        self.assertGreater(self.acceptance["mean_accepted"], line)

    def test_it_says_below_the_line_is_a_net_loss(self):
        source = self.svg("fig18-01_acceptance_breakeven.svg")
        self.assertTrue("净亏损，不是收益小" in source, "图里缺少这段文字")

    def test_the_denominator_is_explained_in_both_halves(self):
        source = self.svg("fig18-01_acceptance_breakeven.svg")
        self.assertTrue("1 = 验证" in source, "图里缺少这段文字")
        self.assertTrue("k × c = 草稿的时间" in source, "图里缺少这段文字")

    def test_the_premise_failure_is_drawn_as_a_premise_not_a_bug(self):
        source = self.svg("fig18-01_acceptance_breakeven.svg")
        self.assertTrue("不是式子失灵，是式子的前提失效" in source, "图里缺少这段文字")

    def test_it_says_the_number_does_not_transfer(self):
        source = self.svg("fig18-01_acceptance_breakeven.svg")
        self.assertTrue("完全不可迁移" in source, "图里缺少这段文字")

    # --- 图18-2 ---
    def test_the_launch_shares_drawn_match_the_module(self):
        source = self.svg("fig18-02_cuda_graph_timeline.svg")
        self.assertAlmostEqual(self.dc.launch_share(7e9, 1000), 0.0357, places=4)
        self.assertAlmostEqual(self.dc.launch_share(30e9, 1000), 0.0083, places=4)
        self.assertTrue("0.5 ÷ 14 = 3.6%" in source, "图里缺少这段文字")
        self.assertTrue("0.5 ÷ 60 = 0.8%" in source, "图里缺少这段文字")

    def test_the_threshold_drawn_matches_the_derivation(self):
        source = self.svg("fig18-02_cuda_graph_timeline.svg")
        for bandwidth, drawn in ((1000, "1000 GB/s → 25B"),
                                 (2039, "2039 GB/s → 51B")):
            threshold = self.dc.cuda_graph_threshold_params(bandwidth)
            with self.subTest(bandwidth=bandwidth):
                self.assertEqual(f"{bandwidth} GB/s → {threshold / 1e9:.0f}B", drawn)
                self.assertTrue(drawn in source, f"图里缺少 {drawn}")

    def test_the_launch_constant_drawn_matches_the_module(self):
        source = self.svg("fig18-02_cuda_graph_timeline.svg")
        self.assertEqual(self.dc.LAUNCH_MS_PER_STEP, 0.5)
        self.assertEqual(self.dc.CUDA_GRAPH_SHARE_FLOOR, 0.01)
        self.assertTrue("0.5 ÷ 下限 = 1%  →  下限 50 ms" in source, "图里缺少这段文字")

    def test_it_admits_the_timeline_is_not_to_scale(self):
        """真实比例下那 0.5 ms 只占 3.6%，画出来看不见，图里必须说破。"""
        source = self.svg("fig18-02_cuda_graph_timeline.svg")
        self.assertTrue("不按比例" in source, "图里缺少这段文字")
        self.assertTrue("画不出来" in source, "图里缺少这段文字")

    def test_the_threshold_is_stated_as_a_property_of_the_card(self):
        source = self.svg("fig18-02_cuda_graph_timeline.svg")
        self.assertTrue("分界线是卡的属性，不是常数" in source, "图里缺少这段文字")

if __name__ == "__main__":
    unittest.main()
