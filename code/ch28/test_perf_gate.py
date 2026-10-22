#!/usr/bin/env python3
"""Tests for code/ch28/perf_gate.py.

28.1's drift arithmetic, 28.3's threshold rule and 28.4's three silent
regressions are pinned here. The most important one is the last: a result whose
every latency metric improved must still be blocked when it changed precision
without quality data.
"""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

import perf_gate as pg

HERE = Path(__file__).resolve().parent
EV = HERE.parent.parent / "content" / "ch28" / "evidence"
BASELINE = json.loads((EV / "gate-baseline.json").read_text(encoding="utf-8"))
THRESHOLDS = json.loads((EV / "gate-thresholds.json").read_text(encoding="utf-8"))


def load(name):
    return json.loads((EV / name).read_text(encoding="utf-8"))


class TestDrift(unittest.TestCase):
    def test_the_five_steps_28_1_lists(self):
        """5 / 4 / 6 / 5 / 4 连乘是 1.26 倍，不是两倍。"""
        r = pg.drift([0.05, 0.04, 0.06, 0.05, 0.04])
        self.assertAlmostEqual(r["cumulative"], 1.2637, places=3)

    def test_all_five_are_inside_the_gate_threshold(self):
        """这是 28.1 那句“每一项单独看都在噪声范围内”的机器版。"""
        r = pg.drift([0.05, 0.04, 0.06, 0.05, 0.04], threshold=0.08)
        self.assertTrue(r["all_within_threshold"])
        self.assertEqual(r["steps_over_threshold"], [])
        self.assertIn("门禁一次都不会响", r["reading"])

    def test_a_twelve_percent_step_would_be_caught(self):
        """审阅指出的那处：12% 不在噪声里，会被 8% 的阈值拦住。"""
        r = pg.drift([0.08, 0.05, 0.12, 0.06, 0.09], threshold=0.08)
        self.assertFalse(r["all_within_threshold"])
        self.assertEqual(r["steps_over_threshold"], [3, 5])
        self.assertIn("超过了", r["reading"])

    def test_thirteen_five_percent_steps_nearly_double_it(self):
        """28.8 案例二：两周一次、26 周 13 次、每次 5%，1.89 倍。"""
        r = pg.drift([0.05] * 13)
        self.assertAlmostEqual(r["cumulative"], 1.886, places=3)

    def test_steps_to_double(self):
        self.assertAlmostEqual(pg.steps_to_double(0.05), 14.2, places=1)
        self.assertAlmostEqual(pg.steps_to_double(0.08), 9.0, places=1)

    def test_empty_rejected(self):
        with self.assertRaises(pg.GateError):
            pg.drift([])


class TestThresholdRule(unittest.TestCase):
    def test_the_lower_bound_is_the_identification_line(self):
        """下限不是「两倍 CV」：各 3 轮是可识别线 2.27 × CV，各 1 轮是 2.77 × CV。

        两倍那个说法比两者都低，会放过一档必然持续误报的阈值
        （28.3，Part 6 审阅 P1-15）。
        """
        lo, hi = pg.THRESHOLD_MULTIPLE
        self.assertAlmostEqual(lo, 2.267, places=3)
        self.assertEqual(hi, 3.0)
        self.assertGreater(pg.IDENTIFICATION_LINE_1_RUN, lo)

    def test_case_one_before_and_after(self):
        """28.8 案例一：变异系数 9% 时 5% 的阈值没法用；压到 2.6% 后 8% 就稳。"""
        bad = pg.threshold_advice(0.09)
        self.assertGreater(bad["min_usable"], 0.05)
        good = pg.threshold_advice(0.026)
        self.assertAlmostEqual(good["recommended"], 0.08, places=3)
        self.assertLessEqual(good["min_usable"], 0.08)

    def test_false_alarm_and_detection_28_3(self):
        """CV 2.6%、阈值 8%：单指标误报约 1.5%，五个约 7%，8% 回归检出一半，各 3 轮时 10% 检出约 83%。"""
        good = pg.threshold_advice(0.026)
        self.assertAlmostEqual(good["single_run"]["difference_sd"], 0.0368, places=4)
        self.assertAlmostEqual(good["single_run"]["false_alarm_per_metric"], 0.0148, places=3)
        self.assertAlmostEqual(good["single_run"]["false_alarm_any_of"], 0.072, places=3)
        self.assertAlmostEqual(good["single_run"]["detection"], 0.5, places=3)
        self.assertAlmostEqual(good["three_runs"]["detection"], 0.827, places=3)
        self.assertAlmostEqual(good["identification_line_3_runs"], 0.059, places=3)

    def test_a_gate_inside_the_noise_is_refused(self):
        bad = pg.check_threshold_sanity({"p95_latency_ms": 0.05},
                                        {"p95_latency_ms": 0.09})
        self.assertEqual(len(bad), 1)
        self.assertIn("可识别线", bad[0])

    def test_a_sane_gate_passes(self):
        self.assertEqual(
            pg.check_threshold_sanity({"p95_latency_ms": 0.10},
                                      {"p95_latency_ms": 0.026}), [])

    def test_the_default_table_matches_28_3(self):
        self.assertEqual(pg.DEFAULT_THRESHOLDS["p50_latency_ms"], 0.05)
        self.assertEqual(pg.DEFAULT_THRESHOLDS["p95_latency_ms"], 0.10)
        self.assertEqual(pg.DEFAULT_THRESHOLDS["throughput_tps"], 0.05)
        self.assertEqual(pg.DEFAULT_THRESHOLDS["peak_memory_gib"], 0.02)

    def test_p99_is_observe_only(self):
        """28.3：P99 波动很大，用作观察不用作阻断。"""
        self.assertIn("p99_latency_ms", pg.OBSERVE_ONLY)
        self.assertNotIn("p99_latency_ms", pg.DEFAULT_THRESHOLDS)


