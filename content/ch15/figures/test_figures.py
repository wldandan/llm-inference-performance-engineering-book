#!/usr/bin/env python3
"""Figure tests for Chapter 15.

Beyond the shared visual contract, the numeric assertions pin every number drawn
in these figures to code/ch15/decode_model.py 与 code/ch15/model-7b-generic.json, so the pictures and the code cannot drift apart. That
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
CHAPTER = FIGURE_DIR.parent / "ch15.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch15"))

CONFIG = json.loads((ROOT / "code" / "ch15" / "model-7b-generic.json")
                    .read_text(encoding="utf-8"))

FIGURES = {
    "fig15-01_intensity_axis.svg": "算术强度数轴上 Decode 的位置",
    "fig15-02_step_breakdown.svg": "一步 Decode 的时间构成与实测的差",
    "fig15-03_batch_free_lunch.svg": "批量的免费区间与三处边界",
    "fig15-04_context_climb.svg": "单步耗时随生成长度的爬升",
}

FORBIDDEN = {
    # 15.2 讲的是比值，不是某张卡的容量
    "fig15-01_intensity_axis.svg": ["GiB", "并发"],
    # 15.3 的下限里没有 KV，那是 15.7 的事
    "fig15-02_step_breakdown.svg": ["KV 搬运 0.54"],
    # 免费区间那张图不谈质量
    "fig15-03_batch_free_lunch.svg": ["质量", "量化"],
    # 15.7 不画 Prefill 的公式
    "fig15-04_context_climb.svg": ["交叉点 16640", "S × ("],
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
                caption = f"图15-{i}："
                self.assertTrue(caption in text, f"正文缺少图注 {caption}")

    def test_no_em_dash_in_any_figure(self):
        """全书体例：不用破折号。"""
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertFalse("——" in source, "图里不该出现这段文字")


class TestNumbersMatchTheModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import decode_model as dm
        cls.dm = dm

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    # --- 图15-1 ---
    def test_the_three_intensities_drawn_match_the_identity(self):
        source = self.svg("fig15-01_intensity_axis.svg")
        self.assertEqual(self.dm.decode_arithmetic_intensity(1, 2), 1.0)
        self.assertEqual(self.dm.decode_arithmetic_intensity(1, 1), 2.0)
        self.assertEqual(self.dm.decode_arithmetic_intensity(1, 0.5), 4.0)
        self.assertTrue("FP16 是 1 · INT8 是 2 · INT4 是 4" in source, "图里缺少这段文字")

    def test_the_balance_point_drawn_matches_the_a100_pair(self):
        source = self.svg("fig15-01_intensity_axis.svg")
        balance = self.dm.hardware_balance_point(self.dm.A100_PEAK_TFLOPS,
                                                 self.dm.A100_BANDWIDTH_GB_PER_S)
        self.assertEqual(f"{balance:.0f}", "153")
        self.assertTrue("A100 分界点 153" in source, "图里缺少这段文字")

    def test_it_says_the_identity_is_independent_of_model_size(self):
        self.assertIn("与模型多大无关", self.svg("fig15-01_intensity_axis.svg"))

    def test_it_says_quantization_cannot_push_far_enough(self):
        source = self.svg("fig15-01_intensity_axis.svg")
        self.assertTrue("推不了多远" in source, "图里缺少这段文字")
        self.assertTrue("先撑不住的是质量" in source, "图里缺少这段文字")

    # --- 图15-2 ---
    def test_the_floor_drawn_matches_the_division(self):
        source = self.svg("fig15-02_step_breakdown.svg")
        floor = self.dm.step_floor_ms(self.dm.weight_bytes(7e9, 2), 1000)
        self.assertEqual(f"{floor:.0f}", "14")
        self.assertTrue("理论下限 14 ms（只有权重）" in source, "图里缺少这段文字")

    def test_the_three_segments_sum_to_the_measured_value(self):
        source = self.svg("fig15-02_step_breakdown.svg")
        self.assertAlmostEqual(14.0 + 0.5 + 2.5, 17.0, places=6)
        self.assertTrue("实测 17 ms" in source, "图里缺少这段文字")

    def test_the_ratio_drawn_matches_and_reads_bandwidth_bound(self):
        source = self.svg("fig15-02_step_breakdown.svg")
        self.assertTrue("比值 1.21" in source, "图里缺少这段文字")
        self.assertIn("带宽受限", self.dm.read_ratio(17.0 / 14.0))

    def test_it_says_cuda_graph_only_treats_the_launch_half(self):
        source = self.svg("fig15-02_step_breakdown.svg")
        self.assertTrue("只治 kernel 启动那 0.5 ms" in source, "图里缺少这段文字")
        self.assertTrue("引擎侧那 2.5 ms 它治不了" in source, "图里缺少这段文字")

    def test_it_says_the_3ms_is_paid_every_step(self):
        source = self.svg("fig15-02_step_breakdown.svg")
        self.assertTrue("3 ms × 500 步 = 1.5 秒" in source, "图里缺少这段文字")

    # --- 图15-3 ---
    def test_the_crossover_batch_drawn_matches(self):
        source = self.svg("fig15-03_batch_free_lunch.svg")
        cross = self.dm.crossover_batch(self.dm.A100_PEAK_TFLOPS,
                                        self.dm.A100_BANDWIDTH_GB_PER_S, 2)
        self.assertEqual(f"{cross:.0f}", "153")
        self.assertTrue("交叉批量 153" in source, "图里缺少这段文字")

    def test_the_two_endpoint_numbers_drawn_match_the_model(self):
        source = self.svg("fig15-03_batch_free_lunch.svg")
        one = self.dm.build_point(CONFIG, 1, 512, bandwidth_gb_per_s=1000)
        thirty_two = self.dm.build_point(CONFIG, 32, 512, bandwidth_gb_per_s=1000)
        self.assertEqual(f"{one['throughput_tps']:.0f}", "71")
        self.assertEqual(f"{thirty_two['throughput_tps']:.0f}", "1982")
        self.assertTrue("71" in source, "图里缺少这段文字")
        self.assertTrue("1982" in source, "图里缺少这段文字")
        self.assertEqual(f"{one['tpot_ms']:.1f}", "14.1")
        self.assertEqual(f"{thirty_two['tpot_ms']:.1f}", "16.1")
        self.assertTrue("14.1 涨到 16.1 ms" in source, "图里缺少这段文字")

    def test_the_throughput_multiple_drawn_matches(self):
        source = self.svg("fig15-03_batch_free_lunch.svg")
        one = self.dm.build_point(CONFIG, 1, 512, bandwidth_gb_per_s=1000)
        thirty_two = self.dm.build_point(CONFIG, 32, 512, bandwidth_gb_per_s=1000)
        ratio = thirty_two["throughput_tps"] / one["throughput_tps"]
        self.assertEqual(f"{ratio:.0f}", "28")
        self.assertTrue("吞吐涨 28 倍" in source, "图里缺少这段文字")

    def test_all_three_boundaries_are_drawn(self):
        source = self.svg("fig15-03_batch_free_lunch.svg")
        for label in ("KV 显存装不下", "滑向算力受限", "Attention 不摊薄"):
            with self.subTest(label=label):
                self.assertTrue(label in source, "图里缺少这段文字")

    def test_it_admits_the_model_fails_past_the_crossover(self):
        """两条曲线只算搬运，所以越过交叉批量之后它们不再是预测。"""
        source = self.svg("fig15-03_batch_free_lunch.svg")
        self.assertTrue("估算模型自己失效的地方" in source, "图里缺少这段文字")

    def test_it_explains_why_the_panels_are_stacked(self):
        source = self.svg("fig15-03_batch_free_lunch.svg")
        self.assertTrue("不叠成双纵轴" in source, "图里缺少这段文字")

    # --- 图15-4 ---
    def test_the_kv_numbers_drawn_match_the_model(self):
        source = self.svg("fig15-04_context_climb.svg")
        point = self.dm.build_point(CONFIG, 32, 8000, bandwidth_gb_per_s=1000)
        self.assertEqual(f"{point['kv_gib_per_step']:.0f}", "31")
        self.assertTrue("KV 31 GiB 已超过权重 13 GiB" in source, "图里缺少这段文字")
        self.assertTrue(point["kv_dominates"])

    def test_the_weight_size_in_binary_is_drawn_not_the_decimal_one(self):
        """图里讲的是显存占用的对比，所以用二进制的 13 GiB 而不是 14 GB。"""
        source = self.svg("fig15-04_context_climb.svg")
        self.assertEqual(f"{self.dm.weight_bytes(7e9, 2) / 1024 ** 3:.0f}", "13")
        self.assertTrue("13 GiB" in source, "图里缺少这段文字")

    def test_the_floor_line_is_marked_as_length_independent(self):
        source = self.svg("fig15-04_context_climb.svg")
        self.assertTrue("权重下限 14 ms，不随长度变" in source, "图里缺少这段文字")
        short = self.dm.build_point(CONFIG, 1, 128, bandwidth_gb_per_s=1000)
        long_ = self.dm.build_point(CONFIG, 1, 16384, bandwidth_gb_per_s=1000)
        self.assertEqual(short["step_floor_ms"], long_["step_floor_ms"])

    def test_the_right_edge_multiple_matches_the_model(self):
        """图里那句“近六倍”说的是曲线右端，不是被圈出的那一点。"""
        source = self.svg("fig15-04_context_climb.svg")
        at_edge = self.dm.build_point(CONFIG, 32, 16000, bandwidth_gb_per_s=1000)
        self.assertAlmostEqual(at_edge["step_estimate_ms"] / 14.0, 5.8, delta=0.2)
        self.assertTrue("批量 32 到右端已是下限的近六倍" in source, "图里缺少这段文字")
        at_mark = self.dm.build_point(CONFIG, 32, 8000, bandwidth_gb_per_s=1000)
        self.assertAlmostEqual(at_mark["step_estimate_ms"] / 14.0, 3.4, delta=0.1)

    def test_both_mechanisms_are_named(self):
        source = self.svg("fig15-04_context_climb.svg")
        self.assertTrue("计算量的平方项" in source, "图里缺少这段文字")
        self.assertTrue("KV 读取量的线性增长" in source, "图里缺少这段文字")

if __name__ == "__main__":
    unittest.main()
