#!/usr/bin/env python3
"""Tests for code/ch27/autoscale_sim.py.

27.4's loop-lag table, 27.5's time-scale mismatch and 22.4's cache formula are
pinned here, so the chapter's three central claims cannot drift away from the
code that demonstrates them.
"""

from __future__ import annotations

import math
import unittest
from pathlib import Path

import autoscale_sim as asim

HERE = Path(__file__).resolve().parent
TRACE = (HERE.parent.parent / "content" / "ch27" / "evidence"
         / "traffic-trace-sample.csv")

BASE = dict(capacity_per_instance=150, scale_up_threshold=0.7,
            scale_down_threshold=0.4, cold_start_s=300, observation_s=60,
            decision_s=60, scale_up_cooldown_s=180,
            scale_down_cooldown_s=1800, min_instances=3, max_instances=30)


def flat_trace(values, step=30):
    return [{"t": i * step, "demand": float(v)} for i, v in enumerate(values)]


class TestLoopLag(unittest.TestCase):
    def test_the_table_27_4_gives(self):
        r = asim.loop_lag()
        self.assertEqual(r["low_s"], 30 + 30 + 180)
        self.assertEqual(r["high_s"], 90 + 120 + 600)
        self.assertEqual(r["low_min"], 4.0)
        self.assertEqual(r["high_min"], 13.5)

    def test_the_two_times_rule(self):
        """经验上取两倍：13.5 分钟的滞后要求变化持续 27 分钟以上。"""
        r = asim.loop_lag()
        self.assertEqual(r["actionable_threshold_min"], 27.0)
        self.assertIn("追不上", r["reading"])

    def test_three_parts_only(self):
        self.assertEqual(set(asim.LAG_PARTS),
                         {"observation", "decision", "cold_start"})

    def test_cold_start_is_the_dominant_part_by_default(self):
        r = asim.loop_lag(60, 60, 300)
        self.assertEqual(r["dominant"], "cold_start")
        self.assertAlmostEqual(r["total_min"], 7.0)
        self.assertIn("预热实例池", r["reading"])

    def test_a_warm_pool_moves_the_dominant_part(self):
        """27.5：预热实例池能把冷启动压到秒级，整个滞后就由前两段决定。"""
        r = asim.loop_lag(60, 60, 10)
        self.assertNotEqual(r["dominant"], "cold_start")
        self.assertLess(r["total_s"], 150)

    def test_all_zero_rejected(self):
        with self.assertRaises(asim.SimError):
            asim.loop_lag(0, 0, 0)


class TestCacheImpact(unittest.TestCase):
    def test_the_formula_22_4_gives(self):
        """|N − M| ÷ max(N, M)。"""
        for before, after, want in ((12, 11, 1/12), (12, 10, 2/12),
                                    (12, 8, 4/12), (12, 4, 8/12)):
            with self.subTest(before=before, after=after):
                r = asim.cache_impact(before, after)
                self.assertAlmostEqual(r["prefix_moved_share"], want, places=3)

    def test_a_three_fold_scale_down_cannot_be_cheap(self):
        """P0-2 那处：12 → 4 必须重建三分之二，一致性哈希救不回来。"""
        r = asim.cache_impact(12, 4)
        self.assertAlmostEqual(r["prefix_moved_share"], 0.6667, places=3)
        self.assertGreater(r["prefix_moved_share"], 0.5)

    def test_modulo_retention_is_gcd_over_max(self):
        """取模哈希保住 gcd(N, M) ÷ max(N, M)：12 → 11 只有 1/12，12 → 8 是 1/3。"""
        for before, after, kept in ((12, 11, 1/12), (12, 10, 2/12),
                                    (12, 8, 4/12), (12, 4, 4/12), (12, 6, 6/12)):
            with self.subTest(before=before, after=after):
                self.assertAlmostEqual(asim.modulo_kept_share(before, after), kept)
                r = asim.cache_impact(before, after, consistent_hashing=False)
                self.assertAlmostEqual(r["prefix_kept_share"], kept, places=3)

    def test_modulo_matches_brute_force(self):
        for before, after in ((12, 11), (12, 8), (12, 4), (9, 6)):
            keys = 36000
            kept = sum(1 for h in range(keys) if h % before == h % after) / keys
            self.assertAlmostEqual(kept, asim.modulo_kept_share(before, after), places=3)

    def test_twelve_to_four_is_the_same_for_both(self):
        """67-2：12 是 4 的倍数，取模碰巧和一致性哈希一样保住三分之一。"""
        r = asim.cache_impact(12, 4)
        self.assertEqual(r["consistent_moved_share"], r["modulo_moved_share"])
        self.assertIn("换哪种哈希都救不回来", r["reading"])

    def test_the_three_warm_times_the_case_uses(self):
        """案例二：12 → 8 取模八十分钟、一致性哈希四十分钟；12 → 4 两种都是八十分钟。"""
        def warm(b, a, consistent=True):
            return asim.cache_impact(b, a, consistent_hashing=consistent,
                                     warm_minutes_full=120)["estimated_warm_minutes"]
        self.assertEqual(warm(12, 8, consistent=False), 80.0)
        self.assertEqual(warm(12, 8), 40.0)
        self.assertEqual(warm(12, 4), 80.0)
        self.assertEqual(warm(12, 4, consistent=False), 80.0)

    def test_shallower_scale_down_keeps_more(self):
        deep = asim.cache_impact(12, 4)["prefix_kept_share"]
        shallow = asim.cache_impact(12, 10)["prefix_kept_share"]
        self.assertGreater(shallow, deep)

    def test_zero_instances_rejected(self):
        with self.assertRaises(asim.SimError):
            asim.cache_impact(0, 4)