class TestRunPassing(unittest.TestCase):
    def setUp(self):
        self.r = pg.check_run(load("gate-result-pass.json"), BASELINE,
                              THRESHOLDS)

    def test_it_passes(self):
        self.assertEqual(self.r["verdict"], "pass")
        self.assertEqual(self.r["exit_code"], 0)

    def test_p99_is_reported_but_not_blocking(self):
        row = next(m for m in self.r["metrics"]
                   if m["metric"] == "p99_latency_ms")
        self.assertTrue(row["observe_only"])
        self.assertFalse(row["blocking"])
        self.assertGreater(row["change"], 0.05)

    def test_memory_has_the_tightest_threshold(self):
        row = next(m for m in self.r["metrics"]
                   if m["metric"] == "peak_memory_gib")
        self.assertEqual(row["threshold"], 0.02)


class TestRunSilentRegression(unittest.TestCase):
    """28.4 的核心：延迟全都更好，仍然要被拦住。"""

    def setUp(self):
        self.doc = load("gate-result-silent.json")
        self.r = pg.check_run(self.doc, BASELINE, THRESHOLDS)

    def test_every_latency_metric_improved(self):
        for m in self.r["metrics"]:
            if m["metric"].endswith("latency_ms"):
                with self.subTest(metric=m["metric"]):
                    self.assertLess(m["change"], 0)

    def test_memory_dropped_a_fifth(self):
        row = next(m for m in self.r["metrics"]
                   if m["metric"] == "peak_memory_gib")
        self.assertLess(row["change"], -0.2)

    def test_only_the_two_sided_memory_check_fires(self):
        """延迟和吞吐这几项都更好，一条都不响；显存双向判，降两成就响。

        它波动极小，往哪边动超过阈值都是真实的变化，而这一轮正是精度被悄悄
        改了（28.3、Part 6 审阅 P1-17）。这一项响之前，这份报告只有断言和
        质量数据拦得住。
        """
        self.assertEqual(self.r["threshold_failed"], ["peak_memory_gib"])
        row = next(m for m in self.r["metrics"]
                   if m["metric"] == "peak_memory_gib")
        self.assertTrue(row["two_sided"])
        # 「变差」那一侧没有越线：它是降下来的。
        self.assertLess(row["worse_by"], row["threshold"])
        self.assertIn("配置悄悄改了", row["why"])

    def test_it_is_blocked_anyway(self):
        self.assertEqual(self.r["verdict"], "fail")
        self.assertEqual(self.r["exit_code"], 1)

    def test_both_silent_kinds_are_named_in_the_reason(self):
        reason = self.r["blocking_reason"]
        self.assertIn("断言未通过", reason)
        self.assertIn("28.4 第一类", reason)

    def test_the_failing_assertion_is_the_kernel_one(self):
        self.assertEqual(
            self.r["silent_regression_checks"]["config"]["failed"],
            ["attention_kernel_allowlisted"])

    def test_precision_change_requires_quality_data(self):
        checks = self.r["silent_regression_checks"]["quality"]
        self.assertTrue(checks["required"])
        self.assertFalse(checks["present"])


