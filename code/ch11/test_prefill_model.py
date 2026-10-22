#!/usr/bin/env python3
"""Tests for the Chapter 11 Prefill estimator.

Beyond the usual unit checks, these tests pin every number that appears in
the chapter text to the code, so the two cannot drift apart.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import prefill_model as pm

CONFIG_PATH = Path(__file__).resolve().parent / "model-qwen25-05b.json"


def load() -> dict:
    return pm.load_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


class ConfigTest(unittest.TestCase):
    def test_shared_config_is_valid(self):
        config = load()
        self.assertEqual(config["name"], "Qwen2.5-0.5B")

    def test_missing_field_is_rejected(self):
        config = load()
        del config["layers"]
        with self.assertRaises(pm.ModelError):
            pm.load_config(config)

    def test_heads_must_tile_hidden_size(self):
        config = load()
        config["head_dim"] = 63
        with self.assertRaises(pm.ModelError):
            pm.load_config(config)

    def test_gqa_grouping_must_divide(self):
        config = load()
        config["num_key_value_heads"] = 3
        with self.assertRaises(pm.ModelError):
            pm.load_config(config)


class ShapeTest(unittest.TestCase):
    def setUp(self):
        self.config = load()

    def test_crossover_matches_11_2(self):
        # 2*896 + 2*128 + 3*4864
        self.assertEqual(pm.crossover_tokens(self.config), 16640)

    def test_crossover_is_independent_of_layer_count(self):
        deep = dict(self.config, layers=48)
        self.assertEqual(
            pm.crossover_tokens(deep), pm.crossover_tokens(self.config)
        )

    def test_kv_dim(self):
        self.assertEqual(pm.kv_dim(self.config), 128)

    def test_non_embedding_params_is_358m(self):
        self.assertEqual(pm.non_embedding_params(self.config), 357_826_560)

    def test_embedding_overcount_is_38_percent(self):
        block = pm.compute_block(self.config, 8000)
        self.assertAlmostEqual(
            block["params_overcount_if_embedding_included"], 1.380, places=2
        )


class AttentionShareTest(unittest.TestCase):
    """11.2's table, all five rows."""

    def setUp(self):
        self.config = load()

    def test_table(self):
        expected = {
            512: (0.031, 0.030),
            2048: (0.123, 0.110),
            8000: (0.481, 0.325),
            16640: (1.000, 0.500),
            32768: (1.969, 0.663),
        }
        for tokens, (of_gemm, of_total) in expected.items():
            block = pm.compute_block(self.config, tokens)
            self.assertAlmostEqual(
                block["attention_share_of_gemm"], of_gemm, places=3,
                msg=f"{tokens} token 的 Attention/GEMM 与 11.2 的表不符",
            )
            self.assertAlmostEqual(
                block["attention_share_of_total"], of_total, places=3,
                msg=f"{tokens} token 的 Attention/总 与 11.2 的表不符",
            )

    def test_attention_equals_gemm_at_the_crossover(self):
        block = pm.compute_block(self.config, 16640)
        self.assertEqual(block["gemm_flops"], block["attention_flops"])


class DoublingTest(unittest.TestCase):
    """11.7 case 1: doubling never reaches four times."""

    def setUp(self):
        self.config = load()

    def test_case_one_is_2_2_not_4(self):
        self.assertAlmostEqual(
            pm.doubling_factor(self.config, 2000), 2.215, places=3
        )

    def test_crossover_doubling_is_exactly_three(self):
        self.assertAlmostEqual(
            pm.doubling_factor(self.config, 16640), 3.0, places=9
        )

    def test_doubling_is_monotonic_and_bounded_by_four(self):
        previous = 0.0
        for tokens in (500, 1000, 2000, 8000, 16640, 100_000, 10_000_000):
            factor = pm.doubling_factor(self.config, tokens)
            self.assertGreater(factor, previous)
            self.assertLess(factor, 4.0, "四倍必须是取不到的上限")
            previous = factor

    def test_relative_cost_ratio_equals_flops_ratio(self):
        a = pm.relative_cost(self.config, 400)
        b = pm.relative_cost(self.config, 8000)
        fa = pm.compute_block(self.config, 400)["total_flops"]
        fb = pm.compute_block(self.config, 8000)["total_flops"]
        self.assertAlmostEqual(b / a, fb / fa, places=9)

    def test_11_1_thirty_times(self):
        """400 -> 8000 is 28.9x, which is why 11.1 measures 30x."""
        ratio = pm.relative_cost(self.config, 8000) / pm.relative_cost(
            self.config, 400
        )
        self.assertAlmostEqual(ratio, 28.9, places=1)


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.config = load()

    def test_11_3_numbers(self):
        block = pm.memory_block(self.config, 8000, 50)
        self.assertEqual(block["kv_bytes_per_token_per_layer"], 512)
        self.assertEqual(block["kv_bytes_per_token"], 12288)
        self.assertAlmostEqual(block["kv_mib_one_request"], 93.75, places=2)
        self.assertAlmostEqual(block["kv_gib_at_concurrency"], 4.58, places=2)
        self.assertAlmostEqual(block["kv_mib_if_mha"], 656.25, places=2)

    def test_kv_cache_is_strictly_linear(self):
        one = pm.kv_cache_bytes(self.config, 4000)
        two = pm.kv_cache_bytes(self.config, 8000)
        self.assertEqual(two, 2 * one)

    def test_13_4_attention_matrix_sizes(self):
        small = pm.attention_matrix_bytes(self.config, 600) / 1024**2
        large = pm.attention_matrix_bytes(self.config, 8000) / 1024**2
        self.assertAlmostEqual(small, 9.61, places=2)
        self.assertAlmostEqual(large, 1708.98, places=2)
        self.assertAlmostEqual(large / small, 177.8, places=1)


