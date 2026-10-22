#!/usr/bin/env python3
"""Tests for code/ch26/capacity_cost.py.

The numbers 26.2 to 26.7 state are pinned here, and so are the rules the chapter
is built on: 峰均比不是峰谷比；单卡并发要按本次负载的总长度折算；单卡吞吐要按
Prefill 占时折到本次负载，而且折的是 占时/(1−占时)；余量由故障、升级、预测误差
和突发四项论证；单位成本的分母是有用的实际产出。
"""

from __future__ import annotations

import unittest

import capacity_cost as cc

BASE = dict(dau=500000, sessions_per_user=3.2, peak_to_mean=3.0,
            calls_per_session=2.4, input_tokens=2600, output_tokens=220,
            request_duration=4.2, gpu_concurrency=130,
            concurrency_at_tokens=2300, gpu_output_tps=1560,
            prefill_share=0.10, measured_io_ratio=1.5,
            gpu_monthly=12000, headroom=0.3,
            api_input_price=0.0008, api_output_price=0.002)
STATIC = dict(BASE, ignore_prefill=True)


class TestDemandChain(unittest.TestCase):
    def setUp(self):
        self.d = cc.demand(dau=500000, sessions_per_user=3.2, peak_to_mean=3.0,
                           calls_per_session=2.4, input_tokens=2600,
                           output_tokens=220)

    def test_daily_sessions(self):
        """50 万 × 3.2 = 160 万。"""
        self.assertEqual(self.d["daily_sessions"], 1600000.0)

    def test_mean_session_qps(self):
        """160 万 ÷ 86400 ≈ 18.5。"""
        self.assertEqual(round(self.d["mean_session_qps"], 1), 18.5)

    def test_peak_call_qps_needs_both_multipliers(self):
        """18.5 × 3（峰均比）× 2.4（每次对话的调用数）≈ 133。"""
        self.assertEqual(round(self.d["peak_call_qps"]), 133)

    def test_the_two_qps_are_not_the_same_quantity(self):
        """26.8 案例一就是把这两个量当成同一个数用了。"""
        ratio = self.d["peak_call_qps"] / self.d["mean_session_qps"]
        self.assertAlmostEqual(ratio, 3.0 * 2.4, places=4)
        self.assertIn("峰均比", self.d["note"])

    def test_token_rates(self):
        self.assertEqual(round(self.d["peak_input_tps"] / 1000), 347)
        self.assertEqual(round(self.d["peak_output_tps"] / 1000), 29)

    def test_peak_to_mean_below_one_rejected(self):
        with self.assertRaises(cc.ModelError):
            cc.demand(dau=1, sessions_per_user=1, peak_to_mean=0.5,
                      calls_per_session=1, input_tokens=1, output_tokens=1)

    def test_peak_to_trough_plugged_in_by_mistake(self):
        """P0-9：把第 22 章的峰谷比 11.25 当峰均比代进来，卡数是正确值的 3.7 倍。"""
        right = cc.build_model(STATIC)["sizing"]["gpus_by_throughput"]
        wrong = cc.build_model(dict(STATIC, peak_to_mean=11.25))["sizing"]["gpus_by_throughput"]
        self.assertAlmostEqual(wrong / right, 3.75, places=2)
        self.assertAlmostEqual(wrong, 70.5, places=1)


class TestLittlesLaw(unittest.TestCase):
    def test_the_number_26_3_states(self):
        """133 × 4.2 ≈ 559。"""
        self.assertEqual(round(cc.inflight(133, 4.2)), 559)

    def test_zero_duration_rejected(self):
        with self.assertRaises(cc.ModelError):
            cc.inflight(100, 0)


class TestConcurrencyScaling(unittest.TestCase):
    def test_the_folding_26_3_does(self):
        """第 16 章那 130 条是按 2300 token 算的；本例 2820 token → 106 条。"""
        self.assertEqual(round(cc.scale_concurrency(130, 2300, 2820)), 106)

    def test_29_8_case_one_is_this_same_calculation(self):
        """上下文 2600 → 3400，并发上限降约四分之一。"""
        drop = 1 - cc.scale_concurrency(100, 2600, 3400) / 100
        self.assertAlmostEqual(drop, 0.2353, places=4)

    def test_zero_rejected(self):
        with self.assertRaises(cc.ModelError):
            cc.scale_concurrency(130, 0, 2820)


