#!/usr/bin/env python3
"""Tests for the Chapter 17 quantization estimator and quality checker.

Pins every number in 17.2, 17.3, 17.4, 17.5 and 17.8, plus the synthetic
evalset sample in `content/ch17/evidence/`. Most of the `evaluate` tests are
rejection tests, because the value of that half is what it refuses to accept.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import unittest
from pathlib import Path

import quant_tradeoff as qt

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHARED_CONFIG = REPO / "code" / "ch15" / "model-7b-generic.json"
EVIDENCE = REPO / "content" / "ch17" / "evidence"
EVALSET = EVIDENCE / "quant-eval-sample.jsonl"
RESULTS = EVIDENCE / "quant-eval-results.json"

CONFIG = json.loads(SHARED_CONFIG.read_text(encoding="utf-8"))

MODEL = dict(params=7e9, layers=32, kv_heads=8, head_dim=128,
             gpu_memory_gib=80, bandwidth_gb_per_s=1000, overhead_gib=6,
             avg_context=2300, weight_dtypes=["fp16", "int8", "int4"],
             kv_dtypes=["fp16", "int8"])


def load_evalset() -> list[dict]:
    return [json.loads(line) for line
            in EVALSET.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_results() -> dict:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


class TestSection172WeightSide(unittest.TestCase):
    """17.2 权重量化那半张表：14 / 7 / 3.5 GB，14 / 7 / 3.5 ms，并发涨约 14%。"""

    def test_weight_sizes(self):
        self.assertAlmostEqual(qt.weight_gb(7e9, "fp16"), 14.0, places=6)
        self.assertAlmostEqual(qt.weight_gb(7e9, "int8"), 7.0, places=6)
        self.assertAlmostEqual(qt.weight_gb(7e9, "int4"), 3.5, places=6)

    def test_step_floors(self):
        self.assertAlmostEqual(qt.step_floor_ms(7e9, "fp16", 1000), 14.0, places=6)
        self.assertAlmostEqual(qt.step_floor_ms(7e9, "int8", 1000), 7.0, places=6)
        self.assertAlmostEqual(qt.step_floor_ms(7e9, "int4", 1000), 3.5, places=6)

    def test_the_floor_drops_exactly_in_proportion_to_bit_width(self):
        """“Decode 单步下限按比例下降”，一句话一条测试。"""
        for dtype, factor in (("int8", 0.5), ("int4", 0.25)):
            with self.subTest(dtype=dtype):
                self.assertAlmostEqual(
                    qt.step_floor_ms(7e9, dtype, 1000)
                    / qt.step_floor_ms(7e9, "fp16", 1000),
                    factor, places=6)

    def test_arithmetic_intensity_is_1_2_4(self):
        """17.2 那张三行表，也是 15.2 那个恒等式的另一面。"""
        self.assertEqual(qt.arithmetic_intensity("fp16"), 1.0)
        self.assertEqual(qt.arithmetic_intensity("int8"), 2.0)
        self.assertEqual(qt.arithmetic_intensity("int4"), 4.0)

    def test_even_int4_stays_far_below_the_ridge_point(self):
        """所以延迟收益接近线性，先撑不住的是质量，不是硬件。"""
        self.assertLess(qt.arithmetic_intensity("int4"), 153.0 / 30)

    def test_int8_weights_lift_concurrency_by_about_14_percent(self):
        report = qt.estimate(**MODEL)
        row = next(c for c in report["combos"]
                   if c["combo"] == "weight=int8/kv=fp16")
        self.assertEqual(row["kv_budget_gib"], 59.0)
        self.assertEqual(row["concurrency"], 210)
        self.assertAlmostEqual(row["delta_concurrency"], 0.1351, places=3)

    def test_the_budget_starts_from_the_utilization_cut(self):
        """与 16.6 第 1 步同口径：引擎只拿到 80 GiB 的九成。"""
        report = qt.estimate(**MODEL)
        self.assertEqual(report["hardware"]["gpu_memory_utilization"], 0.9)
        self.assertEqual(report["hardware"]["usable_gib"], 72.0)
        row = next(c for c in report["combos"]
                   if c["combo"] == "weight=fp16/kv=fp16")
        self.assertEqual(row["kv_budget_gib"], 52.0)

    def test_weight_deduction_rounds_up_to_a_whole_gib(self):
        """16.2 那处刻意的保守：14 GB 按 14 GiB 扣。"""
        self.assertEqual(qt.weight_memory_gib_conservative(7e9, "fp16"), 14.0)
        self.assertEqual(qt.weight_memory_gib_conservative(7e9, "int8"), 7.0)
        self.assertEqual(qt.weight_memory_gib_conservative(7e9, "int4"), 4.0)


class TestSection172KvSide(unittest.TestCase):
    """17.2 KV 量化那半张表：128 → 64 KiB，42.6 → 85.2 万 token，185 → 370 条。"""

    def test_kv_bytes_halve(self):
        self.assertEqual(qt.kv_bytes_per_token(32, 8, 128, "fp16"), 131072)
        self.assertEqual(qt.kv_bytes_per_token(32, 8, 128, "int8"), 65536)

    def test_total_tokens_and_concurrency(self):
        report = qt.estimate(**MODEL)
        fp16 = next(c for c in report["combos"]
                    if c["combo"] == "weight=fp16/kv=fp16")
        int8 = next(c for c in report["combos"]
                    if c["combo"] == "weight=fp16/kv=int8")
        self.assertEqual(fp16["total_tokens"], 425984)
        self.assertEqual(int8["total_tokens"], 851968)
        self.assertEqual(fp16["concurrency"], 185)
        self.assertEqual(int8["concurrency"], 370)

    def test_kv_quantization_does_not_move_the_step_floor(self):
        """分工那句话的一半：KV 量化主要改善容量，不改善单步下限。"""
        report = qt.estimate(**MODEL)
        fp16 = next(c for c in report["combos"]
                    if c["combo"] == "weight=fp16/kv=fp16")
        int8 = next(c for c in report["combos"]
                    if c["combo"] == "weight=fp16/kv=int8")
        self.assertEqual(fp16["step_floor_ms"], int8["step_floor_ms"])

    def test_weight_quantization_barely_moves_concurrency(self):
        """分工那句话的另一半：权重只占显存的一小部分。"""
        report = qt.estimate(**MODEL)
        w = next(c for c in report["combos"]
                 if c["combo"] == "weight=int8/kv=fp16")
        k = next(c for c in report["combos"]
                 if c["combo"] == "weight=fp16/kv=int8")
        self.assertLess(w["delta_concurrency"], 0.2)
        self.assertGreater(k["delta_concurrency"], 0.9)

    def test_the_division_of_labour_is_stated_in_the_report(self):
        report = qt.estimate(**MODEL)
        self.assertIn("瓶颈是 TPOT 就量权重",
                      report["division_of_labour"]["reading"])

    def test_fp16_must_be_in_both_lists(self):
        with self.assertRaises(qt.QuantError):
            qt.estimate(**(MODEL | {"weight_dtypes": ["int8"]}))
        with self.assertRaises(qt.QuantError):
            qt.estimate(**(MODEL | {"kv_dtypes": ["int8"]}))

    def test_unknown_dtype_is_rejected(self):
        with self.assertRaises(qt.QuantError):
            qt.estimate(**(MODEL | {"weight_dtypes": ["fp16", "int3"]}))


class TestSection173EffectiveBitWidth(unittest.TestCase):
    """17.3：离群值大 100 倍时主体只占约 3 个格子，等效位宽约 1.6 位。"""

    def test_no_outlier_means_the_full_eight_bits(self):
        self.assertEqual(qt.effective_bit_width(1.0), 8.0)

    def test_an_outlier_100x_larger_leaves_about_three_cells(self):
        self.assertAlmostEqual(256 / 100, 2.56, places=2)

    def test_the_effective_width_is_about_1_6_bits(self):
        self.assertAlmostEqual(qt.effective_bit_width(100.0), 1.36, places=2)
        self.assertAlmostEqual(math.log2(3), 1.585, places=3)

    def test_six_and_a_bit_bits_are_lost(self):
        """正文那句“8 位里有六位多被少数几个数占掉了”。"""
        self.assertGreater(8 - qt.effective_bit_width(100.0), 6.0)

    def test_a_milder_outlier_costs_less(self):
        self.assertGreater(qt.effective_bit_width(10.0),
                           qt.effective_bit_width(100.0))

    def test_an_extreme_outlier_bottoms_out_at_zero(self):
        self.assertEqual(qt.effective_bit_width(1000.0), 0.0)

    def test_a_ratio_below_one_is_rejected(self):
        with self.assertRaises(qt.QuantError):
            qt.effective_bit_width(0.5)


class TestSection178RealisedSaving(unittest.TestCase):
    """17.8 案例一：实测是下限的 6.25 倍，权重减半只省 8%。"""

    def test_the_case_one_number(self):
        result = qt.realised_saving(0.5, 6.25)
        self.assertAlmostEqual(result["realised_saving"], 0.08, places=4)

    def test_close_to_the_floor_the_saving_is_about_forty_percent(self):
        """正文的反向用法：实测是下限的 1.2 倍时，权重减半能省四成。"""
        result = qt.realised_saving(0.5, 1.2)
        self.assertAlmostEqual(result["realised_saving"], 0.4167, places=3)

    def test_the_upper_bound_is_always_the_floor_saving(self):
        self.assertEqual(qt.realised_saving(0.5, 6.25)["upper_bound"], 0.5)

    def test_without_a_measurement_only_the_bound_is_given(self):
        result = qt.realised_saving(0.5, None)
        self.assertIsNone(result["realised_saving"])
        self.assertEqual(result["upper_bound"], 0.5)
        self.assertIn("只能给上界", result["reading"])

    def test_a_ratio_below_one_is_rejected_with_the_155_reason(self):
        with self.assertRaises(qt.QuantError) as ctx:
            qt.realised_saving(0.5, 0.9)
        self.assertIn("边界定义", str(ctx.exception))

    def test_a_scheduler_bound_service_earns_a_warning(self):
        report = qt.estimate(**(MODEL | {"measured_tpot_ms": 87.5}))
        self.assertTrue(any("换不回多少" in w for w in report["warnings"]))

    def test_without_a_measurement_the_table_says_so(self):
        report = qt.estimate(**MODEL)
        self.assertTrue(any("不是你会拿到的变化" in w for w in report["warnings"]))

    def test_the_table_always_says_it_does_not_price_quality(self):
        report = qt.estimate(**MODEL)
        self.assertTrue(any("不算质量" in w for w in report["warnings"]))


class TestEvalsetRequirements(unittest.TestCase):
    """17.4：只有短问答的评测集测不出那两类退化。"""

    def test_a_short_qa_only_evalset_is_rejected(self):
        with self.assertRaises(qt.QuantError) as ctx:
            qt.check_evalset([{"kind": "short_qa"}] * 50)
        self.assertIn("long_answer", str(ctx.exception))
        self.assertIn("structured_output", str(ctx.exception))

    def test_a_missing_structured_output_kind_is_rejected(self):
        with self.assertRaises(qt.QuantError):
            qt.check_evalset([{"kind": "short_qa"}, {"kind": "long_answer"}])

    def test_an_empty_evalset_is_rejected(self):
        with self.assertRaises(qt.QuantError):
            qt.check_evalset([])

    def test_the_sample_evalset_carries_both_required_kinds(self):
        summary = qt.check_evalset(load_evalset())
        self.assertIn("long_answer", summary["kinds"])
        self.assertIn("structured_output", summary["kinds"])


class TestEvaluateRejections(unittest.TestCase):
    """底线必须在量化之前定，两边的样本数必须一致。"""

    def setUp(self):
        self.samples = load_evalset()
        self.results = load_results()

    def _call(self, **overrides):
        kwargs = dict(
            samples=self.samples,
            baseline_scores=self.results["baseline_scores"],
            variant_scores=self.results["variant_scores"],
            threshold=0.01,
            threshold_written_at=self.results["threshold_written_at"],
            per_kind=self.results["per_kind"],
        )
        return qt.evaluate(**(kwargs | overrides))

    def test_a_threshold_without_a_written_at_is_rejected(self):
        with self.assertRaises(qt.QuantError) as ctx:
            self._call(threshold_written_at=None)
        self.assertIn("无法证伪", str(ctx.exception))

    def test_mismatched_score_counts_are_rejected(self):
        with self.assertRaises(qt.QuantError):
            self._call(variant_scores=self.results["variant_scores"][:-1])

    def test_a_threshold_outside_zero_to_one_is_rejected(self):
        for bad in (0, 1, 1.5, -0.1):
            with self.subTest(threshold=bad):
                with self.assertRaises(qt.QuantError):
                    self._call(threshold=bad)


class TestTheSyntheticSample(unittest.TestCase):
    """样例刻意演示 17.4 那个稀释陷阱：总分通过，结构化输出已越界。"""

    def setUp(self):
        self.report = qt.evaluate(
            samples=load_evalset(),
            baseline_scores=load_results()["baseline_scores"],
            variant_scores=load_results()["variant_scores"],
            threshold=0.01,
            threshold_written_at=load_results()["threshold_written_at"],
            per_kind=load_results()["per_kind"],
        )

    def test_the_total_drop_clears_the_one_point_line(self):
        self.assertAlmostEqual(self.report["drop"], 0.0068, places=3)
        self.assertLess(self.report["drop"], 0.01)

    def test_but_structured_output_has_breached(self):
        struct = next(k for k in self.report["per_kind"]
                      if k["kind"] == "structured_output")
        self.assertAlmostEqual(struct["drop"], 0.039, places=3)
        self.assertFalse(struct["passed"])

    def test_the_overall_verdict_is_still_a_failure(self):
        """总分通过不能放行：逐维度越界就是不通过。"""
        self.assertFalse(self.report["passed"])

    def test_the_worst_dimension_is_named(self):
        self.assertEqual(self.report["worst_kind"], "structured_output")

    def test_the_reading_explains_why_the_total_is_misleading(self):
        self.assertIn("总分通过而某一维度越界", self.report["reading"])

    def test_short_qa_shows_no_drop_at_all(self):
        """稀释的机理：短问答一分没掉，而它占了一半样本。"""
        short = next(k for k in self.report["per_kind"] if k["kind"] == "short_qa")
        self.assertEqual(short["drop"], 0.0)
        kinds = [s["kind"] for s in load_evalset()]
        self.assertEqual(kinds.count("short_qa"), 10)
        self.assertEqual(len(kinds), 20)

    def test_the_structured_drop_is_the_twentyfold_error_rate_in_the_text(self):
        """0.998 → 0.959 就是 0.2% → 4.1%，二十倍。"""
        self.assertAlmostEqual((1 - 0.959) / (1 - 0.998), 20.5, places=1)

    def test_the_sample_is_labelled_synthetic(self):
        self.assertTrue(load_results()["synthetic"])
        self.assertIn("不是真机结果", load_results()["_note"])

    def test_the_protocol_pins_temperature_to_zero(self):
        self.assertEqual(load_results()["protocol"]["temperature"], 0)


class TestCli(unittest.TestCase):
    def test_estimate_reads_the_shared_config(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = qt.main(["estimate", "--config", str(SHARED_CONFIG),
                          "--measured-tpot-ms", "17"])
        self.assertEqual(rc, 0)
        self.assertIn("14.0 ms", out.getvalue())

    def test_evaluate_runs_on_the_sample(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = qt.main(["evaluate", "--evalset", str(EVALSET),
                          "--results", str(RESULTS), "--threshold", "0.01"])
        self.assertEqual(rc, 0)
        self.assertIn("不通过", out.getvalue())

    def test_estimate_rejects_a_bad_dtype_without_a_traceback(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = qt.main(["estimate", "--config", str(SHARED_CONFIG),
                          "--weight-dtype", "fp16,int3"])
        self.assertEqual(rc, 1)
        self.assertIn("REJECTED", out.getvalue())

    def test_report_is_json_serialisable(self):
        json.dumps(qt.estimate(**(MODEL | {"measured_tpot_ms": 17.0})),
                   ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
