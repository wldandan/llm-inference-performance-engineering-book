#!/usr/bin/env python3
"""Figure tests for Chapter 22.

The numeric assertions recompute every number drawn from
code/ch22/serving_choice.py and content/ch22/evidence/route-eval-sample.json.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER_DIR = FIGURE_DIR.parent
CHAPTER = CHAPTER_DIR / "ch22.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch22"))

FIGURES = {
    "fig22-01_cache_ceiling_staircase.svg": "扩容本身就在削会话级前缀的缓存",
    "fig22-02_routing_tradeoff.svg": "缓存命中率和负载均衡是互相冲突的两个目标",
}

FORBIDDEN = {
    # 22.4 说取舍点取决于可缓存比例，没有一个万能的副本数
    "fig22-01_cache_ceiling_staircase.svg": ["建议副本数", "最多部署"],
    # part05 写明 ch22 不做框架功能对比
    "fig22-02_routing_tradeoff.svg": ["vLLM 比", "框架对比", "性能排名"],
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
            sizes = [float(v) for v in
                     re.findall(r"font-size:(\d+(?:\.\d+)?)px", source)]
            with self.subTest(figure=name):
                self.assertTrue(sizes)
                self.assertGreaterEqual(min(sizes), 14)

    def test_notes_carry_the_four_required_lines(self):
        for name in FIGURES:
            note = (FIGURE_DIR / (name[:-4] + ".figure-note.md")).read_text(
                encoding="utf-8")
            with self.subTest(figure=name):
                for field in ("来源段落", "阅读顺序", "关键结论", "表达边界"):
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
                self.assertIn(name, text, f"{name} 没有出现在正文里")
                caption = f"图22-{i}："
                self.assertIn(caption, text, f"正文缺少图注 {caption}")
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions), "图号与正文出现顺序不一致")

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图22-(\d+)：", text))
        self.assertEqual(found, list(range(1, len(FIGURES) + 1)))

    def test_no_em_dash_and_no_corner_quotes(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertNotIn("——", source)
                self.assertNotIn("「", source)
                self.assertNotIn("」", source)


class TestFiguresMatchTheCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import serving_choice as sc
        cls.sc = sc
        cls.sample = json.loads(
            (ROOT / "content" / "ch22" / "evidence"
             / "route-eval-sample.json").read_text(encoding="utf-8"))
        cls.eval = sc.route_eval(cls.sample)
        cls.rows = {r["strategy"]: r for r in cls.eval["strategies"]}

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_synthetic_data_is_labelled_where_it_is_drawn(self):
        self.assertTrue(self.sample["synthetic"])
        self.assertIn("合成评估", self.svg("fig22-02_routing_tradeoff.svg"))

    # --- 图22-1 ---
    def test_the_bars_match_the_routing_term(self):
        source = self.svg("fig22-01_cache_ceiling_staircase.svg")
        for n, k, drawn in ((1, 2, "50%"), (4, 2, "12.5%"), (8, 2, "6.3%"),
                            (1, 10, "90%"), (4, 10, "62%"), (8, 10, "41%")):
            with self.subTest(instances=n, reuse=k):
                v = self.sc.routing_term(n, k)
                self.assertAlmostEqual(v * 100, float(drawn[:-1]), delta=0.5)
                self.assertIn(f">{drawn}<", source)

    def test_the_three_rows_22_4_tabulates_are_all_in_the_figure(self):
        """正文那张表是 1 / 4 / 8，图里多画了 2 和 16，但这三档必须在。"""
        source = self.svg("fig22-01_cache_ceiling_staircase.svg")
        for label in ("1 个实例", "4 个", "8 个"):
            with self.subTest(label=label):
                self.assertIn(label, source)

    def test_doubling_the_replicas_roughly_halves_it_at_low_reuse(self):
        a = self.sc.routing_term(4, 2)
        b = self.sc.routing_term(8, 2)
        self.assertAlmostEqual(a / b, 2.0)

    def test_the_shared_prefix_case_is_drawn(self):
        """1/N 只对会话级前缀成立，全体共享的前缀必须画出来作对照。"""
        source = self.svg("fig22-01_cache_ceiling_staircase.svg")
        self.assertIn("全体共享的前缀", source)
        self.assertIn("接近 100%", source)

    def test_the_four_cut_formula_is_drawn_in_full(self):
        source = self.svg("fig22-01_cache_ceiling_staircase.svg")
        for term in ("可缓存占比", "局部性", "未被淘汰", "路由项"):
            with self.subTest(term=term):
                self.assertIn(term, source)

    def test_it_says_eviction_makes_it_worse(self):
        source = self.svg("fig22-01_cache_ceiling_staircase.svg")
        self.assertIn("缓存装不下时更糟", source)

    # --- 图22-2 ---
    def test_the_three_points_drawn_match_the_evaluation(self):
        source = self.svg("fig22-02_routing_tradeoff.svg")
        for name in ("round-robin", "prefix-hash", "prefix-hash-with-overflow"):
            row = self.rows[name]
            with self.subTest(strategy=name):
                self.assertIn(f"命中率 {row['cache_hit_rate']:.1%}", source)
                self.assertIn(f"不均衡度 {row['load_skew']:.2f}", source)

    def test_the_two_thresholds_drawn_match_the_code(self):
        source = self.svg("fig22-02_routing_tradeoff.svg")
        self.assertEqual(self.sc.SKEW_UNNOTICEABLE, 0.3)
        self.assertEqual(self.sc.SKEW_P99_DOMINATED, 0.5)
        self.assertIn("0.3 以下感觉不到", source)
        self.assertIn("0.5 以上最慢的实例决定 P99", source)

    def test_the_worst_instance_is_drawn_for_every_strategy(self):
        """22.5：聚合指标会掩盖单实例问题，所以最差实例必须一起画。"""
        source = self.svg("fig22-02_routing_tradeoff.svg")
        for name, row in self.rows.items():
            with self.subTest(strategy=name):
                self.assertIn(
                    f"最差实例 {row['worst_instance']['p95_ttft']:.0f} ms", source)

    def test_the_hidden_gap_drawn_matches(self):
        source = self.svg("fig22-02_routing_tradeoff.svg")
        row = self.rows["prefix-hash"]
        self.assertEqual(row["aggregate_hides"], 440.0)
        self.assertIn("高出 440 ms", source)

    def test_the_practical_pick_drawn_is_the_one_the_code_picks(self):
        source = self.svg("fig22-02_routing_tradeoff.svg")
        self.assertEqual(self.eval["practical"], "prefix-hash-with-overflow")
        self.assertIn(f"实际可用的是{self.eval['practical']}", source)

    def test_the_conflict_the_figure_claims_is_real(self):
        self.assertTrue(self.eval["conflict"])
        self.assertNotEqual(self.eval["best_hit_rate"], self.eval["best_balance"])

    def test_pure_prefix_hash_is_past_the_p99_line(self):
        self.assertGreater(self.rows["prefix-hash"]["load_skew"],
                           self.sc.SKEW_P99_DOMINATED)

    def test_the_overflow_form_is_inside_the_unnoticeable_band(self):
        self.assertLess(self.rows["prefix-hash-with-overflow"]["load_skew"],
                        self.sc.SKEW_UNNOTICEABLE)


if __name__ == "__main__":
    unittest.main()