class ArithmeticIntensityTest(unittest.TestCase):
    def setUp(self):
        self.config = load()

    def test_weights_only_intensity_equals_token_count(self):
        block = pm.arithmetic_intensity_block(self.config, 8000)
        self.assertAlmostEqual(block["prefill_flops_per_byte_weights_only"], 8000.0, places=1)

    def test_intensity_with_activations_is_capped(self):
        """11.4 / B-8: 287, 494, 602 at 512, 2048, 8000 tokens."""
        for tokens, expected in ((512, 286.5), (2048, 493.8), (8000, 601.8)):
            block = pm.arithmetic_intensity_block(self.config, tokens)
            self.assertAlmostEqual(block["prefill_flops_per_byte"], expected, places=1)

    def test_decode_intensity_is_one(self):
        block = pm.arithmetic_intensity_block(self.config, 8000)
        self.assertAlmostEqual(block["decode_flops_per_byte"], 1.0, places=3)

    def test_wider_model_raises_the_cap(self):
        wide = dict(self.config, hidden_size=1792, num_attention_heads=28,
                    head_dim=64, intermediate_size=9728)
        wide = pm.load_config(wide)
        a = pm.arithmetic_intensity_block(self.config, 8000)
        b = pm.arithmetic_intensity_block(wide, 8000)
        self.assertAlmostEqual(
            a["prefill_flops_per_byte_weights_only"],
            b["prefill_flops_per_byte_weights_only"], places=1,
        )
        self.assertGreater(b["prefill_flops_per_byte"], a["prefill_flops_per_byte"])


class ComparisonTest(unittest.TestCase):
    def setUp(self):
        self.config = load()

    def _report(self, measured_ms, **kw):
        return pm.build_report(
            self.config, 8000, peak_tflops=153.0, effective_tflops=30.0,
            concurrency=50, measured_ms=measured_ms, **kw,
        )

    def test_11_5_worked_example(self):
        report = self._report(None)
        self.assertAlmostEqual(report["compute"]["total_flops"] / 1e12, 8.48, places=2)
        self.assertAlmostEqual(report["comparison"]["lower_bound_ms"], 55.4, places=1)
        self.assertAlmostEqual(report["comparison"]["estimate_ms"], 282.6, places=1)

    def test_below_the_floor_points_at_the_cache(self):
        """11.7 case 2: 40 ms against a 55 ms floor."""
        report = self._report(40.0)
        self.assertIn("低于下限", report["comparison"]["reading"])
        self.assertIn("Prefix Cache", report["comparison"]["reading"])

    def test_between_floor_and_estimate_is_not_a_cache_signal(self):
        """150 ms is faster than the estimate but above the floor."""
        report = self._report(150.0)
        self.assertIn("下限与估计之间", report["comparison"]["reading"])
        self.assertIn("不能据此断定缓存命中", report["comparison"]["reading"])

    def test_same_order_reading(self):
        self.assertIn("没有明显异常", self._report(300.0)["comparison"]["reading"])

    def test_absolute_check_fails_while_ratio_check_passes(self):
        """11.1 / 11.5: 2.4 s is 8.5x the estimate, yet 30x matches 28.9x."""
        report = self._report(2400.0, reference_tokens=400, reference_ms=80.0)
        cmp_ = report["comparison"]
        self.assertIn("额外开销", cmp_["reading"])
        self.assertAlmostEqual(cmp_["ratio_to_estimate"], 8.49, places=2)
        self.assertAlmostEqual(cmp_["implied_tflops"], 3.53, places=2)
        rc = report["ratio_check"]
        self.assertTrue(rc["shape_agrees"])
        self.assertAlmostEqual(rc["expected_ratio"], 28.92, places=2)
        self.assertAlmostEqual(rc["measured_ratio"], 30.0, places=2)

    def test_ratio_check_needs_both_measurements(self):
        self.assertFalse(self._report(2400.0)["ratio_check"]["available"])

    def test_no_measurement_means_no_measurement(self):
        report = self._report(None)
        self.assertIsNone(report["comparison"]["measured_ms"])
        self.assertIsNone(report["comparison"]["ratio_to_estimate"])
        self.assertIn("没有测就是没有测", report["comparison"]["reading"])

    def test_beyond_the_context_window_warns(self):
        report = pm.build_report(
            self.config, 40000, effective_tflops=30.0, concurrency=50,
            measured_ms=None,
        )
        self.assertTrue(report["warnings"])

    def test_non_positive_inputs_are_rejected(self):
        for tokens, conc, tflops in ((0, 50, 30.0), (8000, 0, 30.0), (8000, 50, 0.0)):
            with self.assertRaises(pm.ModelError):
                pm.build_report(
                    self.config, tokens, effective_tflops=tflops,
                    concurrency=conc, measured_ms=None,
                )

    def test_effective_cannot_exceed_peak(self):
        with self.assertRaises(pm.ModelError):
            pm.build_report(self.config, 8000, peak_tflops=20.0, effective_tflops=30.0,
                            concurrency=50, measured_ms=None)


class CliTest(unittest.TestCase):
    def test_main_writes_a_report(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "estimate.json"
            code = pm.main([
                "--config", str(CONFIG_PATH),
                "--input-tokens", "8000",
                "--effective-tflops", "30",
                "--measured-ms", "2400",
                "--output", str(out),
            ])
            self.assertEqual(code, 0)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(doc["compute"]["crossover_tokens"], 16640)
            self.assertIn("disclaimer", doc)


if __name__ == "__main__":
    unittest.main()
