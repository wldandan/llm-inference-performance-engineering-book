#!/usr/bin/env python3
"""Tests for code/ch29/release_check.py.

The one that matters most is TestSeamSample: a release whose nine checklist
items are all green must still be blocked, because one seam does not line up.
That is 29.8 案例一, and it is the whole argument of 29.1.
"""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

import release_check as rc

HERE = Path(__file__).resolve().parent
EV = HERE.parent.parent / "content" / "ch29" / "evidence"


def load(name):
    return json.loads((EV / name).read_text(encoding="utf-8"))


class TestTheLists(unittest.TestCase):
    def test_nine_items_in_the_order_29_2_gives(self):
        self.assertEqual(len(rc.CHECKLIST), 9)
        self.assertEqual([k for k, _ in rc.CHECKLIST][:3],
                         ["slo", "baseline", "capacity"])
        self.assertEqual([k for k, _ in rc.CHECKLIST][-1], "owner")

    def test_the_two_that_get_skipped(self):
        """29.2：最容易被跳过的是第五和第八项。"""
        keys = [k for k, _ in rc.CHECKLIST]
        self.assertEqual(keys[4], "monitoring")
        self.assertEqual(keys[7], "rollback")
        self.assertEqual(set(rc.OFTEN_SKIPPED), {"monitoring", "rollback"})

    def test_five_traffic_policy_items_from_ch21(self):
        self.assertEqual(len(rc.TRAFFIC_POLICY_ITEMS), 5)
        self.assertIn("admission", rc.TRAFFIC_POLICY_ITEMS)
        self.assertIn("backpressure", rc.TRAFFIC_POLICY_ITEMS)

    def test_the_required_metrics_include_the_cache_hit_rate(self):
        """命中率是必需项，不是「容易漏」：29.4 的 2 小时窗口和 29.3 的缓存
        恢复期都要用它（Part 6 审阅 P1-22）。"""
        self.assertEqual(len(rc.REQUIRED_METRICS), 11)
        self.assertIn("itl_distribution", rc.REQUIRED_METRICS)
        self.assertIn("prefix_cache_hit_rate", rc.CAUSE_METRICS)

    def test_the_user_facing_outcomes_come_first(self):
        """规律三：先看有用的产出，再看调度器的原因。"""
        self.assertEqual(rc.REQUIRED_METRICS[:len(rc.RESULT_METRICS)],
                         rc.RESULT_METRICS)
        for m in ("ttft_p95", "error_rate", "slo_attainment"):
            self.assertIn(m, rc.RESULT_METRICS)

    def test_rejection_rate_is_watched_next_to_slo_attainment(self):
        """29.2 的 SLO 口径不含被拒绝的请求，拒绝率不单列就能靠拒绝刷达成率。"""
        self.assertIn("rejection_rate", rc.RESULT_METRICS)

    def test_four_observation_windows(self):
        self.assertEqual([w for w, _, _ in rc.OBSERVATION_WINDOW],
                         ["10m", "2h", "24h", "7d"])

    def test_only_the_24h_window_can_verify_capacity(self):
        """29.4：容量核算要跨越一个完整的日内波峰才验证得了。"""
        rows = {w["window"]: w["why"] for w in rc.observation_window()}
        self.assertIn("容量核算", rows["24h"])
        for w in ("10m", "2h", "7d"):
            self.assertNotIn("容量核算", rows[w])

    def test_five_seams(self):
        self.assertEqual(len(rc.CROSS_CHECKS), 5)
        self.assertEqual(rc.CROSS_CHECKS[0][0], "context_length")


class TestMonitoring(unittest.TestCase):
    def test_a_full_list_passes(self):
        r = rc.check_monitoring({"available_metrics": list(rc.REQUIRED_METRICS)})
        self.assertTrue(r["ok"])
        self.assertEqual(r["missing"], [])

    def test_nothing_at_all_is_not_a_yes(self):
        """29.8 案例三：监控就绪不能是一个是非题。"""
        r = rc.check_monitoring(None)
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing"], list(rc.REQUIRED_METRICS))

    def test_the_one_metric_case_three_was_missing(self):
        metrics = [m for m in rc.REQUIRED_METRICS if m != "itl_distribution"]
        r = rc.check_monitoring({"available_metrics": metrics})
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing"], ["itl_distribution"])
        self.assertIn("案例三", r["detail"])


