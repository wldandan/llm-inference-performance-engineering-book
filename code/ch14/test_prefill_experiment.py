#!/usr/bin/env python3
"""Tests for the Chapter 14 experiment report.

Most of these are rejection tests: the report's value is in what it refuses to
accept, because every refusal corresponds to a way an experiment silently
stops being able to support a conclusion.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch11"))

import prefill_experiment as pe  # noqa: E402
from prefill_model import load_config  # noqa: E402

CONFIG_PATH = HERE.parent / "ch11" / "model-qwen25-05b.json"
SAMPLE_PATH = (
    HERE.parent.parent / "content" / "ch14" / "evidence"
    / "prefill-experiment-sample.json"
)


def config() -> dict:
    return load_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def one_round(index: int = 0) -> dict:
    return copy.deepcopy(sample()["rounds"][index])


class StatisticsTest(unittest.TestCase):
    def test_cv_uses_the_sample_convention(self):
        values = [1180.0, 1205.0, 1192.0]
        self.assertAlmostEqual(
            pe.coefficient_of_variation(values), 0.01049, places=4
        )

    def test_detectable_difference_is_t_sqrt_2_over_n_times_cv(self):
        """7.3: three runs against three runs is about 2.3 x CV."""
        values = [1180.0, 1205.0, 1192.0]
        self.assertAlmostEqual(
            pe.detectable_difference(values) / pe.coefficient_of_variation(values),
            2.267, places=3,
        )

    def test_two_runs_are_not_enough(self):
        with self.assertRaises(pe.ExperimentError):
            pe.detectable_difference([1180.0, 1205.0])


class ExpectationTest(unittest.TestCase):
    def test_sample_expectations_are_valid(self):
        for i in range(4):
            pe.validate_expectation(one_round(i)["expectation"])

    def test_missing_written_at_is_rejected(self):
        doc = one_round()["expectation"]
        del doc["written_at"]
        with self.assertRaises(pe.ExperimentError):
            pe.validate_expectation(doc)

    def test_missing_null_criterion_is_rejected(self):
        doc = one_round()["expectation"]
        del doc["null_criterion"]
        with self.assertRaises(pe.ExperimentError):
            pe.validate_expectation(doc)

    def test_magnitude_without_a_basis_is_rejected(self):
        """14.1: every number in the expectation must have a provenance."""
        doc = one_round()["expectation"]
        doc["magnitude"]["ttft_p50_ms"] = {"expected_pct": 0.33}
        with self.assertRaises(pe.ExperimentError) as ctx:
            pe.validate_expectation(doc)
        self.assertIn("出处", str(ctx.exception))


class ReportRejectionTest(unittest.TestCase):
    def test_sample_rounds_all_validate(self):
        for i in range(4):
            pe.validate_report(one_round(i))

    def test_two_changes_are_rejected(self):
        doc = one_round()
        doc["changed"]["enable_prefix_caching"] = "false → true"
        with self.assertRaises(pe.ExperimentError) as ctx:
            pe.validate_report(doc)
        self.assertIn("只允许出现一项", str(ctx.exception))

    def test_nonzero_temperature_is_rejected(self):
        doc = one_round()
        doc["fixed"]["protocol"]["temperature"] = 0.7
        with self.assertRaises(pe.ExperimentError):
            pe.validate_report(doc)

    def test_ambiguous_cache_state_is_rejected(self):
        doc = one_round()
        doc["fixed"]["protocol"]["prefix_cache"] = "sometimes"
        with self.assertRaises(pe.ExperimentError):
            pe.validate_report(doc)

    def test_missing_environment_fingerprint_is_rejected(self):
        doc = one_round()
        del doc["fixed"]["environment"]["gpu"]
        with self.assertRaises(pe.ExperimentError):
            pe.validate_report(doc)

    def test_missing_percentile_algorithm_is_rejected(self):
        doc = one_round()
        del doc["fixed"]["protocol"]["percentile_algorithm"]
        with self.assertRaises(pe.ExperimentError):
            pe.validate_report(doc)

    def test_two_runs_are_rejected(self):
        doc = one_round()
        doc["results"]["baseline"] = doc["results"]["baseline"][:2]
        with self.assertRaises(pe.ExperimentError):
            pe.validate_report(doc)

    def test_empty_guardrails_are_rejected(self):
        doc = one_round()
        doc["guardrails"] = {}
        with self.assertRaises(pe.ExperimentError) as ctx:
            pe.validate_report(doc)
        self.assertIn("不是可选项", str(ctx.exception))

    def test_missing_boundary_field_is_rejected(self):
        for field in pe.BOUNDARY_FIELDS:
            doc = one_round()
            del doc["boundary"][field]
            with self.assertRaises(pe.ExperimentError):
                pe.validate_report(doc)

    def test_indistinguishable_cannot_also_claim_improvement(self):
        """14.7: the fourth verdict must not be rewritten as a small win."""
        doc = one_round(2)
        self.assertEqual(doc["verdict"]["label"], pe.INDISTINGUISHABLE)
        doc["verdict"]["reading"] = "有小幅提升，可以上线"
        with self.assertRaises(pe.ExperimentError) as ctx:
            pe.validate_report(doc)
        self.assertIn("噪声", str(ctx.exception))

    def test_unknown_verdict_label_is_rejected(self):
        doc = one_round()
        doc["verdict"]["label"] = "很棒"
        with self.assertRaises(pe.ExperimentError):
            pe.validate_report(doc)


class JudgeTest(unittest.TestCase):
    BASE = [1195, 1221, 1210]

    def test_round_one_meets_expectation(self):
        v = pe.judge(self.BASE, [801, 815, 806], 0.333)
        self.assertEqual(v["label"], "符合预期")
        self.assertAlmostEqual(v["observed_pct"], 0.332, places=3)
        self.assertLess(abs(v["gap_pct"]), v["detectable_difference"])

    def test_round_two_exceeds_expectation(self):
        """Hit rate 0.82 instead of the assumed 0.4: the basis was wrong."""
        v = pe.judge(self.BASE, [1009, 1028, 1020], 0.08)
        self.assertEqual(v["label"], "高于预期")
        self.assertIn("依据", v["reading"])

    def test_round_three_is_indistinguishable(self):
        v = pe.judge(self.BASE, [1199, 1225, 1215], 0.0)
        self.assertEqual(v["label"], pe.INDISTINGUISHABLE)
        self.assertLess(abs(v["observed_pct"]), v["detectable_difference"])

    def test_round_four_falls_short(self):
        v = pe.judge([210, 218, 214], [148, 152, 150], 0.50)
        self.assertEqual(v["label"], "低于预期")
        self.assertIn("14.5", v["reading"])

    def test_the_gap_is_judged_by_the_same_line(self):
        """A result within the line of the expectation matches, either side."""
        base = [1000.0, 1010.0, 1005.0]
        line = pe.detectable_difference(base)
        just_above = pe.judge(base, [1005 * (1 - 0.30 - line / 2)] * 2 + [1005 * (1 - 0.30 - line / 2) + 0.001], 0.30)
        self.assertEqual(just_above["label"], "符合预期")

    def test_case_two_six_percent_against_a_thirteen_percent_line(self):
        """14.8 case 2: improvement inside the line is not a result."""
        noisy = [1000.0, 1058.0, 942.0]
        line = pe.detectable_difference(noisy)
        self.assertGreater(line, 0.10)
        v = pe.judge(noisy, [940.0, 995.0, 886.0], 0.10)
        self.assertEqual(v["label"], pe.INDISTINGUISHABLE)

    def test_case_two_after_reducing_variance(self):
        quiet = [1000.0, 1016.0, 1008.0]
        self.assertLess(pe.detectable_difference(quiet), 0.03)
        v = pe.judge(quiet, [917.0, 925.0, 921.0], 0.10)
        self.assertNotEqual(v["label"], pe.INDISTINGUISHABLE)

    def test_a_worse_result_beyond_the_line_is_not_indistinguishable(self):
        v = pe.judge([1000.0, 1010.0, 1005.0], [1300.0, 1310.0, 1305.0], 0.10)
        self.assertEqual(v["label"], "低于预期")


class BoundaryTest(unittest.TestCase):
    def test_model_boundary_carries_the_crossover(self):
        text = pe.boundary_from_config(config())
        self.assertIn("16640", text)
        self.assertIn("Qwen2.5-0.5B", text)

    def test_build_report_fills_the_model_boundary(self):
        doc = one_round()
        report = pe.build_report(
            expectation=doc["expectation"],
            workload=doc["fixed"]["workload"],
            protocol=doc["fixed"]["protocol"],
            environment=doc["fixed"]["environment"],
            changed=doc["changed"],
            baseline=doc["results"]["baseline"],
            variant=doc["results"]["variant"],
            guardrails=doc["guardrails"],
            boundary={k: v for k, v in doc["boundary"].items() if k != "model"},
            config=config(),
        )
        self.assertIn("16640", report["boundary"]["model"])


class SampleTest(unittest.TestCase):
    """The synthetic evidence file 14.7 points readers at."""

    def setUp(self):
        self.doc = sample()

    def test_it_says_it_is_synthetic(self):
        self.assertTrue(self.doc["synthetic"])
        self.assertIn("合成数据", self.doc["_note"])

    def test_it_has_the_four_rounds_of_14_4(self):
        self.assertEqual(len(self.doc["rounds"]), 4)
        changed = [next(iter(r["changed"])) for r in self.doc["rounds"]]
        self.assertEqual(
            changed,
            ["retrieval_top_k", "enable_prefix_caching",
             "attention_backend", "enable_chunked_prefill"],
        )

    def test_round_four_primary_metric_is_short_request_itl(self):
        """14.4: the fourth round's main metric is not long-request TTFT."""
        self.assertEqual(
            self.doc["rounds"][3]["results"]["primary_metric"],
            "short_request_itl_p99_ms",
        )

    def test_round_four_records_the_long_request_cost(self):
        guardrails = self.doc["rounds"][3]["guardrails"]
        self.assertIn("long_request_ttft_p95_ms", guardrails)
        # 护栏越过了 SLO，报告必须把它写成一次交换，而不是「预期之内」。
        self.assertIn("SLO", guardrails["long_request_ttft_p95_ms"])
        self.assertIn("交换", guardrails["long_request_ttft_p95_ms"])

    def test_round_three_guardrail_is_quality_not_bit_identity(self):
        # 14.4：在线服务默认不保证逐 token 可复现，所以护栏是质量分。
        guardrails = self.doc["rounds"][2]["guardrails"]
        self.assertIn("quality_score", guardrails)
        self.assertNotIn("output_identical", guardrails)

    def test_every_round_boundary_quotes_the_real_arrival_rate(self):
        # P0-5：boundary 里写的到达率必须就是这一轮固定件里的那个。
        for round_ in self.doc["rounds"]:
            rate = round_["fixed"]["workload"]["arrival"]["rate"]
            self.assertIn(f"{rate} req/s", round_["boundary"]["workload"])

    def test_all_four_verdict_types_appear(self):
        labels = {r["verdict"]["label"] for r in self.doc["rounds"]}
        self.assertEqual(labels, set(pe.VERDICTS))

    def test_three_rounds_keep_the_same_baseline(self):
        ttft_rounds = [r for r in self.doc["rounds"]
                       if r["results"]["primary_metric"] == "ttft_p50_ms"]
        baselines = {tuple(r["results"]["baseline"]) for r in ttft_rounds}
        self.assertEqual(len(baselines), 1, "各轮必须从同一个 Baseline 出发（14.4）")

    def test_workload_and_protocol_are_identical_across_rounds(self):
        workloads = {json.dumps(r["fixed"]["workload"], sort_keys=True)
                     for r in self.doc["rounds"]}
        self.assertEqual(len(workloads), 1)

    def test_expectation_basis_cites_the_model(self):
        basis = self.doc["rounds"][0]["expectation"]["magnitude"]["ttft_p50_ms"]["basis"]
        self.assertIn("16640", basis)


class CliTest(unittest.TestCase):
    def test_main_checks_the_sample(self):
        code = pe.main([
            "--report", str(SAMPLE_PATH),
            "--model-config", str(CONFIG_PATH),
        ])
        self.assertEqual(code, 0)

    def test_main_without_a_report_explains_itself(self):
        self.assertEqual(pe.main([]), 2)

    def test_main_rejects_a_broken_report(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            doc = one_round()
            doc["guardrails"] = {}
            bad.write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual(pe.main(["--report", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
