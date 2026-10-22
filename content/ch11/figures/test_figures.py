#!/usr/bin/env python3
"""Figure tests for Chapter 11.

They check the visual contract and the things this chapter's figures must not
say, not that the pictures look nice. The numeric assertions at the bottom pin
the figures to code/ch11/prefill_model.py, so a figure cannot drift away from
the model the chapter builds.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER = FIGURE_DIR.parent / "ch11.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch11"))

FIGURES = {
    "fig11-01_gemm_vs_attention.svg": "GEMM 与 Attention 在 16640 处交叉",
    "fig11-02_kv_two_directions.svg": "KV Cache 往两个方向长",
    "fig11-03_arithmetic_intensity_axis.svg": "算术强度数轴上的两个点",
    "fig11-04_estimate_vs_measured.svg": "实测落在下限的哪一侧",
}

FORBIDDEN = {
    # 11.2 is about the shape of the compute, not about time.
    "fig11-01_gemm_vs_attention.svg": ["ms", "TFLOP"],
    # 11.3 covers KV Cache only; the rest of the memory bill is chapter 16.
    "fig11-02_kv_two_directions.svg": ["权重占用", "激活值占用", "并发上限"],
    # No figure in this chapter may name a specific card: the balance point is a
    # band and the effective throughput is an assumption.
    "fig11-03_arithmetic_intensity_axis.svg": ["A100", "H100", "GX10"],
    "fig11-04_estimate_vs_measured.svg": ["A100", "H100", "GX10"],
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
                title = root.find(f"{ns}title")
                desc = root.find(f"{ns}desc")
                self.assertIsNotNone(title)
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

    def test_the_balance_point_is_a_band_not_a_line(self):
        """11.4: the hardware balance point varies by card, so it is a range."""
        source = (FIGURE_DIR / "fig11-03_arithmetic_intensity_axis.svg").read_text(
            encoding="utf-8")
        self.assertIn("一两百到几百", source)

    def test_four_times_is_only_ever_mentioned_as_unreachable(self):
        """11.7 case 1: '四倍' may appear, but never as something attainable."""
        source = (FIGURE_DIR / "fig11-01_gemm_vs_attention.svg").read_text(encoding="utf-8")
        for match in re.finditer(r"四倍|趋近 4", source):
            tail = source[match.end():match.end() + 12]
            head = source[max(0, match.start() - 12):match.start()]
            with self.subTest(context=head + "|" + tail):
                self.assertTrue(
                    "取不到" in tail or "不了" in head,
                    "四倍只能以“取不到 / 到不了”的形式出现",
                )

    def test_effective_throughput_is_marked_as_an_assumption(self):
        """11.5: the number divided by is never presented as a spec sheet figure."""
        source = (FIGURE_DIR / "fig11-04_estimate_vs_measured.svg").read_text(encoding="utf-8")
        self.assertIn("假设值", source)
        self.assertIn("不是规格峰值", source)


class TestFiguresMatchTheModel(unittest.TestCase):
    """Every number drawn must come out of code/ch11/prefill_model.py."""

    @classmethod
    def setUpClass(cls):
        import prefill_model as pm

        cls.pm = pm
        cls.config = pm.load_config(json.loads(
            (ROOT / "code" / "ch11" / "model-qwen25-05b.json").read_text(encoding="utf-8")))

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_crossover_drawn_matches_the_config(self):
        crossover = self.pm.crossover_tokens(self.config)
        self.assertEqual(crossover, 16640)
        self.assertIn(str(crossover), self.svg("fig11-01_gemm_vs_attention.svg"))

    def test_attention_shares_drawn_match(self):
        """The five rows are recomputed, not copied: the figure must show them."""
        source = self.svg("fig11-01_gemm_vs_attention.svg")
        chapter = CHAPTER.read_text(encoding="utf-8")
        for tokens in (512, 2048, 8000, 16640, 32768):
            share = self.pm.compute_block(self.config, tokens)["attention_share_of_total"]
            label = f"{round(share * 100)}%"
            with self.subTest(tokens=tokens):
                self.assertIn(label, source)
                self.assertIn(f"| {tokens} |", chapter)

    def test_doubling_factors_drawn_match(self):
        source = self.svg("fig11-01_gemm_vs_attention.svg")
        for tokens in (1000, 2000, 8000, 16640):
            factor = f"{self.pm.doubling_factor(self.config, tokens):.2f}"
            with self.subTest(tokens=tokens):
                self.assertIn(factor, source)

    def test_four_is_shown_as_unreachable(self):
        source = self.svg("fig11-01_gemm_vs_attention.svg")
        self.assertIn("取不到", source)

    def test_kv_numbers_drawn_match(self):
        source = self.svg("fig11-02_kv_two_directions.svg")
        block = self.pm.memory_block(self.config, 8000, 50)
        self.assertEqual(block["kv_bytes_per_token_per_layer"], 512)
        self.assertIn("512 B", source)
        self.assertIn("12 KiB", source)
        self.assertEqual(round(block["kv_mib_one_request"]), 94)
        self.assertIn("94 MiB", source)
        self.assertEqual(f"{block['kv_gib_at_concurrency']:.2f}", "4.58")
        self.assertIn("4.58 GiB", source)

    def test_binary_units_only(self):
        """11.3 fixed the convention; the figure must not mix in MB or GB."""
        source = self.svg("fig11-02_kv_two_directions.svg")
        self.assertNotIn("MB", source)
        self.assertNotIn("GB", source)

    def test_intensity_drawn_matches(self):
        source = self.svg("fig11-03_arithmetic_intensity_axis.svg")
        block = self.pm.arithmetic_intensity_block(self.config, 8000)
        self.assertEqual(round(block["prefill_flops_per_byte_weights_only"]), 8000)
        self.assertEqual(round(block["prefill_flops_per_byte"]), 602)
        self.assertEqual(round(block["decode_flops_per_byte"]), 1)
        self.assertIn("只算权重 8000", source)
        self.assertIn("Prefill ≈ 602", source)
        self.assertIn("相差约 600 倍", source)

    def test_floor_drawn_matches(self):
        source = self.svg("fig11-04_estimate_vs_measured.svg")
        report = self.pm.build_report(self.config, 8000, peak_tflops=153.0,
                                      effective_tflops=30.0,
                                      concurrency=50, measured_ms=None)
        self.assertEqual(round(report["comparison"]["estimate_ms"]), 283)
        self.assertEqual(round(report["comparison"]["lower_bound_ms"]), 55)
        self.assertIn("283 ms", source)
        self.assertIn("55 ms", source)
        self.assertIn("8.5 TFLOPs", source)

    def test_below_the_floor_is_drawn_as_a_signal_not_a_win(self):
        source = self.svg("fig11-04_estimate_vs_measured.svg")
        self.assertIn("低于下限", source)
        self.assertIn("Prefix Cache", source)


class TestChapterIntegration(unittest.TestCase):
    def setUp(self):
        self.text = CHAPTER.read_text(encoding="utf-8")

    def test_chapter_links_every_figure_in_order(self):
        refs = re.findall(r"!\[[^\]]*\]\((figures/[^)]+)\)", self.text)
        self.assertEqual(refs, [f"figures/{name}" for name in FIGURES])

    def test_captions_are_numbered_in_order(self):
        caps = re.findall(r"^图11-(\d+)[：:]", self.text, re.M)
        self.assertEqual(caps, [str(i + 1) for i in range(len(FIGURES))])

    def test_no_placeholder_left(self):
        self.assertNotIn("插图占位", self.text)


if __name__ == "__main__":
    unittest.main()