class TestTrafficPolicy(unittest.TestCase):
    def full(self, **over):
        cfg = {k: {"configured": True} for k in rc.TRAFFIC_POLICY_ITEMS}
        cfg["admission"] = {"enabled": True}
        cfg.update(over)
        return cfg

    def test_five_configured_passes(self):
        self.assertTrue(rc.check_traffic_policy(self.full())["ok"])

    def test_a_missing_one_is_named(self):
        cfg = self.full()
        del cfg["retry"]
        r = rc.check_traffic_policy(cfg)
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing"], ["retry"])

    def test_admission_present_but_off_is_refused(self):
        """21 章：准入是突发流量唯一的防线，配了但没开等于没配。"""
        r = rc.check_traffic_policy(self.full(admission={"enabled": False}))
        self.assertFalse(r["ok"])
        self.assertIn("准入没开启", r["detail"])

    def test_nothing_provided(self):
        r = rc.check_traffic_policy(None)
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing"], list(rc.TRAFFIC_POLICY_ITEMS))


class TestRollback(unittest.TestCase):
    def plan(self, **over):
        p = {"trigger_conditions": ["P95 超阈值"],
             "steps": ["切回旧版本", "等在途请求跑完"],
             "rehearsed_duration_min": 12,
             "irreversible": ["已写入的日志"], "cache_warmup_min": 20}
        p.update(over)
        return p

    def test_a_complete_plan_passes(self):
        self.assertTrue(rc.check_rollback(self.plan())["ok"])

    def test_a_plan_without_a_measured_duration_is_refused(self):
        """29.3：演练的产出就是一个数，没有这个数等于没演练。"""
        r = rc.check_rollback(self.plan(rehearsed_duration_min=None))
        self.assertFalse(r["ok"])
        self.assertTrue(any("演练" in p for p in r["problems"]))

    def test_a_plan_without_a_cache_warmup_period_is_refused(self):
        """29.8 案例二：回滚后旧实例重启，缓存清空，二十分钟里更慢。"""
        r = rc.check_rollback(self.plan(cache_warmup_min=None))
        self.assertFalse(r["ok"])
        self.assertIn("案例二", r["detail"])

    def test_irreversible_must_be_listed_even_if_empty(self):
        self.assertTrue(rc.check_rollback(self.plan(irreversible=[]))["ok"])
        self.assertFalse(rc.check_rollback(self.plan(irreversible=None))["ok"])

    def test_nothing_provided(self):
        self.assertFalse(rc.check_rollback(None)["ok"])


class TestContextLengthConsequence(unittest.TestCase):
    """接缝对不上要能换算成一个数，否则“接缝”只是一句口号。"""

    def test_the_case_one_numbers(self):
        r = rc.context_length_consequence(2600, 3400, 220, 8)
        self.assertEqual(r["modeled_total_tokens"], 2820)
        self.assertEqual(r["actual_total_tokens"], 3620)
        self.assertAlmostEqual(r["concurrency_ratio"], 0.779, places=3)

    def test_eight_cards_in_the_model_are_eleven_in_reality(self):
        r = rc.context_length_consequence(2600, 3400, 220, 8, "memory")
        self.assertEqual(r["instances_needed"], 11)
        self.assertIn("案例一", r["reading"])

    def test_unknown_binding_still_converts_but_asks_for_it(self):
        r = rc.context_length_consequence(2600, 3400, 220, 8)
        self.assertEqual(r["instances_needed"], 11)
        self.assertIn("显存先满", r["reading"])

    def test_throughput_binding_does_not_convert_to_cards(self):
        """第 26 章的主例是吞吐先满：显存多出来的卡不是约束，要重跑容量模型。"""
        r = rc.context_length_consequence(2600, 3400, 220, 36, "throughput")
        self.assertNotIn("instances_needed", r)
        self.assertIn("第 26 章", r["reading"])
        self.assertIn("Prefill", r["reading"])

    def test_the_ratio_is_inverse_to_total_length(self):
        """第 16 章那张表：KV 预算固定，并发反比于平均总长度。"""
        r = rc.context_length_consequence(2600, 5200, 0, 10)
        self.assertAlmostEqual(r["concurrency_ratio"], 0.5)
        self.assertEqual(r["instances_needed"], 20)

    def test_output_tokens_soften_the_ratio(self):
        with_out = rc.context_length_consequence(2600, 3400, 220)
        without = rc.context_length_consequence(2600, 3400, 0)
        self.assertGreater(with_out["concurrency_ratio"],
                           without["concurrency_ratio"])

    def test_no_instances_still_reports_the_ratio(self):
        r = rc.context_length_consequence(2600, 3400)
        self.assertNotIn("instances_needed", r)
        self.assertIn("并发上限", r["reading"])

    def test_zero_rejected(self):
        with self.assertRaises(rc.ReviewError):
            rc.context_length_consequence(0, 3400)


