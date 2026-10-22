#!/usr/bin/env python3
"""Tests for the Chapter 13 applicability self-check.

The three hard rules 13.7 documents get one test each, and the three classroom
cases in 13.8 get one apiece, because a case that the tool disagrees with is a
case the reader cannot trust.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch06"))
sys.path.insert(0, str(HERE.parent / "ch11"))
sys.path.insert(0, str(HERE.parent / "ch12"))

import context_cost as cc  # noqa: E402
import prefill_optimization_check as poc  # noqa: E402
from prefill_model import load_config  # noqa: E402

CONFIG_PATH = HERE.parent / "ch11" / "model-qwen25-05b.json"
SPEC_PATH = HERE.parent / "ch12" / "rag-prompt.json"


def config() -> dict:
    return load_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def bill(items: int = 10, *, order: list[int] | None = None) -> dict:
    doc = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    doc["segments"][2]["items"] = items
    if order is not None:
        doc["segments"] = [doc["segments"][i] for i in order]
    return cc.build_bill(doc, config())


def workload(**overrides) -> dict:
    doc = {
        "identity": {"name": "prefill-long-context", "type": "rag"},
        "length": {
            "prompt": {"p50": 2630, "p90": 6400, "p99": 9200, "max": 12000},
            "output": {"p50": 180, "p90": 320, "p99": 480},
        },
        "arrival": {"mode": "poisson", "rate": 8.0, "duration_s": 120.0,
                    "seed": 20260921},
        "slo": {"metric": "ttft", "quantile": "p95", "threshold_ms": 1500.0},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(doc.get(key), dict):
            doc[key] = {**doc[key], **value}
        else:
            doc[key] = value
    return doc


def by_path(doc: dict, path: str) -> dict:
    return next(o for o in doc["options"] if o["path"] == path)


class InputValidationTest(unittest.TestCase):
    def test_valid_inputs_pass(self):
        poc.validate_inputs(workload(), bill())

    def test_workload_without_length_is_rejected(self):
        doc = workload()
        del doc["length"]
        with self.assertRaises(poc.CheckError):
            poc.validate_inputs(doc, bill())

    def test_workload_without_p99_is_rejected(self):
        doc = workload()
        del doc["length"]["prompt"]["p99"]
        with self.assertRaises(poc.CheckError):
            poc.validate_inputs(doc, bill())

    def test_workload_without_arrival_is_rejected(self):
        doc = workload()
        del doc["arrival"]
        with self.assertRaises(poc.CheckError):
            poc.validate_inputs(doc, bill())

    def test_bill_without_cacheable_is_rejected(self):
        b = bill()
        del b["cacheable"]
        with self.assertRaises(poc.CheckError):
            poc.validate_inputs(workload(), b)


class HardRuleTest(unittest.TestCase):
    """The three rules 13.7 says are written into the script."""

    def setUp(self):
        self.config = config()

    def test_cacheable_below_thirty_percent_is_limited(self):
        doc = poc.build_options(workload(), bill(items=10), self.config)
        option = by_path(doc, "prefix_cache")
        self.assertEqual(option["applicable"], "有限")
        self.assertIn("低于三成", option["reason"])

    def test_cacheable_above_thirty_percent_is_applicable(self):
        doc = poc.build_options(workload(), bill(items=1), self.config)
        self.assertEqual(by_path(doc, "prefix_cache")["applicable"], "适用")

    def test_uniform_lengths_make_chunked_prefill_inapplicable(self):
        flat = workload()
        flat["length"]["prompt"] = {"p50": 3000, "p90": 3200, "p99": 3400,
                                    "max": 3600}
        doc = poc.build_options(flat, bill(), self.config)
        option = by_path(doc, "chunked_prefill")
        self.assertEqual(option["applicable"], "不适用")
        self.assertIn("长短差异不大", option["reason"])

    def test_no_quality_config_warns_on_trimming(self):
        doc = poc.build_options(workload(), bill(), self.config)
        option = by_path(doc, "context_trim")
        self.assertTrue(option["warnings"])
        self.assertIn("评测集", option["warnings"][0])

    def test_quality_config_silences_the_warning(self):
        wl = workload(quality_eval={"dataset": "support-200", "metric": "accuracy"})
        doc = poc.build_options(wl, bill(), self.config)
        self.assertFalse(by_path(doc, "context_trim")["warnings"])


class ClassroomCaseTest(unittest.TestCase):
    """13.8's three cases, checked against the tool."""

    def setUp(self):
        self.config = config()

    def test_case_one_short_prompts_limit_flash_attention(self):
        short = workload()
        short["length"]["prompt"] = {"p50": 600, "p90": 800, "p99": 2200,
                                     "max": 3000}
        doc = poc.build_options(short, bill(), self.config)
        option = by_path(doc, "flash_attention")
        self.assertEqual(option["applicable"], "有限")
        self.assertIn("搬运不是瓶颈", option["reason"])

    def test_case_one_long_prompts_make_it_applicable(self):
        doc = poc.build_options(workload(), bill(), self.config)
        self.assertEqual(by_path(doc, "flash_attention")["applicable"], "适用")

    def test_case_two_misordered_prefix_kills_the_cache(self):
        """Retrieval spliced in front of the system prompt."""
        misordered = bill(order=[2, 0, 1, 4])
        doc = poc.build_options(workload(), misordered, self.config)
        option = by_path(doc, "prefix_cache")
        self.assertEqual(option["applicable"], "有限")
        self.assertTrue(option["warnings"])

    def test_case_three_all_long_low_concurrency_is_inapplicable(self):
        serial = workload()
        serial["length"]["prompt"] = {"p50": 9000, "p90": 11000, "p99": 12000,
                                      "max": 14000}
        serial["arrival"] = {"mode": "closed", "concurrency": 1,
                             "duration_s": 120.0, "seed": 1}
        doc = poc.build_options(serial, bill(), self.config)
        self.assertEqual(by_path(doc, "chunked_prefill")["applicable"], "不适用")


