#!/usr/bin/env python3
"""Tests for code/ch25/e2e_experiment.py.

25.3's budget and 25.7's assertion bases are pinned here: the adjusted budget
adds to 8000 with 300 ms unallocated; 7 model calls get 714 ms each, 234 ms of it
for queueing, so at S = 103 ms the load must stay at or below 0.69 and the
measured 0.9 (927 ms a call) is refused; 5000/480 = 10.4 caps the call count
even with no queue at all; and the 55% hit-rate gate has 9 points of headroom
under a 64% ceiling (1 − 2/7 = 71%, × 0.9).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import e2e_experiment as ee

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent.parent / "content" / "ch25" / "evidence"
OK_REPORT = EVIDENCE / "e2e-experiment-admission.json"
BAD_REPORT = EVIDENCE / "e2e-experiment-three-at-once.json"
GUARD_CFG = EVIDENCE / "guard-rules-sample.json"

BUDGET_KW = dict(total_ms=8000.0, per_step_orchestration_ms=50.0,
                 retrieval_ms=1200.0, model_serving_ms=5000.0,
                 tools_ms=1000.0, measured_call_compute_ms=480.0,
                 model_calls_p95=7, service_time_ms=103.0)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestBudget(unittest.TestCase):
    def test_the_adjusted_budget_in_25_3(self):
        r = ee.build_budget(steps_p95=10, rho=0.69, **BUDGET_KW)
        self.assertEqual(r["layers"]["orchestration"]["ms"], 500.0)
        self.assertEqual(r["layers"]["retrieval"]["ms"], 1200.0)
        self.assertEqual(r["layers"]["model_serving"]["ms"], 5000.0)
        self.assertEqual(r["layers"]["tools"]["ms"], 1000.0)
        self.assertEqual(r["unallocated_ms"], 300.0)

    def test_it_adds_up_to_the_total(self):
        r = ee.build_budget(steps_p95=10, **BUDGET_KW)
        parts = sum(row["ms"] for row in r["layers"].values())
        self.assertEqual(parts + r["unallocated_ms"], r["total_ms"])

    def test_orchestration_is_steps_times_per_step(self):
        """编排层 500 = 10 × 50，步数少了它就跟着少。"""
        r = ee.build_budget(steps_p95=10, **BUDGET_KW)
        self.assertEqual(r["layers"]["orchestration"]["ms"], 10 * 50)

    def test_first_draft_orchestration_is_750(self):
        """25.3 第一版：15 × 50 = 750，各层之和 7950，只剩 50 ms 余量。"""
        r = ee.build_budget(steps_p95=15, **BUDGET_KW)
        self.assertEqual(r["layers"]["orchestration"]["ms"], 750.0)
        self.assertEqual(r["unallocated_ms"], 50.0)

    def test_per_call_split_leaves_234_ms_for_the_queue(self):
        """5000 ÷ 7 ≈ 714 ms 一次调用，扣掉 480 ms 纯计算，只剩约 234 ms 排队。"""
        r = ee.build_budget(steps_p95=10, **BUDGET_KW)
        self.assertAlmostEqual(r["per_call_model_serving_ms"], 714.286, places=3)
        self.assertAlmostEqual(r["queue_allowance_per_call_ms"], 234.286, places=3)

    def test_the_load_ceiling_is_0_69(self):
        """ρ/(1−ρ) ≤ 234/103，即 ρ ≤ 234/(103 + 234) ≈ 0.69。"""
        r = ee.build_budget(steps_p95=10, **BUDGET_KW)
        self.assertAlmostEqual(r["rho_max"], 0.6946, places=4)

    def test_todays_load_is_refused_with_the_queue_numbers(self):
        """25.2 量到的现状：负载率 0.9，每次调用排队约 927 ms，放不进 234 ms。"""
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.build_budget(steps_p95=15, rho=0.9, **BUDGET_KW)
        message = str(ctx.exception)
        self.assertIn("234", message)
        self.assertIn("927", message)
        self.assertIn("0.69", message)
        self.assertIn("动手之前", message)

    def test_the_measured_queue_matches_25_2(self):
        """7 次 × 927 ms ≈ 6.5 秒，正是 21 秒里那 31%。"""
        self.assertAlmostEqual(7 * ee.queue_ms(103.0, 0.9) / 21000, 0.31, places=2)

    def test_at_0_69_it_fits(self):
        r = ee.build_budget(steps_p95=10, rho=0.69, **BUDGET_KW)
        self.assertLess(r["queue_per_call_ms"], r["queue_allowance_per_call_ms"])

    def test_compute_alone_caps_the_call_count_at_ten(self):
        """5000 ÷ 480 = 10.4：连排队都不算，最多也只能放 10 次调用。"""
        self.assertEqual(ee.max_feasible_calls(5000, 480), 10)
        kw = dict(BUDGET_KW, model_calls_p95=11, service_time_ms=None)
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.build_budget(steps_p95=10, **kw)
        self.assertIn("最多 10 次", str(ctx.exception))

    def test_without_a_call_count_each_step_is_one_call(self):
        """不给调用次数时按每步一次调用：15 步每次只有 333 ms，连纯计算都放不下。"""
        kw = dict(BUDGET_KW, model_calls_p95=None, service_time_ms=None)
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.build_budget(steps_p95=15, **kw)
        self.assertIn("333", str(ctx.exception))

    def test_layers_summing_over_the_total_is_refused(self):
        kw = dict(BUDGET_KW)
        kw["retrieval_ms"] = 3000.0
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.build_budget(steps_p95=10, **kw)
        self.assertIn("已经超过总预算", str(ctx.exception))

    def test_unallocated_is_not_handed_to_a_layer(self):
        r = ee.build_budget(steps_p95=10, **BUDGET_KW)
        self.assertIn("共用", r["unallocated_basis"])
        self.assertIn("5.9", r["unallocated_basis"])

    def test_acceptance_is_end_to_end_p95_not_a_sum_of_layer_p95s(self):
        r = ee.build_budget(steps_p95=10, **BUDGET_KW)
        self.assertIn("不拿各层自己的 P95 相加", r["acceptance"])

    def test_bad_inputs_rejected(self):
        for kw in ({"total_ms": 0.0}, {"model_serving_ms": 0.0},
                   {"measured_call_compute_ms": 0.0}):
            merged = dict(BUDGET_KW)
            merged.update(kw)
            with self.assertRaises(ee.ExperimentError):
                ee.build_budget(steps_p95=10, **merged)
        with self.assertRaises(ee.ExperimentError):
            ee.build_budget(steps_p95=0, **BUDGET_KW)


class TestQueueAndAmdahlInTheProse(unittest.TestCase):
    def test_case_one_saves_about_seven_percent(self):
        """案例一：7 次调用各省 220 ms，约 1.5 秒，21 秒里约 7%。"""
        saved = 7 * (480 - 260)
        self.assertAlmostEqual(saved / 21000, 0.073, places=3)

    def test_case_one_if_throughput_had_risen_too(self):
        """同样省 220 ms 若来自满载吞吐：ρ 0.9 → 0.49，排队塌下去，端到端约省 36%。"""
        k = 260 / 480
        rho, s = 0.9 * k, 103.0 * k
        queue_saved = 7 * (ee.queue_ms(103.0, 0.9) - ee.queue_ms(s, rho))
        total = (queue_saved + 7 * 220) / 21000
        self.assertAlmostEqual(rho, 0.4875)
        self.assertAlmostEqual(total, 0.365, places=2)

    def test_fewer_calls_drop_the_queue_to_a_twentieth(self):
        """25.5：调用次数降到三分之一，ρ 0.9 → 0.3，排队从 9 个 S 降到约 0.43 个。"""
        before = ee.queue_ms(1.0, 0.9)
        after = ee.queue_ms(1.0, 0.3)
        self.assertAlmostEqual(after, 0.4286, places=4)
        self.assertAlmostEqual(before / after, 21.0, places=1)


class TestHitRateCeiling(unittest.TestCase):
    def test_seven_calls_gives_seventy_one_percent_cacheable(self):
        """1 − 2/7 ≈ 71%，这就是 25.7 那个 71% 的来源。"""
        self.assertAlmostEqual(ee.cacheable_share_from_calls(7), 0.7143, places=4)

    def test_more_calls_means_a_higher_cacheable_share(self):
        """调用越多可缓存占比越高，Agent 场景天然适合 Prefix Cache。"""
        shares = [ee.cacheable_share_from_calls(n) for n in (4, 10, 20, 40)]
        self.assertEqual(shares, sorted(shares))
        self.assertAlmostEqual(shares[0], 0.5)
        self.assertAlmostEqual(shares[-1], 0.95)

    def test_the_ceiling_is_about_sixty_four_percent(self):
        """0.714 × 0.9 ≈ 64%。"""
        self.assertAlmostEqual(ee.hit_rate_ceiling(1 - 2 / 7, 0.9), 0.6429, places=4)

    def test_the_gate_has_nine_points_of_headroom(self):
        r = ee.ceiling_check(calls=7, route_hit=0.9, threshold=0.55)
        self.assertAlmostEqual(r["ceiling"], 0.6429, places=4)
        self.assertAlmostEqual(r["headroom"], 0.0929, places=4)
        self.assertTrue(r["reachable"])
        self.assertIn("9.3 个点", r["reading"])

    def test_a_gate_at_the_ceiling_is_flagged_as_unreachable(self):
        """门槛等于天花板时断言必然长期红着，这是本该在设阈值时发现的。"""
        ceiling = ee.hit_rate_ceiling(1 - 2 / 7, 0.9)
        r = ee.ceiling_check(calls=7, route_hit=0.9, threshold=ceiling)
        self.assertFalse(r["reachable"])
        self.assertIn("必然长期红着", r["reading"])

    def test_round_robin_across_three_instances_cannot_reach_the_gate(self):
        """三实例轮询：7 次调用的会话前缀路由项约 0.6（22.4），缓存吃紧时往 1/3 掉，都够不着 55%。"""
        import importlib.util
        path = HERE.parent / "ch22" / "serving_choice.py"
        spec = importlib.util.spec_from_file_location("sc22", path)
        sc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sc)
        term = sc.routing_term(3, 7)
        self.assertAlmostEqual(term, 0.597, places=3)
        for route in (term, 1 / 3):
            r = ee.ceiling_check(calls=7, route_hit=route, threshold=0.55)
            self.assertFalse(r["reachable"])

    def test_single_call_has_no_prefix(self):
        with self.assertRaises(ee.ExperimentError):
            ee.cacheable_share_from_calls(1)


class TestGuard(unittest.TestCase):
    def test_the_sample_passes_all_five(self):
        r = ee.guard(load(GUARD_CFG)["rules"])
        self.assertTrue(r["passed"])
        self.assertEqual(len(r["rules"]), 5)
        self.assertEqual(r["failed"], [])

    def test_five_rules_are_the_five_25_7_lists(self):
        self.assertEqual(len(ee.GUARD_RULES), 5)
        self.assertIn("prefix_cache_hit_rate", ee.GUARD_RULES)
        self.assertIn("attention_kernel_allowlisted", ee.GUARD_RULES)

    def test_a_missing_rule_is_refused(self):
        rules = load(GUARD_CFG)["rules"]
        rules.pop("steps_p95")
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.guard(rules)
        self.assertIn("一条都不能少", str(ctx.exception))

    def test_a_rule_without_a_basis_is_refused(self):
        """没有依据的门禁半年后没人敢改，也没人敢相信。"""
        rules = load(GUARD_CFG)["rules"]
        rules["load_skew"].pop("basis")
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.guard(rules)
        self.assertIn("没人敢改", str(ctx.exception))

    def test_a_numeric_rule_without_a_threshold_is_refused(self):
        rules = load(GUARD_CFG)["rules"]
        rules["load_skew"].pop("threshold")
        with self.assertRaises(ee.ExperimentError):
            ee.guard(rules)

    def test_direction_min_and_max_both_work(self):
        rules = load(GUARD_CFG)["rules"]
        rules["prefix_cache_hit_rate"]["actual"] = 0.54
        r = ee.guard(rules)
        self.assertIn("prefix_cache_hit_rate", r["failed"])
        rules = load(GUARD_CFG)["rules"]
        rules["load_skew"]["actual"] = 0.44
        r = ee.guard(rules)
        self.assertIn("load_skew", r["failed"])

    def test_a_value_sitting_exactly_on_the_threshold_passes(self):
        """阈值是设计点不是越线：25.3 那份预算就是按步数 P95 = 10 给的。"""
        rules = load(GUARD_CFG)["rules"]
        rules["steps_p95"]["actual"] = 10
        self.assertTrue(ee.guard(rules)["passed"])
        rules["steps_p95"]["actual"] = 11
        self.assertFalse(ee.guard(rules)["passed"])

    def test_the_old_threshold_of_fifteen_steps_would_have_passed(self):
        """25.3 的第一版 15 步：门槛定在 15 会放过编排层超支的那次回退（14 × 50 = 700 > 500）。"""
        rules = load(GUARD_CFG)["rules"]
        rules["steps_p95"] = {"actual": 14, "threshold": 15,
                              "direction": "max", "basis": "旧门槛"}
        self.assertTrue(ee.guard(rules)["passed"])
        # 换成正确的门槛，同一个实测值就被拦住了。
        rules["steps_p95"]["threshold"] = 10
        self.assertFalse(ee.guard(rules)["passed"])

    def test_a_false_boolean_fails(self):
        rules = load(GUARD_CFG)["rules"]
        rules["attention_kernel_allowlisted"]["actual"] = False
        r = ee.guard(rules)
        self.assertEqual(r["failed"], ["attention_kernel_allowlisted"])
        self.assertIn("部署应当中止", r["reading"])


class TestReportChecks(unittest.TestCase):
    def test_the_passing_report_checks_out(self):
        r = ee.check_report(load(OK_REPORT))
        self.assertTrue(r["verdict"]["passed"])
        self.assertEqual(r["verdict"]["label"], "符合预期")
        self.assertTrue(r["scorecard"]["veto_holds"])

    def test_ten_dimensions(self):
        """质量从检索的子字段里提出来，自己占一维：它是否决项（25.6）。"""
        r = ee.check_report(load(OK_REPORT))
        self.assertEqual(len(r["scorecard"]["dimensions"]), 10)
        self.assertIn("quality", r["scorecard"]["dimensions"])
        self.assertEqual(tuple(r["scorecard"]["dimensions"]), ee.DIMENSIONS)

    def test_the_failing_report_is_valid_but_failed(self):
        """报告可以格式正确而结论是失败，检查器不该把这两件事混在一起。"""
        r = ee.check_report(load(BAD_REPORT))
        self.assertFalse(r["verdict"]["passed"])
        self.assertFalse(r["scorecard"]["veto_holds"])
        self.assertEqual(sorted(r["scorecard"]["vetoes_breached"]),
                         ["preemption_count", "task_success_rate"])

    def test_improving_dimensions_do_not_outrank_a_veto(self):
        r = ee.check_report(load(BAD_REPORT))
        self.assertEqual(len(r["scorecard"]["dimensions_improved"]), 2)
        self.assertIn("记分卡不是投票", r["scorecard"]["reading"])

    def test_claiming_passed_with_a_breached_veto_is_refused(self):
        doc = load(BAD_REPORT)
        doc["verdict"]["passed"] = True
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.check_report(doc)
        self.assertIn("抵不过", str(ctx.exception))

    def test_an_idle_breakdown_is_refused(self):
        """25.2：空闲时排队为零，那张表会完全是另一个样子。"""
        doc = load(OK_REPORT)
        doc["layer_breakdown"]["collected_under_load"] = "idle"
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.check_report(doc)
        self.assertIn("不可用于决策", str(ctx.exception))

    def test_an_unlabelled_breakdown_is_refused(self):
        doc = load(OK_REPORT)
        doc["layer_breakdown"].pop("collected_under_load")
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.check_report(doc)
        self.assertIn("压测下", str(ctx.exception))

    def test_shares_that_do_not_sum_to_one_are_refused(self):
        doc = load(OK_REPORT)
        doc["layer_breakdown"]["shares"]["retrieval"] = 0.50
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.check_report(doc)
        self.assertIn("算了两遍", str(ctx.exception))

    def test_empty_cross_layer_is_refused(self):
        doc = load(OK_REPORT)
        doc["cross_layer"] = []
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.check_report(doc)
        self.assertIn("没有看", str(ctx.exception))

    def test_boundary_needs_five_items_including_the_chain(self):
        self.assertEqual(len(ee.BOUNDARY_ITEMS), 5)
        doc = load(OK_REPORT)
        doc["boundary"].pop("chain_structure")
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.check_report(doc)
        self.assertIn("chain_structure", str(ctx.exception))
        self.assertIn("链路变了结论就不成立", str(ctx.exception))

    def test_missing_expectation_is_refused(self):
        doc = load(OK_REPORT)
        doc.pop("expectation")
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.check_report(doc)
        self.assertIn("事前写下", str(ctx.exception))

    def test_a_verdict_outside_ch14s_four_is_refused(self):
        doc = load(OK_REPORT)
        doc["verdict"]["label"] = "略有改善"
        with self.assertRaises(ee.ExperimentError):
            ee.check_report(doc)

    def test_all_four_ch14_verdicts_have_a_reading(self):
        for label in ee.VERDICTS:
            self.assertIn(label, ee.VERDICT_READING)

    def test_a_missing_veto_dimension_is_refused(self):
        doc = load(OK_REPORT)
        doc["scorecard"]["quality"].pop("quality")
        with self.assertRaises(ee.ExperimentError) as ctx:
            ee.check_report(doc)
        self.assertIn("否决项", str(ctx.exception))

    def test_budget_overruns_are_reported_not_hidden(self):
        """这两轮都只走到六项改动里的头几项，端到端 16 秒 / 24 秒，
        离 8 秒那份预算还远，所以四层全部超支——报告要照直说。"""
        r = ee.check_report(load(OK_REPORT))
        self.assertEqual(sorted(r["budget_overruns"]), sorted(ee.LAYERS))

    def test_the_failing_report_overruns_more_than_the_passing_one(self):
        ok = ee.check_report(load(OK_REPORT))
        bad = ee.check_report(load(BAD_REPORT))
        self.assertEqual(sorted(bad["budget_overruns"]), sorted(ee.LAYERS))
        ok_ms = load(OK_REPORT)["budget_check"]["model_serving"]["actual_ms"]
        bad_ms = load(BAD_REPORT)["budget_check"]["model_serving"]["actual_ms"]
        self.assertGreater(bad_ms, 2 * ok_ms)


class TestSampleReportsAgreeWithTheBudget(unittest.TestCase):
    def test_the_passing_round_did_not_touch_the_steps(self):
        """这一轮只开准入。合并细粒度工具是 25.4 的第 5 项，还没做，
        所以步数 P95 仍是 34，编排层照 25.3 的预算还在超支（34 × 50 > 500）。
        它正是 25.5 那句「别用步数之比去估模型服务的负载」的反面教材来源。"""
        doc = load(OK_REPORT)
        steps = doc["scorecard"]["orchestration"]["steps_p95"]
        self.assertEqual(steps, 34)
        self.assertGreater(steps * 50, 500)
        self.assertTrue(any("步数没变" in line for line in doc["cross_layer"]))

    def test_the_passing_rounds_hit_rate_sits_under_the_round_robin_ceiling(self):
        """路由也没改：三实例轮询时会话前缀的命中天花板约 43%（25.7），
        所以这一轮的命中率必然够不着 55% 那条门槛，前缀亲和是第 2 项的事。"""
        doc = load(OK_REPORT)
        hit = doc["scorecard"]["retrieval"]["cache_hit_rates"]["prefix"]
        round_robin_ceiling = ee.hit_rate_ceiling(1 - 2 / 7, 0.6)
        self.assertLessEqual(hit, round_robin_ceiling)
        self.assertLess(hit, 0.55)

    def test_the_affinity_round_lifts_the_hit_rate(self):
        """三项一起改的那一轮动了路由，命中率应当高于轮询那一轮，
        并且落在前缀亲和的天花板 64% 以下。"""
        ok = load(OK_REPORT)["scorecard"]["retrieval"]["cache_hit_rates"]
        bad = load(BAD_REPORT)["scorecard"]["retrieval"]["cache_hit_rates"]
        self.assertGreater(bad["prefix"], ok["prefix"])
        self.assertLess(bad["prefix"], ee.hit_rate_ceiling(1 - 2 / 7, 0.9))

    def test_no_instance_beats_the_cacheable_share(self):
        """单个实例的命中率也不能超过可缓存占比 71%。"""
        for path in (OK_REPORT, BAD_REPORT):
            per = load(path)["scorecard"]["routing"]["per_instance_hit_rate"]
            self.assertLess(max(per), 1 - 2 / 7, path.name)

    def test_the_passing_reports_skew_clears_22_4s_threshold(self):
        doc = load(OK_REPORT)
        self.assertLess(doc["scorecard"]["routing"]["load_skew"], 0.30)

    def test_the_failing_reports_skew_is_past_the_p99_line(self):
        doc = load(BAD_REPORT)
        self.assertGreater(doc["scorecard"]["routing"]["load_skew"], 0.50)

    def test_both_declared_synthetic(self):
        for path in (OK_REPORT, BAD_REPORT, GUARD_CFG):
            doc = load(path)
            self.assertTrue(doc["synthetic"], path.name)
            self.assertIn("合成设定", doc["_note"], path.name)

    def test_the_pair_shares_its_collection_conditions(self):
        """对比成立靠的是采集条件和边界相同。分解本身是被改动的对象，
        24 秒和 16 秒的两轮不可能有同一张分解表（Part 5 审阅 P0-12）。"""
        a, b = load(OK_REPORT), load(BAD_REPORT)
        self.assertEqual(a["boundary"], b["boundary"])
        for key in ("collected_under_load", "load_note"):
            self.assertEqual(a["layer_breakdown"][key],
                             b["layer_breakdown"][key], key)
        self.assertNotEqual(a["layer_breakdown"]["shares"],
                            b["layer_breakdown"]["shares"])

    def test_each_round_layers_add_up_to_its_own_end_to_end(self):
        """各层实测之和要等于这一轮自己的端到端 P95（25.8 那条检查）。"""
        for path in (OK_REPORT, BAD_REPORT):
            doc = load(path)
            total = sum(row["actual_ms"]
                        for row in doc["budget_check"].values())
            p95 = doc["scorecard"]["end_to_end"]["p95_task_ms"]
            self.assertAlmostEqual(total / p95, 1.0, places=2, msg=path.name)


class TestCli(unittest.TestCase):
    def test_budget_at_0_69_exits_zero(self):
        self.assertEqual(ee.main(["budget", "--slo", "8000", "--steps-p95", "10",
                                  "--model-calls-p95", "7",
                                  "--service-time-ms", "103", "--rho", "0.69"]), 0)

    def test_budget_at_todays_load_exits_one(self):
        self.assertEqual(ee.main(["budget", "--slo", "8000", "--steps-p95", "15",
                                  "--model-calls-p95", "7",
                                  "--service-time-ms", "103", "--rho", "0.9"]), 1)

    def test_run_exits_zero_on_both_samples(self):
        for path in (OK_REPORT, BAD_REPORT):
            self.assertEqual(ee.main(["run", "--report", str(path)]), 0)

    def test_guard_exit_code_is_the_gate(self):
        self.assertEqual(ee.main(["guard", "--config", str(GUARD_CFG)]), 0)

    def test_ceiling_exits_one_when_unreachable(self):
        self.assertEqual(ee.main(["ceiling", "--calls", "7",
                                  "--route-hit", "0.33"]), 1)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(ee.main([]), 2)


if __name__ == "__main__":
    unittest.main()
