import json
import inspect
import os
import tempfile
import unittest

from bench_client import (
    MetricsCollector,
    build_payload,
    build_report,
    load_request_plan,
    percentile,
    summarize,
)


class BuildPayloadTest(unittest.TestCase):
    def test_build_payload_uses_chat_completion_shape(self):
        payload = build_payload(model="Qwen/Qwen2.5-0.5B", prompt="hello", max_tokens=32, temperature=0.0)

        self.assertEqual(payload["model"], "Qwen/Qwen2.5-0.5B")
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertEqual(payload["messages"][0]["content"], "hello")
        self.assertEqual(payload["max_tokens"], 32)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["stream_options"], {"include_usage": True})


class MetricsCollectorTest(unittest.TestCase):
    def test_computes_ttft_itl_and_tps(self):
        collector = MetricsCollector(start_time=10.0)
        collector.on_token(10.25, "A")
        collector.on_token(10.35, "B")
        collector.on_token(10.50, "C")
        collector.set_usage(prompt_tokens=100, completion_tokens=3)
        result = collector.finish(end_time=10.70)

        self.assertAlmostEqual(result["ttft_ms"], 250.0)
        self.assertAlmostEqual(result["itl_avg_ms"], 125.0)
        self.assertAlmostEqual(result["total_latency_ms"], 700.0)
        self.assertAlmostEqual(result["tokens_per_second"], 4.29)


class PercentileTest(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(percentile([1, 2, 3, 4], 95), 3.85)
        self.assertIsNone(percentile([], 95))


class LoadRequestPlanTest(unittest.TestCase):
    def _write_jsonl(self, rows):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        self.addCleanup(os.remove, path)
        return path

    def test_loads_prompt_and_max_tokens_per_line(self):
        path = self._write_jsonl(
            [
                {"prompt": "short prompt", "max_tokens": 32},
                {"prompt": "a much longer prompt " * 50, "max_tokens": 256},
            ]
        )

        plan = load_request_plan(path, count=2)

        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["prompt"], "short prompt")
        self.assertEqual(plan[0]["max_tokens"], 32)
        self.assertEqual(plan[1]["max_tokens"], 256)

    def test_cycles_when_count_exceeds_file_length(self):
        path = self._write_jsonl([{"prompt": "only one line", "max_tokens": 16}])

        plan = load_request_plan(path, count=5)

        self.assertEqual(len(plan), 5)
        self.assertTrue(all(item["prompt"] == "only one line" for item in plan))

    def test_defaults_max_tokens_when_missing(self):
        path = self._write_jsonl([{"prompt": "no max tokens field"}])

        plan = load_request_plan(path, count=1, default_max_tokens=64)

        self.assertEqual(plan[0]["max_tokens"], 64)

    def test_rejects_empty_file(self):
        path = self._write_jsonl([])

        with self.assertRaises(ValueError):
            load_request_plan(path, count=1)