class TestPassSample(unittest.TestCase):
    def setUp(self):
        self.r = rc.review(load("release-docs-pass.json"))

    def test_it_passes(self):
        self.assertEqual(self.r["verdict"], "通过")
        self.assertEqual(self.r["checklist"]["missing"], [])

    def test_all_five_seams_line_up(self):
        self.assertEqual(self.r["cross_check"]["mismatched"], [])
        self.assertEqual(self.r["cross_check"]["unknown"], [])

    def test_every_seam_was_actually_checked(self):
        for row in self.r["cross_check"]["rows"]:
            with self.subTest(seam=row["key"]):
                self.assertEqual(row["status"], "一致")
                self.assertIsNotNone(row["left_value"])
                self.assertIsNotNone(row["right_value"])


class TestSeamSample(unittest.TestCase):
    """本文件最重要的一组：九项全绿，仍然不通过。"""

    def setUp(self):
        self.r = rc.review(load("release-docs-seam.json"))

    def test_all_nine_items_are_green(self):
        self.assertEqual(self.r["checklist"]["missing"], [])

    def test_it_is_blocked_anyway(self):
        self.assertEqual(self.r["verdict"], "不通过")

    def test_exactly_one_seam_is_the_reason(self):
        self.assertEqual(self.r["cross_check"]["mismatched"], ["context_length"])
        self.assertIn("接缝对不上", self.r["reason"])
        self.assertNotIn("清单缺项", self.r["reason"])

    def test_the_mismatch_carries_its_consequence(self):
        row = next(r for r in self.r["cross_check"]["rows"]
                   if r["key"] == "context_length")
        self.assertEqual(row["consequence"]["instances_needed"], 11)

    def test_the_capacity_model_says_memory_binds(self):
        self.assertEqual(load("release-docs-seam.json")["capacity"]
                         ["binding_constraint"], "memory")

    def test_only_the_runtime_differs_from_the_passing_sample(self):
        """两份样例只差新版本 prompt 模板那两个数，其余完全相同。"""
        a = load("release-docs-pass.json")
        b = load("release-docs-seam.json")
        for key in a:
            if key in ("_note", "release", "runtime", "gate", "change"):
                continue
            with self.subTest(key=key):
                self.assertEqual(a[key], b[key])
        self.assertEqual(a["runtime"]["prompt_template_tokens"], 12000)
        self.assertEqual(b["runtime"]["prompt_template_tokens"], 16000)
        # 这个长度上 KV 放得下的条数低于批量，显存确实先满，按总长度之比
        # 换算卡数才成立（Part 6 审阅 P1-24）。
        self.assertEqual(b["capacity"]["binding_constraint"], "memory")


class TestGapsSample(unittest.TestCase):
    def setUp(self):
        self.r = rc.review(load("release-docs-gaps.json"))

    def test_exactly_the_two_often_skipped_items_are_missing(self):
        self.assertEqual(self.r["checklist"]["missing"],
                         ["monitoring", "rollback"])
        self.assertEqual(self.r["checklist"]["skipped_among_the_easy_ones"],
                         ["monitoring", "rollback"])

    def test_the_seams_are_fine_here(self):
        self.assertEqual(self.r["cross_check"]["mismatched"], [])

    def test_the_reason_names_the_checklist_not_the_seams(self):
        self.assertIn("清单缺项", self.r["reason"])
        self.assertNotIn("接缝对不上", self.r["reason"])

    def test_it_is_blocked(self):
        self.assertEqual(self.r["verdict"], "不通过")