class TestPrefillShare(unittest.TestCase):
    def test_the_odds_scale_with_the_ratio_not_the_share(self):
        """附录 B-4：25% 在 6.67 量到，本例 11.82 是 37.1%，降到 8.18 是 29.0%，RAG 40 是 66.7%。"""
        self.assertAlmostEqual(cc.prefill_share_at(0.25, 6.67, 11.82), 0.371, places=3)
        self.assertAlmostEqual(cc.prefill_share_at(0.25, 6.67, 8.18), 0.290, places=3)
        self.assertAlmostEqual(cc.prefill_share_at(0.25, 6.67, 40.0), 0.667, places=3)

    def test_the_book_numbers(self):
        """26.3：第 19 章负载（比 1.5）占 10%，本例（比 11.8）约 47%。"""
        share = cc.prefill_share_at(0.10, 1.5, 2600 / 220)
        self.assertAlmostEqual(share, 0.467, places=3)
        # 线性放大会给 79%，再长一点就超过 100%
        self.assertAlmostEqual(0.10 * (2600 / 220) / 1.5, 0.788, places=3)

    def test_the_book_throughput(self):
        r = cc.prefill_adjusted_output_tps(
            1560, measured_io_ratio=1.5, actual_io_ratio=2600 / 220,
            prefill_share_at_measure=0.10)
        self.assertAlmostEqual(r["pure_decode_tps"], 1733.3, places=1)
        self.assertAlmostEqual(r["output_tps"], 924, delta=1)

    def test_never_reaches_the_whole_card(self):
        """比值形式下占时永远小于 1，再长的输入也只是逼近整张卡。"""
        self.assertLess(cc.prefill_share_at(0.30, 2.0, 400.0), 1.0)

    def test_without_it_input_length_cannot_move_anything(self):
        r = cc.prefill_adjusted_output_tps(
            1813, measured_io_ratio=None, actual_io_ratio=11.8,
            prefill_share_at_measure=None)
        self.assertFalse(r["adjusted"])
        self.assertEqual(r["output_tps"], 1813)
        self.assertIn("不影响卡数", r["note"])

    def test_giving_the_share_without_its_basis_is_rejected(self):
        with self.assertRaises(cc.ModelError) as ctx:
            cc.prefill_adjusted_output_tps(
                1813, measured_io_ratio=None, actual_io_ratio=11.8,
                prefill_share_at_measure=0.25)
        self.assertIn("在什么输入输出比下测的", str(ctx.exception))


class TestSizing(unittest.TestCase):
    def test_the_static_answer_is_sixteen(self):
        r = cc.build_model(STATIC)["sizing"]
        self.assertEqual(r["binding_constraint"], "throughput")
        self.assertAlmostEqual(r["gpus_by_throughput"], 18.8, places=1)
        self.assertAlmostEqual(r["gpus_by_memory"], 5.3, places=1)

    def test_the_prefill_corrected_answer_is_thirty_two(self):
        """补上 Prefill 占时：31.7 张，取整 32，加 30% 余量 42。"""
        r = cc.build_model(BASE)["sizing"]
        self.assertAlmostEqual(r["gpus_by_throughput"], 31.7, places=1)
        self.assertEqual(r["gpus_minimum"], 32)
        self.assertEqual(r["gpus_required"], 42)

    def test_per_card_inflight_unifies_the_two_constraints(self):
        """T-18：静态时每卡在途约 30 条，补上 Prefill 后约 18 条，显存允许 106 条。"""
        static = cc.build_model(STATIC)["sizing"]
        fixed = cc.build_model(BASE)["sizing"]
        self.assertAlmostEqual(static["per_card_inflight_at_full_throughput"], 29.8, places=1)
        self.assertAlmostEqual(fixed["per_card_inflight_at_full_throughput"], 17.6, places=1)
        self.assertAlmostEqual(fixed["per_card_inflight_memory_allows"], 106.0, places=1)
        self.assertAlmostEqual(fixed["per_card_service_time_ms"], 238, delta=1)

    def test_memory_can_bind_on_a_different_load(self):
        r = cc.size_cards(peak_output_tps=2000, gpu_output_tps=1813,
                          inflight_requests=900, gpu_concurrency=60,
                          headroom=0.0)
        self.assertEqual(r["binding_constraint"], "memory")

    def test_zero_throughput_rejected(self):
        with self.assertRaises(cc.ModelError):
            cc.size_cards(peak_output_tps=1, gpu_output_tps=0,
                          inflight_requests=1, gpu_concurrency=1, headroom=0)

    def test_longer_context_moves_both_sides_but_throughput_still_binds(self):
        """第 29 章 67-6：2600 → 3400 时显存一侧 5.3 → 6.8 张，仍不是约束；
        吞吐一侧 31.7 → 36.3 张，42 张变 48 张。"""
        r = cc.build_model(dict(BASE, input_tokens=3400))["sizing"]
        self.assertAlmostEqual(r["gpus_by_memory"], 6.8, places=1)
        self.assertAlmostEqual(r["gpus_by_throughput"], 36.3, places=1)
        self.assertEqual(r["binding_constraint"], "throughput")
        self.assertEqual(r["gpus_required"], 48)