class RoutingTest(unittest.TestCase):
    def setUp(self):
        self.config = config()

    def test_routing_term_matches_the_table_in_13_3(self):
        self.assertAlmostEqual(poc.routing_term(4, 2), 0.125, places=4)
        self.assertAlmostEqual(poc.routing_term(4, 10), 0.6225, places=3)
        self.assertAlmostEqual(poc.routing_term(4, 100), 0.96, places=2)
        self.assertEqual(poc.routing_term(1, 5), 1 - 1 / 5)

    def test_shared_prefix_is_not_cut_by_routing(self):
        shared = poc.build_options(
            workload(deployment={"replicas": 4, "prefix_scope": "shared"}),
            bill(items=1), self.config)
        self.assertIn("100.0%", by_path(shared, "prefix_cache")["expected"])

    def test_a_single_replica_still_pays_the_first_write(self):
        # 13.3：单实例那一行不是 100%，每个前缀第一次出现时总要写一次。
        single = poc.build_options(
            workload(deployment={"replicas": 1, "prefix_reuse": 2}),
            bill(items=1), self.config)
        self.assertIn("50.0%", by_path(single, "prefix_cache")["expected"])

    def test_session_prefix_uses_the_reuse_count(self):
        doc = poc.build_options(
            workload(deployment={"replicas": 4, "prefix_reuse": 2}), bill(items=1), self.config)
        option = by_path(doc, "prefix_cache")
        self.assertIn("12.5%", option["expected"])
        self.assertTrue(any("复用 2 次" in w for w in option["warnings"]))

    def test_random_routing_divides_the_ceiling(self):
        wl = workload(deployment={"replicas": 4, "cache_aware_routing": False})
        doc = poc.build_options(wl, bill(items=1), self.config)
        option = by_path(doc, "prefix_cache")
        self.assertTrue(any("四" in w or "4 副本" in w for w in option["warnings"]))
        self.assertIn("期望收益上限约", option["expected"])

    def test_a_missing_reuse_count_falls_back_to_reuse_twice(self):
        # P0-3：1/N 不是最坏情况，确有复用时的最小值在 k = 2，等于 1/(2N)。
        doc = poc.build_options(
            workload(deployment={"replicas": 4}), bill(items=1), self.config)
        option = by_path(doc, "prefix_cache")
        self.assertIn("12.5%", option["expected"])
        self.assertAlmostEqual(poc.routing_term(4, 2), 1 / (2 * 4), places=6)

    def test_cache_aware_routing_recovers_it(self):
        random_ = poc.build_options(
            workload(deployment={"replicas": 4}), bill(items=1), self.config
        )
        aware = poc.build_options(
            workload(deployment={"replicas": 4, "cache_aware_routing": True}),
            bill(items=1), self.config,
        )
        self.assertNotEqual(
            by_path(random_, "prefix_cache")["expected"],
            by_path(aware, "prefix_cache")["expected"],
        )
        # 它收回的是路由打散那一刀；首次写入那一刀留着，所以仍然不是 100%。
        self.assertIn("50.0%", by_path(aware, "prefix_cache")["expected"])