class TestInstancesSeam(unittest.TestCase):
    """实例数这处接缝是两个不等式，不是相等关系。"""

    def row(self, docs):
        r = rc.review(docs)
        return next(x for x in r["cross_check"]["rows"] if x["key"] == "instances")

    def test_peak_and_floor_inside_the_range_is_consistent(self):
        row = self.row(load("release-docs-pass.json"))
        self.assertEqual(row["status"], "一致")
        self.assertEqual(row["left_value"], (8, 3))
        self.assertEqual(row["right_value"], (24, 3))

    def test_min_equal_to_peak_is_not_required(self):
        """要求最小实例数等于峰值卡数，等于说波谷永远缩不下来。"""
        docs = load("release-docs-pass.json")
        docs["autoscale"]["min_instances"] = 5
        self.assertEqual(self.row(docs)["status"], "一致")

    def test_max_below_peak_is_named(self):
        docs = load("release-docs-pass.json")
        docs["autoscale"]["max_instances"] = 6
        row = self.row(docs)
        self.assertEqual(row["status"], "不一致")
        self.assertIn("最大实例数 6 低于峰值卡数 8", row["note"])

    def test_min_below_floor_is_named(self):
        docs = load("release-docs-pass.json")
        docs["autoscale"]["min_instances"] = 1
        row = self.row(docs)
        self.assertEqual(row["status"], "不一致")
        self.assertIn("最小实例数 1 低于下限卡数 3", row["note"])

    def test_a_missing_floor_cannot_be_checked(self):
        docs = load("release-docs-pass.json")
        docs["capacity"].pop("floor_instances")
        self.assertEqual(self.row(docs)["status"], "无法核对")


class TestConditionalPass(unittest.TestCase):
    def test_a_seam_that_cannot_be_checked_is_not_a_pass(self):
        docs = load("release-docs-pass.json")
        docs["runtime"].pop("prompt_template_tokens")
        r = rc.review(docs)
        self.assertEqual(r["verdict"], "有条件通过")
        self.assertEqual(r["cross_check"]["unknown"], ["context_length"])

    def test_a_waiver_on_record_keeps_the_gate_item_green(self):
        docs = load("release-docs-pass.json")
        docs["gate"]["verdict"] = "fail"
        docs["gate"]["waiver"] = "PERF-1182，已知回退，产品同意"
        r = rc.review(docs)
        self.assertNotIn("gate", r["checklist"]["missing"])
        self.assertIn("豁免", r["checklist"]["items"]["gate"]["detail"])

    def test_a_failed_gate_without_a_waiver_blocks(self):
        docs = load("release-docs-pass.json")
        docs["gate"]["verdict"] = "fail"
        r = rc.review(docs)
        self.assertIn("gate", r["checklist"]["missing"])

    def test_an_unknown_cold_start_blocks(self):
        docs = load("release-docs-pass.json")
        docs.pop("cold_start_s")
        r = rc.review(docs)
        self.assertIn("cold_start", r["checklist"]["missing"])
        self.assertIn("27.5", r["checklist"]["items"]["cold_start"]["detail"])

    def test_empty_material_is_refused(self):
        with self.assertRaises(rc.ReviewError):
            rc.review({})


class TestPacket(unittest.TestCase):
    def test_it_has_the_five_blocks_29_6_lists(self):
        docs = load("release-docs-pass.json")
        text = rc.packet(docs, rc.review(docs))
        for head in ("九项清单", "五处接缝", "观察窗口", "回滚", "责任人"):
            with self.subTest(head=head):
                self.assertIn(head, text)

    def test_missing_items_are_marked_not_left_blank(self):
        docs = load("release-docs-gaps.json")
        text = rc.packet(docs, rc.review(docs))
        self.assertIn("**缺项**", text)
        self.assertIn("未演练", text)

    def test_the_consequence_shows_up_in_the_packet(self):
        docs = load("release-docs-seam.json")
        text = rc.packet(docs, rc.review(docs))
        self.assertIn("11 张", text)


class TestSamples(unittest.TestCase):
    def test_all_declared_synthetic(self):
        for name in ("release-docs-pass.json", "release-docs-seam.json",
                     "release-docs-gaps.json"):
            with self.subTest(file=name):
                self.assertIn("合成设定", load(name)["_note"])


class TestCli(unittest.TestCase):
    def path(self, name):
        return str(EV / name)

    def test_pass_exits_zero(self):
        self.assertEqual(
            rc.main(["check", "--docs", self.path("release-docs-pass.json")]), 0)

    def test_seam_exits_one(self):
        self.assertEqual(
            rc.main(["check", "--docs", self.path("release-docs-seam.json")]), 1)

    def test_gaps_exits_one(self):
        self.assertEqual(
            rc.main(["check", "--docs", self.path("release-docs-gaps.json")]), 1)

    def test_packet_exits_zero_on_a_passing_release(self):
        self.assertEqual(
            rc.main(["packet", "--docs", self.path("release-docs-pass.json")]), 0)

    def test_window_exits_zero(self):
        self.assertEqual(rc.main(["window"]), 0)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(rc.main([]), 2)


if __name__ == "__main__":
    unittest.main()
