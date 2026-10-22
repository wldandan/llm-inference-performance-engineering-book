#!/usr/bin/env python3
"""Unit tests for Chapter 7 Demo: reproducible Baseline runner.

No GPU and no server: a fake transport stands in for vLLM so the report
contract and the load generator can be tested on their own.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ch06"))
from workload_builder import build_workload  # noqa: E402

from run_baseline import (  # noqa: E402
    BaselineError,
    build_report,
    check_environment,
    coefficient_of_variation,
    detectable_difference,
    line_factor,
    nearest_rank_percentile,
    plan_requests,
    run_once,
)


class FakeTransport:
    """Returns a scripted TTFT sequence and records what it was sent."""

    def __init__(self, ttfts: list[float], hold_s: float = 0.0):
        self.ttfts = list(ttfts)
        self.hold_s = hold_s
        self.calls = 0
        self.prompts: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self._lock = threading.Lock()

    def send(self, prompt: str, max_tokens: int) -> dict:
        with self._lock:
            ttft = self.ttfts[self.calls % len(self.ttfts)]
            self.calls += 1
            self.prompts.append(prompt)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        if self.hold_s:
            time.sleep(self.hold_s)
        with self._lock:
            self.in_flight -= 1
        return {"ok": True, "ttft_ms": ttft, "e2e_ms": ttft * 4}


def workload(arrival: str = "poisson", rate: float | None = 2000.0,
             concurrency: int | None = None) -> dict:
    return build_workload(
        profile="chat", arrival=arrival, rate=rate, concurrency=concurrency,
        duration_s=60.0, seed=11, slo_metric="ttft",
        slo_quantile="p95", slo_threshold_ms=2000.0,
    )


def environment(**overrides) -> dict:
    env = {
        "python_version": "3.11.9",
        "vllm_version": "0.9.1",
        "model_name": "Qwen/Qwen2.5-0.5B-Instruct",
        "model_revision": "a1b2c3d",
        "gpu_name": "NVIDIA GB10",
        "driver_version": "550.54.15",
        "launch_command": "vllm serve ... --max-num-seqs 64",
    }
    env.update(overrides)
    return env


class TestStatistics(unittest.TestCase):
    def test_nearest_rank_matches_chapter_5(self):
        self.assertEqual(nearest_rank_percentile([120, 190, 300], 50), 190)
        self.assertEqual(nearest_rank_percentile([120, 190, 300], 95), 300)

    def test_line_factor_matches_the_table_in_7_3(self):
        self.assertAlmostEqual(line_factor(3), 2.27, places=2)
        self.assertAlmostEqual(line_factor(5), 1.46, places=2)
        self.assertAlmostEqual(line_factor(12), 0.85, places=2)

    def test_cv_and_line_match_the_worked_example_in_7_3(self):
        runs = [210.0, 235.0, 218.0]
        self.assertAlmostEqual(coefficient_of_variation(runs), 0.0578, places=4)
        self.assertAlmostEqual(detectable_difference(runs), 0.131, places=3)

    def test_more_runs_lower_the_line(self):
        runs = [210.0, 235.0, 218.0]
        three = detectable_difference(runs, runs_per_group=3)
        twelve = detectable_difference(runs, runs_per_group=12)
        self.assertLess(twelve, three / 2)

    def test_case_one_numbers_are_not_distinguishable(self):
        """7.8 case 1: a 7.6% mean improvement under a 14% line."""
        baseline = [210.0, 238.0, 225.0]
        optimized = [180.0, 228.0, 214.0]
        line = detectable_difference(baseline)
        mean_b = sum(baseline) / 3
        mean_o = sum(optimized) / 3
        improvement = (mean_b - mean_o) / mean_b
        self.assertAlmostEqual(line, 0.142, places=3)
        self.assertAlmostEqual(improvement, 0.0758, places=3)
        self.assertLess(improvement, line)

    def test_cv_needs_more_than_one_run(self):
        with self.assertRaises(BaselineError):
            coefficient_of_variation([210.0])


class TestEnvironment(unittest.TestCase):
    def test_complete_fingerprint_passes(self):
        check_environment(environment())

    def test_missing_model_revision_is_refused(self):
        with self.assertRaises(BaselineError) as ctx:
            check_environment(environment(model_revision=""))
        self.assertIn("model_revision", str(ctx.exception))

    def test_missing_launch_command_is_refused(self):
        with self.assertRaises(BaselineError) as ctx:
            check_environment(environment(launch_command="   "))
        self.assertIn("launch_command", str(ctx.exception))


class TestLoadGenerator(unittest.TestCase):
    def test_poisson_plan_uses_exponential_gaps_and_is_reproducible(self):
        doc = workload(rate=10.0)
        plan_a = plan_requests(doc, 400)
        plan_b = plan_requests(doc, 400)
        self.assertEqual(plan_a, plan_b)
        offsets = [p["planned_offset_s"] for p in plan_a]
        self.assertEqual(offsets, sorted(offsets))
        gaps = [b - a for a, b in zip(offsets, offsets[1:])]
        mean_gap = sum(gaps) / len(gaps)
        self.assertAlmostEqual(mean_gap, 0.1, delta=0.02)
        # exponential gaps: the standard deviation is close to the mean
        sd = (sum((g - mean_gap) ** 2 for g in gaps) / (len(gaps) - 1)) ** 0.5
        self.assertAlmostEqual(sd / mean_gap, 1.0, delta=0.2)

    def test_constant_plan_is_evenly_spaced(self):
        offsets = [p["planned_offset_s"] for p in plan_requests(workload("constant", 4.0), 5)]
        self.assertEqual(offsets, [0.0, 0.25, 0.5, 0.75, 1.0])

    def test_open_loop_sends_concurrently(self):
        transport = FakeTransport([100.0], hold_s=0.05)
        run_once(workload(rate=2000.0), transport, run_index=1, request_count=40)
        self.assertGreater(transport.max_in_flight, 1)

    def test_closed_loop_holds_the_configured_concurrency(self):
        transport = FakeTransport([100.0], hold_s=0.02)
        doc = workload("closed", rate=None, concurrency=4)
        result = run_once(doc, transport, run_index=1, request_count=20)
        self.assertEqual(result["requests"], 20)
        self.assertLessEqual(transport.max_in_flight, 4)
        self.assertGreater(transport.max_in_flight, 1)

    def test_latency_counts_from_the_planned_send_time(self):
        """A client that falls behind schedule must not hide the delay (6.3)."""
        transport = FakeTransport([100.0], hold_s=0.05)
        result = run_once(workload(rate=2000.0), transport, run_index=1,
                          request_count=20, max_in_flight=1)
        lags = [r["send_lag_ms"] for r in result["raw"]]
        self.assertGreater(max(lags), 100.0)
        last = result["raw"][-1]
        self.assertAlmostEqual(last["ttft_ms"], 100.0 + last["send_lag_ms"], places=6)

    def test_prompts_are_prefix_free_within_and_across_runs(self):
        transport = FakeTransport([100.0])
        doc = workload()
        for i in range(3):
            run_once(doc, transport, run_index=i + 1, request_count=30)
        prompts = transport.prompts
        self.assertEqual(len(set(prompts)), len(prompts))
        for a in prompts:
            for b in prompts:
                if a is not b:
                    self.assertFalse(b.startswith(a))
        first_words = {p.split()[0] for p in prompts}
        self.assertEqual(len(first_words), len(prompts))

    def test_every_run_replays_the_same_lengths(self):
        transport = FakeTransport([100.0])
        doc = workload()
        runs = [run_once(doc, transport, run_index=i + 1, request_count=25) for i in range(3)]
        shapes = [[(r["prompt_tokens_target"], r["max_tokens"]) for r in run["raw"]] for run in runs]
        self.assertEqual(shapes[0], shapes[1])
        self.assertEqual(shapes[1], shapes[2])

    def test_burst_is_refused_rather_than_faked(self):
        doc = workload("burst", rate=10.0)
        with self.assertRaises(BaselineError):
            plan_requests(doc, 10)


class TestReport(unittest.TestCase):
    def _runs(self, n=3, request_count=20):
        doc = workload()
        transport = FakeTransport([200.0, 210.0, 190.0, 230.0, 205.0])
        return doc, [
            run_once(doc, transport, run_index=i + 1, request_count=request_count)
            for i in range(n)
        ]

    def test_four_blocks_present(self):
        doc, runs = self._runs()
        report = build_report(doc, environment(), runs, warmup_requests=20, prefix_cache="off")
        self.assertEqual(
            sorted(report), ["environment", "protocol", "results", "workload"]
        )

    def test_protocol_records_load_generation_and_conventions(self):
        doc, runs = self._runs()
        p = build_report(doc, environment(), runs, warmup_requests=20,
                         prefix_cache="off")["protocol"]
        self.assertTrue(p["warmup_excluded"])
        self.assertEqual(p["warmup_requests"], 20)
        self.assertEqual(p["requests_per_run"], 20)
        self.assertEqual(p["prefix_cache"], "off")
        self.assertEqual(p["latency_origin"], "planned send time (open loop)")
        self.assertEqual(p["percentile_algorithm"], "nearest-rank")
        self.assertEqual(p["stdev_convention"], "sample (n-1)")
        self.assertEqual(p["in_flight_at_end"], "drained")

    def test_prefix_cache_state_is_required(self):
        doc, runs = self._runs()
        with self.assertRaises(BaselineError):
            build_report(doc, environment(), runs, warmup_requests=20, prefix_cache="")

    def test_raw_per_request_records_are_kept(self):
        doc, runs = self._runs()
        report = build_report(doc, environment(), runs, warmup_requests=20, prefix_cache="off")
        self.assertEqual(len(report["results"]["per_run"][0]["raw"]), 20)

    def test_small_runs_warn_about_the_tail_sample(self):
        doc, runs = self._runs(request_count=20)
        report = build_report(doc, environment(), runs, warmup_requests=20, prefix_cache="off")
        self.assertTrue(report["results"]["warnings"])
        doc, runs = self._runs(request_count=200)
        report = build_report(doc, environment(), runs, warmup_requests=20, prefix_cache="off")
        self.assertEqual(report["results"]["warnings"], [])

    def test_refuses_fewer_than_three_runs(self):
        doc, runs = self._runs(n=2)
        with self.assertRaises(BaselineError) as ctx:
            build_report(doc, environment(), runs, warmup_requests=20, prefix_cache="off")
        self.assertIn("at least three runs", str(ctx.exception))

    def test_refuses_incomplete_environment(self):
        doc, runs = self._runs()
        with self.assertRaises(BaselineError):
            build_report(doc, environment(vllm_version=""), runs,
                         warmup_requests=20, prefix_cache="off")

    def test_reports_the_detectable_difference_and_its_rule(self):
        doc, runs = self._runs()
        stats = build_report(doc, environment(), runs, warmup_requests=20,
                             prefix_cache="off")["results"]["ttft_p95_ms"]
        self.assertIn("detectable_difference", stats)
        self.assertGreaterEqual(stats["detectable_difference"], 0)
        self.assertIn("2.27 x CV", stats["detectable_difference_rule"])


if __name__ == "__main__":
    unittest.main()
