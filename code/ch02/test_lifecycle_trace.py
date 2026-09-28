import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LifecycleTraceTest(unittest.TestCase):
    def load_module(self):
        try:
            return importlib.import_module("lifecycle_trace")
        except ModuleNotFoundError:
            self.fail("lifecycle_trace module has not been implemented")

    def test_completed_request_is_split_into_lifecycle_intervals(self):
        lifecycle_trace = self.load_module()
        events = [
            {"request_id": "req-1", "event": "request_received", "ts_ms": 0},
            {"request_id": "req-1", "event": "queued", "ts_ms": 2},
            {"request_id": "req-1", "event": "scheduled", "ts_ms": 12},
            {"request_id": "req-1", "event": "first_token", "ts_ms": 42},
            {"request_id": "req-1", "event": "last_token", "ts_ms": 92},
            {"request_id": "req-1", "event": "finished", "ts_ms": 97},
        ]

        result = lifecycle_trace.analyze_request(events)

        self.assertEqual(result["request_id"], "req-1")
        self.assertEqual(result["terminal_state"], "finished")
        self.assertEqual(
            result["durations_ms"],
            {
                "admission": 2,
                "queue": 10,
                "scheduled_to_first_token": 30,
                "decode": 50,
                "response_tail": 5,
                "end_to_end": 97,
            },
        )

    def test_cancelled_request_keeps_completed_intervals(self):
        lifecycle_trace = self.load_module()
        events = [
            {"request_id": "req-2", "event": "request_received", "ts_ms": 5},
            {"request_id": "req-2", "event": "queued", "ts_ms": 7},
            {"request_id": "req-2", "event": "scheduled", "ts_ms": 20},
            {"request_id": "req-2", "event": "cancelled", "ts_ms": 29},
        ]

        result = lifecycle_trace.analyze_request(events)

        self.assertEqual(result["terminal_state"], "cancelled")
        self.assertEqual(result["durations_ms"]["admission"], 2)
        self.assertEqual(result["durations_ms"]["queue"], 13)
        self.assertIsNone(result["durations_ms"]["scheduled_to_first_token"])
        self.assertEqual(result["durations_ms"]["end_to_end"], 24)

    def test_out_of_order_timestamps_are_rejected(self):
        lifecycle_trace = self.load_module()
        events = [
            {"request_id": "req-3", "event": "request_received", "ts_ms": 10},
            {"request_id": "req-3", "event": "queued", "ts_ms": 8},
        ]

        with self.assertRaisesRegex(ValueError, "timestamps"):
            lifecycle_trace.analyze_request(events)

    def test_invalid_transition_is_rejected(self):
        lifecycle_trace = self.load_module()
        events = [
            {"request_id": "req-4", "event": "request_received", "ts_ms": 0},
            {"request_id": "req-4", "event": "first_token", "ts_ms": 10},
        ]

        with self.assertRaisesRegex(ValueError, "transition"):
            lifecycle_trace.analyze_request(events)

    def test_multiple_requests_are_grouped_and_summarized(self):
        lifecycle_trace = self.load_module()
        events = [
            {"request_id": "req-ok", "event": "request_received", "ts_ms": 0},
            {"request_id": "req-stop", "event": "request_received", "ts_ms": 1},
            {"request_id": "req-ok", "event": "queued", "ts_ms": 2},
            {"request_id": "req-stop", "event": "cancelled", "ts_ms": 3},
            {"request_id": "req-ok", "event": "scheduled", "ts_ms": 4},
            {"request_id": "req-ok", "event": "first_token", "ts_ms": 8},
            {"request_id": "req-ok", "event": "last_token", "ts_ms": 9},
            {"request_id": "req-ok", "event": "finished", "ts_ms": 10},
        ]

        report = lifecycle_trace.analyze_events(events)

        self.assertEqual(report["summary"], {"requests": 2, "finished": 1, "cancelled": 1, "failed": 0})
        self.assertEqual([item["request_id"] for item in report["requests"]], ["req-ok", "req-stop"])

    def test_jsonl_events_are_loaded(self):
        lifecycle_trace = self.load_module()
        self.assertTrue(hasattr(lifecycle_trace, "load_jsonl"), "load_jsonl has not been implemented")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            path.write_text(
                '{"request_id":"req-1","event":"request_received","ts_ms":0}\n'
                '{"request_id":"req-1","event":"cancelled","ts_ms":3}\n',
                encoding="utf-8",
            )

            events = lifecycle_trace.load_jsonl(path)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["event"], "cancelled")

    def test_invalid_jsonl_reports_the_line_number(self):
        lifecycle_trace = self.load_module()
        self.assertTrue(hasattr(lifecycle_trace, "load_jsonl"), "load_jsonl has not been implemented")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            path.write_text('{"request_id":"req-1"}\nnot-json\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "line 2"):
                lifecycle_trace.load_jsonl(path)

    def test_cli_prints_a_json_report(self):
        script = Path(__file__).with_name("lifecycle_trace.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "events.jsonl"
            input_path.write_text(
                '{"request_id":"req-1","event":"request_received","ts_ms":0}\n'
                '{"request_id":"req-1","event":"cancelled","ts_ms":3}\n',
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(script), "--input", str(input_path)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout.strip(), "", "CLI has not been implemented")
        self.assertEqual(json.loads(result.stdout)["summary"]["cancelled"], 1)

    def test_cli_can_save_the_json_report(self):
        script = Path(__file__).with_name("lifecycle_trace.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "events.jsonl"
            output_path = Path(temp_dir) / "report.json"
            input_path.write_text(
                '{"request_id":"req-1","event":"request_received","ts_ms":0}\n'
                '{"request_id":"req-1","event":"cancelled","ts_ms":3}\n',
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output_path.exists(), "CLI did not create the requested report")
            self.assertEqual(json.loads(output_path.read_text())["summary"]["cancelled"], 1)


if __name__ == "__main__":
    unittest.main()
