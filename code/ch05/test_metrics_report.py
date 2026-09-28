import importlib.util
import math
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("metrics_report.py")


def load_metrics_report():
    if not MODULE_PATH.exists():
        raise AssertionError("code/ch05/metrics_report.py must exist")
    spec = importlib.util.spec_from_file_location("chapter05_metrics_report", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def record(
    request_id,
    start_ms,
    token_times_ms,
    end_ms,
    prompt_tokens=10,
    output_tokens=None,
    success=True,
    quality_pass=True,
    quality_metric="task_score",
    quality_score=None,
    quality_threshold=0.5,
    evaluator_name="unit-test-rule",
    evaluator_version="1",
    cost_usd=0.01,
):
    if output_tokens is None:
        output_tokens = len(token_times_ms)
    if quality_score is None:
        quality_score = 1.0 if quality_pass else 0.0
    return {
        "request_id": request_id,
        "start_ms": start_ms,
        "token_times_ms": token_times_ms,
        "end_ms": end_ms,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "success": success,
        "quality_pass": quality_pass,
        "quality_metric": quality_metric,
        "quality_score": quality_score,
        "quality_threshold": quality_threshold,
        "evaluator_name": evaluator_name,
        "evaluator_version": evaluator_version,
        "cost_usd": cost_usd,
    }


class MetricsReportTests(unittest.TestCase):
    def setUp(self):
        self.metrics = load_metrics_report()

    def test_request_metrics_compute_ttft_e2e_and_itl(self):
        metrics = self.metrics.request_metrics(record("a", 100, [160, 200, 250], 270))
        self.assertEqual(metrics["ttft_ms"], 60)
        self.assertEqual(metrics["e2e_ms"], 170)
        self.assertEqual(metrics["itls_ms"], [40, 50])

    def test_tpot_excludes_first_token_interval(self):
        metrics = self.metrics.request_metrics(record("a", 0, [100, 140, 200], 210))
        self.assertEqual(metrics["tpot_ms"], 50)

    def test_throughput_uses_shared_wall_clock_window(self):
        records = [
            record("a", 0, [100, 150], 200),
            record("b", 50, [120, 180, 240], 250),
        ]
        report = self.metrics.build_report(records, ttft_slo_ms=200, e2e_slo_ms=400)
        self.assertTrue(
            math.isclose(report["throughput"]["successful_output_tokens_per_second"], 20)
        )
        self.assertTrue(
            math.isclose(report["throughput"]["successful_requests_per_second"], 8)
        )

    def test_goodput_requires_success_and_both_slos(self):
        records = [
            record("good", 0, [100, 140], 160),
            record("slow", 0, [250, 290], 320),
            record("failed", 0, [], 100, output_tokens=0, success=False),
            record("bad-quality", 0, [100, 140], 160, quality_pass=False),
        ]
        report = self.metrics.build_report(records, ttft_slo_ms=200, e2e_slo_ms=300)
        self.assertEqual(report["throughput"]["good_requests"], 1)
        self.assertTrue(
            math.isclose(report["throughput"]["goodput_requests_per_second"], 3.125)
        )

    def test_throughput_names_raw_successful_and_observed_rates(self):
        records = [
            record("ok", 0, [100, 150], 200),
            record("partial", 50, [120], 250, output_tokens=1, success=False),
        ]
        report = self.metrics.build_report(records, ttft_slo_ms=200, e2e_slo_ms=300)

        throughput = report["throughput"]
        self.assertTrue(
            math.isclose(
                throughput["submitted_requests_per_second_over_run_window"], 8.0
            )
        )
        self.assertTrue(math.isclose(throughput["successful_requests_per_second"], 4.0))
        self.assertTrue(math.isclose(throughput["successful_output_tokens_per_second"], 8.0))
        self.assertTrue(math.isclose(throughput["observed_output_tokens_per_second"], 12.0))
        self.assertNotIn("requests_per_second", throughput)
        self.assertNotIn("arrival_requests_per_second", throughput)
        self.assertNotIn("output_tokens_per_second", throughput)

    def test_quality_contract_is_auditable_and_consistent(self):
        report = self.metrics.build_report(
            [record("a", 0, [100], 120)],
            ttft_slo_ms=200,
            e2e_slo_ms=300,
        )
        self.assertEqual(
            report["measurement_contract"]["quality"],
            {
                "metric": "task_score",
                "threshold": 0.5,
                "evaluator_name": "unit-test-rule",
                "evaluator_version": "1",
            },
        )

        with self.assertRaisesRegex(ValueError, "quality_pass"):
            self.metrics.request_metrics(
                record("bad", 0, [100], 120, quality_pass=True, quality_score=0.1)
            )

    def _default_budget(self, **overrides):
        kwargs = dict(
            ttft_slo_ms=250,
            e2e_slo_ms=800,
            client_to_gateway_ms=20,
            admission_ms=20,
            queue_ms=60,
            scheduled_to_first_token_ms=130,
            decode_streaming_ms=500,
            response_tail_ms=40,
        )
        kwargs.update(overrides)
        return self.metrics.build_latency_budget(**kwargs)

    def test_latency_budget_splits_ttft_and_post_first_token_time(self):
        budget = self._default_budget()

        self.assertEqual(budget["ttft_allocated_ms"], 230)
        self.assertEqual(budget["e2e_allocated_ms"], 770)
        self.assertEqual(budget["unallocated_total_ms"], 30)
        self.assertEqual(budget["unallocated_before_first_token_ms"], 20)
        self.assertEqual(budget["unallocated_after_first_token_ms"], 10)

    def test_allocated_stages_plus_total_slack_equal_the_e2e_slo(self):
        budget = self._default_budget()

        self.assertEqual(
            sum(budget["components_ms"].values()) + budget["unallocated_total_ms"],
            budget["e2e_slo_ms"],
        )

    def test_the_two_slack_numbers_are_not_additive(self):
        budget = self._default_budget()
        rows_a_reader_might_add = (
            sum(budget["components_ms"].values())
            + budget["unallocated_before_first_token_ms"]
            + budget["unallocated_after_first_token_ms"]
        )

        self.assertEqual(rows_a_reader_might_add, budget["e2e_slo_ms"])
        self.assertEqual(
            budget["unallocated_before_first_token_ms"]
            + budget["unallocated_after_first_token_ms"],
            budget["unallocated_total_ms"],
        )
        self.assertNotIn("ttft_unallocated_ms", budget)
        self.assertNotIn("e2e_unallocated_ms", budget)

    def test_budget_names_the_segment_no_metric_covers(self):
        budget = self._default_budget()
        segments = budget["unmeasured_segments"]

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["segment"], "first_token -> first_chunk_received")
        self.assertEqual(segments[0]["belongs_to"], "ttft")

    def test_latency_budget_rejects_over_allocation(self):
        with self.assertRaisesRegex(ValueError, "TTFT budget"):
            self._default_budget(
                ttft_slo_ms=100,
                e2e_slo_ms=200,
                client_to_gateway_ms=20,
                admission_ms=20,
                queue_ms=40,
                scheduled_to_first_token_ms=40,
                decode_streaming_ms=50,
                response_tail_ms=10,
            )

    def test_latency_budget_rejects_ttft_slack_larger_than_total_slack(self):
        with self.assertRaisesRegex(ValueError, "TTFT slack"):
            self._default_budget(
                ttft_slo_ms=250,
                e2e_slo_ms=790,
                decode_streaming_ms=520,
            )

    def test_good_request_cost_is_higher_than_successful_request_cost(self):
        records = self.metrics.load_jsonl(MODULE_PATH.with_name("sample.jsonl"))
        report = self.metrics.build_report(records, ttft_slo_ms=250, e2e_slo_ms=800)
        cost = report["cost"]

        self.assertAlmostEqual(cost["usd_per_successful_request"], 0.0035 / 3)
        self.assertAlmostEqual(cost["usd_per_good_request"], 0.0035 / 2)
        self.assertGreater(cost["usd_per_good_request"], cost["usd_per_successful_request"])

    def test_nearest_rank_percentile_is_explicit_and_deterministic(self):
        values = list(range(1, 101))
        self.assertEqual(self.metrics.nearest_rank_percentile(values, 50), 50)
        self.assertEqual(self.metrics.nearest_rank_percentile(values, 95), 95)
        self.assertEqual(self.metrics.nearest_rank_percentile(values, 99), 99)

    def test_cost_metrics_name_their_denominators(self):
        records = [
            record("a", 0, [10, 20], 30, cost_usd=0.02),
            record("b", 0, [10, 20, 30], 40, cost_usd=0.03),
        ]
        report = self.metrics.build_report(records, ttft_slo_ms=50, e2e_slo_ms=50)
        self.assertTrue(
            math.isclose(report["cost"]["usd_per_million_output_tokens"], 10_000)
        )
        self.assertTrue(math.isclose(report["cost"]["usd_per_successful_request"], 0.025))

    def test_invalid_or_inconsistent_records_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "sorted"):
            self.metrics.request_metrics(record("a", 0, [100, 90], 120))
        with self.assertRaisesRegex(ValueError, "output_tokens"):
            self.metrics.request_metrics(record("b", 0, [100], 120, output_tokens=2))
    def test_failed_request_preserves_observed_partial_output(self):
        metrics = self.metrics.request_metrics(
            record("partial-timeout", 0, [100, 160], 300, output_tokens=2, success=False)
        )

        self.assertFalse(metrics["success"])
        self.assertEqual(metrics["output_tokens"], 2)
        self.assertEqual(metrics["ttft_ms"], 100)
        self.assertEqual(metrics["itls_ms"], [60])

    def test_report_separates_successful_and_partial_output_tokens(self):
        records = [
            record("ok", 0, [100, 150], 180),
            record("partial-timeout", 0, [100], 200, output_tokens=1, success=False),
        ]

        report = self.metrics.build_report(records, ttft_slo_ms=200, e2e_slo_ms=300)

        self.assertEqual(report["throughput"]["successful_output_tokens"], 2)
        self.assertEqual(report["throughput"]["partial_output_tokens"], 1)
        self.assertEqual(report["throughput"]["observed_output_tokens"], 3)
        self.assertEqual(
            report["measurement_contract"]["failure_output_policy"],
            "partial tokens are observed work but excluded from successful output rate",
        )

    def test_report_carries_measurement_contract_and_percentile_method(self):
        report = self.metrics.build_report(
            [record("a", 0, [100, 150], 180)],
            ttft_slo_ms=200,
            e2e_slo_ms=300,
            workload={"name": "interactive-chat", "concurrency": 1},
        )
        self.assertEqual(report["mode"], "synthetic_client_metrics")
        self.assertEqual(report["measurement_contract"]["clock"], "client_wall_clock_ms")
        self.assertEqual(report["measurement_contract"]["percentile_method"], "nearest_rank")
        self.assertEqual(
            report["measurement_contract"]["goodput_definition"],
            "success AND quality_pass AND TTFT/E2E within SLO",
        )
        self.assertEqual(report["workload"]["name"], "interactive-chat")
        self.assertIn("不是 Benchmark", report["note"])


if __name__ == "__main__":
    unittest.main()
