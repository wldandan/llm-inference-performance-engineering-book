#!/usr/bin/env python3
"""Figure tests for Chapter 23.

The numeric assertions recompute every number drawn from
code/ch23/rag_trace.py, code/ch11/prefill_model.py, and
content/ch23/evidence/rag-trace-sample.json. 23.3's pair (3000 token → 600 ms,
9000 token → 2350 ms) is derived here, not copied.
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
CHAPTER = CHAPTER_DIR / "ch23.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch11"))
sys.path.insert(0, str(ROOT / "code" / "ch23"))

FIGURES = {
    "fig23-01_rag_stage_breakdown.svg": "一次 RAG 调用的时间去了哪",
    "fig23-02_quality_drives_cost.svg": "检索不准的代价比按 token 数线性推算出来的更贵",
}

FORBIDDEN = {
    # 23.2 说各段耗时是量级，不是某个推荐配置
    "fig23-01_rag_stage_breakdown.svg": ["推荐 top_k", "建议 final_k 设为"],
    # 23.3 说幅度要实测，图里不该给一个万能的收益承诺
    "fig23-02_quality_drives_cost.svg": ["一定能省", "保证降低"],
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
                caption = f"图23-{i}："
                self.assertIn(caption, text, f"正文缺少图注 {caption}")
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions), "图号与正文出现顺序不一致")

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图23-(\d+)：", text))
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
        import prefill_model as pm
        import rag_trace as rt
        cls.pm, cls.rt = pm, rt
        cls.trace = json.loads(
            (ROOT / "content" / "ch23" / "evidence"
             / "rag-trace-sample.json").read_text(encoding="utf-8"))
        cls.reading = rt.analyze(cls.trace)
        cls.config = pm.load_config(json.loads(
            (ROOT / "code" / "ch11" / "model-qwen25-05b.json")
            .read_text(encoding="utf-8")))

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_synthetic_data_is_labelled_where_it_is_drawn(self):
        self.assertTrue(self.trace["synthetic"])
        self.assertIn("合成 trace", self.svg("fig23-01_rag_stage_breakdown.svg"))

    # --- 图23-1 ---
    def test_all_seven_stages_are_drawn_with_their_times(self):
        source = self.svg("fig23-01_rag_stage_breakdown.svg")
        for stage in self.rt.STAGES:
            ms = self.reading["stages_warm_ms"][stage]
            with self.subTest(stage=stage):
                self.assertIn(f"{ms:.0f} ms", source)

    def test_the_shares_drawn_match_the_analysis(self):
        source = self.svg("fig23-01_rag_stage_breakdown.svg")
        for stage in self.rt.STAGES:
            share = self.reading["stage_share"][stage]
            with self.subTest(stage=stage):
                self.assertIn(f"{share:.1%}", source)

    def test_the_generation_split_drawn_matches(self):
        source = self.svg("fig23-01_rag_stage_breakdown.svg")
        self.assertIn(f"{self.reading['generation_share']:.1%}", source)
        self.assertIn(f"{self.reading['before_generation_share']:.1%}", source)

    def test_the_cold_warm_ratio_drawn_matches(self):
        source = self.svg("fig23-01_rag_stage_breakdown.svg")
        ratio = self.reading["cold_vs_warm"]["per_stage_ratio"]["retrieve"]
        self.assertAlmostEqual(ratio, 3.579, places=3)
        self.assertIn(f"{ratio:.2f} 倍", source)

    def test_the_end_to_end_gap_drawn_matches(self):
        source = self.svg("fig23-01_rag_stage_breakdown.svg")
        pct = (self.reading["cold_vs_warm"]["total_ratio"] - 1) * 100
        self.assertIn(f"端到端只慢 {pct:.1f}%", source)

    def test_retrieve_is_where_the_cold_warm_gap_lives(self):
        self.assertEqual(self.reading["cold_vs_warm"]["worst_stage"], "retrieve")

    # --- 图23-2 ---
    def test_the_real_ratio_drawn_comes_from_chapter_11(self):
        source = self.svg("fig23-02_quality_drives_cost.svg")
        ratio = (self.pm.relative_cost(self.config, 9000)
                 / self.pm.relative_cost(self.config, 3000))
        self.assertAlmostEqual(ratio, 3.9165, places=4)
        self.assertIn(f"实际 {ratio:.2f} 倍", source)

    def test_the_linear_reference_is_drawn_as_three(self):
        source = self.svg("fig23-02_quality_drives_cost.svg")
        self.assertIn("按 token 线性推 3.0 倍", source)
        self.assertEqual(9000 / 3000, 3.0)

    def test_the_two_attention_shares_drawn_match(self):
        source = self.svg("fig23-02_quality_drives_cost.svg")
        lo = self.rt.attention_share(self.config, 3000)
        hi = self.rt.attention_share(self.config, 9000)
        self.assertEqual(round(lo * 100), 15)
        self.assertEqual(round(hi * 100), 35)
        self.assertIn(f"{lo:.0%} 涨到 {hi:.0%}", source)

    def test_the_ttft_pair_drawn_is_derived_not_copied(self):
        source = self.svg("fig23-02_quality_drives_cost.svg")
        long_ttft = self.rt.ttft_after_context_change(self.config, 3000, 600.0,
                                                      9000)
        self.assertEqual(f"{long_ttft:.0f}", "2350")
        self.assertIn("TTFT 600 ms", source)
        self.assertIn("TTFT 2350 ms", source)

    def test_the_net_gain_drawn_matches_the_chapter(self):
        source = self.svg("fig23-02_quality_drives_cost.svg")
        long_ttft = self.rt.ttft_after_context_change(self.config, 3000, 600.0,
                                                      9000)
        saved = long_ttft - 600.0
        self.assertEqual(f"{saved:.0f}", "1750")
        self.assertIn("省下的 TTFT 1750 ms", source)
        self.assertIn("净收益 1450 到 1700 ms", source)

    def test_the_chapter_states_the_same_pair(self):
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("TTFT 2350 ms", chapter)
        self.assertIn("`2350 − 600 = 1750 ms`", chapter)

    def test_the_figure_says_the_magnitude_must_be_measured(self):
        source = self.svg("fig23-02_quality_drives_cost.svg")
        self.assertIn("幅度要实测", source)


if __name__ == "__main__":
    unittest.main()
