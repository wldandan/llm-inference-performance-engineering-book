#!/usr/bin/env python3
"""Unit tests for Chapter 10 Demo: root-cause report checker."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from rca_report import BLOCKS, ReportError, main, summarize, validate_report

SAMPLE = (
    Path(__file__).resolve().parent.parent.parent
    / "content" / "ch10" / "evidence" / "rca-report-sample.json"
)


def sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


class TestSampleReport(unittest.TestCase):
    """The worked investigation in 10.6 must pass its own checker."""

    def test_sample_file_exists(self):
        self.assertTrue(SAMPLE.exists(), f"missing {SAMPLE}")

    def test_sample_passes_validation(self):
        validate_report(sample())

    def test_sample_carries_all_seven_blocks(self):
        doc = sample()
        for block in BLOCKS:
            self.assertIn(block, doc)

    def test_sample_is_labelled_synthetic(self):
        self.assertIn("合成数据", sample()["_note"])

    def test_sample_summary_matches_the_narrative(self):
        s = summarize(sample())
        self.assertEqual(s["supported"], ["H1"])
        self.assertEqual(s["ruled_out"], ["H3"])
        self.assertEqual(s["unconfirmed"], ["H2"])
        self.assertEqual(s["confidence"], "high")
        self.assertGreaterEqual(s["explicit_exclusions"], 3)
        self.assertGreaterEqual(s["open_questions"], 2)

    def test_sample_records_both_resolved_and_not_resolved(self):
        c = sample()["conclusion"]
        self.assertIn("620", c["resolved"])
        self.assertIn("55%", c["not_resolved"])


class TestRejections(unittest.TestCase):
    """The five rejections listed in 10.7, plus the unfinished-thread rule."""

    def test_rejects_problem_without_scope(self):
        doc = sample()
        doc["problem"]["scope"] = ""
        with self.assertRaises(ReportError) as ctx:
            validate_report(doc)
        self.assertIn("problem.scope", str(ctx.exception))

    def test_rejects_problem_without_baseline(self):
        doc = sample()
        del doc["problem"]["baseline"]
        with self.assertRaises(ReportError):
            validate_report(doc)

    def test_rejects_hypothesis_without_expected_evidence(self):
        doc = sample()
        doc["hypotheses"][0]["expected_evidence"] = "  "
        with self.assertRaises(ReportError) as ctx:
            validate_report(doc)
        self.assertIn("cannot be falsified", str(ctx.exception))

    def test_rejects_hypothesis_without_threshold(self):
        doc = sample()
        del doc["hypotheses"][0]["threshold"]
        with self.assertRaises(ReportError) as ctx:
            validate_report(doc)
        self.assertIn("threshold", str(ctx.exception))

    def test_rejects_conclusion_citing_missing_evidence(self):
        doc = sample()
        doc["conclusion"]["supported_by"] = ["E3", "E99"]
        with self.assertRaises(ReportError) as ctx:
            validate_report(doc)
        self.assertIn("E99", str(ctx.exception))

    def test_rejects_evidence_without_collection_condition(self):
        doc = sample()
        doc["evidence"][0]["collection_condition"] = ""
        with self.assertRaises(ReportError) as ctx:
            validate_report(doc)
        self.assertIn("collection_condition", str(ctx.exception))

    def test_rejects_single_hypothesis_with_nothing_ruled_out(self):
        doc = sample()
        doc["hypotheses"] = [copy.deepcopy(doc["hypotheses"][0])]
        doc["ruled_out"] = []
        doc["unknowns"] = []
        with self.assertRaises(ReportError) as ctx:
            validate_report(doc)
        self.assertIn("conclusion looking for evidence", str(ctx.exception))

    def test_rejects_unconfirmed_hypothesis_missing_from_unknowns(self):
        doc = sample()
        doc["unknowns"] = [
            u for u in doc["unknowns"] if "H2" not in u["item"] + u["reason"] + u["impact"]
        ]
        with self.assertRaises(ReportError) as ctx:
            validate_report(doc)
        self.assertIn("unconfirmed", str(ctx.exception))

    def test_rejects_verification_that_changes_the_workload(self):
        doc = sample()
        doc["next_step"]["verification"] = "换一份更真实的负载再跑一次"
        with self.assertRaises(ReportError) as ctx:
            validate_report(doc)
        self.assertIn("same workload", str(ctx.exception))

    def test_rejects_unknown_change_tier(self):
        doc = sample()
        doc["next_step"]["tier"] = "magic"
        with self.assertRaises(ReportError):
            validate_report(doc)


class TestCli(unittest.TestCase):
    def test_cli_accepts_the_sample(self):
        self.assertEqual(main(["--input", str(SAMPLE)]), 0)


if __name__ == "__main__":
    unittest.main()
