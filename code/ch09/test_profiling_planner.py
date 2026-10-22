#!/usr/bin/env python3
"""Unit tests for Chapter 9 Demo: profiling plan builder."""

from __future__ import annotations

import unittest

from profiling_planner import LAYERS, PlannerError, is_falsifiable, plan, route_symptom


class TestFalsifiability(unittest.TestCase):
    def test_vague_symptom_is_rejected(self):
        self.assertFalse(is_falsifiable("服务慢"))
        self.assertFalse(is_falsifiable("性能差"))
        self.assertFalse(is_falsifiable("   "))

    def test_symptom_with_a_number_is_workable(self):
        self.assertTrue(is_falsifiable("TTFT P99 从 400 ms 升到 6 s"))

    def test_symptom_naming_a_segment_is_workable(self):
        self.assertTrue(is_falsifiable("TTFT 高但 Queue 正常"))

    def test_planner_warns_on_a_vague_symptom(self):
        result = plan("服务慢", ["request_metrics"])
        self.assertTrue(any("目标不清" in w for w in result["warnings"]))


class TestLayerSkipping(unittest.TestCase):
    def test_warns_when_asking_for_device_without_request_evidence(self):
        result = plan("某个 kernel 耗时是同类的三倍", [], want_layer="device")
        self.assertTrue(any("跳级" in w for w in result["warnings"]))
        self.assertEqual(result["next_layer"], "request")

    def test_no_skip_warning_once_request_evidence_exists(self):
        result = plan("某个 kernel 耗时是同类的三倍", ["request_metrics",
                                                     "cpu_profile",
                                                     "engine_trace"],
                      want_layer="device")
        self.assertFalse(any("跳级" in w for w in result["warnings"]))
        self.assertEqual(result["next_layer"], "device")

    def test_next_layer_is_the_shallowest_uncovered_one(self):
        result = plan("TTFT 高但 Queue 正常", ["request_metrics"])
        self.assertEqual(result["next_layer"], "process")


class TestRouting(unittest.TestCase):
    def test_queue_symptom_routes_to_request_level(self):
        self.assertEqual(route_symptom("Queue 时间占 TTFT 的 88%"), "request")

    def test_batch_symptom_routes_to_framework(self):
        self.assertEqual(route_symptom("batch 一直只有两条请求"), "framework")

    def test_kernel_symptom_routes_to_device(self):
        self.assertEqual(route_symptom("某个 kernel 耗时是同类的三倍"), "device")


class TestPlanShape(unittest.TestCase):
    def test_seven_blocks_present(self):
        result = plan("TTFT 高但 Queue 正常", ["request_metrics"])
        for block in ("symptom", "already_known", "next_layer", "rationale",
                      "expected_cost", "window", "must_record"):
            self.assertIn(block, result)

    def test_cost_block_treats_overhead_as_bias_not_noise(self):
        cheap = plan("TTFT 高但 Queue 正常", ["request_metrics"])["expected_cost"]
        self.assertEqual(cheap["comparable_to_baseline"], "same_conditions_only")
        self.assertIn("同样的采样", cheap["comparison_rule"])
        expensive = plan("某个 kernel 慢",
                         ["request_metrics", "cpu_profile", "engine_trace"],
                         want_layer="device")["expected_cost"]
        self.assertEqual(expensive["comparable_to_baseline"], "never")
        self.assertIn("偏差", expensive["note"])
        self.assertIn("不能拿它和第 7.3 节的可识别线比大小", expensive["note"])

    def test_must_record_covers_window_and_overhead(self):
        must = plan("TTFT 高但 Queue 正常", ["request_metrics"])["must_record"]
        joined = "".join(must)
        for item in ("起止时刻", "请求数", "采样率", "开销"):
            self.assertIn(item, joined)

    def test_unknown_evidence_is_rejected(self):
        with self.assertRaises(PlannerError):
            plan("TTFT 高", ["nsight_dump"])

    def test_layers_are_ordered_cheap_to_expensive(self):
        self.assertEqual(LAYERS, ("request", "process", "framework", "device"))


if __name__ == "__main__":
    unittest.main()
