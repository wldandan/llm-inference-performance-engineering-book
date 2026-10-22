#!/usr/bin/env python3
"""Figure tests for Chapter 14.

The numeric assertions pin the figures to the synthetic report at
content/ch14/evidence/prefill-experiment-sample.json and to
code/ch14/prefill_experiment.py, so the pictures and the evidence file cannot
drift apart.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch14.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch11"))
sys.path.insert(0, str(ROOT / "code" / "ch14"))

FIGURES = {
    "fig14-01_four_rounds.svg": "四轮各看什么，各自的护栏是什么",
    "fig14-02_four_verdicts.svg": "四种结论，第四种最容易被改写",
    "fig14-03_boundary_four_axes.svg": "四项边界与各自的失效方式",
}

FORBIDDEN = {
    # 14.4 carries no gain numbers: those belong to 14-2.
    "fig14-01_four_rounds.svg": ["33.1%", "57%", "收益"],
    # 14.5 uses one criterion book-wide, and it is not the range.
    "fig14-02_four_verdicts.svg": ["极差 11%", "极差判据"],
    # 14.6 names no card.
    "fig14-03_boundary_four_axes.svg": ["A100", "H100", "GX10"],
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
                self.assertIn("marker-end", source)
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

    def test_synthetic_data_is_labelled(self):
        """The sample is not a real-machine result and the figures must say so."""
        for name in ("fig14-02_four_verdicts.svg", "fig14-03_boundary_four_axes.svg"):
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertIn("合成样例", source)

    def test_the_line_is_named_correctly(self):
        """14.1: the criterion is the detectable difference, never the range."""
        source = (FIGURE_DIR / "fig14-02_four_verdicts.svg").read_text(encoding="utf-8")
        self.assertIn("可识别线", source)
        self.assertIn("2.3 × 变异系数", source)
        self.assertIn("不是极差", source)




class TestFiguresMatchTheSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import prefill_experiment as pe

        cls.pe = pe
        cls.sample = json.loads(
            (ROOT / "content" / "ch14" / "evidence"
             / "prefill-experiment-sample.json").read_text(encoding="utf-8"))
        cls.rounds = cls.sample["rounds"]

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_every_round_appears_in_the_table(self):
        source = self.svg("fig14-01_four_rounds.svg")
        for label in ("Top-K 10 → 6", "启用 Prefix Cache",
                      "确认 Attention 实现", "启用 Chunked Prefill"):
            with self.subTest(label=label):
                self.assertIn(label, source)

    def test_round_four_primary_metric_is_drawn_as_different(self):
        source = self.svg("fig14-01_four_rounds.svg")
        self.assertEqual(self.rounds[3]["results"]["primary_metric"],
                         "short_request_itl_p99_ms")
        self.assertIn("短请求的 ITL", source)
        self.assertIn("不是 TTFT", source)

    def test_all_three_fixed_blocks_are_drawn(self):
        source = self.svg("fig14-01_four_rounds.svg")
        for block in self.pe.FIXED_BLOCKS:
            with self.subTest(block=block):
                self.assertIn(block, source)

    def test_guardrails_column_exists_for_every_round(self):
        source = self.svg("fig14-01_four_rounds.svg")
        self.assertIn("护栏", source)
        for r in self.rounds:
            self.assertTrue(r["guardrails"])

    def test_the_four_verdicts_drawn_match_the_sample(self):
        source = self.svg("fig14-02_four_verdicts.svg")
        labels = {r["verdict"]["label"] for r in self.rounds}
        self.assertEqual(labels, set(self.pe.VERDICTS))
        for verdict in self.pe.VERDICTS:
            with self.subTest(verdict=verdict):
                self.assertIn(verdict.replace("预期", "预期"), source)

    def test_observed_values_drawn_match_the_sample(self):
        source = self.svg("fig14-02_four_verdicts.svg")
        for r, drawn in zip(self.rounds, ("33.2%", "15.7%", "−0.4%", "29.9%")):
            observed = r["verdict"]["observed_pct"] * 100
            with self.subTest(round=r["changed"]):
                self.assertAlmostEqual(abs(observed),
                                       float(drawn.rstrip("%").lstrip("−")),
                                       delta=0.15)
                self.assertIn(drawn, source)

    def test_detectable_line_drawn_matches(self):
        source = self.svg("fig14-02_four_verdicts.svg")
        line = self.rounds[0]["verdict"]["detectable_difference"] * 100
        self.assertEqual(f"{line:.1f}%", "2.5%")
        self.assertIn("2.5%", source)

    def test_the_indistinguishable_round_is_inside_the_band(self):
        r = next(x for x in self.rounds
                 if x["verdict"]["label"] == self.pe.INDISTINGUISHABLE)
        self.assertLess(abs(r["verdict"]["observed_pct"]),
                        r["verdict"]["detectable_difference"])

    def test_small_improvement_label_is_crossed_out(self):
        """14.7: the rewrite the checker refuses must be shown as refused."""
        source = self.svg("fig14-02_four_verdicts.svg")
        self.assertIn("小幅有效", source)
        self.assertIn("用噪声支撑结论", source)

    def test_the_troubleshooting_order_is_drawn(self):
        source = self.svg("fig14-02_four_verdicts.svg")
        for step in ("越过可识别线", "变量泄漏", "前提条件", "最后才怀疑预期"):
            with self.subTest(step=step):
                self.assertIn(step, source)

    def test_all_four_boundary_fields_are_drawn(self):
        source = self.svg("fig14-03_boundary_four_axes.svg")
        for label in ("模型", "负载", "硬件", "配置"):
            with self.subTest(label=label):
                self.assertIn(label, source)

    def test_crossover_numbers_drawn_match_the_model(self):
        source = self.svg("fig14-03_boundary_four_axes.svg")

        def crossover(hidden, kv_dim, inter):
            return 2 * hidden + 2 * kv_dim + 3 * inter

        self.assertEqual(crossover(896, 128, 4864), 16640)
        self.assertEqual(crossover(3584, 512, 18944), 65024)
        self.assertIn("16640", source)
        self.assertIn("65024", source)
        for cross, share in ((16640, "15.3%"), (65024, "4.4%")):
            r = 3000 / cross
            self.assertEqual(f"{r / (1 + r) * 100:.1f}%", share)
            self.assertIn(share, source)

    def test_boundary_model_line_carries_the_crossover(self):
        """14.6's requirement is enforced by the tool, and drawn here."""
        for r in self.rounds:
            self.assertIn("交叉点", r["boundary"]["model"])

class TestChapterIntegration(unittest.TestCase):
    def setUp(self):
        self.text = CHAPTER.read_text(encoding="utf-8")

    def test_chapter_links_every_figure_in_order(self):
        refs = re.findall(r"!\[[^\]]*\]\((figures/[^)]+)\)", self.text)
        self.assertEqual(refs, [f"figures/{name}" for name in FIGURES])

    def test_captions_are_numbered_in_order(self):
        caps = re.findall(r"^图14-(\d+)[：:]", self.text, re.M)
        self.assertEqual(caps, [str(i + 1) for i in range(len(FIGURES))])

    def test_no_placeholder_left(self):
        self.assertNotIn("插图占位", self.text)


if __name__ == "__main__":
    unittest.main()