class TestRunRefusals(unittest.TestCase):
    def test_a_different_environment_is_refused(self):
        doc = load("gate-result-pass.json")
        doc["environment"]["gpu"] = "2 × 80GiB"
        with self.assertRaises(pg.GateError) as ctx:
            pg.check_run(doc, BASELINE, THRESHOLDS)
        self.assertIn("不构成对比", str(ctx.exception))

    def test_a_different_workload_hash_is_refused(self):
        doc = load("gate-result-pass.json")
        doc["environment"]["workload_hash"] = "wl-other"
        with self.assertRaises(pg.GateError):
            pg.check_run(doc, BASELINE, THRESHOLDS)

    def test_a_missing_fingerprint_field_is_refused(self):
        doc = load("gate-result-pass.json")
        doc["environment"].pop("framework_version")
        with self.assertRaises(pg.GateError):
            pg.check_run(doc, BASELINE, THRESHOLDS)

    def test_a_threshold_inside_the_noise_is_refused(self):
        doc = load("gate-result-pass.json")
        doc["variation"]["p95_latency_ms"] = 0.09
        with self.assertRaises(pg.GateError) as ctx:
            pg.check_run(doc, BASELINE, THRESHOLDS)
        self.assertIn("28.3 原则一", str(ctx.exception))

    def test_no_assertions_downgrades_to_warn(self):
        doc = load("gate-result-pass.json")
        doc["assertions"] = []
        r = pg.check_run(doc, BASELINE, THRESHOLDS)
        self.assertEqual(r["verdict"], "warn")
        self.assertEqual(r["exit_code"], 2)

    def test_release_mode_wants_a_saturation_datapoint(self):
        doc = load("gate-result-pass.json")
        doc.pop("saturation")
        r = pg.check_run(doc, BASELINE, THRESHOLDS, mode="release")
        self.assertEqual(r["verdict"], "warn")
        self.assertTrue(any("饱和" in w for w in r["warnings"]))

    def test_unknown_mode_rejected(self):
        with self.assertRaises(pg.GateError):
            pg.check_run(load("gate-result-pass.json"), BASELINE,
                         THRESHOLDS, mode="fast")


class TestPromote(unittest.TestCase):
    def setUp(self):
        self.ok = pg.check_run(load("gate-result-pass.json"), BASELINE,
                               THRESHOLDS)
        self.bad = pg.check_run(load("gate-result-silent.json"), BASELINE,
                                THRESHOLDS)

    def test_a_reason_is_required(self):
        with self.assertRaises(pg.GateError) as ctx:
            pg.promote(self.ok, reason=None, approver="a", kind="improvement")
        self.assertIn("为什么该换基线", str(ctx.exception))

    def test_an_approver_is_required(self):
        with self.assertRaises(pg.GateError) as ctx:
            pg.promote(self.ok, reason="r", approver=None, kind="improvement")
        self.assertIn("签字", str(ctx.exception))

    def test_only_the_two_kinds_28_3_allows(self):
        with self.assertRaises(pg.GateError) as ctx:
            pg.promote(self.ok, reason="r", approver="a", kind="routine")
        self.assertIn("28.3", str(ctx.exception))

    def test_a_failed_result_cannot_become_the_baseline(self):
        """28.8 案例二那条路，从这里堵住。"""
        with self.assertRaises(pg.GateError) as ctx:
            pg.promote(self.bad, reason="r", approver="a", kind="improvement")
        self.assertIn("案例二", str(ctx.exception))

    def test_a_valid_promotion_records_who_and_why(self):
        r = pg.promote(self.ok, reason="Ch17 KV 量化验收", approver="mango",
                       kind="improvement")
        self.assertTrue(r["promoted"])
        self.assertEqual(r["approver"], "mango")
        self.assertIn("换基准要留记录", r["note"])


class TestSamples(unittest.TestCase):
    def test_all_declared_synthetic(self):
        for name in ("gate-baseline.json", "gate-result-pass.json",
                     "gate-result-silent.json", "gate-thresholds.json"):
            doc = load(name)
            with self.subTest(file=name):
                self.assertIn("合成设定", doc["_note"])

    def test_the_two_results_share_one_environment(self):
        a = load("gate-result-pass.json")["environment"]
        b = load("gate-result-silent.json")["environment"]
        self.assertEqual(a, b)


class TestCli(unittest.TestCase):
    def test_pass_exits_zero(self):
        self.assertEqual(pg.main([
            "run", "--result", str(EV / "gate-result-pass.json"),
            "--baseline", str(EV / "gate-baseline.json"),
            "--thresholds", str(EV / "gate-thresholds.json")]), 0)

    def test_silent_regression_exits_one(self):
        self.assertEqual(pg.main([
            "run", "--result", str(EV / "gate-result-silent.json"),
            "--baseline", str(EV / "gate-baseline.json"),
            "--thresholds", str(EV / "gate-thresholds.json")]), 1)

    def test_promote_without_reason_exits_one(self):
        self.assertEqual(pg.main([
            "promote", "--result", str(EV / "gate-result-pass.json"),
            "--baseline", str(EV / "gate-baseline.json")]), 1)

    def test_drift_exits_zero(self):
        self.assertEqual(pg.main(["drift", "--steps", "0.05,0.04"]), 0)

    def test_threshold_exits_zero(self):
        self.assertEqual(pg.main(["threshold", "--cv", "0.026"]), 0)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(pg.main([]), 2)


if __name__ == "__main__":
    unittest.main()