class TestThresholds(unittest.TestCase):
    def test_symmetric_thresholds_are_rejected(self):
        """27.6：两个方向的风险不对称，用同一个阈值的系统会持续抖动。"""
        kw = dict(BASE, scale_down_threshold=0.7)
        with self.assertRaises(asim.SimError) as ctx:
            asim.simulate(flat_trace([500] * 10), **kw)
        self.assertIn("风险不对称", str(ctx.exception))

    def test_inverted_thresholds_are_rejected(self):
        kw = dict(BASE, scale_down_threshold=0.8, scale_up_threshold=0.5)
        with self.assertRaises(asim.SimError):
            asim.simulate(flat_trace([500] * 10), **kw)

    def test_a_valid_hysteresis_band_passes(self):
        asim.simulate(flat_trace([400] * 20), **BASE)

    def test_unknown_strategy_rejected(self):
        with self.assertRaises(asim.SimError):
            asim.simulate(flat_trace([400] * 10), strategy="magic", **BASE)


class TestSimulateOnTheSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = asim.load_trace(TRACE)
        cls.result = asim.simulate(cls.trace, strategy="reactive", **BASE)

    def test_the_trace_carries_both_kinds_of_change(self):
        """27.5 那张表要区分趋势和突发，所以样例轨迹两者都有。"""
        scale = self.result["trace"]
        self.assertGreater(scale["peak_over_median"], 3.0)
        self.assertLessEqual(scale["surge_duration_s"], 120)

    def test_the_loop_lag_is_the_sum_of_three_parts(self):
        self.assertEqual(self.result["loop_lag_s"], 60 + 60 + 300)

    def test_almost_all_the_unmet_demand_is_in_the_surge(self):
        """这是 27.5 那句话的量：趋势跟得上，突发跟不上。"""
        r = self.result
        self.assertGreater(r["unmet_in_surge"] / r["unmet_demand"], 0.9)
        self.assertEqual(r["verdict"], "趋势跟得上，突发跟不上")

    def test_the_trend_itself_is_served(self):
        r = self.result
        self.assertLess(r["unmet_in_trend"] / (r["unmet_demand"] or 1), 0.1)

    def test_the_effective_lag_matches_the_configured_one(self):
        self.assertEqual(self.result["lag"]["mean_s"], 420.0)

    def test_a_warm_pool_shortens_the_lag_but_not_below_the_other_two(self):
        r = asim.simulate(self.trace, strategy="warm-pool", **BASE)
        self.assertLess(r["loop_lag_s"], self.result["loop_lag_s"])
        self.assertGreaterEqual(r["loop_lag_s"], 120)


