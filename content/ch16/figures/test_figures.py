#!/usr/bin/env python3
"""Figure tests for Chapter 16.

Beyond the shared visual contract, the numeric assertions pin every number drawn
in these figures to code/ch16/kv_capacity.py 与 code/ch15/model-7b-generic.json, so the pictures and the code cannot drift apart. That
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
CHAPTER = FIGURE_DIR.parent / "ch16.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch15"))
sys.path.insert(0, str(ROOT / "code" / "ch16"))
CONFIG = json.loads((ROOT / "code" / "ch15" / "model-7b-generic.json")
                    .read_text(encoding="utf-8"))

FIGURES = {
    "fig16-01_fragmentation.svg": "外部碎片与内部碎片",
    "fig16-02_capacity_waterfall.svg": "容量表的九步",
    "fig16-03_context_inverse.svg": "并发上限与上下文长度成反比",
}

FORBIDDEN = {
    # 16.4 讲的是分配方式，不是总量，也不谈量化
    "fig16-01_fragmentation.svg": ["量化", "INT8"],
    # 16.6 那张表不含质量维度
    "fig16-02_capacity_waterfall.svg": ["质量", "评测集"],
    # 16.7 不点具体显卡型号
    "fig16-03_context_inverse.svg": ["A100", "H100", "GX10"],
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
                self.assertTrue("PingFang SC" in source, "图里缺少这段文字")
                self.assertFalse("Key Takeaway" in source, "图里不该出现这段文字")
                self.assertTrue("关键结论" in source, "图里缺少这段文字")

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
                    self.assertFalse(term in source, "图里不该出现这段文字")

    def test_every_figure_is_referenced_in_the_chapter(self):
        text = CHAPTER.read_text(encoding="utf-8")
        for i, name in enumerate(FIGURES, 1):
            with self.subTest(figure=name):
                self.assertTrue(name in text, f"{name} 没有出现在正文里")
                caption = f"图16-{i}："
                self.assertTrue(caption in text, f"正文缺少图注 {caption}")

    def test_no_em_dash_in_any_figure(self):
        """全书体例：不用破折号。"""
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertFalse("——" in source, "图里不该出现这段文字")


class TestNumbersMatchTheCalculator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import kv_capacity as kc
        cls.kc = kc
        cls.table = dict(layers=32, kv_heads=8, head_dim=128, dtype="fp16",
                         gpu_memory_gib=80, weight_memory_gib=14, overhead_gib=6,
                         avg_context=2300, p99_context=9200, block_size=16)
        cls.report = kc.build_report(**cls.table)

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    # --- 图16-1 ---
    def test_block_waste_numbers_drawn_match(self):
        source = self.svg("fig16-01_fragmentation.svg")
        per_token = self.kc.bytes_per_token(32, 8, 128, 2)
        total = self.kc.kv_budget_bytes(80, 14, 6) / per_token
        small = self.kc.block_accounting(total, 16, per_token, 128)
        large = self.kc.block_accounting(total, 128, per_token, 128)
        self.assertAlmostEqual(small["waste_gib_total"] * 1024, 128.0, places=1)
        self.assertAlmostEqual(large["waste_gib_total"], 1.0, places=2)
        self.assertTrue("约浪费 128 MiB" in source, "图里缺少这段文字")
        self.assertTrue("约浪费 1 GiB" in source, "图里缺少这段文字")

    def test_the_internal_fragment_bound_drawn_matches_the_block_size(self):
        source = self.svg("fig16-01_fragmentation.svg")
        self.assertTrue("块大小 16 时最多 15 个 token 的空间" in source, "图里缺少这段文字")
        self.assertTrue("平均半块" in source, "图里缺少这段文字")

    def test_it_states_the_trade_in_both_directions(self):
        source = self.svg("fig16-01_fragmentation.svg")
        self.assertTrue("浪费没有上界" in source, "图里缺少这段文字")
        self.assertTrue("浪费有上界" in source, "图里缺少这段文字")

    def test_the_case_one_numbers_are_drawn(self):
        source = self.svg("fig16-01_fragmentation.svg")
        self.assertTrue("剩 8 GiB，最大的一块只有 1.2 GiB" in source, "图里缺少这段文字")

    # --- 图16-2 ---
    def test_every_step_of_the_table_is_drawn(self):
        source = self.svg("fig16-02_capacity_waterfall.svg")
        self.assertEqual(self.report["budget"]["kv_budget_gib"], 52.0)
        self.assertEqual(self.report["budget"]["usable_gib"], 72.0)
        self.assertEqual(self.report["total_tokens"], 425984)
        self.assertEqual(self.report["concurrency_avg"], 185)
        self.assertEqual(self.report["recommended"], [129, 148])
        for drawn in ("80 GiB", "72 GiB", "14 GiB", "6 GiB", "52 GiB", "128 KiB",
                      "425984", "2300 token", "185 条", "130~148 条"):
            with self.subTest(drawn=drawn):
                self.assertTrue(drawn in source, "图里缺少这段文字")

    def test_the_four_service_specific_steps_are_flagged(self):
        source = self.svg("fig16-02_capacity_waterfall.svg")
        for step in ("第 1 步", "第 3 步", "第 7 步", "第 9 步"):
            with self.subTest(step=step):
                self.assertTrue(step in source, "图里缺少这段文字")
        self.assertTrue("gpu_memory_utilization" in source, "图里缺少这段文字")
        self.assertTrue("读启动日志" in source, "图里缺少这段文字")

    def test_the_first_step_is_the_utilization_cut_not_the_whole_card(self):
        """16.6 第 1 步：按整张卡起算会把 KV 预算高估 8 GiB。"""
        source = self.svg("fig16-02_capacity_waterfall.svg")
        full = self.kc.kv_budget_bytes(80, 14, 6, utilization=1.0)
        default = self.kc.kv_budget_bytes(80, 14, 6)
        self.assertAlmostEqual((full - default) / self.kc.GIB, 8.0, places=6)
        self.assertTrue("高估 8 GiB" in source, "图里缺少这段文字")

    def test_the_discount_range_matches_the_module_constants(self):
        source = self.svg("fig16-02_capacity_waterfall.svg")
        self.assertEqual(self.kc.DISCOUNT_LOW, 0.70)
        self.assertEqual(self.kc.DISCOUNT_HIGH, 0.80)
        self.assertTrue("按 70%~80% 取" in source, "图里缺少这段文字")

    def test_it_says_the_table_is_a_starting_point_not_a_prediction(self):
        source = self.svg("fig16-02_capacity_waterfall.svg")
        self.assertTrue("不是精确预测" in source, "图里缺少这段文字")

    # --- 图16-3 ---
    def test_all_four_points_on_the_curve_match(self):
        source = self.svg("fig16-03_context_inverse.svg")
        total = self.report["total_tokens"]
        for context, drawn in ((2300, "185 条"), (4600, "92 条"),
                               (9200, "46 条"), (32000, "13 条")):
            with self.subTest(context=context):
                self.assertEqual(f"{self.kc.concurrency(total, context)} 条", drawn)
                self.assertTrue(drawn in source, "图里缺少这段文字")

    def test_the_mixed_distribution_numbers_match(self):
        source = self.svg("fig16-03_context_inverse.svg")
        mix = [(0.97, 2300), (0.03, 32000)]
        report = self.kc.build_report(**(self.table | {"mix": mix}))
        m = report["mixed"]
        self.assertAlmostEqual(m["average_context"], 3191.0, places=1)
        self.assertEqual(m["concurrency_at_mixed_average"], 133)
        self.assertEqual(m["concurrency_if_all_longest"], 13)
        self.assertTrue("混合平均 3191 token  →  133 条" in source, "图里缺少这段文字")
        self.assertTrue("全是长请求时  →  13 条" in source, "图里缺少这段文字")

    def test_the_average_is_explicitly_not_the_ceiling(self):
        source = self.svg("fig16-03_context_inverse.svg")
        self.assertTrue("平均值不是上限" in source, "图里缺少这段文字")
        self.assertTrue("最坏情况下的混合" in source, "图里缺少这段文字")

    def test_the_inverse_relation_holds_in_the_drawn_points(self):
        total = self.report["total_tokens"]
        self.assertEqual(self.kc.concurrency(total, 4600),
                         self.kc.concurrency(total, 2300) // 2)

if __name__ == "__main__":
    unittest.main()