class TestFloor(unittest.TestCase):
    """下限卡数：第 27 章最小实例数和第 29 章那处接缝要的数。"""

    def test_default_floor_is_five(self):
        f = cc.build_model(BASE)["floor"]
        self.assertAlmostEqual(f["gpus_at_trough_exact"], 3.17, places=2)
        self.assertEqual(f["gpus_floor"], 5)
        self.assertAlmostEqual(f["peak_to_trough"], 10.0)

    def test_floor_never_below_two(self):
        f = cc.floor_cards(minimum_at_peak=3, peak_to_mean=3,
                           trough_to_mean=0.1, headroom=0.3)
        self.assertEqual(f["gpus_floor"], 2)

    def test_floor_scales_with_the_trough(self):
        lo = cc.floor_cards(minimum_at_peak=31.738, peak_to_mean=3,
                            trough_to_mean=0.3, headroom=0.3)["gpus_floor"]
        hi = cc.floor_cards(minimum_at_peak=31.738, peak_to_mean=3,
                            trough_to_mean=0.6, headroom=0.3)["gpus_floor"]
        self.assertLess(lo, hi)

    def test_trough_above_mean_rejected(self):
        with self.assertRaises(cc.ModelError):
            cc.floor_cards(minimum_at_peak=31.738, peak_to_mean=3,
                           trough_to_mean=1.2, headroom=0.3)


class TestMargin(unittest.TestCase):
    def setUp(self):
        self.minimum = cc.build_model(BASE)["sizing"]["gpus_minimum_exact"]
        self.rows = {r["cards"]: r for r in cc.margin_table(self.minimum, [36, 42, 45, 48])}

    def test_load_rates(self):
        self.assertEqual([round(self.rows[c]["rho"], 2) for c in (36, 42, 45, 48)],
                         [0.88, 0.76, 0.71, 0.66])

    def test_burst_drain_minutes(self):
        """一分钟三倍突发：36 张约 13.9 分钟，42 张约 5.2，45 张约 3.8，48 张约 2.9。"""
        self.assertEqual([self.rows[c]["drain_minutes"] for c in (36, 42, 45, 48)],
                         [13.9, 5.2, 3.8, 2.9])

    def test_single_replica_upper_bound(self):
        self.assertEqual([round(self.rows[c]["amplification"], 1) for c in (36, 42, 48)],
                         [7.5, 3.1, 1.9])

    def test_erlang_c_is_far_gentler(self):
        """按负载派发：0.085、0.005、0.0003 个 S。"""
        self.assertAlmostEqual(self.rows[36]["erlang_c_wait"], 0.085, places=2)
        self.assertAlmostEqual(self.rows[42]["erlang_c_wait"], 0.005, places=3)
        self.assertLess(self.rows[48]["erlang_c_wait"], 0.001)

    def test_review_b1_erlang_numbers(self):
        """附录 B-1：16 张当量、18 张时 Erlang C 平均排队 0.266 个 S、53% 要排队。"""
        row = cc.margin_table(16, [18])[0]
        self.assertAlmostEqual(row["erlang_c_wait"], 0.266, places=3)
        self.assertAlmostEqual(row["erlang_c_wait_probability"], 0.531, places=3)

    def test_n_plus_one(self):
        self.assertLess(self.rows[36]["rho_one_down"], 1.0)
        self.assertAlmostEqual(self.rows[42]["rho_one_down"], self.minimum / 41, places=4)

    def test_the_first_three_items_multiply_to_about_a_quarter(self):
        """(1 + 2/32) × 1.15 ≈ 1.22。"""
        self.assertAlmostEqual((1 + 2 / 32) * 1.15, 1.222, places=3)

    def test_ninety_percent_drains_in_seventeen_minutes(self):
        self.assertAlmostEqual(cc.drain_minutes(0.9), 17.0, places=1)
        self.assertAlmostEqual(cc.drain_minutes(0.7), 3.67, places=2)

    def test_at_the_minimum_the_wait_diverges(self):
        rows = cc.margin_table(16, [16])
        self.assertIsNone(rows[0]["amplification"])
        self.assertIn("不能上线", rows[0]["reading"])

    def test_target_load(self):
        self.assertAlmostEqual(cc.target_load(n_plus_one_cards=2, total_cards=28,
                                              forecast_error=0.15, burst_rho=0.70),
                               0.70)