class TestCompare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = asim.load_trace(TRACE)
        cls.result = asim.compare(cls.trace, BASE)

    def test_all_four_strategies_are_run(self):
        names = [s["strategy"] for s in self.result["strategies"]]
        self.assertEqual(names, list(asim.STRATEGIES))

    def test_admission_only_is_sized_at_p95_over_the_target_load(self):
        """67-3：按需求 P95 ÷ 0.7 配，11 个实例，成本 44，仍比反应式的 49.1 便宜。"""
        self.assertEqual(self.result["admission_only_static_instances"], 11)
        rows = {s["strategy"]: s for s in self.result["strategies"]}
        self.assertAlmostEqual(rows["admission-only"]["cost_index"], 44.0, places=1)
        self.assertAlmostEqual(rows["admission-only"]["rejected_demand"], 133440.0, places=0)
        self.assertIn("Goodput", self.result["loss_note"])

    def test_admission_only_is_sized_not_pinned_to_the_minimum(self):
        """27.5 那张表里它配的是预留余量，不是最小实例数。"""
        self.assertGreater(self.result["admission_only_static_instances"],
                           BASE["min_instances"])

    def test_admission_only_serves_everything_it_accepts(self):
        row = next(s for s in self.result["strategies"]
                   if s["strategy"] == "admission-only")
        self.assertEqual(row["unmet_demand"], 0.0)
        self.assertGreater(row["rejected_demand"], 0)

    def test_admission_only_is_cheaper_than_the_scaling_strategies(self):
        """27.8：在突发为主的流量上它常常更好，而成本更低。"""
        rows = {s["strategy"]: s for s in self.result["strategies"]}
        for s in ("reactive", "scheduled", "warm-pool"):
            with self.subTest(strategy=s):
                self.assertLess(rows["admission-only"]["cost_index"],
                                rows[s]["cost_index"])

    def test_the_scaling_strategies_all_miss_the_surge(self):
        rows = {s["strategy"]: s for s in self.result["strategies"]}
        for s in ("reactive", "scheduled", "warm-pool"):
            with self.subTest(strategy=s):
                self.assertGreater(rows[s]["unmet_demand"], 0)

    def test_the_reading_names_both_halves(self):
        self.assertIn("趋势那一段都跟得上", self.result["reading"])
        self.assertIn("27.5", self.result["reading"])


class TestScalingEfficiencyBand(unittest.TestCase):
    def test_the_band_27_2_states(self):
        self.assertEqual(asim.SCALING_EFFICIENCY, (0.8, 0.9))

    def test_the_case_three_numbers_sit_in_and_out_of_it(self):
        """案例三：改之前效率 81%，改之后 89%，都在带内。"""
        self.assertAlmostEqual(1.62 / 2, 0.81)
        self.assertAlmostEqual(1.78 / 2, 0.89)
        for eff in (1.62 / 2, 1.78 / 2):
            self.assertGreaterEqual(eff, asim.SCALING_EFFICIENCY[0])
            self.assertLessEqual(eff, asim.SCALING_EFFICIENCY[1])


class TestTraceLoading(unittest.TestCase):
    def test_the_sample_is_declared_synthetic(self):
        note = TRACE.with_suffix(".README.md")
        self.assertTrue(note.exists())
        self.assertIn("合成设定", note.read_text(encoding="utf-8"))

    def test_short_trace_rejected(self):
        with self.assertRaises(asim.SimError):
            asim.trace_variation_scale(flat_trace([100, 100]))

    def test_zero_median_rejected(self):
        with self.assertRaises(asim.SimError):
            asim.trace_variation_scale(flat_trace([0, 0, 0, 0, 0]))


class TestCli(unittest.TestCase):
    def test_lag_exits_zero(self):
        self.assertEqual(asim.main(["lag"]), 0)

    def test_cache_exits_zero(self):
        self.assertEqual(asim.main(["cache", "--before", "12", "--after", "4"]), 0)

    def test_simulate_exits_zero(self):
        self.assertEqual(asim.main(["simulate", "--traffic", str(TRACE)]), 0)

    def test_compare_exits_zero(self):
        self.assertEqual(asim.main(["compare", "--traffic", str(TRACE)]), 0)

    def test_symmetric_thresholds_exit_one(self):
        self.assertEqual(asim.main(["simulate", "--traffic", str(TRACE),
                                    "--scale-down-threshold", "0.7"]), 1)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(asim.main([]), 2)


if __name__ == "__main__":
    unittest.main()
