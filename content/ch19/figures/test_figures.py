#!/usr/bin/env python3
"""Figure tests for Chapter 19.

Beyond the shared visual contract, the numeric assertions pin every number drawn
in these figures to content/ch19/evidence/decode-experiment-sample.json 与 code/ch19/decode_experiment.py, so the pictures and the code cannot drift apart. That
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
CHAPTER = FIGURE_DIR.parent / "ch19.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch15"))
sys.path.insert(0, str(ROOT / "code" / "ch14"))
sys.path.insert(0, str(ROOT / "code" / "ch19"))
CONFIG = json.loads((ROOT / "code" / "ch15" / "model-7b-generic.json")
                    .read_text(encoding="utf-8"))

FIGURES = {
    "fig19-01_goodput_vs_tps.svg": "TPS 峰值与 Goodput 峰值不在同一处",
    "fig19-02_five_round_scorecard.svg": "五轮实验的五维记分卡",
}

FORBIDDEN = {
    # 19.3 的取舍标准来自 SLO，不是某个经验批量
    "fig19-01_goodput_vs_tps.svg": ["建议批量设成", "经验值 32"],
    # 记分卡不给总分，因为它不是投票
    "fig19-02_five_round_scorecard.svg": ["总分", "得分 4/5"],
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
                caption = f"图19-{i}："
                self.assertTrue(caption in text, f"正文缺少图注 {caption}")

    def test_no_em_dash_in_any_figure(self):
        """全书体例：不用破折号。"""
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertNotIn("——", source)


class TestFiguresMatchTheSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import decode_experiment as de
        cls.de = de
        cls.doc = json.loads(
            (ROOT / "content" / "ch19" / "evidence"
             / "decode-experiment-sample.json").read_text(encoding="utf-8"))
        cls.result = de.check_series(cls.doc)
        cls.sweep = de.analyse_sweep(
            next(r for r in cls.doc["rounds"] if r["round"] == 0)["sweep"]["points"])

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_synthetic_data_is_labelled_in_both_figures(self):
        self.assertTrue(self.doc["synthetic"])
        for name in FIGURES:
            with self.subTest(figure=name):
                self.assertTrue("合成样例" in self.svg(name), "图里缺少合成样例的标注")

    # --- 图19-1 ---
    def test_the_two_peaks_drawn_match_the_sweep(self):
        source = self.svg("fig19-01_goodput_vs_tps.svg")
        self.assertEqual(self.sweep["peak_batch_by_goodput"], 32)
        self.assertEqual(self.sweep["peak_batch_by_tps"], 128)
        self.assertFalse(self.sweep["peaks_coincide"])
        self.assertTrue("可行集里的 Goodput 峰值 1560" in source, "图里缺少这段文字")
        self.assertTrue("名义 TPS 3332" in source, "图里缺少这段文字")

    def test_the_goodput_at_the_tps_peak_matches(self):
        source = self.svg("fig19-01_goodput_vs_tps.svg")
        at128 = next(r for r in self.sweep["points"] if r["batch"] == 128)
        self.assertEqual(f"{at128['goodput']:.0f}", "666")
        self.assertTrue("批量 128 只剩 666" in source, "图里缺少这段文字")

    def test_the_unconstrained_peak_is_drawn_as_infeasible(self):
        """批量 64 的 Goodput 全表最高，但达标率不满足 SLO，图里要标出来。"""
        source = self.svg("fig19-01_goodput_vs_tps.svg")
        rows = {r["batch"]: r for r in self.sweep["points"]}
        best = max(rows.values(), key=lambda r: r["goodput"])
        self.assertEqual(best["batch"], 64)
        self.assertFalse(best["feasible"])
        self.assertTrue("全表最高 1807，达标率 74%" in source, "图里缺少这段文字")

    def test_the_shortfall_and_the_nominal_gain_drawn_match(self):
        source = self.svg("fig19-01_goodput_vs_tps.svg")
        rows = {r["batch"]: r for r in self.sweep["points"]}
        gain = rows[128]["tps"] / rows[32]["tps"] - 1
        shortfall = 1 - rows[128]["goodput"] / rows[32]["goodput"]
        self.assertEqual(f"{gain * 100:.0f}%", "109%")
        self.assertEqual(f"{shortfall * 100:.0f}%", "57%")
        # 图里只画两个峰值和 128 那一档的 Goodput，百分比留给 19.9 案例三的正文。
        self.assertIn("名义 TPS 3332", source)
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("高 109%", chapter)

    def test_every_attainment_drawn_matches_the_sweep(self):
        source = self.svg("fig19-01_goodput_vs_tps.svg")
        for row in self.sweep["points"]:
            drawn = f"{row['slo_attainment'] * 100:.0f}%"
            with self.subTest(batch=row["batch"]):
                self.assertTrue(drawn in source, f"图里缺少达标率 {drawn}")

    def test_the_slo_line_drawn_matches_the_workload(self):
        source = self.svg("fig19-01_goodput_vs_tps.svg")
        slo = self.doc["rounds"][0]["fixed"]["workload"]["slo"]
        self.assertEqual(slo["good_request"]["itl_p95_ms_per_request"], 80)
        self.assertEqual(slo["good_request"]["ttft_ms"], 1500)
        self.assertEqual(slo["required_attainment"], 0.95)
        self.assertTrue("SLO 80 ms" in source, "图里缺少这段文字")
        self.assertTrue("可行档位" in source, "图里缺少这段文字")

    def test_the_pareto_reminder_is_drawn(self):
        source = self.svg("fig19-01_goodput_vs_tps.svg")
        self.assertTrue("前沿上的候选都留着" in source, "图里缺少这段文字")

    # --- 图19-2 ---
    def test_all_five_rounds_are_drawn(self):
        source = self.svg("fig19-02_five_round_scorecard.svg")
        for r in self.doc["rounds"]:
            with self.subTest(round=r["round"]):
                self.assertTrue(f"第 {r['round']} 轮" in source, "图里缺少这一轮")

    def test_all_five_dimensions_are_drawn(self):
        source = self.svg("fig19-02_five_round_scorecard.svg")
        self.assertEqual(len(self.de.SCORECARD_DIMENSIONS), 5)
        for label in ("单条体验", "系统吞吐", "容量", "接受长度", "质量"):
            with self.subTest(label=label):
                self.assertTrue(label in source, "图里缺少这一维")

    def test_round_two_is_drawn_as_four_improved_one_breached(self):
        source = self.svg("fig19-02_five_round_scorecard.svg")
        r2 = next(r for r in self.result["rounds"] if r["round"] == 2)
        self.assertFalse(r2["verdict"]["passed"])
        self.assertEqual(r2["verdict"]["failed_by"], "quality")
        self.assertTrue(r2["quality"]["breached"])
        self.assertTrue("越界" in source, "图里缺少越界那一格")
        self.assertTrue("质量越界  失败回滚" in source, "图里缺少这段文字")

    def test_round_three_is_drawn_as_valid_but_not_kept(self):
        source = self.svg("fig19-02_five_round_scorecard.svg")
        self.assertEqual(self.result["rounds_valid_but_not_kept"], [3])
        self.assertTrue("成立但不留" in source, "图里缺少这段文字")

    def test_round_three_acceptance_drawn_matches_the_sample(self):
        source = self.svg("fig19-02_five_round_scorecard.svg")
        r3 = next(r for r in self.doc["rounds"] if r["round"] == 3)
        self.assertEqual(r3["scorecard"]["acceptance"]["mean_accepted"], 2.1)
        self.assertTrue("2.1 离线 3.6" in source, "图里缺少这段文字")

    def test_round_four_is_drawn_as_indistinguishable_yet_kept(self):
        source = self.svg("fig19-02_five_round_scorecard.svg")
        r4 = next(r for r in self.result["rounds"] if r["round"] == 4)
        self.assertEqual(r4["verdict"]["label"], self.de.INDISTINGUISHABLE)
        self.assertTrue(r4["verdict"]["kept"])
        self.assertTrue("不可分辨  收益在容量" in source, "图里缺少这段文字")

    def test_the_veto_rule_is_stated_not_implied(self):
        source = self.svg("fig19-02_five_round_scorecard.svg")
        self.assertTrue("记分卡不是投票" in source, "图里缺少这段文字")
        self.assertTrue("质量是否决项" in source, "图里缺少这段文字")

    def test_the_preemption_count_is_named_as_near_veto(self):
        source = self.svg("fig19-02_five_round_scorecard.svg")
        self.assertTrue("抢占计数接近否决项" in source, "图里缺少这段文字")

    def test_only_round_two_failed_in_the_series(self):
        self.assertEqual(self.result["rounds_failed"], [2])

if __name__ == "__main__":
    unittest.main()
