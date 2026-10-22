#!/usr/bin/env python3
"""Unit tests for Chapter 6 Demo: workload description builder and checker."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workload_builder import (
    WorkloadError,
    build_workload,
    expected_concurrency,
    main,
    validate_workload,
)


def chat_doc(**overrides) -> dict:
    doc = build_workload(
        profile="chat",
        arrival="poisson",
        rate=10.0,
        concurrency=None,
        duration_s=60.0,
        seed=7,
        slo_metric="ttft",
        slo_quantile="p95",
        slo_threshold_ms=2000.0,
    )
    doc.update(overrides)
    return doc


class TestBuild(unittest.TestCase):
    def test_four_blocks_present(self):
        doc = chat_doc()
        self.assertEqual(
            sorted(doc), ["arrival", "identity", "length", "slo"]
        )

    def test_agent_profile_carries_step_distribution(self):
        doc = build_workload(
            profile="agent", arrival="poisson", rate=2.0, concurrency=None,
            duration_s=120.0, seed=1, slo_metric="task_e2e",
            slo_quantile="p95", slo_threshold_ms=60000.0,
        )
        self.assertIn("steps", doc)
        self.assertGreater(doc["steps"]["mean"], 0)

    def test_closed_loop_records_concurrency_and_no_rate(self):
        doc = build_workload(
            profile="chat", arrival="closed", rate=None, concurrency=32,
            duration_s=60.0, seed=3, slo_metric="ttft",
            slo_quantile="p95", slo_threshold_ms=2000.0,
        )
        self.assertEqual(doc["arrival"]["concurrency"], 32)
        self.assertNotIn("rate", doc["arrival"])

    def test_seed_is_always_recorded(self):
        self.assertEqual(chat_doc()["arrival"]["seed"], 7)


class TestCheckerRejections(unittest.TestCase):
    """The five rejections listed in 6.7, plus the no-performance-numbers rule."""

    def test_rejects_non_monotonic_quantiles(self):
        doc = chat_doc()
        doc["length"]["prompt"]["p50"] = 9999
        with self.assertRaises(WorkloadError) as ctx:
            validate_workload(doc)
        self.assertIn("non-decreasing", str(ctx.exception))

    def test_rejects_open_loop_without_rate(self):
        doc = chat_doc()
        del doc["arrival"]["rate"]
        with self.assertRaises(WorkloadError) as ctx:
            validate_workload(doc)
        self.assertIn("requires a positive rate", str(ctx.exception))

    def test_rejects_closed_loop_without_concurrency(self):
        doc = chat_doc()
        doc["arrival"] = {"mode": "closed", "duration_s": 60.0, "seed": 7}
        with self.assertRaises(WorkloadError) as ctx:
            validate_workload(doc)
        self.assertIn("requires a positive concurrency", str(ctx.exception))

    def test_rejects_threshold_without_quantile(self):
        doc = chat_doc()
        del doc["slo"]["quantile"]
        with self.assertRaises(WorkloadError) as ctx:
            validate_workload(doc)
        self.assertIn("quantile", str(ctx.exception))

    def test_rejects_agent_without_step_distribution(self):
        doc = chat_doc()
        doc["identity"]["type"] = "agent"
        with self.assertRaises(WorkloadError) as ctx:
            validate_workload(doc)
        self.assertIn("steps block", str(ctx.exception))

    def test_rejects_missing_seed(self):
        doc = chat_doc()
        del doc["arrival"]["seed"]
        with self.assertRaises(WorkloadError) as ctx:
            validate_workload(doc)
        self.assertIn("seed", str(ctx.exception))

    def test_rejects_performance_numbers_in_a_description(self):
        doc = chat_doc()
        doc["results"] = {"ttft_p95_ms": 210}
        with self.assertRaises(WorkloadError) as ctx:
            validate_workload(doc)
        self.assertIn("must not carry performance numbers", str(ctx.exception))

    def test_rejects_closed_loop_that_also_sets_a_rate(self):
        doc = build_workload(
            profile="chat", arrival="closed", rate=None, concurrency=32,
            duration_s=60.0, seed=3, slo_metric="ttft",
            slo_quantile="p95", slo_threshold_ms=2000.0,
        )
        doc["arrival"]["rate"] = 16
        with self.assertRaises(WorkloadError) as ctx:
            validate_workload(doc)
        self.assertIn("rate is an outcome", str(ctx.exception))


class TestLittlesLaw(unittest.TestCase):
    def test_matches_the_worked_example_in_6_4(self):
        doc = chat_doc()
        doc["arrival"]["rate"] = 10
        self.assertAlmostEqual(expected_concurrency(doc, 2.0), 20.0)

    def test_reverses_to_the_stretched_latency(self):
        doc = chat_doc()
        doc["arrival"]["rate"] = 10
        # 55 in flight at 10 req/s implies a 5.5 s mean latency, not a broken law.
        self.assertAlmostEqual(55 / doc["arrival"]["rate"], 5.5)

    def test_refuses_closed_loop(self):
        doc = build_workload(
            profile="chat", arrival="closed", rate=None, concurrency=20,
            duration_s=60.0, seed=3, slo_metric="ttft",
            slo_quantile="p95", slo_threshold_ms=2000.0,
        )
        with self.assertRaises(WorkloadError):
            expected_concurrency(doc, 2.0)


class TestCli(unittest.TestCase):
    def test_writes_a_valid_file_and_validates_it_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workload-chat.json"
            self.assertEqual(main(["--profile", "chat", "--arrival", "poisson",
                                   "--rate", "10", "--duration", "60",
                                   "--output", str(path)]), 0)
            doc = json.loads(path.read_text(encoding="utf-8"))
            validate_workload(doc)
            self.assertEqual(main(["--validate", str(path)]), 0)

    def test_validate_returns_nonzero_on_a_broken_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            doc = chat_doc()
            doc["length"]["output"]["p90"] = 1
            path.write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual(main(["--validate", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
