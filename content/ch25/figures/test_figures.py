#!/usr/bin/env python3
"""Figure tests for Chapter 25.

The budget figure's two columns are produced by code/ch25/e2e_experiment.py at
build time, including the refusal, so the picture cannot claim a split the
checker would reject.
"""

from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER_DIR = FIGURE_DIR.parent
CHAPTER = CHAPTER_DIR / "ch25.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch25"))

FIGURES = {
    "fig25-01_layer_breakdown.svg": "分层定位，不是分层优化",
    "fig25-02_budget_split.svg": "拆预算会立刻暴露不可能的目标",
}

FORBIDDEN = {
    # 25.2 的结论是先分解，不是给一份通用的层级占比
    "fig25-01_layer_breakdown.svg": ["通常各层占比", "标准分布"],
    # 25.3 说预算分配是业务决策，图里不该给一份万能预算
    "fig25-02_budget_split.svg": ["推荐预算", "通用分配"],
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
                caption = f"图25-{i}："
                self.assertIn(caption, text, f"正文缺少图注 {caption}")
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions), "图号与正文出现顺序不一致")

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图25-(\d+)：", text))
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
        import e2e_experiment as ee
        cls.ee = ee
        cls.kw = dict(total_ms=8000.0, per_step_orchestration_ms=50.0,
                      retrieval_ms=1200.0, model_serving_ms=5000.0,
                      tools_ms=1000.0, measured_call_compute_ms=480.0,
                      model_calls_p95=7, service_time_ms=103.0)
        cls.feasible = ee.build_budget(steps_p95=10, rho=0.69, **cls.kw)
        cls.first = ee.build_budget(steps_p95=15, **cls.kw)

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    # --- 图25-1 ---
    def test_the_four_layer_shares_add_to_one(self):
        source = self.svg("fig25-01_layer_breakdown.svg")
        for share in ("18%", "22%", "47%", "13%"):
            with self.subTest(share=share):
                self.assertIn(share, source)
        self.assertEqual(18 + 22 + 47 + 13, 100)

    def test_the_model_service_split_matches_the_chapter(self):
        """47% 里排队 31%、GPU 16%，两者相加正好是 47。"""
        source = self.svg("fig25-01_layer_breakdown.svg")
        self.assertIn("排队 31%", source)
        self.assertIn("GPU 16%", source)
        self.assertEqual(31 + 16, 47)

    def test_seven_calls_fit_the_sixteen_percent(self):
        """GPU 16% 是 3.36 秒，正好是 7 次 480 ms 的调用。"""
        source = self.svg("fig25-01_layer_breakdown.svg")
        self.assertIn("模型调用约 7 次", source)
        self.assertAlmostEqual(0.16 * 21000 / 480, 7.0, places=1)

    def test_the_seven_percent_conclusion(self):
        """16% × (1 − 260/480) ≈ 7%。"""
        source = self.svg("fig25-01_layer_breakdown.svg")
        self.assertIn("端到端只改善约 7%", source)
        self.assertEqual(round(0.16 * (480 - 260) / 480 * 100), 7)

    def test_it_says_the_breakdown_must_be_taken_under_load(self):
        source = self.svg("fig25-01_layer_breakdown.svg")
        self.assertIn("分解要在压测下做", source)

    def test_it_asks_why_the_load_is_high(self):
        source = self.svg("fig25-01_layer_breakdown.svg")
        self.assertIn("先问负载率为什么高", source)
        self.assertIn("满载吞吐", source)

    def test_synthetic_setting_is_labelled(self):
        self.assertIn("合成设定", self.svg("fig25-01_layer_breakdown.svg"))

    # --- 图25-2 ---
    def test_todays_load_is_actually_refused(self):
        """图里左栏那一版必须是检查器真的拒掉的那一版。"""
        with self.assertRaises(self.ee.ExperimentError):
            self.ee.build_budget(steps_p95=15, rho=0.9, **self.kw)

    def test_the_per_call_numbers_drawn_match(self):
        source = self.svg("fig25-02_budget_split.svg")
        self.assertAlmostEqual(self.first["per_call_model_serving_ms"], 714.286, places=3)
        self.assertIn("每次调用 714 ms", source)
        self.assertIn("排队只占得到 234 ms", source)
        # 同一个量只能有一个数：正文用的是实测 6510 ÷ 7 ≈ 930，不是式子给的 927。
        self.assertIn("每次排队约 930 ms", source)

    def test_the_load_ceiling_drawn_matches_the_code(self):
        source = self.svg("fig25-02_budget_split.svg")
        self.assertAlmostEqual(self.feasible["rho_max"], 0.6946, places=4)
        self.assertIn("负载率 ≤ 0.69", source)
        self.assertIn("234 ÷ (103 + 234) ≈ 0.69", source)

    def test_every_layer_of_the_feasible_budget_is_drawn(self):
        source = self.svg("fig25-02_budget_split.svg")
        for key in self.ee.LAYERS:
            ms = self.feasible["layers"][key]["ms"]
            with self.subTest(layer=key):
                self.assertIn(f"{ms:.0f} ms", source)
        self.assertIn(f"{self.feasible['unallocated_ms']:.0f} ms", source)

    def test_the_feasible_budget_adds_to_the_total(self):
        source = self.svg("fig25-02_budget_split.svg")
        parts = sum(row["ms"] for row in self.feasible["layers"].values())
        self.assertEqual(parts + self.feasible["unallocated_ms"], 8000.0)
        self.assertIn("8000 ms", source)

    def test_the_first_draft_total_is_drawn(self):
        source = self.svg("fig25-02_budget_split.svg")
        self.assertIn(f"{15 * 50 + 1200 + 5000 + 1000} ms", source)

    def test_the_subtitle_carries_the_same_numbers(self):
        source = self.svg("fig25-02_budget_split.svg")
        self.assertIn("排队只占得到 234 ms，负载率要守在 0.69 以下", source)

    def test_the_chapter_states_the_same_numbers(self):
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("每次约 714 ms", chapter)
        self.assertIn("留给排队的只有约 234 ms", chapter)
        self.assertIn("未分配余量     300 ms", chapter)


if __name__ == "__main__":
    unittest.main()
