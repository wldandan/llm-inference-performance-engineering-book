#!/usr/bin/env python3
"""Tests for code/ch21/overload_drill.py.

The numbers 21.5 and 案例一 state are pinned here: 1 + p×r at three failure
rates, 1/(1−p) at p = 0.9, the four-round table (1.04 / 1.18 / 1.62 / 2.65),
and the tie between that table's last p and the case's stated availability
(0.73⁴ ≈ 28%, so 71.6%).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import overload_drill as od

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent.parent / "content" / "ch21" / "evidence"
NO_ADMISSION = EVIDENCE / "overload-drill-no-admission.json"
WITH_ADMISSION = EVIDENCE / "overload-drill-with-admission.json"


def drill(points, capacity=12.0):
    """A minimal report from [(offered, goodput, rejected)] triples."""
    return {
        "capacity_qps": capacity,
        "steps": [{"offered_qps": o, "accepted_qps": o - rej,
                   "rejected_qps": rej, "goodput": g, "p95_ttft": 100.0,
                   "error_breakdown": {}}
                  for o, g, rej in points],
    }


class TestAmplificationFormulas(unittest.TestCase):
    def test_the_three_rows_21_5_tabulates(self):
        """r = 2，代入 2% / 50% / 90%：精确值 1.02 / 1.75 / 2.71，上界 1.04 / 2.00 / 2.80。"""
        self.assertAlmostEqual(od.exact_amplification(0.02, 2), 1.0204)
        self.assertAlmostEqual(od.exact_amplification(0.50, 2), 1.75)
        self.assertAlmostEqual(od.exact_amplification(0.90, 2), 2.71)
        self.assertAlmostEqual(od.bounded_amplification(0.02, 2), 1.04)
        self.assertAlmostEqual(od.bounded_amplification(0.50, 2), 2.00)
        self.assertAlmostEqual(od.bounded_amplification(0.90, 2), 2.80)

    def test_the_shorthand_is_an_upper_bound(self):
        """1 + p·r 对应“每次重试都失败”，只会比精确值大，不会比它小。"""
        for p in (0.0, 0.02, 0.3, 0.5, 0.9, 1.0):
            for r in (0, 1, 2, 3, 5):
                with self.subTest(p=p, r=r):
                    self.assertLessEqual(od.exact_amplification(p, r),
                                         od.bounded_amplification(p, r) + 1e-12)

    def test_exact_tends_to_the_unbounded_form(self):
        self.assertAlmostEqual(od.exact_amplification(0.9, 200),
                               od.unbounded_amplification(0.9), places=6)

    def test_unbounded_at_ninety_percent_is_ten(self):
        self.assertAlmostEqual(od.unbounded_amplification(0.9), 10.0)

    def test_unbounded_diverges_at_one(self):
        """p 趋近 1 时放大系数发散，这不是一个可以报出来的数字。"""
        with self.assertRaises(od.DrillError) as ctx:
            od.unbounded_amplification(1.0)
        self.assertIn("雪崩", str(ctx.exception))

    def test_bounded_is_defined_at_p_equals_one(self):
        """有限次重试在 p = 1 时仍然有界，这正是它和无限重试的区别。"""
        self.assertAlmostEqual(od.bounded_amplification(1.0, 3), 4.0)

    def test_zero_retries_means_no_amplification(self):
        self.assertAlmostEqual(od.bounded_amplification(0.9, 0), 1.0)

    def test_negative_retries_rejected(self):
        with self.assertRaises(od.DrillError):
            od.bounded_amplification(0.1, -1)


class TestUserVisibleFailure(unittest.TestCase):
    def test_three_retries_means_four_attempts(self):
        self.assertAlmostEqual(od.user_visible_failure(0.73, 3), 0.73 ** 4)

    def test_case_one_two_numbers_are_the_same_p(self):
        """案例一 的 73% 和 71% 不是各自量出来的，是同一个 p 的两种表现。"""
        fail = od.user_visible_failure(0.73, 3)
        self.assertAlmostEqual(fail, 0.2840, places=4)
        self.assertAlmostEqual(1 - fail, 0.7160, places=4)

    def test_no_retry_means_p_itself(self):
        self.assertAlmostEqual(od.user_visible_failure(0.4, 0), 0.4)


class TestRetryLoop(unittest.TestCase):
    def setUp(self):
        self.result = od.retry_loop([0.04, 0.15, 0.40, 0.73], retries=3)

    def test_case_one_table(self):
        """轮次 0-3 的放大系数必须是 1.04 / 1.18 / 1.62 / 2.65（上界 1.12 / 1.45 / 2.20 / 3.19）。"""
        got = [round(r["amplification"], 2) for r in self.result["rounds"]]
        self.assertEqual(got, [1.04, 1.18, 1.62, 2.65])
        bound = [r["upper_bound"] for r in self.result["rounds"]]
        self.assertEqual(bound, [1.12, 1.45, 2.2, 3.19])

    def test_first_round_looks_harmless(self):
        """第 0 轮那 4% 的额外流量看起来完全无害，而它正是推高 p 的那一下。"""
        first = self.result["rounds"][0]
        self.assertLess(first["amplification"], 1.05)

    def test_availability_matches_the_case(self):
        self.assertAlmostEqual(self.result["availability"], 0.716, places=3)

    def test_unbounded_column_is_present_for_comparison(self):
        last = self.result["rounds"][-1]
        self.assertAlmostEqual(last["unbounded_amplification"], 1 / 0.27,
                               places=3)

    def test_empty_sequence_rejected(self):
        with self.assertRaises(od.DrillError):
            od.retry_loop([], retries=3)


class TestFailureCurve(unittest.TestCase):
    def test_failure_rate_counts_rejections_and_errors_alike(self):
        """客户端看不出被拒和出错的区别，它的重试策略对两者一视同仁。"""
        curve = od.failure_curve(drill([(12.0, 6.0, 6.0)]))
        self.assertEqual(curve, [(1.0, 0.5)])

    def test_capacity_is_required(self):
        report = drill([(12.0, 11.0, 0.0)])
        report.pop("capacity_qps")
        with self.assertRaises(od.DrillError) as ctx:
            od.failure_curve(report)
        self.assertIn("倍数", str(ctx.exception))

    def test_curve_is_sorted_by_load(self):
        curve = od.failure_curve(drill([(24.0, 8.0, 0.0), (6.0, 6.0, 0.0)]))
        self.assertEqual([x for x, _ in curve], [0.5, 2.0])

    def test_goodput_above_offered_is_clamped_not_negative(self):
        curve = od.failure_curve(drill([(10.0, 11.0, 0.0)]))
        self.assertEqual(curve[0][1], 0.0)


class TestInterpolate(unittest.TestCase):
    CURVE = [(1.0, 0.04), (1.5, 0.44), (2.0, 0.64)]

    def test_midpoint(self):
        self.assertAlmostEqual(od.interpolate(self.CURVE, 1.25), 0.24, places=4)

    def test_clamped_below(self):
        self.assertEqual(od.interpolate(self.CURVE, 0.1), 0.04)

    def test_clamped_above_rather_than_extrapolated(self):
        """超出实测范围不外推：真实曲线比任何一条直线都更陡，外推出来的数字会读着让人安心。"""
        self.assertEqual(od.interpolate(self.CURVE, 9.0), 0.64)

    def test_exact_point(self):
        self.assertAlmostEqual(od.interpolate(self.CURVE, 1.5), 0.44)


class TestRatesFromDrill(unittest.TestCase):
    def test_measured_curve_answers_the_discussion_question(self):
        """案例一 问“15% 是从哪来的”，答案是从自己那份演练的曲线上读。"""
        report = json.loads(NO_ADMISSION.read_text(encoding="utf-8"))
        r = od.rates_from_drill(report, initial_p=0.04, retries=3)
        self.assertEqual(r["source"], "drill")
        rates = [row["failure_rate"] for row in r["rounds"]]
        self.assertAlmostEqual(rates[0], 0.04)
        # 演练曲线比案例走得慢（第 1 轮 7.4% 对 15%），但同样一路走到 94.2%。
        self.assertAlmostEqual(rates[1], 0.073841, places=5)
        self.assertGreater(rates[2], rates[1])
        self.assertAlmostEqual(rates[-1], 0.941667, places=5)
        self.assertEqual(len(rates), 17)
        self.assertAlmostEqual(r["availability"], 0.2137, places=4)

    def test_loop_settles_at_a_fixed_point(self):
        report = json.loads(NO_ADMISSION.read_text(encoding="utf-8"))
        r = od.rates_from_drill(report, initial_p=0.04, retries=3)
        self.assertFalse(r["diverged"])
        self.assertTrue(r["fixed_point"])

    def test_admission_keeps_the_loop_from_running_away(self):
        """加了准入之后同一个回路收不起来：这就是三条纪律的价值。"""
        report = json.loads(WITH_ADMISSION.read_text(encoding="utf-8"))
        r = od.rates_from_drill(report, initial_p=0.04, retries=3)
        self.assertLess(r["final_failure_rate"], 0.45)
        self.assertGreater(r["availability"], 0.96)

    def test_single_point_curve_rejected(self):
        with self.assertRaises(od.DrillError) as ctx:
            od.rates_from_drill(drill([(12.0, 11.0, 0.0)]), 0.04, 3)
        self.assertIn("插值", str(ctx.exception))


class TestAnalyzeShapes(unittest.TestCase):
    def test_dangerous_is_21_1_case_a(self):
        report = json.loads(NO_ADMISSION.read_text(encoding="utf-8"))
        r = od.analyze(report)
        self.assertEqual(r["shape"], "危险")
        self.assertEqual(r["goodput_peak"], 11.5)
        self.assertAlmostEqual(r["goodput_retained"], 0.1826, places=4)
        self.assertEqual(r["rejected_final_qps"], 0.0)
        self.assertFalse(r["rejected_past_peak"])

    def test_healthy_is_21_1_case_b(self):
        report = json.loads(WITH_ADMISSION.read_text(encoding="utf-8"))
        r = od.analyze(report)
        self.assertEqual(r["shape"], "健康")
        self.assertGreaterEqual(r["goodput_retained"], od.HEALTHY_FLOOR)
        self.assertTrue(r["rejected_past_peak"])
        # 报的是末档那一个速率，不是各档相加（Part 5 审阅 P2-3）。
        self.assertEqual(r["rejected_final_qps"],
                         report["steps"][-1]["rejected_qps"])

    def test_degraded_band(self):
        r = od.analyze(drill([(6.0, 6.0, 0.0), (12.0, 11.0, 0.5),
                              (24.0, 7.5, 6.0)]))
        self.assertEqual(r["shape"], "退化")
        self.assertIn("满载吞吐 × 排队超时", r["reading"])

    def test_a_ramp_that_never_reached_capacity_is_not_healthy(self):
        """这是唯一一种会让人挨伤的错答案：没压到容量的曲线被判成健康。"""
        r = od.analyze(drill([(3.0, 3.0, 0.0), (6.0, 6.0, 0.0),
                              (9.0, 9.0, 0.0)]))
        self.assertEqual(r["shape"], "未到容量")
        self.assertIn("再跑一遍", r["reading"])

    def test_flat_goodput_with_no_rejections_is_suspicious(self):
        """goodput 平稳而一条都没拒：瓶颈可能在压测客户端。"""
        r = od.analyze(drill([(6.0, 6.0, 0.0), (12.0, 11.0, 0.0),
                              (24.0, 10.8, 0.0)]))
        self.assertEqual(r["shape"], "可疑")
        self.assertIn("压测客户端", r["reading"])

    def test_fewer_than_three_steps_rejected(self):
        with self.assertRaises(od.DrillError) as ctx:
            od.analyze(drill([(6.0, 6.0, 0.0), (12.0, 11.0, 0.0)]))
        self.assertIn("三档", str(ctx.exception))

    def test_all_zero_goodput_rejected(self):
        with self.assertRaises(od.DrillError):
            od.analyze(drill([(6.0, 0.0, 0.0), (12.0, 0.0, 0.0),
                              (24.0, 0.0, 0.0)]))

    def test_missing_field_rejected(self):
        report = drill([(6.0, 6.0, 0.0), (12.0, 11.0, 0.0), (24.0, 4.0, 0.0)])
        report["steps"][1].pop("rejected_qps")
        with self.assertRaises(od.DrillError):
            od.analyze(report)


class TestRetryPolicyClassification(unittest.TestCase):
    def test_timeout_must_not_be_retried(self):
        """一次超时的请求可能已经花了几秒 GPU 时间，重试等于让它算两遍。"""
        r = od.classify_retry_policy(["connection_failed", "timeout"])
        self.assertFalse(r["ok"])
        self.assertIn("timeout", r["must_not_retry"])

    def test_the_three_retryable_kinds_pass(self):
        r = od.classify_retry_policy(list(od.RETRYABLE_ERRORS))
        self.assertTrue(r["ok"])

    def test_429_without_retry_after_is_not_retryable(self):
        """不给 Retry-After，客户端只能立刻重试，而立刻重试会加剧过载。"""
        r = od.classify_retry_policy(["429_without_retry_after"])
        self.assertFalse(r["ok"])


class TestSummarizeStep(unittest.TestCase):
    def test_a_fast_failure_is_not_goodput(self):
        results = [{"status": 429, "ttft_ms": 5.0, "error": "429_with_retry_after"}
                   for _ in range(10)]
        s = od.summarize_step(10.0, results, slo_ttft_ms=1500)
        self.assertEqual(s["goodput"], 0.0)
        self.assertEqual(s["rejected_qps"], 10.0)

    def test_a_slow_success_is_not_goodput_either(self):
        results = [{"status": 200, "ttft_ms": 4000.0, "error": ""}
                   for _ in range(10)]
        s = od.summarize_step(10.0, results, slo_ttft_ms=1500)
        self.assertEqual(s["accepted_qps"], 10.0)
        self.assertEqual(s["goodput"], 0.0)

    def test_p95_is_over_accepted_requests_only(self):
        """被拒的请求几毫秒就返回，混进 TTFT 分布会把 P95 拉低一大截。"""
        results = ([{"status": 200, "ttft_ms": 1200.0, "error": ""}] * 10
                   + [{"status": 429, "ttft_ms": 3.0,
                       "error": "429_with_retry_after"}] * 90)
        s = od.summarize_step(100.0, results, slo_ttft_ms=1500)
        self.assertEqual(s["p95_ttft"], 1200.0)

    def test_p95_uses_nearest_rank(self):
        """20 个样本里只有 1 个高值时，P95 落在第 19 个上，也就是不算那个尖。"""
        results = ([{"status": 200, "ttft_ms": 100.0, "error": ""}] * 19
                   + [{"status": 200, "ttft_ms": 900.0, "error": ""}])
        s = od.summarize_step(20.0, results, slo_ttft_ms=1500)
        self.assertEqual(s["p95_ttft"], 100.0)

    def test_every_field_21_8_lists_is_present(self):
        results = [{"status": 200, "ttft_ms": 100.0, "error": ""}]
        s = od.summarize_step(1.0, results, slo_ttft_ms=1500)
        for field in od.STEP_FIELDS:
            self.assertIn(field, s)

    def test_no_results_rejected(self):
        with self.assertRaises(od.DrillError):
            od.summarize_step(10.0, [], slo_ttft_ms=1500)


class TestCancelCheck(unittest.TestCase):
    def test_propagated(self):
        r = od.cancel_check({"running": 12, "kv_usage": 0.61},
                            {"running": 11, "kv_usage": 0.48})
        self.assertTrue(r["propagated"])

    def test_gateway_swallowed_the_signal(self):
        """Running 和 KV 都没动，说明链路上有一段吞掉了取消信号。"""
        r = od.cancel_check({"running": 12, "kv_usage": 0.61},
                            {"running": 12, "kv_usage": 0.61})
        self.assertFalse(r["propagated"])
        self.assertIn("网关", r["reading"])

    def test_running_dropped_but_kv_did_not(self):
        """位置让出来了而显存没还，这仍然不算生效。"""
        r = od.cancel_check({"running": 12, "kv_usage": 0.61},
                            {"running": 11, "kv_usage": 0.60})
        self.assertFalse(r["propagated"])

    def test_missing_field_rejected(self):
        with self.assertRaises(od.DrillError):
            od.cancel_check({"running": 12}, {"running": 11, "kv_usage": 0.4})


class TestSampleReports(unittest.TestCase):
    def test_both_are_declared_synthetic(self):
        for path in (NO_ADMISSION, WITH_ADMISSION):
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(doc["synthetic"], path.name)
            self.assertIn("合成设定", doc["_note"], path.name)

    def test_the_pair_differs_only_in_admission(self):
        a = json.loads(NO_ADMISSION.read_text(encoding="utf-8"))
        b = json.loads(WITH_ADMISSION.read_text(encoding="utf-8"))
        for key in ("capacity_qps", "ramp", "slo_ttft_ms", "slo_itl_ms"):
            self.assertEqual(a[key], b[key], key)
        self.assertEqual([s["offered_qps"] for s in a["steps"]],
                         [s["offered_qps"] for s in b["steps"]])

    def test_admission_version_only_returns_retryable_errors(self):
        """加了准入之后错误全是带 Retry-After 的 429，这是 21.2 要求的那种拒绝。"""
        b = json.loads(WITH_ADMISSION.read_text(encoding="utf-8"))
        kinds = set()
        for s in b["steps"]:
            kinds.update(s["error_breakdown"])
        self.assertTrue(kinds <= set(od.RETRYABLE_ERRORS), kinds)

    def test_no_admission_version_is_full_of_timeouts(self):
        a = json.loads(NO_ADMISSION.read_text(encoding="utf-8"))
        total = sum(s["error_breakdown"].get("timeout", 0) for s in a["steps"])
        self.assertGreater(total, 1000)


class TestCli(unittest.TestCase):
    def test_analyze_exits_zero(self):
        self.assertEqual(
            od.main(["analyze", "--report", str(WITH_ADMISSION)]), 0)

    def test_retry_storm_needs_one_of_two_inputs(self):
        self.assertEqual(od.main(["retry-storm"]), 1)

    def test_retry_storm_explicit_rates(self):
        self.assertEqual(
            od.main(["retry-storm", "--failure-rates", "0.04,0.15,0.40,0.73",
                     "--retries", "3"]), 0)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(od.main([]), 2)


if __name__ == "__main__":
    unittest.main()
