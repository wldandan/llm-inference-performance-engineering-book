import io
import unittest
from unittest.mock import patch

from streaming_client import (
    DEFAULT_MODEL,
    MetricsCollector,
    build_report,
    build_payload,
    gpu_snapshot,
    percentile,
    request_once,
)


class Chapter01StreamingClientTest(unittest.TestCase):
    def test_default_model_supports_chat_requests(self):
        self.assertEqual(DEFAULT_MODEL, "Qwen/Qwen2.5-0.5B-Instruct")

    def test_build_payload_uses_chat_completion_shape(self):
        payload = build_payload(
            model="Qwen/Qwen2.5-0.5B-Instruct",
            prompt="hello",
            max_tokens=32,
            temperature=0.0,
        )

        self.assertEqual(payload["model"], "Qwen/Qwen2.5-0.5B-Instruct")
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertEqual(payload["messages"][0]["content"], "hello")
        self.assertEqual(payload["max_tokens"], 32)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["stream_options"], {"include_usage": True})

    def test_metrics_collector_names_client_chunk_metrics_explicitly(self):
        collector = MetricsCollector(start_time=10.0)
        collector.on_content_chunk(10.25, "A")
        collector.on_content_chunk(10.35, "B")
        collector.on_content_chunk(10.50, "C")
        collector.set_usage(prompt_tokens=100, completion_tokens=3)
        result = collector.finish(end_time=10.70)

        self.assertAlmostEqual(result["time_to_first_content_chunk_ms"], 250.0)
        self.assertAlmostEqual(result["chunk_interval_avg_ms"], 125.0)
        self.assertAlmostEqual(result["total_latency_ms"], 700.0)
        self.assertAlmostEqual(result["request_output_rate_tokens_per_second"], 4.29)
        self.assertNotIn("output_tokens_per_second", result)
        self.assertEqual(result["prompt_tokens"], 100)
        self.assertEqual(result["output_tokens"], 3)

    def test_metrics_collector_does_not_treat_chunks_as_tokens(self):
        collector = MetricsCollector(start_time=10.0)
        collector.on_content_chunk(10.25, "one chunk may contain several tokens")

        result = collector.finish(end_time=10.75)

        self.assertIsNone(result["request_output_rate_tokens_per_second"])

    def test_request_once_rejects_stream_without_done_event(self):
        body = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
        with patch("streaming_client.urllib.request.urlopen", return_value=io.BytesIO(body)):
            result = request_once("http://localhost/v1", "EMPTY", "model", "hi", 8, 0.0, 1)

        self.assertFalse(result["success"])
        self.assertIn("without [DONE]", result["error"])

    def test_request_once_reports_sse_error_payload(self):
        body = b'data: {"error":{"message":"engine failed"}}\n\n'
        with patch("streaming_client.urllib.request.urlopen", return_value=io.BytesIO(body)):
            result = request_once("http://localhost/v1", "EMPTY", "model", "hi", 8, 0.0, 1)

        self.assertFalse(result["success"])
        self.assertIn("engine failed", result["error"])

    def test_request_once_rejects_done_stream_without_content(self):
        with patch("streaming_client.urllib.request.urlopen", return_value=io.BytesIO(b"data: [DONE]\n\n")):
            result = request_once("http://localhost/v1", "EMPTY", "model", "hi", 8, 0.0, 1)

        self.assertFalse(result["success"])
        self.assertIn("no content", result["error"])

    def test_percentile(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(percentile([1, 2, 3, 4], 95), 3.85)
        self.assertIsNone(percentile([], 95))

    def test_build_report_includes_prompt(self):
        report = build_report(
            started_at="2026-07-30T00:00:00+0800",
            base_url="http://127.0.0.1:8000/v1",
            model="Qwen/Qwen2.5-0.5B-Instruct",
            prompt="hello",
            prompt_repeat=1,
            max_tokens=8,
            concurrency=1,
            results=[{"success": True, "time_to_first_content_chunk_ms": 1.0}],
            before_gpu=None,
            after_gpu=None,
        )

        self.assertEqual(report["prompt"], "hello")

    def test_gpu_snapshot_handles_unavailable_memory_fields(self):
        output = "NVIDIA GB10, 12, [N/A], [N/A]\n"
        with patch("streaming_client.shutil.which", return_value="/usr/bin/nvidia-smi"), patch(
            "streaming_client.subprocess.check_output", return_value=output
        ):
            snapshot = gpu_snapshot()

        self.assertEqual(snapshot["gpus"][0]["gpu_util_pct"], 12.0)
        self.assertIsNone(snapshot["gpus"][0]["memory_used_mb"])
        self.assertIsNone(snapshot["gpus"][0]["memory_total_mb"])


if __name__ == "__main__":
    unittest.main()
