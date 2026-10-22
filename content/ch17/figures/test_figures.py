#!/usr/bin/env python3
"""Figure tests for Chapter 17.

Beyond the shared visual contract, the numeric assertions pin every number drawn
in these figures to code/ch17/quant_tradeoff.py 与 code/ch15/model-7b-generic.json, so the pictures and the code cannot drift apart. That
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
CHAPTER = FIGURE_DIR.parent / "ch17.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch15"))
sys.path.insert(0, str(ROOT / "code" / "ch17"))
CONFIG = json.loads((ROOT / "code" / "ch15" / "model-7b-generic.json")
                    .read_text(encoding="utf-8"))

FIGURES = {
    "fig17-01_two_ledgers.svg": "权重量化推延迟，KV 量化推容量",
    "fig17-02_benefit_vs_risk.svg": "三项量化手段的收益与质量风险",
}

FORBIDDEN = {
    # 17.2 只算搬运，质量那一半在 17.4，不混在同一张图里
    "fig17-01_two_ledgers.svg": ["评测集", "准确率"],
    # 17.5 排的是顺序，不给具体收益数字，免得被当成承诺
    "fig17-02_benefit_vs_risk.svg": ["14 ms", "370 条"],
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
                caption = f"图17-{i}："
                self.assertTrue(caption in text, f"正文缺少图注 {caption}")

    def test_no_em_dash_in_any_figure(self):
        """全书体例：不用破折号。"""
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertFalse("——" in source, "图里不该出现这段文字")


class TestNumbersMatchTheEstimator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import quant_tradeoff as qt
        cls.qt = qt
        cls.report = qt.estimate(
            params=7e9, layers=32, kv_heads=8, head_dim=128,
            gpu_memory_gib=80, bandwidth_gb_per_s=1000, overhead_gib=6,
            avg_context=2300, weight_dtypes=["fp16", "int8", "int4"],
            kv_dtypes=["fp16", "int8"])

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def combo(self, name: str) -> dict:
        return next(c for c in self.report["combos"] if c["combo"] == name)

    # --- 图17-1 ---
    def test_the_three_step_floors_drawn_match(self):
        source = self.svg("fig17-01_two_ledgers.svg")
        for dtype, drawn in (("fp16", "FP16 14 ms"), ("int8", "INT8  7 ms"),
                             ("int4", "INT4 3.5 ms")):
            floor = self.qt.step_floor_ms(7e9, dtype, 1000)
            with self.subTest(dtype=dtype):
                self.assertAlmostEqual(floor, float(drawn.split()[-2]), places=3)
        self.assertTrue("FP16  14 ms" in source, "图里缺少这段文字")
        self.assertTrue("INT8   7 ms" in source, "图里缺少这段文字")
        self.assertTrue("INT4 3.5 ms" in source, "图里缺少这段文字")

    def test_the_weight_side_concurrency_gain_drawn_matches(self):
        source = self.svg("fig17-01_two_ledgers.svg")
        row = self.combo("weight=int8/kv=fp16")
        self.assertEqual(row["kv_budget_gib"], 59.0)
        self.assertEqual(row["concurrency"], 210)
        self.assertAlmostEqual(row["delta_concurrency"], 0.1351, places=3)
        self.assertTrue("并发只涨 14%" in source, "图里缺少这段文字")
        self.assertTrue("52 → 59 GiB，185 → 210 条" in source, "图里缺少这段文字")

    def test_the_kv_side_numbers_drawn_match(self):
        source = self.svg("fig17-01_two_ledgers.svg")
        fp16 = self.combo("weight=fp16/kv=fp16")
        int8 = self.combo("weight=fp16/kv=int8")
        self.assertEqual(fp16["total_tokens"], 425984)
        self.assertEqual(int8["total_tokens"], 851968)
        self.assertEqual(int8["concurrency"], 370)
        self.assertTrue("42.6 万 → 85.2 万 token，并发 185 → 370 条" in source, "图里缺少这段文字")

    def test_kv_quantization_leaves_the_step_floor_alone(self):
        source = self.svg("fig17-01_two_ledgers.svg")
        self.assertEqual(self.combo("weight=fp16/kv=fp16")["step_floor_ms"],
                         self.combo("weight=fp16/kv=int8")["step_floor_ms"])
        self.assertTrue("单步下限一点没动" in source, "图里缺少这段文字")

    def test_both_halves_name_their_own_target(self):
        source = self.svg("fig17-01_two_ledgers.svg")
        self.assertTrue("瓶颈是 TPOT 就量权重" in source, "图里缺少这段文字")
        self.assertTrue("瓶颈是并发就量 KV" in source, "图里缺少这段文字")

    # --- 图17-2 ---
    def test_all_three_items_are_drawn_in_order(self):
        source = self.svg("fig17-02_benefit_vs_risk.svg")
        for label in ("① KV Cache INT8", "② 权重 INT8", "③ 权重 INT4"):
            with self.subTest(label=label):
                self.assertTrue(label in source, "图里缺少这段文字")

    def test_kv_int8_is_drawn_in_the_low_risk_corner(self):
        """17.5：KV 量化排第一，是因为收益直接、能单独回退，风险和权重 INT8 同档。

        图上不写「风险最低」：那是没有出处的排序，正文已经改掉了。
        """
        source = self.svg("fig17-02_benefit_vs_risk.svg")
        self.assertTrue("风险低" in source, "图里缺少这段文字")
        self.assertTrue("风险最高" in source, "图里缺少这段文字")
        self.assertNotIn("风险最低", source)

    def test_the_two_cheaper_things_are_drawn_first(self):
        source = self.svg("fig17-02_benefit_vs_risk.svg")
        self.assertTrue("按长度分流" in source, "图里缺少这段文字")
        self.assertTrue("查框架开销" in source, "图里缺少这段文字")
        self.assertTrue("没有质量风险" in source, "图里缺少这段文字")

    def test_int4_carries_the_evalset_warning(self):
        source = self.svg("fig17-02_benefit_vs_risk.svg")
        self.assertTrue("没有评测集就不要进这一格" in source, "图里缺少这段文字")

    def test_the_case_three_lesson_is_drawn(self):
        source = self.svg("fig17-02_benefit_vs_risk.svg")
        self.assertTrue("只要把长请求分流出去" in source, "图里缺少这段文字")

if __name__ == "__main__":
    unittest.main()