class TestCosts(unittest.TestCase):
    def setUp(self):
        self.model = cc.build_model(dict(BASE, show_saturated=True))
        self.c = self.model["costs"]

    def test_decomposition(self):
        """实际 ÷ 满载 = 1 ÷ 平均负载率 ≈ 3.96；峰均比 3、余量 30% 的粗算是 3.9。"""
        self.assertAlmostEqual(self.c["utilization"], 0.2519, places=3)
        self.assertAlmostEqual(self.c["actual_over_saturated"], 3.97, places=2)
        self.assertAlmostEqual(self.c["cost_per_million_token_actual"]
                               / self.c["cost_per_million_token_saturated"],
                               self.c["actual_over_saturated"], places=2)
        self.assertAlmostEqual(3.0 * 1.3, 3.9)

    def test_unit_costs(self):
        """满载约 0.39 元，实际约 1.55 元每百万 token；API 混合价约 0.89 元。"""
        self.assertAlmostEqual(self.c["cost_per_million_token_saturated"], 0.391, places=3)
        self.assertAlmostEqual(self.c["cost_per_million_token_actual"], 1.5514, places=3)
        api_per_m = self.c["api_monthly"] / (self.c["monthly_tokens"] / 1e6)
        self.assertAlmostEqual(api_per_m, 0.894, places=3)

    def test_useful_share_shrinks_the_denominator(self):
        r = cc.build_model(dict(BASE, useful_share=0.9))["costs"]
        self.assertAlmostEqual(r["cost_per_million_token_actual"], 1.7238, places=3)

    def test_saturated_basis_is_opt_in(self):
        plain = cc.build_model(BASE)["costs"]
        self.assertNotIn("cost_per_million_token_saturated", plain)
        self.assertIn("案例二", self.c["saturated_warning"])

    def test_per_user_cost(self):
        self.assertAlmostEqual(self.c["cost_per_user_monthly"], 1.008)

    def test_case_two_arithmetic(self):
        """26.8 案例二：3.2 元看着省 64%，按 27% 负载率折回去是 11.9 元。"""
        self.assertEqual(round((9 - 3.2) / 9, 2), 0.64)
        self.assertEqual(round(3.2 / 0.27, 1), 11.9)


class TestWhatIf(unittest.TestCase):
    def setUp(self):
        self.r = cc.whatif(BASE, ["traffic=3x", "input_tokens=1800",
                                  "peak_to_mean=2.0"])
        self.rows = {row["scenario"]: row for row in self.r["scenarios"]}

    def test_the_three_rows_26_7_prints(self):
        self.assertEqual(self.r["baseline"]["gpus"], 42)
        self.assertEqual(self.rows["traffic=3x"]["gpus"], 124)
        self.assertEqual(self.rows["input_tokens=1800"]["gpus"], 36)
        self.assertEqual(self.rows["peak_to_mean=2.0"]["gpus"], 28)
        self.assertAlmostEqual(self.rows["input_tokens=1800"]["cost_change"], -0.143, places=3)
        self.assertAlmostEqual(self.rows["peak_to_mean=2.0"]["cost_change"], -0.333, places=3)

    def test_input_length_moves_nothing_without_prefill(self):
        r = cc.whatif(STATIC, ["input_tokens=1800"])
        self.assertEqual(r["scenarios"][0]["gpus_delta"], 0)
        self.assertEqual(r["no_effect"], ["input_tokens=1800"])

    def test_tripling_traffic_is_three_times_the_cards(self):
        """维持同样的负载率，卡数和流量成正比：31.7 → 95，加余量 124。"""
        exact = cc.build_model(dict(BASE, dau=1500000))["sizing"]["gpus_by_throughput"]
        self.assertAlmostEqual(exact / cc.build_model(BASE)["sizing"]["gpus_by_throughput"], 3.0, places=4)

    def test_the_26_6_example(self):
        """峰均比 3 → 2：19500 ÷ 924 ≈ 21 张，比 32 张降约三分之一。"""
        self.assertEqual(round(89 * 220 / 924), 21)

    def test_unknown_scenario_key_rejected(self):
        with self.assertRaises(cc.ModelError) as ctx:
            cc.whatif(BASE, ["gpu_price=100"])
        self.assertIn("不认识的场景键", str(ctx.exception))

    def test_traffic_must_be_a_multiple(self):
        with self.assertRaises(cc.ModelError):
            cc.whatif(BASE, ["traffic=3"])


class TestCli(unittest.TestCase):
    def test_size_exits_zero(self):
        self.assertEqual(cc.main(["size"]), 0)

    def test_size_static_exits_zero(self):
        self.assertEqual(cc.main(["size", "--ignore-prefill"]), 0)

    def test_margin_exits_zero(self):
        self.assertEqual(cc.main(["margin", "--minimum-cards", "27.3",
                                  "--options", "31,36,39,41"]), 0)

    def test_whatif_needs_a_scenario(self):
        self.assertEqual(cc.main(["whatif"]), 1)

    def test_whatif_exits_zero(self):
        self.assertEqual(cc.main(["whatif", "--scenario", "peak_to_mean=2.0"]), 0)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(cc.main([]), 2)


if __name__ == "__main__":
    unittest.main()