class SummarizeTest(unittest.TestCase):
    def test_summarize_accepts_wall_clock_duration_for_global_throughput(self):
        self.assertIn("benchmark_duration_s", inspect.signature(summarize).parameters)

    def test_summarize_uses_wall_clock_for_global_throughput(self):
        results = [
            {"success": True, "prompt_tokens": 100, "output_tokens": 10},
            {"success": True, "prompt_tokens": 300, "output_tokens": 30},
        ]

        summary = summarize(results, benchmark_duration_s=2.0)

        self.assertEqual(summary.get("benchmark_duration_s"), 2.0)
        self.assertEqual(summary.get("request_throughput_rps"), 1.0)
        self.assertEqual(summary.get("input_throughput_tokens_per_second"), 200.0)
        self.assertEqual(summary.get("output_throughput_tokens_per_second"), 20.0)

    def test_summarize_reports_success_and_percentiles(self):
        results = [
            {"success": True, "ttft_ms": 100.0, "itl_avg_ms": 20.0, "total_latency_ms": 500.0, "tokens_per_second": 10.0},
            {"success": True, "ttft_ms": 200.0, "itl_avg_ms": 30.0, "total_latency_ms": 600.0, "tokens_per_second": 12.0},
            {"success": False, "error": "boom"},
        ]

        summary = summarize(results)

        self.assertEqual(summary["requests"], 3)
        self.assertEqual(summary["successes"], 2)
        self.assertEqual(summary["failures"], 1)
        self.assertAlmostEqual(summary["ttft_avg_ms"], 150.0)
        self.assertEqual(len(summary["failures_detail"]), 1)

    def test_summarize_records_input_and_output_token_distributions(self):
        results = [
            {
                "success": True,
                "prompt_tokens": 100,
                "output_tokens": 10,
                "total_latency_ms": 500.0,
                "tokens_per_second": 20.0,
            },
            {
                "success": True,
                "prompt_tokens": 300,
                "output_tokens": 30,
                "total_latency_ms": 1000.0,
                "tokens_per_second": 30.0,
            },
        ]

        summary = summarize(results)

        self.assertEqual(
            summary.get("input_tokens"),
            {"min": 100, "p50": 200.0, "p95": 290.0, "max": 300, "total": 400},
        )
        self.assertEqual(
            summary.get("output_tokens"),
            {"min": 10, "p50": 20.0, "p95": 29.0, "max": 30, "total": 40},
        )


class BuildReportTest(unittest.TestCase):
    def test_build_report_accepts_duration_and_engine_batch_size(self):
        parameters = inspect.signature(build_report).parameters
        self.assertIn("benchmark_duration_s", parameters)
        self.assertIn("batch_size", parameters)

    def test_build_report_includes_label_and_config(self):
        report = build_report(
            label="baseline",
            started_at="2026-09-03T00:00:00+0800",
            base_url="http://127.0.0.1:8000/v1",
            model="Qwen/Qwen2.5-0.5B",
            concurrency=4,
            config={"block-size": "8 (undersized)"},
            results=[{"success": True, "ttft_ms": 1.0}],
            before_gpu=None,
            after_gpu=None,
        )

        self.assertEqual(report["label"], "baseline")
        self.assertEqual(report["concurrency"], 4)
        self.assertEqual(report["config"]["block-size"], "8 (undersized)")

    def test_build_report_uses_versioned_reproducible_schema(self):
        report = build_report(
            label="baseline",
            started_at="2026-09-03T00:00:00+0800",
            base_url="http://127.0.0.1:8000/v1",
            model="Qwen/Qwen2.5-0.5B",
            concurrency=4,
            config={"note": "prefix cache disabled"},
            results=[
                {
                    "success": True,
                    "prompt_tokens": 100,
                    "output_tokens": 10,
                    "ttft_ms": 25.0,
                    "total_latency_ms": 100.0,
                    "tokens_per_second": 100.0,
                }
            ],
            before_gpu={
                "gpus": [
                    {
                        "name": "Example GPU",
                        "gpu_util_pct": 10.0,
                        "memory_used_mb": 1024.0,
                        "memory_total_mb": 8192.0,
                    }
                ]
            },
            after_gpu={
                "gpus": [
                    {
                        "name": "Example GPU",
                        "gpu_util_pct": 20.0,
                        "memory_used_mb": 2048.0,
                        "memory_total_mb": 8192.0,
                    }
                ]
            },
        )

        self.assertEqual(report.get("schema_version"), "1.0")
        self.assertEqual(report["model"]["id"], "Qwen/Qwen2.5-0.5B")
        self.assertEqual(report["workload"]["client_concurrency"], 4)
        self.assertIn("batch_size", report["workload"])
        self.assertEqual(report["workload"]["input_tokens"]["total"], 100)
        self.assertEqual(report["workload"]["output_tokens"]["total"], 10)
        self.assertEqual(report["hardware"]["gpus"][0]["name"], "Example GPU")
        self.assertEqual(report["metrics"]["gpu_memory_used_mb"]["max_observed"], 2048.0)
        self.assertIn("python_version", report["environment"])
        self.assertIn("platform", report["environment"])


if __name__ == "__main__":
    unittest.main()