class ShapeTest(unittest.TestCase):
    def setUp(self):
        self.config = config()
        self.doc = poc.build_options(workload(), bill(), self.config)

    def test_all_four_paths_are_reported(self):
        self.assertEqual([o["path"] for o in self.doc["options"]], list(poc.PATHS))

    def test_every_verdict_is_one_of_three(self):
        for option in self.doc["options"]:
            self.assertIn(option["applicable"], poc.VERDICTS)

    def test_every_option_names_whose_metric_improves(self):
        for option in self.doc["options"]:
            self.assertTrue(option["improves_whose_metric"])
        self.assertEqual(
            by_path(self.doc, "chunked_prefill")["improves_whose_metric"],
            "其他请求",
        )

    def test_every_option_cites_an_input_field(self):
        for option in self.doc["options"]:
            self.assertTrue(option["evidence_field"])

    def test_order_follows_13_6(self):
        self.assertEqual(
            self.doc["try_in_this_order"],
            ["上下文裁剪", "Prefix Cache", "FlashAttention", "Chunked Prefill"],
        )

    def test_discipline_says_one_at_a_time(self):
        self.assertIn("一次只试一条", self.doc["discipline"])

    def test_trim_gain_exceeds_the_cut(self):
        """13.2: the gain beats the token cut, by a few points."""
        for tokens, expected in ((3000, 0.437), (8000, 0.478), (16640, 0.520)):
            gain = poc._trim_gain(self.config, tokens, 0.40)
            self.assertAlmostEqual(gain, expected, places=3)
            self.assertGreater(gain, 0.40)
            self.assertLess(gain, 0.60)


class CliTest(unittest.TestCase):
    def test_main_runs_the_whole_pipeline(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            wl = tmp_path / "workload.json"
            cost = tmp_path / "cost.json"
            out = tmp_path / "options.json"
            wl.write_text(json.dumps(workload()), encoding="utf-8")
            cost.write_text(json.dumps(bill()), encoding="utf-8")
            code = poc.main([
                "--workload", str(wl),
                "--context-cost", str(cost),
                "--model-config", str(CONFIG_PATH),
                "--output", str(out),
            ])
            self.assertEqual(code, 0)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(doc["options"]), 4)

    def test_main_rejects_a_bill_from_the_wrong_tool(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            wl = tmp_path / "workload.json"
            cost = tmp_path / "cost.json"
            wl.write_text(json.dumps(workload()), encoding="utf-8")
            cost.write_text(json.dumps({"totals": {"input_tokens": 100}}),
                            encoding="utf-8")
            code = poc.main([
                "--workload", str(wl),
                "--context-cost", str(cost),
                "--model-config", str(CONFIG_PATH),
            ])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
