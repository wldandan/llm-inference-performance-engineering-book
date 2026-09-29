import unittest

from compare import format_table, load_reports, pct_change


class PctChangeTest(unittest.TestCase):
    def test_positive_change(self):
        self.assertAlmostEqual(pct_change(100.0, 150.0), 50.0)

    def test_negative_change(self):
        self.assertAlmostEqual(pct_change(100.0, 60.0), -40.0)

    def test_none_when_baseline_missing(self):
        self.assertIsNone(pct_change(None, 60.0))
        self.assertIsNone(pct_change(100.0, None))

    def test_none_when_baseline_zero(self):
        self.assertIsNone(pct_change(0.0, 60.0))


class LoadReportsTest(unittest.TestCase):
    def test_loads_summary_and_label_from_each_file(self, tmp_path=None):
        import json
        import os
        import tempfile

        rows = []
        paths = []
        for label, ttft in [("baseline", 200.0), ("optimized", 80.0)]:
            fd, path = tempfile.mkstemp(suffix=".json")
            report = {"label": label, "summary": {"ttft_avg_ms": ttft, "failures": 0}}
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(report, f)
            paths.append(path)
            self.addCleanup(os.remove, path)

        reports = load_reports(paths)

        self.assertEqual(reports[0]["label"], "baseline")
        self.assertEqual(reports[1]["summary"]["ttft_avg_ms"], 80.0)


class FormatTableTest(unittest.TestCase):
    def test_first_report_is_baseline_with_no_change_column(self):
        reports = [
            {"label": "baseline", "summary": {"ttft_avg_ms": 200.0, "tokens_per_second_sum": 10.0, "failures": 0}},
            {"label": "optimized", "summary": {"ttft_avg_ms": 80.0, "tokens_per_second_sum": 25.0, "failures": 0}},
        ]

        table = format_table(reports, metrics=["ttft_avg_ms", "tokens_per_second_sum"])

        self.assertIn("baseline", table)
        self.assertIn("optimized", table)
        self.assertIn("-60.0%", table)  # ttft dropped 60%
        self.assertIn("+150.0%", table)  # throughput up 150%

    def test_flags_failures(self):
        reports = [
            {"label": "baseline", "summary": {"ttft_avg_ms": 200.0, "failures": 3}},
        ]

        table = format_table(reports, metrics=["ttft_avg_ms"])

        self.assertIn("failures=3", table)

    def test_marks_metric_change_as_better_or_worse(self):
        reports = [
            {
                "label": "baseline",
                "summary": {"ttft_avg_ms": 200.0, "output_throughput_tokens_per_second": 10.0, "failures": 0},
            },
            {
                "label": "optimized",
                "summary": {"ttft_avg_ms": 80.0, "output_throughput_tokens_per_second": 25.0, "failures": 0},
            },
        ]

        table = format_table(reports, metrics=["ttft_avg_ms", "output_throughput_tokens_per_second"])

        self.assertIn("-60.0% better", table)
        self.assertIn("+150.0% better", table)

    def test_warns_when_baseline_and_candidate_are_not_comparable(self):
        reports = [
            {
                "label": "baseline",
                "model": {"id": "model-a"},
                "workload": {"client_concurrency": 4, "input_tokens": {"total": 100}},
                "hardware": {"gpus": [{"name": "GPU-A"}]},
                "summary": {"ttft_avg_ms": 200.0, "failures": 0},
            },
            {
                "label": "optimized",
                "model": {"id": "model-b"},
                "workload": {"client_concurrency": 8, "input_tokens": {"total": 200}},
                "hardware": {"gpus": [{"name": "GPU-B"}]},
                "summary": {"ttft_avg_ms": 80.0, "failures": 0},
            },
        ]

        table = format_table(reports, metrics=["ttft_avg_ms"])

        self.assertIn("WARNING: optimized model differs from baseline", table)
        self.assertIn("WARNING: optimized client_concurrency differs from baseline", table)
        self.assertIn("WARNING: optimized input_tokens differs from baseline", table)
        self.assertIn("WARNING: optimized GPU model differs from baseline", table)

    def test_accepts_legacy_reports_where_model_is_a_string(self):
        reports = [
            {"label": "baseline", "model": "model-a", "summary": {"ttft_avg_ms": 100.0, "failures": 0}},
            {"label": "optimized", "model": "model-a", "summary": {"ttft_avg_ms": 80.0, "failures": 0}},
        ]

        table = format_table(reports, metrics=["ttft_avg_ms"])

        self.assertIn("-20.0% better", table)


if __name__ == "__main__":
    unittest.main()
