#!/usr/bin/env python3
"""Tests for the Chapter 15 Decode estimator.

Two jobs. The first is the usual validation. The second, and the reason this
file is long, is to pin every number printed in Chapter 15 to the code that
produces it: if the text and the code disagree, this suite fails. That is what
caught two wrong numbers in Chapter 11 during the 2026-09-22 review.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

import decode_model as dm

HERE = Path(__file__).resolve().parent
CONFIG_7B = json.loads((HERE / "model-7b-generic.json").read_text(encoding="utf-8"))
CONFIG_05B = json.loads(
    (HERE.parent / "ch11" / "model-qwen25-05b.json").read_text(encoding="utf-8")
)

GIB = 1024 ** 3
MIB = 1024 ** 2
KIB = 1024


class TestConfigValidation(unittest.TestCase):
    def test_shared_config_loads(self):
        config = dm.load_config(CONFIG_7B)
        self.assertEqual(config["params_total"], 7_000_000_000)
        self.assertEqual(config["bytes_per_element"], 2)

    def test_non_object_is_rejected(self):
        with self.assertRaises(dm.ModelError):
            dm.load_config([1, 2, 3])

    def test_missing_field_is_rejected(self):
        broken = {k: v for k, v in CONFIG_7B.items() if k != "layers"}
        with self.assertRaises(dm.ModelError):
            dm.load_config(broken)

    def test_zero_field_is_rejected(self):
        with self.assertRaises(dm.ModelError):
            dm.load_config({**CONFIG_7B, "head_dim": 0})

    def test_gqa_head_ratio_is_checked(self):
        with self.assertRaises(dm.ModelError):
            dm.load_config({**CONFIG_7B, "num_key_value_heads": 7})

    def test_zero_bandwidth_is_rejected(self):
        with self.assertRaises(dm.ModelError):
            dm.build_report(CONFIG_7B, [1], [512], bandwidth_gb_per_s=0)

    def test_empty_sweep_is_rejected(self):
        with self.assertRaises(dm.ModelError):
            dm.build_report(CONFIG_7B, [], [512], bandwidth_gb_per_s=1000)
        with self.assertRaises(dm.ModelError):
            dm.build_report(CONFIG_7B, [1], [], bandwidth_gb_per_s=1000)

    def test_batch_below_one_is_rejected(self):
        with self.assertRaises(dm.ModelError):
            dm.build_point(CONFIG_7B, 0, 512, bandwidth_gb_per_s=1000)


class TestSection153WeightsAndFloor(unittest.TestCase):
    """15.3: 权重 14 GB，单步下限 14 ms，对应每秒约 71 个 token。"""

    def test_weight_bytes_are_decimal(self):
        self.assertEqual(dm.weight_bytes(7e9, 2), 14e9)
        self.assertAlmostEqual(dm.weight_bytes(7e9, 2) / 1e9, 14.0, places=6)

    def test_the_same_weights_in_binary_are_13_gib(self):
        """16.2 说破的那处交界：同一份权重，十进制 14 GB、二进制 13.04 GiB。"""
        self.assertAlmostEqual(dm.weight_bytes(7e9, 2) / GIB, 13.04, places=2)

    def test_step_floor_is_14ms(self):
        self.assertAlmostEqual(dm.step_floor_ms(14e9, 1000), 14.0, places=6)

    def test_floor_corresponds_to_71_tokens_per_second(self):
        report = dm.build_report(CONFIG_7B, [1], [512], bandwidth_gb_per_s=1000)
        self.assertEqual(report["comparison"]["tokens_per_second_at_floor"], 71.4)

    def test_floor_does_not_depend_on_context_length(self):
        """15.3 第二层含义：权重字节数固定，和输入多长没关系。"""
        short = dm.build_point(CONFIG_7B, 1, 128, bandwidth_gb_per_s=1000)
        long_ = dm.build_point(CONFIG_7B, 1, 16384, bandwidth_gb_per_s=1000)
        self.assertEqual(short["step_floor_ms"], long_["step_floor_ms"])

    def test_halving_the_weight_width_halves_the_floor(self):
        """17.2 的收益上界就是这一条。"""
        fp16 = dm.step_floor_ms(dm.weight_bytes(7e9, 2), 1000)
        int8 = dm.step_floor_ms(dm.weight_bytes(7e9, 1), 1000)
        self.assertAlmostEqual(int8, fp16 / 2, places=6)


class TestSection152ArithmeticIntensity(unittest.TestCase):
    """15.2：批量 1 的 Decode 算术强度恒等于 1，与模型大小无关。"""

    def test_fp16_batch_one_is_exactly_one(self):
        self.assertEqual(dm.decode_arithmetic_intensity(1, 2), 1.0)

    def test_int8_is_two_and_int4_is_four(self):
        self.assertEqual(dm.decode_arithmetic_intensity(1, 1), 2.0)
        self.assertEqual(dm.decode_arithmetic_intensity(1, 0.5), 4.0)

    def test_it_is_identical_for_the_05b_and_the_7b(self):
        """这是 15.2 那句“与模型多大无关”，两份真实配置各跑一次。"""
        small = dm.build_point(CONFIG_05B | {"params_total": 494_032_768},
                              1, 512, bandwidth_gb_per_s=1000)
        large = dm.build_point(CONFIG_7B, 1, 512, bandwidth_gb_per_s=1000)
        self.assertEqual(small["arithmetic_intensity"],
                         large["arithmetic_intensity"])
        self.assertEqual(large["arithmetic_intensity"], 1.0)

    def test_batch_multiplies_it(self):
        """15.4 理由二：批量为 B 时算术强度约等于 B。"""
        point = dm.build_point(CONFIG_7B, 32, 512, bandwidth_gb_per_s=1000)
        self.assertEqual(point["arithmetic_intensity"], 32.0)

    def test_a100_balance_point_is_153(self):
        self.assertAlmostEqual(dm.hardware_balance_point(312.0, 2039.0), 153.0,
                              places=0)

    def test_the_gap_is_two_orders_of_magnitude(self):
        """15.2 的结论句：批量 1 是 1，卡的分界点是上百。"""
        balance = dm.hardware_balance_point(312.0, 2039.0)
        self.assertGreater(balance / dm.decode_arithmetic_intensity(1, 2), 100)


class TestSection154Batching(unittest.TestCase):
    """15.4：批量 32 摊薄到约 0.44 ms/token，交叉批量在一百多。"""

    def test_batch_32_amortizes_to_0_44ms(self):
        """正文那张对照表：14 GB 读一遍，产出 32 个 token。"""
        self.assertAlmostEqual(14.0 / 32, 0.4375, places=4)
        point = dm.build_point(CONFIG_7B, 32, 1, bandwidth_gb_per_s=1000)
        self.assertAlmostEqual(point["amortized_ms_per_token"], 0.4375, places=3)

    def test_throughput_grows_and_tpot_barely_moves_below_the_crossover(self):
        report = dm.build_report(CONFIG_7B, [1, 32], [512],
                                 bandwidth_gb_per_s=1000)
        one, thirty_two = report["points"]
        self.assertGreater(thirty_two["throughput_tps"],
                           one["throughput_tps"] * 25)
        # "单条请求的 TPOT 几乎没有变差"：短上下文下 30 倍吞吐只换来不到 20% 的 TPOT
        self.assertLess(thirty_two["tpot_ms"] / one["tpot_ms"], 1.2)

    def test_crossover_batch_on_an_a100_is_in_the_low_hundreds(self):
        cross = dm.crossover_batch(312.0, 2039.0, 2)
        self.assertAlmostEqual(cross, 153.0, places=0)
        self.assertTrue(100 <= cross < 1000)

    def test_int8_weights_pull_the_crossover_in(self):
        """位宽减半，同一张卡上更小的批量就算力受限了。

        这一条是 17.2 的边界：量化让每个字节承载的运算翻倍，所以算术强度提前
        追上分界点。批量已经很大的服务，量化的收益会比小批量时明显小。
        """
        fp16 = dm.crossover_batch(312.0, 2039.0, 2)
        int8 = dm.crossover_batch(312.0, 2039.0, 1)
        self.assertLess(int8, fp16)
        self.assertAlmostEqual(int8, fp16 / 2, places=6)
        self.assertAlmostEqual(int8, 76.5, places=1)

    def test_no_peak_tflops_means_no_balance_point(self):
        """没给峰值算力就不猜一个：分界点和交叉批量都留空。"""
        report = dm.build_report(CONFIG_7B, [1], [512], bandwidth_gb_per_s=1000)
        self.assertIsNone(report["hardware"]["balance_point_flops_per_byte"])
        self.assertIsNone(report["hardware"]["crossover_batch"])

    def test_crossing_the_crossover_batch_raises_a_warning(self):
        report = dm.build_report(CONFIG_7B, [1, 256], [512],
                                 bandwidth_gb_per_s=2039,
                                 peak_tflops=312.0)
        self.assertTrue(any("免费" in w for w in report["warnings"]))


class TestSection157KvRead(unittest.TestCase):
    """15.7：8000 token 时单条 KV 是 1000 MiB，批量 32 时 31 GiB 超过权重。"""

    def test_bytes_per_token_is_128_kib(self):
        self.assertEqual(dm.kv_bytes_per_token(CONFIG_7B), 131072)
        self.assertEqual(dm.kv_bytes_per_token(CONFIG_7B) / KIB, 128.0)

    def test_8000_tokens_is_1000_mib(self):
        point = dm.build_point(CONFIG_7B, 1, 8000, bandwidth_gb_per_s=1000)
        self.assertEqual(point["kv_bytes_per_step"] / MIB, 1000.0)

    def test_batch_32_at_8000_tokens_is_31_gib(self):
        point = dm.build_point(CONFIG_7B, 32, 8000, bandwidth_gb_per_s=1000)
        self.assertAlmostEqual(point["kv_gib_per_step"], 31.25, places=2)

    def test_batch_32_at_8000_tokens_overtakes_the_weights(self):
        """正文那句“这时 Attention 成了主导”，由代码判定，不靠眼量。"""
        point = dm.build_point(CONFIG_7B, 32, 8000, bandwidth_gb_per_s=1000)
        self.assertTrue(point["kv_dominates"])
        self.assertGreater(point["kv_gib_per_step"],
                           dm.weight_bytes(7e9, 2) / GIB)

    def test_a_single_request_at_8000_tokens_does_not_overtake_them(self):
        point = dm.build_point(CONFIG_7B, 1, 8000, bandwidth_gb_per_s=1000)
        self.assertFalse(point["kv_dominates"])

    def test_kv_read_grows_linearly_in_both_batch_and_context(self):
        base = dm.build_point(CONFIG_7B, 4, 1000, bandwidth_gb_per_s=1000)
        twice_batch = dm.build_point(CONFIG_7B, 8, 1000, bandwidth_gb_per_s=1000)
        twice_ctx = dm.build_point(CONFIG_7B, 4, 2000, bandwidth_gb_per_s=1000)
        self.assertEqual(twice_batch["kv_bytes_per_step"],
                         base["kv_bytes_per_step"] * 2)
        self.assertEqual(twice_ctx["kv_bytes_per_step"],
                         base["kv_bytes_per_step"] * 2)

    def test_context_beyond_the_window_warns_instead_of_silently_computing(self):
        point = dm.build_point(CONFIG_7B, 1, 99999, bandwidth_gb_per_s=1000)
        self.assertTrue(any("context_window" in w for w in point["warnings"]))


class TestSection155ReadingTheRatio(unittest.TestCase):
    """15.5：实测与下限的比值分三档，第一档是“比下限还快”。"""

    def test_below_the_floor_is_flagged_as_a_definition_problem(self):
        self.assertIn("边界定义", dm.read_ratio(0.8))

    def test_the_156_example_is_bandwidth_bound(self):
        """15.6：理论下限 14 ms、实测 17 ms，比值 1.21。"""
        self.assertAlmostEqual(17.0 / 14.0, 1.214, places=3)
        self.assertIn("带宽受限", dm.read_ratio(17.0 / 14.0))

    def test_the_ch15_case_one_ratio_is_scheduler_bound(self):
        """15.9 案例一：实测是下限的两倍多，加卡不解决调度开销。"""
        self.assertIn("调度受限", dm.read_ratio(2.2))

    def test_the_ch17_case_one_ratio_is_scheduler_bound(self):
        """17.8 案例一：实测是下限的 6.25 倍，量化只能省 8%。"""
        self.assertIn("调度受限", dm.read_ratio(6.25))
        self.assertAlmostEqual(0.5 / 6.25, 0.08, places=6)

    def test_mixed_band_exists_between_the_two(self):
        self.assertIn("混合", dm.read_ratio(1.6))

    def test_no_measurement_means_no_reading(self):
        report = dm.build_report(CONFIG_7B, [1], [512], bandwidth_gb_per_s=1000)
        self.assertIsNone(report["comparison"]["ratio"])
        self.assertIn("没有实测值", report["comparison"]["reading"])

    def test_a_non_positive_measurement_is_rejected(self):
        with self.assertRaises(dm.ModelError):
            dm.build_report(CONFIG_7B, [1], [512], bandwidth_gb_per_s=1000,
                            measured_tpot_ms=0)


class TestReportShape(unittest.TestCase):
    def test_both_unit_conventions_are_labelled(self):
        report = dm.build_report(CONFIG_7B, [1], [512], bandwidth_gb_per_s=1000)
        self.assertIn("decimal", report["units"]["weights_and_bandwidth"])
        self.assertIn("binary", report["units"]["memory_occupancy"])

    def test_points_are_sorted_and_deduplicated(self):
        report = dm.build_report(CONFIG_7B, [32, 1, 32], [512, 512],
                                 bandwidth_gb_per_s=1000)
        self.assertEqual([p["batch"] for p in report["points"]], [1, 32])

    def test_report_is_json_serialisable(self):
        report = dm.build_report(CONFIG_7B, [1, 8], [512, 4096],
                                 bandwidth_gb_per_s=1000, peak_tflops=312.0,
                                 balance_bandwidth_gb_per_s=2039.0,
                                 measured_tpot_ms=17.0)
        json.dumps(report, ensure_ascii=False)

    def test_bandwidth_falls_back_to_the_shared_config(self):
        report = dm.build_report(CONFIG_7B, [1], [512])
        self.assertEqual(report["hardware"]["bandwidth_gb_per_s"], 1000)

    def test_cli_runs_and_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = dm.main(["--config", str(HERE / "model-7b-generic.json"),
                          "--batch", "1,32", "--context", "4096",
                          "--measured-tpot-ms", "17"])
        self.assertEqual(rc, 0)

    def test_cli_rejects_a_config_without_params_total(self):
        """ch11 那份 Qwen2.5-0.5B 模型配置没有 params_total，不能直接拿来跑这一章。"""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = dm.main(["--config",
                          str(HERE.parent / "ch11" / "model-qwen25-05b.json"),
                          "--batch", "1", "--context", "512"])
        self.assertEqual(rc, 1)
        self.assertIn("params_total", out.getvalue())


if __name__ == "__main__":
    unittest.main()
