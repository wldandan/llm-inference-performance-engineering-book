#!/usr/bin/env python3
"""Figure tests for Chapter 24.

The numeric assertions recompute every number drawn from
code/ch24/agent_profile.py and content/ch24/evidence/agent-traces-sample.jsonl.
"""

from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER_DIR = FIGURE_DIR.parent
CHAPTER = CHAPTER_DIR / "ch24.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch24"))

FIGURES = {
    "fig24-01_step_amplification.svg": "步数放大三样东西",
    "fig24-02_tail_waste_patterns.svg": "长尾任务里的浪费模式",
}

FORBIDDEN = {
    # 24.2 说带重试的 Agent 不适用乘法模型，图里不该把它说成通用公式
    "fig24-01_step_amplification.svg": ["任何 Agent 都", "通用公式"],
    # 24.7 的产出是模式，不是某个万能的步数上限
    "fig24-02_tail_waste_patterns.svg": ["步数上限设为", "建议 max_steps"],
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
                caption = f"图24-{i}："
                self.assertIn(caption, text, f"正文缺少图注 {caption}")
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions), "图号与正文出现顺序不一致")

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图24-(\d+)：", text))
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
        import agent_profile as ap
        cls.ap = ap
        cls.traces = ap.load_traces(
            ROOT / "content" / "ch24" / "evidence" / "agent-traces-sample.jsonl")
        cls.tail = ap.tail(cls.traces, percentile=0.7)
        cls.slo = ap.step_slo(0.95, 15, 0.95)
        example = next(t for t in cls.traces if t["task_id"] == "t-001")
        cls.tokens = ap.cumulative_tokens(
            [s["input_tokens"] for s in example["steps"]])

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_synthetic_data_is_labelled_where_it_is_drawn(self):
        header = (ROOT / "content" / "ch24" / "evidence"
                  / "agent-traces-sample.jsonl").read_text(
            encoding="utf-8").splitlines()[0]
        self.assertIn("合成设定", header)
        self.assertIn("合成追踪", self.svg("fig24-02_tail_waste_patterns.svg"))

    # --- 图24-1 ---
    def test_the_four_pass_rates_drawn_match_24_2(self):
        source = self.svg("fig24-01_step_amplification.svg")
        for n, drawn in ((5, "77%"), (8, "66%"), (15, "46%"), (35, "17%")):
            with self.subTest(steps=n):
                self.assertEqual(f"{self.ap.task_pass_rate(0.95, n):.0%}", drawn)
                self.assertIn(drawn, source)

    def test_the_three_token_figures_drawn_match(self):
        source = self.svg("fig24-01_step_amplification.svg")
        self.assertEqual(self.tokens["exact"], 174500.0)
        self.assertEqual(self.tokens["trapezoid_estimate"], 180000.0)
        self.assertEqual(self.tokens["naive_first_step_times_steps"], 24000.0)
        self.assertIn("逐步累加 174500 token", source)
        self.assertIn("= 180000", source)
        self.assertIn("只得 24000", source)

    def test_the_estimate_error_drawn_matches(self):
        source = self.svg("fig24-01_step_amplification.svg")
        self.assertIn(f"偏高 {self.tokens['estimate_error_share']:.1%}", source)

    def test_the_naive_understatement_drawn_matches(self):
        source = self.svg("fig24-01_step_amplification.svg")
        self.assertIn(f"低估 {self.tokens['naive_understates_by']:.1f} 倍", source)

    def test_the_inverse_drawn_matches(self):
        source = self.svg("fig24-01_step_amplification.svg")
        self.assertIn(f"单步需要 {self.slo['required_step_pass_rate']:.2%}", source)
        self.assertEqual(round(self.slo["required_step_pass_rate"] * 100, 2),
                         99.66)

    def test_halving_the_steps_is_drawn_as_the_better_lever(self):
        source = self.svg("fig24-01_step_amplification.svg")
        self.assertIn(f"砍到 {self.slo['halved_steps']} 步", source)
        self.assertIn(f"就能到 {self.slo['halved_task_pass_rate']:.0%}", source)
        self.assertGreater(self.slo["halved_task_pass_rate"],
                           self.slo["task_pass_rate"])

    def test_the_three_amplifications_are_labelled_distinctly(self):
        source = self.svg("fig24-01_step_amplification.svg")
        for phrase in ("按步数线性放大", "按步数的平方放大", "按步数指数衰减"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, source)

    # --- 图24-2 ---
    def test_the_tail_tasks_drawn_match(self):
        source = self.svg("fig24-02_tail_waste_patterns.svg")
        self.assertEqual(self.tail["tasks_in_tail"], 4)
        for row in self.tail["tail_tasks"]:
            with self.subTest(task=row["task_id"]):
                self.assertIn(row["task_id"], source)
                self.assertIn(f"{row['steps']} 步", source)

    def test_the_pattern_counts_drawn_match(self):
        source = self.svg("fig24-02_tail_waste_patterns.svg")
        for pattern in self.ap.WASTE_PATTERNS:
            count = self.tail["pattern_counts"].get(pattern, 0)
            with self.subTest(pattern=pattern):
                self.assertIn(f"出现在 {count} 个任务里", source)

    def test_the_shared_pattern_count_in_the_takeaway_matches(self):
        source = self.svg("fig24-02_tail_waste_patterns.svg")
        self.assertGreaterEqual(len(self.tail["shared_patterns"]), 2)
        self.assertIn(f"{len(self.tail['shared_patterns'])} 种模式出现在两个以上",
                      source)

    def test_all_three_patterns_and_their_thresholds_are_drawn(self):
        source = self.svg("fig24-02_tail_waste_patterns.svg")
        self.assertEqual(self.ap.REPEAT_THRESHOLD, 4)
        self.assertEqual(self.ap.OSCILLATION_THRESHOLD, 4)
        self.assertEqual(self.ap.SAME_RESOURCE_THRESHOLD, 4)
        for pattern in self.ap.WASTE_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, source)
        self.assertIn("≥ 4 次", source)

    def test_the_percentile_drawn_matches_the_run(self):
        source = self.svg("fig24-02_tail_waste_patterns.svg")
        self.assertIn(f"P{self.tail['percentile'] * 100:.0f} 以上", source)

    def test_the_small_sample_caveat_is_in_the_note(self):
        """十个任务的 P95 就是最大值，所以这张图取的是 P70，这件事要写在图注里。"""
        note = (FIGURE_DIR / "fig24-02_tail_waste_patterns.figure-note.md"
                ).read_text(encoding="utf-8")
        self.assertIn("P95 就是最大值", note)


if __name__ == "__main__":
    unittest.main()
