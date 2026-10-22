#!/usr/bin/env python3
"""Tests for the Chapter 18 applicability checker.

Pins 18.3's formula, 18.4's derived threshold, 18.6's table thresholds, 18.7's
four criteria and both cases in 18.8. Many are refusal tests: the point of this
script is what it declines to estimate.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

import decode_optimization_check as dc

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHARED_CONFIG = REPO / "code" / "ch15" / "model-7b-generic.json"
ACCEPTANCE = REPO / "content" / "ch18" / "evidence" / "draft-acceptance-sample.json"

BASE = dict(tpot_measured=17.0, tpot_floor=14.0, batch_p50=8, batch_p95=16,
            model_params=7e9, bandwidth_gb_per_s=1000)


def acceptance_doc() -> dict:
    return json.loads(ACCEPTANCE.read_text(encoding="utf-8"))


class TestBottleneckForm(unittest.TestCase):
    """18.7 的三档，与 15.5 同一把尺。"""

    def test_bandwidth_bound_band(self):
        self.assertEqual(dc.bottleneck_form(17.0, 14.0)["form"], "带宽受限")

    def test_mixed_band(self):
        self.assertEqual(dc.bottleneck_form(25.0, 14.0)["form"], "混合")

    def test_scheduler_bound_band(self):
        self.assertEqual(dc.bottleneck_form(42.0, 14.0)["form"], "调度受限")

    def test_below_the_floor_is_a_definition_problem_not_good_news(self):
        shape = dc.bottleneck_form(12.0, 14.0)
        self.assertEqual(shape["form"], "口径有问题")
        self.assertIn("不是好消息", shape["reason"])

    def test_the_boundaries_are_1_3_and_2_0(self):
        self.assertEqual(dc.RATIO_BANDWIDTH_BOUND, 1.3)
        self.assertEqual(dc.RATIO_SCHEDULER_BOUND, 2.0)
        self.assertEqual(dc.bottleneck_form(14 * 1.3, 14.0)["form"], "带宽受限")
        self.assertEqual(dc.bottleneck_form(14 * 2.0, 14.0)["form"], "混合")

    def test_non_positive_inputs_are_rejected(self):
        with self.assertRaises(dc.CheckError):
            dc.bottleneck_form(0, 14.0)
        with self.assertRaises(dc.CheckError):
            dc.bottleneck_form(17.0, 0)


class TestSection183Formula(unittest.TestCase):
    """18.3：收益比 = a ÷ (1 + k × c)，盈亏线 a > 1 + k × c。"""

    def test_the_break_even_line_at_k4_c01_is_1_4(self):
        self.assertAlmostEqual(dc.spec_break_even(4, 0.1), 1.4, places=6)

    def test_the_two_worked_examples_in_183(self):
        self.assertAlmostEqual(dc.spec_gain(3.2, 4, 0.1), 2.286, places=3)
        self.assertAlmostEqual(dc.spec_gain(1.1, 4, 0.1), 0.7857, places=3)

    def test_below_the_line_it_is_a_net_loss_not_a_small_gain(self):
        self.assertLess(dc.spec_gain(1.1, 4, 0.1), 1.0)
        self.assertGreater(dc.spec_gain(1.5, 4, 0.1), 1.0)

    def test_exactly_on_the_line_gives_exactly_one(self):
        self.assertAlmostEqual(dc.spec_gain(1.4, 4, 0.1), 1.0, places=6)

    def test_a_larger_k_raises_both_sides_so_it_has_an_optimum(self):
        """“猜的个数 k 加大会同时抬高分子和分母，所以它有最优值”。"""
        self.assertGreater(dc.spec_break_even(8, 0.1),
                           dc.spec_break_even(4, 0.1))

    def test_acceptance_below_one_is_rejected(self):
        """不匹配的位置上用的是目标模型自己的结果，所以至少接受 1 个。"""
        with self.assertRaises(dc.CheckError):
            dc.spec_gain(0.8, 4, 0.1)

    def test_draft_memory_is_1_3_gib_and_displaces_about_11k_tokens(self):
        """18.3：十分之一大的草稿模型 1.3 GiB，吃掉约 1.1 万个 token。"""
        cost = dc.draft_memory_cost(0.7e9, 2, 131072)
        self.assertAlmostEqual(cost["draft_gb_decimal"], 1.4, places=3)
        self.assertAlmostEqual(cost["draft_gib"], 1.304, places=3)
        self.assertEqual(cost["tokens_displaced"], 10681)

    def test_at_int8_kv_the_same_draft_displaces_twice_as_many(self):
        """19.5 那笔账用的是 64 KiB，所以是 2.1 万而不是 1.1 万。"""
        cost = dc.draft_memory_cost(0.7e9, 2, 65536)
        self.assertEqual(cost["tokens_displaced"], 21362)


class TestSection184CudaGraphThreshold(unittest.TestCase):
    """18.4：那条线是算出来的，随带宽移动，不是写死的 30B。"""

    def test_launch_share_at_7b_is_3_6_percent(self):
        self.assertAlmostEqual(dc.launch_share(7e9, 1000), 0.0357, places=4)

    def test_launch_share_at_30b_is_below_one_percent(self):
        self.assertLess(dc.launch_share(30e9, 1000), 0.01)
        self.assertAlmostEqual(dc.launch_share(30e9, 1000), 0.0083, places=4)

    def test_the_one_percent_line_lands_at_25b_on_a_1000_gbps_card(self):
        self.assertAlmostEqual(
            dc.cuda_graph_threshold_params(1000) / 1e9, 25.0, places=1)

    def test_the_line_moves_with_bandwidth(self):
        """带宽越高，同样参数量下单步越短，启动开销占比越大。"""
        self.assertAlmostEqual(
            dc.cuda_graph_threshold_params(2039) / 1e9, 50.975, places=2)
        self.assertGreater(dc.cuda_graph_threshold_params(2039),
                           dc.cuda_graph_threshold_params(1000))

    def test_30b_is_past_the_line_so_it_is_marked_limited(self):
        report = dc.build_report(**(BASE | {"model_params": 30e9,
                                            "tpot_floor": 60.0,
                                            "tpot_measured": 66.0}))
        self.assertEqual(report["cuda_graph"]["verdict"], "收益有限")

    def test_7b_on_a_bandwidth_bound_service_is_a_confirmation_not_a_todo(self):
        """18.6：多数框架默认开启，所以这往往是确认项。"""
        report = dc.build_report(**BASE)
        self.assertEqual(report["cuda_graph"]["verdict"], "确认项")

    def test_7b_on_a_scheduler_bound_service_is_applicable(self):
        report = dc.build_report(**(BASE | {"tpot_measured": 42.0}))
        self.assertEqual(report["cuda_graph"]["verdict"], "适用")

    def test_graph_memory_is_not_multiplied_out_of_buckets(self):
        """18.8 案例二：档位数只记录，不乘一个每档固定值。"""
        report = dc.build_report(**(BASE | {"captured_buckets": 20}))
        memory = report["cuda_graph"]["memory_cost"]
        self.assertIsNone(memory["graph_memory_gib"])
        self.assertIn("启动日志", memory["source"])
        self.assertIn("最大捕获批量", memory["note"])

    def test_graph_memory_comes_from_the_startup_log(self):
        report = dc.build_report(**(BASE | {"captured_buckets": 20,
                                            "graph_memory_gib": 1.6}))
        memory = report["cuda_graph"]["memory_cost"]
        self.assertEqual(memory["graph_memory_gib"], 1.6)
        self.assertEqual(memory["source"], "启动日志")

    def test_zero_buckets_is_rejected(self):
        with self.assertRaises(dc.CheckError):
            dc.build_report(**(BASE | {"captured_buckets": 0}))


class TestAcceptanceRateAndLength(unittest.TestCase):
    """18.3：α 是逐位置接受率，a 是一轮平均产出几个 token。"""

    def test_a_from_alpha(self):
        self.assertAlmostEqual(dc.mean_accepted_from_rate(0.231, 4), 1.30, places=2)
        self.assertAlmostEqual(dc.mean_accepted_from_rate(0.775, 4), 3.20, places=2)

    def test_k_has_an_optimum(self):
        self.assertEqual(dc.best_k(0.8, 0.1), 6)
        self.assertLess(dc.best_k(0.8, 0.26), dc.best_k(0.8, 0.1))

    def test_batch_ceiling_is_ridge_over_k_plus_one(self):
        self.assertAlmostEqual(dc.spec_batch_ceiling(153, 4), 30.6, places=1)
        self.assertAlmostEqual(dc.spec_batch_ceiling(306, 4), 61.2, places=1)

    def test_a_rate_report_is_converted_and_best_k_reported(self):
        report = dc.build_report(**(BASE | {"acceptance": {
            "acceptance_rate": 0.8, "k": 4, "draft_cost_ratio": 0.1}}))
        spec = report["spec_decoding"]
        self.assertAlmostEqual(spec["mean_accepted_length"], 3.362, places=3)
        self.assertEqual(spec["best_k"], 6)


class TestAcceptanceIsNeverGuessed(unittest.TestCase):
    """18.7 那条刻意的规则，而且它压过其他判据。"""

    def test_without_a_report_the_verdict_is_pending(self):
        report = dc.build_report(**BASE)
        self.assertEqual(report["spec_decoding"]["verdict"], "待测")

    def test_without_a_report_no_gain_ratio_is_produced(self):
        report = dc.build_report(**BASE)
        self.assertIsNone(report["spec_decoding"]["gain_ratio"])
        self.assertIsNone(report["spec_decoding"]["break_even_acceptance"])

    def test_the_reason_says_why_no_industry_average_is_used(self):
        report = dc.build_report(**BASE)
        joined = " ".join(report["spec_decoding"]["reasons"])
        self.assertIn("完全不可迁移", joined)

    def test_pending_also_raises_a_do_not_deploy_warning(self):
        report = dc.build_report(**BASE)
        self.assertTrue(any("不要部署" in w for w in report["warnings"]))

    def test_pending_wins_even_on_a_low_batch_bandwidth_bound_service(self):
        """其他判据全部有利时，缺接受率仍然只能是“待测”。"""
        report = dc.build_report(**(BASE | {"batch_p50": 1, "batch_p95": 2}))
        self.assertEqual(report["spec_decoding"]["verdict"], "待测")

    def test_a_report_missing_a_field_is_rejected_by_the_cli(self):
        broken = HERE / "_broken-acceptance.json"
        broken.write_text(json.dumps({"mean_accepted": 3.6}), encoding="utf-8")
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = dc.main(["--config", str(SHARED_CONFIG),
                              "--tpot-measured", "17", "--batch-p50", "8",
                              "--draft-acceptance", str(broken)])
            self.assertEqual(rc, 1)
            self.assertIn("无法代入", out.getvalue())
        finally:
            broken.unlink()


class TestSection188CaseOne(unittest.TestCase):
    """18.8 案例一：接受率 1.3、批量 40，公式给 0.93，实测慢 15%。"""

    ARGS = BASE | {"tpot_measured": 16.0, "batch_p50": 40, "batch_p95": 64,
                   "acceptance": {"mean_accepted": 1.3, "k": 4,
                                  "draft_cost_ratio": 0.1}}

    def setUp(self):
        self.report = dc.build_report(**self.ARGS)
        self.spec = self.report["spec_decoding"]

    def test_the_formula_predicts_a_seven_percent_slowdown(self):
        self.assertAlmostEqual(self.spec["gain_ratio"], 0.929, places=3)
        self.assertAlmostEqual(1 - 1.3 / 1.4, 0.0714, places=3)

    def test_the_verdict_is_not_applicable(self):
        self.assertEqual(self.spec["verdict"], "不适用")

    def test_it_says_net_loss_not_small_gain(self):
        joined = " ".join(self.spec["reasons"])
        self.assertIn("净亏损而不是收益小", joined)

    def test_the_high_batch_reason_is_reported_separately(self):
        """两个原因在式子里是分开的两项，报告里也分开写。"""
        joined = " ".join(self.spec["reasons"])
        self.assertIn("≈ 31", joined)
        self.assertIn("低于盈亏线", joined)

    def test_the_premise_warning_explains_the_missing_eight_points(self):
        self.assertIsNotNone(self.spec["premise_warning"])
        self.assertIn("前提失效", self.spec["premise_warning"])
        self.assertTrue(any("前提失效" in w for w in self.report["warnings"]))

    def test_it_reports_the_number_rather_than_silently_adjusting_it(self):
        """脚本不改数字，改的是对数字的解读。"""
        self.assertAlmostEqual(self.spec["gain_ratio"], 1.3 / 1.4, places=3)


class TestSection188CaseOneSecondHalf(unittest.TestCase):
    """同一配置换到代码补全：接受率 3.6，收益比 2.57，TPOT 降 61%。"""

    ARGS = BASE | {"batch_p50": 4, "batch_p95": 8,
                   "acceptance": {"mean_accepted": 3.6, "k": 4,
                                  "draft_cost_ratio": 0.1}}

    def test_the_gain_ratio_is_2_57(self):
        spec = dc.build_report(**self.ARGS)["spec_decoding"]
        self.assertAlmostEqual(spec["gain_ratio"], 2.571, places=3)

    def test_that_ratio_is_a_61_percent_tpot_drop(self):
        self.assertAlmostEqual(1 - 1 / 2.571, 0.611, places=3)

    def test_the_verdict_is_applicable(self):
        self.assertEqual(dc.build_report(**self.ARGS)["spec_decoding"]["verdict"],
                         "适用")

    def test_at_low_batch_there_is_no_premise_warning(self):
        self.assertIsNone(
            dc.build_report(**self.ARGS)["spec_decoding"]["premise_warning"])

    def test_the_same_config_gives_opposite_verdicts_in_two_scenarios(self):
        """同样的技术，两个场景的结果完全相反。"""
        low = dc.build_report(**self.ARGS)["spec_decoding"]["verdict"]
        high = dc.build_report(**TestSection188CaseOne.ARGS)["spec_decoding"]["verdict"]
        self.assertNotEqual(low, high)


class TestTheSyntheticAcceptanceSample(unittest.TestCase):
    def test_it_is_labelled_synthetic(self):
        doc = acceptance_doc()
        self.assertTrue(doc["synthetic"])
        self.assertIn("不是真机结果", doc["_note"])

    def test_it_carries_the_k_and_c_that_make_the_denominator_1_4(self):
        doc = acceptance_doc()
        self.assertEqual(doc["k"], 4)
        self.assertEqual(doc["draft_cost_ratio"], 0.1)
        self.assertAlmostEqual(dc.spec_break_even(doc["k"],
                                                  doc["draft_cost_ratio"]),
                               1.4, places=6)

    def test_the_code_completion_scenario_is_above_the_line(self):
        doc = acceptance_doc()
        self.assertEqual(doc["scenario"], "code-completion")
        self.assertGreater(doc["mean_accepted"],
                           dc.spec_break_even(doc["k"], doc["draft_cost_ratio"]))

    def test_the_customer_service_scenario_is_below_the_line(self):
        doc = acceptance_doc()
        chat = next(s for s in doc["other_scenarios"]
                    if s["scenario"] == "customer-service-chat")
        self.assertLess(chat["mean_accepted"],
                        dc.spec_break_even(doc["k"], doc["draft_cost_ratio"]))

    def test_the_sample_spans_both_sides_of_the_line(self):
        """一份样例里同时有盈和亏的场景，这是刻意的。"""
        doc = acceptance_doc()
        line = dc.spec_break_even(doc["k"], doc["draft_cost_ratio"])
        values = [doc["mean_accepted"]] + [s["mean_accepted"]
                                           for s in doc["other_scenarios"]]
        self.assertTrue(any(v > line for v in values))
        self.assertTrue(any(v < line for v in values))

    def test_the_protocol_pins_temperature_to_zero(self):
        self.assertEqual(acceptance_doc()["protocol"]["temperature"], 0)


class TestTryOrderAndShape(unittest.TestCase):
    def test_the_first_step_is_always_the_155_comparison(self):
        report = dc.build_report(**BASE)
        self.assertIn("15.5", report["try_order"][0]["step"])

    def test_a_scheduler_bound_service_puts_cuda_graph_before_spec(self):
        report = dc.build_report(**(BASE | {"tpot_measured": 42.0}))
        steps = [s["step"] for s in report["try_order"]]
        self.assertLess(next(i for i, s in enumerate(steps) if "CUDA Graph" in s),
                        next(i for i, s in enumerate(steps) if "接受率" in s))

    def test_a_bandwidth_bound_service_puts_spec_first(self):
        report = dc.build_report(**BASE)
        steps = [s["step"] for s in report["try_order"]]
        self.assertLess(next(i for i, s in enumerate(steps) if "接受率" in s),
                        next(i for i, s in enumerate(steps) if "CUDA Graph" in s))

    def test_kernel_level_is_always_last_and_a_confirmation(self):
        report = dc.build_report(**BASE)
        self.assertIn("kernel", report["try_order"][-1]["step"])
        self.assertIn("确认项", report["kernel_level"]["verdict"])

    def test_a_scheduler_bound_service_is_told_spec_will_not_help(self):
        report = dc.build_report(**(BASE | {"tpot_measured": 42.0}))
        self.assertEqual(report["spec_decoding"]["verdict"], "待测")
        joined = " ".join(report["spec_decoding"]["reasons"])
        self.assertIn("换不回调度开销", joined)

    def test_the_memory_cost_warning_is_always_present(self):
        """18.8 误区一：不损失质量不等于没有代价。"""
        report = dc.build_report(**BASE)
        self.assertTrue(any("挤压" in w for w in report["warnings"]))

    def test_a_high_p95_with_a_low_p50_asks_for_two_batch_points(self):
        report = dc.build_report(**(BASE | {"batch_p50": 8, "batch_p95": 64}))
        joined = " ".join(report["spec_decoding"]["reasons"])
        self.assertIn("两个批量档位", joined)

    def test_p95_below_p50_is_rejected(self):
        with self.assertRaises(dc.CheckError):
            dc.build_report(**(BASE | {"batch_p50": 32, "batch_p95": 8}))

    def test_report_is_json_serialisable(self):
        json.dumps(dc.build_report(**(BASE | {"captured_buckets": 20,
                                              "draft_params": 0.7e9})),
                   ensure_ascii=False)


class TestCli(unittest.TestCase):
    def test_it_derives_the_floor_from_the_shared_config(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = dc.main(["--config", str(SHARED_CONFIG),
                          "--tpot-measured", "17", "--batch-p50", "8"])
        self.assertEqual(rc, 0)
        self.assertIn("1.214", out.getvalue())

    def test_it_runs_with_the_synthetic_acceptance_sample(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = dc.main(["--config", str(SHARED_CONFIG),
                          "--tpot-measured", "25", "--batch-p50", "8",
                          "--batch-p95", "32", "--draft-params", "0.7e9",
                          "--captured-buckets", "20",
                          "--draft-acceptance", str(ACCEPTANCE)])
        self.assertEqual(rc, 0)
        self.assertIn("2.571", out.getvalue())

    def test_a_measurement_below_the_floor_is_reported_not_crashed(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = dc.main(["--config", str(SHARED_CONFIG),
                          "--tpot-measured", "10", "--batch-p50", "8"])
        self.assertEqual(rc, 0)
        self.assertIn("口径有问题", out.getvalue())


if __name__ == "__main__":
    unittest.main()
