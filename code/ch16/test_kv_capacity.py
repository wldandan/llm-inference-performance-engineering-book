#!/usr/bin/env python3
"""Tests for the Chapter 16 capacity calculator.

Every number in 16.2, 16.4, 16.5, 16.6, 16.7 and 16.9 is pinned here. The
suite's job is to fail when the text and the code drift apart, which is the
failure mode the 2026-09-22 review found six instances of in Part 3.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

import kv_capacity as kc

HERE = Path(__file__).resolve().parent
SHARED_CONFIG = HERE.parent / "ch15" / "model-7b-generic.json"

GIB = 1024 ** 3
MIB = 1024 ** 2
KIB = 1024

# 16.6's table, as arguments.
TABLE = dict(
    layers=32, kv_heads=8, head_dim=128, dtype="fp16",
    gpu_memory_gib=80, weight_memory_gib=14, overhead_gib=6,
    avg_context=2300, p99_context=9200, block_size=16,
)


class TestSection162BytesPerToken(unittest.TestCase):
    """16.2：每 token 131072 字节 = 128 KiB，4096 token = 512 MiB。"""

    def test_bytes_per_token_is_131072(self):
        self.assertEqual(kc.bytes_per_token(32, 8, 128, 2), 131072)

    def test_that_is_exactly_128_kib(self):
        self.assertEqual(kc.bytes_per_token(32, 8, 128, 2) / KIB, 128.0)

    def test_4096_tokens_is_exactly_512_mib(self):
        self.assertEqual(4096 * kc.bytes_per_token(32, 8, 128, 2) / MIB, 512.0)

    def test_66_gib_holds_132_such_requests(self):
        """16.1、16.2 开头那个上界：80 减 14 就是 66 GiB。"""
        per_request = 4096 * kc.bytes_per_token(32, 8, 128, 2)
        self.assertEqual(int(66 * GIB // per_request), 132)

    def test_mha_would_be_four_times_larger(self):
        """GQA 的收益：这个 7B 是 32 个 Q head 对 8 个 KV head，比例 4。
        第 11 章那个 0.5B 是 14 对 2，比例 7，两处不同是模型形状不同。"""
        gqa = kc.bytes_per_token(32, 8, 128, 2)
        mha = kc.bytes_per_token(32, 32, 128, 2)
        self.assertEqual(mha, gqa * 4)

    def test_int8_kv_halves_it(self):
        """17.5 与 19.5 那笔账的起点。"""
        self.assertEqual(kc.bytes_per_token(32, 8, 128, 1),
                         kc.bytes_per_token(32, 8, 128, 2) / 2)

    def test_non_positive_shape_is_rejected(self):
        for kwargs in ({"layers": 0}, {"kv_heads": 0}, {"head_dim": 0}):
            args = dict(layers=32, kv_heads=8, head_dim=128,
                        bytes_per_element=2) | kwargs
            with self.assertRaises(kc.CapacityError):
                kc.bytes_per_token(**args)


class TestSection166TheTable(unittest.TestCase):
    """16.6：72 GiB 可用预算、52 GiB 给 KV、42.6 万 token、185 条、建议 130~148 条。"""

    def setUp(self):
        self.report = kc.build_report(**TABLE)

    def test_budget_is_60_gib(self):
        self.assertEqual(self.report["budget"]["kv_budget_gib"], 52.0)

    def test_total_tokens_is_425984(self):
        self.assertEqual(self.report["total_tokens"], 425984)

    def test_the_text_rounds_it_to_490000(self):
        """正文写 ≈426000，精确值 425984，差 0.004%，这个近似是诚实的。"""
        self.assertLess(abs(425984 - 426000) / 425984, 0.005)

    def test_concurrency_at_average_length_is_185(self):
        self.assertEqual(self.report["concurrency_avg"], 185)

    def test_concurrency_at_p99_length_is_46(self):
        self.assertEqual(self.report["concurrency_p99"], 46)

    def test_recommended_range_is_130_to_148(self):
        self.assertEqual(self.report["recommended"], [129, 148])

    def test_the_safe_number_sits_between_the_two_concurrencies(self):
        """16.8 那句刻意的设计：安全并发在 P99 与平均之间。"""
        low, high = self.report["recommended"]
        self.assertLess(self.report["concurrency_p99"], low)
        self.assertLessEqual(high, self.report["concurrency_avg"])

    def test_concurrency_floors_rather_than_rounds(self):
        """装不下的请求不会半装进去。"""
        self.assertEqual(kc.concurrency(1000, 300), 3)

    def test_overhead_always_carries_a_measure_it_yourself_warning(self):
        self.assertTrue(any("必须在自己的环境里实测" in w
                            for w in self.report["warnings"]))

    def test_a_budget_eaten_by_weights_is_rejected_with_an_explanation(self):
        with self.assertRaises(kc.CapacityError) as ctx:
            kc.kv_budget_bytes(80, 76, 6)
        self.assertIn("没有显存留给 KV Cache", str(ctx.exception))

    def test_p99_shorter_than_average_is_rejected(self):
        with self.assertRaises(kc.CapacityError):
            kc.build_report(**(TABLE | {"avg_context": 9200,
                                        "p99_context": 2300}))

    def test_unknown_dtype_is_rejected(self):
        with self.assertRaises(kc.CapacityError):
            kc.build_report(**(TABLE | {"dtype": "fp4"}))


class TestSection167LongContextTable(unittest.TestCase):
    """16.7 那张四行表，每一行都由代码算出来。"""

    EXPECTED = [(2300, 185), (4600, 92), (9200, 46), (32000, 13)]

    def test_all_four_rows(self):
        total = kc.kv_budget_bytes(80, 14, 6) / kc.bytes_per_token(32, 8, 128, 2)
        for context, expected in self.EXPECTED:
            with self.subTest(context=context):
                self.assertEqual(kc.concurrency(total, context), expected)

    def test_per_request_kv_sizes_in_the_table(self):
        per_token = kc.bytes_per_token(32, 8, 128, 2)
        self.assertAlmostEqual(2300 * per_token / MIB, 287.5, places=1)
        self.assertAlmostEqual(4600 * per_token / MIB, 575.0, places=1)
        self.assertAlmostEqual(9200 * per_token / GIB, 1.12, places=2)
        self.assertAlmostEqual(32000 * per_token / GIB, 3.91, places=2)

    def test_concurrency_is_inversely_proportional_to_length(self):
        """“并发上限和它成反比”这句话，由两倍长度掉一半并发验证。"""
        total = kc.kv_budget_bytes(80, 14, 6) / kc.bytes_per_token(32, 8, 128, 2)
        self.assertEqual(kc.concurrency(total, 4600),
                         kc.concurrency(total, 2300) // 2)

    def test_the_ch12_topk_example_halves_the_ceiling(self):
        """16.7：1530 → 2930 token，并发乘 0.52。"""
        self.assertAlmostEqual(1530 / 2930, 0.52, places=2)


class TestSection164BlockWaste(unittest.TestCase):
    """16.4：平均浪费半个块，乘并发才是总账。"""

    def test_128_concurrency_block_16_wastes_about_128_mib(self):
        per_token = kc.bytes_per_token(32, 8, 128, 2)
        total = kc.kv_budget_bytes(80, 14, 6) / per_token
        blocks = kc.block_accounting(total, 16, per_token, 128)
        self.assertEqual(blocks["waste_tokens_total"], 1024.0)
        self.assertAlmostEqual(blocks["waste_gib_total"] * 1024, 128.0, places=1)

    def test_block_128_wastes_about_1_gib(self):
        per_token = kc.bytes_per_token(32, 8, 128, 2)
        total = kc.kv_budget_bytes(80, 14, 6) / per_token
        blocks = kc.block_accounting(total, 128, per_token, 128)
        self.assertEqual(blocks["waste_tokens_total"], 8192.0)
        self.assertAlmostEqual(blocks["waste_gib_total"], 1.0, places=2)

    def test_eight_times_the_block_size_is_eight_times_the_waste(self):
        per_token = kc.bytes_per_token(32, 8, 128, 2)
        total = kc.kv_budget_bytes(80, 14, 6) / per_token
        small = kc.block_accounting(total, 16, per_token, 128)
        large = kc.block_accounting(total, 128, per_token, 128)
        self.assertEqual(large["waste_tokens_total"],
                         small["waste_tokens_total"] * 8)

    def test_block_count_for_the_52_gib_budget(self):
        per_token = kc.bytes_per_token(32, 8, 128, 2)
        total = kc.kv_budget_bytes(80, 14, 6) / per_token
        self.assertEqual(kc.block_accounting(total, 16, per_token, 1)["blocks_total"],
                         26624)

    def test_utilization_is_what_shrinks_the_pool(self):
        """16.6 第 1 步：按整张卡起算会多出 8 GiB 的 KV 预算。"""
        full = kc.kv_budget_bytes(80, 14, 6, utilization=1.0)
        default = kc.kv_budget_bytes(80, 14, 6)
        self.assertAlmostEqual((full - default) / kc.GIB, 8.0, places=6)
        self.assertAlmostEqual(default / kc.GIB, 52.0, places=6)

    def test_a_large_block_size_earns_a_warning(self):
        report = kc.build_report(**(TABLE | {"block_size": 512}))
        self.assertTrue(any("换走一部分并发上限" in w for w in report["warnings"]))

    def test_zero_block_size_is_rejected(self):
        with self.assertRaises(kc.CapacityError):
            kc.block_accounting(1000, 0, 131072, 10)


class TestSection165Preemption(unittest.TestCase):
    """16.5：8000 token 占 1000 MiB，换出单程 65 ms、往返 131 ms。

    这一组测试记录了一次被代码改掉的正文结论。初稿写的是“分界点随长度移动，
    短序列上重算更划算”。摊到每个 token 上算一遍就知道那是错的，于是正文改成
    了“换出在墙钟上永远更快，判据在时间之外”。
    """

    def setUp(self):
        self.per_token = kc.bytes_per_token(32, 8, 128, 2)

    def test_8000_tokens_is_exactly_1000_mib(self):
        cost = kc.preemption_cost(8000, self.per_token)
        self.assertEqual(cost["kv_mib"], 1000.0)

    def test_swap_one_way_is_65ms_over_16gbps(self):
        cost = kc.preemption_cost(8000, self.per_token, pcie_gb_per_s=16.0)
        self.assertAlmostEqual(cost["swap_one_way_ms"], 65.5, places=1)

    def test_round_trip_is_131ms(self):
        cost = kc.preemption_cost(8000, self.per_token, pcie_gb_per_s=16.0)
        self.assertAlmostEqual(cost["swap_round_trip_ms"], 131.1, places=1)

    def test_the_binary_to_decimal_conversion_is_reported(self):
        """1000 MiB 是 1.0486 GB，不是 1.0 GB；这个换算写在报告里。"""
        cost = kc.preemption_cost(8000, self.per_token)
        self.assertAlmostEqual(cost["kv_gb_decimal"], 1.0486, places=4)

    def test_recompute_at_8000_tokens_is_about_1_3_seconds(self):
        """正文那个 1.3 秒：GEMM 项加 Attention 的平方项，有效算力 100 TFLOPS。

        Attention 那一项按第 11.2 节的式子是 2 × hidden × S² 每层，不是 4 ×。
        """
        params, layers, hidden, s = 7e9, 32, 4096, 8000
        flops = 2 * params * s + 2 * layers * hidden * s * s
        self.assertAlmostEqual(flops / 100e12, 1.29, places=2)

    def test_swap_is_about_ten_times_faster_at_8000_tokens(self):
        # 1.29 s ÷ 131 ms ≈ 9.8，正文说的「快一个数量级」。
        cost = kc.preemption_cost(8000, self.per_token, recompute_ms=1288)
        self.assertIn("换出", cost["faster_on_wall_clock"])
        self.assertGreater(cost["wall_clock_speedup"], 9)
        self.assertLess(cost["wall_clock_speedup"], 11)

    def test_the_per_token_ratio_is_about_nine_and_length_independent(self):
        """正文那句“这个差距在短序列上同样成立”，就是这一条。"""
        recompute_per_token_ms = 2 * 7e9 / 100e12 * 1000
        swap_round_trip_per_token_ms = 2 * self.per_token / 16e9 * 1000
        self.assertAlmostEqual(recompute_per_token_ms, 0.14, places=2)
        self.assertAlmostEqual(swap_round_trip_per_token_ms, 0.0164, places=4)
        self.assertAlmostEqual(
            recompute_per_token_ms / swap_round_trip_per_token_ms, 8.5, places=1
        )

    def test_swap_still_wins_on_wall_clock_at_500_tokens(self):
        """初稿的错处：短序列并没有反过来。"""
        params, layers, hidden, s = 7e9, 32, 4096, 500
        recompute_ms = (2 * params * s + 4 * layers * hidden * s * s) / 100e12 * 1000
        cost = kc.preemption_cost(s, self.per_token, recompute_ms=recompute_ms)
        self.assertIn("换出", cost["faster_on_wall_clock"])

    def test_the_gap_widens_with_length_because_of_the_quadratic_term(self):
        def recompute_ms(s):
            return (2 * 7e9 * s + 2 * 32 * 4096 * s * s) / 100e12 * 1000
        short = kc.preemption_cost(500, self.per_token,
                                   recompute_ms=recompute_ms(500))
        long_ = kc.preemption_cost(32000, self.per_token,
                                   recompute_ms=recompute_ms(32000))
        self.assertGreater(long_["wall_clock_speedup"], short["wall_clock_speedup"])

    def test_it_never_calls_either_one_the_better_deal(self):
        """判据不是时间，所以报告里不出现“划算”。"""
        cost = kc.preemption_cost(8000, self.per_token, recompute_ms=1288)
        self.assertNotIn("划算", cost["faster_on_wall_clock"])
        self.assertIn("判据不是哪个更快", cost["why_wall_clock_is_not_the_judge"])

    def test_the_two_costs_wall_clock_misses_are_named(self):
        cost = kc.preemption_cost(8000, self.per_token)
        note = cost["why_wall_clock_is_not_the_judge"]
        # 代价落在谁身上：重算打断全卡，换出吃主机内存（16.5）。
        self.assertIn("跟着停", note)
        self.assertIn("摊给了所有人", note)
        self.assertIn("主机内存", note)

    def test_host_memory_scales_with_concurrency(self):
        """正文那个 31 GiB：批量 32 条各 1000 MiB。"""
        cost = kc.preemption_cost(8000, self.per_token,
                                  concurrency_for_host_memory=32)
        self.assertAlmostEqual(cost["host_memory"]["host_gib_needed"], 31.25,
                               places=2)

    def test_without_a_measured_recompute_time_no_comparison_is_made(self):
        cost = kc.preemption_cost(8000, self.per_token)
        self.assertIn("不比时间", cost["faster_on_wall_clock"])
        self.assertIsNone(cost["wall_clock_speedup"])

    def test_non_positive_pcie_is_rejected(self):
        with self.assertRaises(kc.CapacityError):
            kc.preemption_cost(8000, self.per_token, pcie_gb_per_s=0)

    def test_non_positive_recompute_time_is_rejected(self):
        with self.assertRaises(kc.CapacityError):
            kc.preemption_cost(8000, self.per_token, recompute_ms=0)


class TestSection169MixedDistribution(unittest.TestCase):
    """16.9 案例三：混合平均给 133 条，全是长请求时只有 13 条。"""

    MIX = [(0.97, 2300), (0.03, 32000)]

    def test_mixed_average_is_3191_tokens(self):
        self.assertAlmostEqual(kc.mixed_average_context(self.MIX), 3191.0,
                               places=1)

    def test_concurrency_at_the_mixed_average_is_133(self):
        report = kc.build_report(**(TABLE | {"mix": self.MIX}))
        self.assertEqual(report["mixed"]["concurrency_at_mixed_average"], 133)

    def test_the_all_long_ceiling_is_13(self):
        report = kc.build_report(**(TABLE | {"mix": self.MIX}))
        self.assertEqual(report["mixed"]["concurrency_if_all_longest"], 13)

    def test_the_all_long_ceiling_matches_the_division_in_the_text(self):
        """52 GiB ÷ 3.91 GiB = 13 条。"""
        self.assertEqual(int(52 / 3.906), 13)

    def test_the_two_numbers_differ_by_an_order_of_magnitude(self):
        """案例三的教训：掉到 133，不是 13；那 13 是另一个数。"""
        report = kc.build_report(**(TABLE | {"mix": self.MIX}))
        m = report["mixed"]
        self.assertGreater(m["concurrency_at_mixed_average"],
                           m["concurrency_if_all_longest"] * 9)

    def test_the_reading_says_the_ceiling_is_the_worst_case_mix(self):
        report = kc.build_report(**(TABLE | {"mix": self.MIX}))
        self.assertIn("最坏情况下的混合", report["mixed"]["reading"])

    def test_a_mix_that_does_not_sum_to_one_is_rejected(self):
        with self.assertRaises(kc.CapacityError):
            kc.mixed_average_context([(0.9, 2300), (0.03, 32000)])

    def test_an_empty_mix_is_rejected(self):
        with self.assertRaises(kc.CapacityError):
            kc.mixed_average_context([])

    def test_a_mix_adds_a_warning_about_the_average_step(self):
        report = kc.build_report(**(TABLE | {"mix": self.MIX}))
        self.assertTrue(any("默认了混合比例稳定" in w for w in report["warnings"]))


class TestMeasurementComparison(unittest.TestCase):
    """16.8 那两个用法：实测偏低查 overhead，实测偏高查负载画像。"""

    def test_no_measurement_means_no_conclusion(self):
        report = kc.build_report(**TABLE)
        self.assertIn("压测的起点", report["comparison"]["reading"])

    def test_a_low_measurement_points_at_overhead(self):
        report = kc.build_report(**(TABLE | {"measured_concurrency": 60}))
        self.assertIn("--overhead 估小了", report["comparison"]["reading"])

    def test_a_high_measurement_points_at_the_workload_profile(self):
        report = kc.build_report(**(TABLE | {"measured_concurrency": 300}))
        self.assertIn("负载画像", report["comparison"]["reading"])

    def test_a_measurement_inside_the_band_says_the_books_balance(self):
        report = kc.build_report(**(TABLE | {"measured_concurrency": 160}))
        self.assertIn("显存账对得上", report["comparison"]["reading"])

    def test_non_positive_measurement_is_rejected(self):
        with self.assertRaises(kc.CapacityError):
            kc.build_report(**(TABLE | {"measured_concurrency": 0}))


class TestReportShapeAndCli(unittest.TestCase):
    def test_both_unit_conventions_are_labelled(self):
        report = kc.build_report(**TABLE)
        self.assertIn("binary", report["units"]["memory"])
        self.assertIn("decimal", report["units"]["transfer"])

    def test_report_is_json_serialisable(self):
        report = kc.build_report(**(TABLE | {"mix": [(0.97, 2300), (0.03, 32000)],
                                             "recompute_ms": 400,
                                             "measured_concurrency": 160}))
        json.dumps(report, ensure_ascii=False)

    def test_it_reads_the_shared_part4_config(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = kc.main(["--config", str(SHARED_CONFIG),
                          "--weight-memory", "14",
                          "--avg-context", "2300", "--p99-context", "9200"])
        self.assertEqual(rc, 0)
        self.assertIn("185 条", out.getvalue())

    def test_cli_rejects_a_mix_without_a_colon(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = kc.main(["--config", str(SHARED_CONFIG), "--weight-memory", "14",
                          "--avg-context", "2300", "--mix", "0.97"])
        self.assertEqual(rc, 1)
        self.assertIn("占比:长度", out.getvalue())

    def test_cli_reports_a_rejection_without_a_traceback(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = kc.main(["--layers", "32", "--kv-heads", "8", "--head-dim", "128",
                          "--gpu-memory", "80", "--weight-memory", "76",
                          "--overhead", "6", "--avg-context", "2300"])
        self.assertEqual(rc, 1)
        self.assertIn("REJECTED", out.getvalue())


if __name__ == "__main__":
    unittest.main()
