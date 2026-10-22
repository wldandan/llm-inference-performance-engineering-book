#!/usr/bin/env python3
"""Figure tests for Chapter 26.

图26-1 链上每一个数、图26-2 曲线上每一个落点，都由 code/ch26/capacity_cost.py 在
构建时算出来，所以这里核对的是「图里写的和模型算的是同一个数」，不是「图里写了
某个字符串」。
"""

from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch26.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch26"))

FIGURES = {
    "fig26-01_demand_chain.svg": "从日活到卡数，中间那一步不能省",
    "fig26-02_headroom_curve.svg": "余量买的是什么",
}

FORBIDDEN = {
    # 26.3 的结论是折算这一步不能省，不是给一份通用的单卡并发
    "fig26-01_demand_chain.svg": ["通用容量表", "单卡标准并发"],
    # 26.3 说这条代入只给量级，图里不该出现具体的等待毫秒数
    "fig26-02_headroom_curve.svg": ["等待 ms", "平均等待毫秒"],
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
                caption = f"图26-{i}："
                self.assertIn(caption, text, f"正文缺少图注 {caption}")
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions), "图号与正文出现顺序不一致")

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图26-(\d+)：", text))
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
        import capacity_cost as cc
        cls.cc = cc
        cls.params = dict(dau=500000, sessions_per_user=3.2, peak_to_mean=3.0,
                          calls_per_session=2.4, input_tokens=2600,
                          output_tokens=220, request_duration=4.2,
                          gpu_concurrency=130, concurrency_at_tokens=2300,
                          gpu_output_tps=1560, prefill_share=0.10,
                          measured_io_ratio=1.5, gpu_monthly=12000,
                          headroom=0.3, api_input_price=0.0008,
                          api_output_price=0.002)
        cls.model = cc.build_model(cls.params)
        cls.static = cc.build_model(dict(cls.params, ignore_prefill=True))
        cls.minimum = cls.model["sizing"]["gpus_minimum_exact"]
        cls.margin = {r["cards"]: r for r in cc.margin_table(cls.minimum, [36, 42, 45, 48])}

    def svg(self, name):
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    # --- 图26-1 ---
    def test_every_rung_of_the_chain_is_drawn(self):
        source = self.svg("fig26-01_demand_chain.svg")
        d = self.model["demand"]
        for value in (f"{d['daily_sessions']:.0f}",
                      f"{d['mean_session_qps']:.1f}",
                      f"{d['peak_session_qps']:.1f}",
                      f"{d['peak_call_qps']:.0f}",
                      f"{d['peak_output_tps']:.0f}"):
            with self.subTest(value=value):
                self.assertIn(value, source)

    def test_it_says_peak_to_mean_not_peak_to_trough(self):
        source = self.svg("fig26-01_demand_chain.svg")
        self.assertIn("峰均比", source)
        self.assertNotIn("峰谷比", source)

    def test_the_inflight_count_comes_from_littles_law(self):
        source = self.svg("fig26-01_demand_chain.svg")
        expected = self.cc.inflight(self.model["demand"]["peak_call_qps"], 4.2)
        self.assertIn(f"在途 {expected:.0f} 条", source)

    def test_the_scaling_step_is_the_one_drawn_in_red(self):
        source = self.svg("fig26-01_demand_chain.svg")
        self.assertIn("130 × 2300 ÷ 2820 ≈ 106 条", source)

    def test_static_and_corrected_are_drawn_side_by_side(self):
        source = self.svg("fig26-01_demand_chain.svg")
        self.assertIn(f"{self.static['sizing']['gpus_by_throughput']:.1f} 张", source)
        self.assertIn(f"{self.model['sizing']['gpus_by_throughput']:.1f} 张", source)
        self.assertIn(f"{self.model['sizing']['gpus_by_memory']:.1f} 张", source)
        self.assertIn("29333 ÷ 924", source)
        self.assertIn("吞吐先满，刚好够 32 张，加 30% 余量 42 张", source)

    def test_the_prefill_note_matches_the_code(self):
        source = self.svg("fig26-01_demand_chain.svg")
        self.assertIn("Prefill 占时 10% → 47%", source)

    def test_the_two_multipliers_case_one_missed(self):
        source = self.svg("fig26-01_demand_chain.svg")
        self.assertIn("3 × 2.4 = 7.2 倍", source)

    def test_synthetic_setting_is_labelled(self):
        self.assertIn("合成设定", self.svg("fig26-01_demand_chain.svg"))

    # --- 图26-2 ---
    def test_the_four_points_match_the_margin_table(self):
        source = self.svg("fig26-02_headroom_curve.svg")
        for cards in (36, 42, 45, 48):
            row = self.margin[cards]
            with self.subTest(cards=cards):
                self.assertIn(f"{cards} 张　负载率 {row['rho']:.2f}　"
                              f"{row['drain_minutes']:.1f} 分钟", source)

    def test_the_queue_comparison_matches(self):
        source = self.svg("fig26-02_headroom_curve.svg")
        for cards in (36, 42, 48):
            row = self.margin[cards]
            with self.subTest(cards=cards):
                self.assertIn(f">{row['amplification']:.1f}<", source)
                self.assertIn(f">{row['erlang_c_wait']:.3f}<", source)

    def test_it_names_both_queue_models(self):
        source = self.svg("fig26-02_headroom_curve.svg")
        self.assertIn("单副本上界", source)
        self.assertIn("Erlang C", source)

    def test_it_says_not_to_promise_milliseconds(self):
        source = self.svg("fig26-02_headroom_curve.svg")
        self.assertIn("不要用它承诺毫秒数", source)

    def test_the_chapter_states_the_same_numbers(self):
        chapter = CHAPTER.read_text(encoding="utf-8")
        for text in ("36 张   负载率 0.88   一分钟三倍突发约 13.9 分钟消化完",
                     "42 张   负载率 0.76   约 5.2 分钟",
                     "按输出吞吐         29000 ÷ 924 ≈ 32 张"):
            with self.subTest(text=text):
                self.assertIn(text, chapter)


if __name__ == "__main__":
    unittest.main()
