#!/usr/bin/env python3
"""Figure tests for Chapter 27.

图27-1 上的每一个数都由 code/ch27/autoscale_sim.py 在构建时算出来：滞后的三段、
两倍门槛、那次突发的持续时间、四种策略的未满足与成本。所以这里核对的是图和仿真
说的是同一件事。
"""

from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch27.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch27"))

FIGURES = {
    "fig27-01_time_scales.svg": "变化比回路快时，弹性就调不了",
}

FORBIDDEN = {
    # 27.5 的结论是分尺度选手段，不是「弹性没用」
    "fig27-01_time_scales.svg": ["弹性没用", "不要用 Autoscaling",
                                 "推荐冷启动"],
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
                caption = f"图27-{i}："
                self.assertIn(caption, text)
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions))

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图27-(\d+)：", text))
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
        import autoscale_sim as asim
        cls.asim = asim
        cls.lag = asim.loop_lag()
        trace = asim.load_trace(
            ROOT / "content" / "ch27" / "evidence" / "traffic-trace-sample.csv")
        base = dict(capacity_per_instance=150, scale_up_threshold=0.7,
                    scale_down_threshold=0.4, cold_start_s=300,
                    observation_s=60, decision_s=60, scale_up_cooldown_s=180,
                    scale_down_cooldown_s=1800, min_instances=3,
                    max_instances=30)
        cls.compare = asim.compare(trace, base)
        cls.svg = (FIGURE_DIR / "fig27-01_time_scales.svg").read_text(
            encoding="utf-8")

    def test_the_lag_band_matches_the_three_parts(self):
        self.assertEqual(self.lag["low_s"], 240)
        self.assertEqual(self.lag["high_s"], 810)
        self.assertIn(f"回路滞后 {self.lag['low_min']:.0f} 到 "
                      f"{self.lag['high_min']:.1f} 分", self.svg)

    def test_the_threshold_is_twice_the_lag(self):
        self.assertEqual(self.lag["actionable_threshold_min"],
                         self.lag["high_min"] * 2)
        self.assertIn(f"门槛 {self.lag['actionable_threshold_min']:.0f} 分",
                      self.svg)

    def test_the_surge_is_shorter_than_the_lag(self):
        """这是整张图的论点：突发比回路还短。

        图上用的是这次模拟实际配的滞后（观测 + 决策 + 冷启动 = 420 秒），
        不是 27.4 那张表的上界 810 秒：同一条轨迹只能有一个滞后
        （Part 6 审阅 P1-13）。
        """
        surge = self.compare["trace"]["surge_duration_s"]
        sim_lag = 60 + 60 + 300
        self.assertLess(surge, sim_lag)
        self.assertLess(surge, self.lag["low_s"])
        self.assertIn(f"样例轨迹那次突发只持续 {surge:.0f} 秒，"
                      f"比这次模拟的滞后 {sim_lag} 秒还短", self.svg)

    def test_all_four_strategies_are_drawn(self):
        for row in self.compare["strategies"]:
            with self.subTest(strategy=row["strategy"]):
                self.assertIn(row["strategy"], self.svg)
                self.assertIn(f"{row['unmet_demand'] / 1000:.0f}k", self.svg)

    def test_only_admission_only_has_no_unmet_demand(self):
        rows = {r["strategy"]: r for r in self.compare["strategies"]}
        self.assertEqual(rows["admission-only"]["unmet_demand"], 0.0)
        for s in ("reactive", "scheduled", "warm-pool"):
            with self.subTest(strategy=s):
                self.assertGreater(rows[s]["unmet_demand"], 0)

    def test_admission_only_is_also_the_cheapest(self):
        rows = {r["strategy"]: r for r in self.compare["strategies"]}
        cheapest = min(rows.values(), key=lambda r: r["cost_index"])
        self.assertEqual(cheapest["strategy"], "admission-only")
        self.assertIn("成本还更低", self.svg)

    def test_the_three_kinds_come_from_the_chapter_table(self):
        """27.5 那张表分三类，区分前两类的是可不可预测（Part 6 审阅 P0-2）。"""
        for kind in ("突发", "日内波峰与小时级增长", "长期增长"):
            with self.subTest(kind=kind):
                self.assertIn(kind, self.svg)

    def test_it_does_not_claim_elasticity_is_useless(self):
        self.assertIn("弹性不是没用", self.svg)

    def test_the_chapter_states_the_same_time_scales(self):
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("突发 | 秒到分钟", chapter)
        self.assertIn("不可预测的增长 | 小时到天", chapter)
        self.assertIn("可预测的周期 | 日内波峰", chapter)


if __name__ == "__main__":
    unittest.main()
