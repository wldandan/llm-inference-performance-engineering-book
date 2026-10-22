#!/usr/bin/env python3
"""Tests for the Chapter 12 context cost sheet."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch11"))

import context_cost as cc  # noqa: E402
from prefill_model import load_config  # noqa: E402

SPEC_PATH = HERE / "rag-prompt.json"
CONFIG_PATH = HERE.parent / "ch11" / "model-qwen25-05b.json"


def spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def config() -> dict:
    return load_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


class SpecValidationTest(unittest.TestCase):
    def test_sample_spec_is_valid(self):
        cc.validate_spec(spec())

    def test_unknown_source_is_rejected(self):
        doc = spec()
        doc["segments"][0]["source"] = "magic"
        with self.assertRaises(cc.SpecError):
            cc.validate_spec(doc)

    def test_both_tokens_and_per_item_is_rejected(self):
        doc = spec()
        doc["segments"][2]["tokens"] = 100
        with self.assertRaises(cc.SpecError):
            cc.validate_spec(doc)

    def test_per_item_without_items_is_rejected(self):
        doc = spec()
        del doc["segments"][2]["items"]
        with self.assertRaises(cc.SpecError):
            cc.validate_spec(doc)

    def test_quality_field_is_rejected(self):
        doc = spec()
        doc["quality_score"] = 0.79
        with self.assertRaises(cc.SpecError):
            cc.validate_spec(doc)

    def test_quality_on_a_segment_is_rejected(self):
        doc = spec()
        doc["segments"][2]["recall"] = 0.9
        with self.assertRaises(cc.SpecError):
            cc.validate_spec(doc)

    def test_duplicate_segment_names_are_rejected(self):
        doc = spec()
        doc["segments"][1]["name"] = doc["segments"][0]["name"]
        with self.assertRaises(cc.SpecError):
            cc.validate_spec(doc)

    def test_baseline_needs_both_fields(self):
        doc = spec()
        del doc["baseline"]["ttft_ms"]
        with self.assertRaises(cc.SpecError):
            cc.validate_spec(doc)


class BillTest(unittest.TestCase):
    """The numbers 12.1 through 12.4 print."""

    def setUp(self):
        self.config = config()

    def test_top_k_10_is_2630_tokens(self):
        bill = cc.build_bill(spec(), self.config)
        self.assertEqual(bill["totals"]["input_tokens"], 2630)

    def test_top_k_10_ttft_is_738ms(self):
        bill = cc.build_bill(spec(), self.config)
        self.assertAlmostEqual(bill["totals"]["estimated_ttft_ms"], 737.8, places=1)

    def test_12_4_table(self):
        """Top-K 3 / 5 / 10 / 20 -> tokens and TTFT."""
        expected = {3: (1230, 320.0), 5: (1630, 433.6), 10: (2630, 737.8),
                    20: (4630, 1433.7)}
        doc = spec()
        for items, (tokens, ttft) in expected.items():
            d = copy.deepcopy(doc)
            d["segments"][2]["items"] = items
            bill = cc.build_bill(d, self.config)
            self.assertEqual(bill["totals"]["input_tokens"], tokens)
            self.assertAlmostEqual(
                bill["totals"]["estimated_ttft_ms"], ttft, places=1,
                msg=f"Top-K={items} 的 TTFT 与 12.4 的表不符",
            )

    def test_12_1_ratio(self):
        """Top-K 3 -> 10 is 2.31x, matching the measured 320 -> 740 ms."""
        low, high = [], []
        for items, bucket in ((3, low), (10, high)):
            d = spec()
            d["segments"][2]["items"] = items
            bucket.append(cc.build_bill(d, self.config))
        ratio = (
            high[0]["totals"]["estimated_ttft_ms"]
            / low[0]["totals"]["estimated_ttft_ms"]
        )
        self.assertAlmostEqual(ratio, 2.31, places=2)

    def test_user_question_is_the_shortest_segment(self):
        bill = cc.build_bill(spec(), self.config)
        rows = [r for r in bill["segments"] if r["tokens"] > 0]
        shortest = min(rows, key=lambda r: r["tokens"])
        self.assertEqual(shortest["source"], "user")

    def test_retrieval_is_the_largest_segment(self):
        bill = cc.build_bill(spec(), self.config)
        largest = max(bill["segments"], key=lambda r: r["tokens"])
        self.assertEqual(largest["source"], "retrieval")

    def test_shares_sum_to_one(self):
        bill = cc.build_bill(spec(), self.config)
        self.assertAlmostEqual(sum(r["share"] for r in bill["segments"]), 1.0, places=3)

    def test_no_baseline_means_no_absolute_milliseconds(self):
        doc = spec()
        del doc["baseline"]
        bill = cc.build_bill(doc, self.config)
        self.assertIsNone(bill["totals"]["estimated_ttft_ms"])
        self.assertIn("不编绝对毫秒数", bill["totals"]["ttft_basis"])

    def test_output_tokens_are_explicitly_out_of_scope(self):
        bill = cc.build_bill(spec(), self.config)
        self.assertIn("输出", bill["totals"]["output_tokens_note"])


class CacheableTest(unittest.TestCase):
    def setUp(self):
        self.config = config()

    def test_prefix_excludes_the_trailing_user_question(self):
        bill = cc.build_bill(spec(), self.config)
        self.assertEqual(bill["cacheable"]["prefix_tokens"], 600)

    def test_12_2_two_notches(self):
        expected = {3: (0.488, 0.471), 10: (0.228, 0.204)}
        for items, (share, saving) in expected.items():
            d = spec()
            d["segments"][2]["items"] = items
            bill = cc.build_bill(d, self.config)
            self.assertAlmostEqual(
                bill["cacheable"]["prefix_share_of_tokens"], share, places=3
            )
            self.assertAlmostEqual(
                bill["cacheable"]["prefill_saving_if_fully_hit"], saving, places=3
            )

    def test_saving_is_below_the_token_share(self):
        """13.3: the cached prefix is the cheapest part of the prompt."""
        for items in (1, 3, 5, 10, 20):
            d = spec()
            d["segments"][2]["items"] = items
            bill = cc.build_bill(d, self.config)
            c = bill["cacheable"]
            self.assertLess(
                c["prefill_saving_if_fully_hit"], c["prefix_share_of_tokens"]
            )

    def test_13_3_sixty_percent_prefix_saves_less(self):
        cfg = self.config
        for total, expected in ((3000, 0.563), (8000, 0.522), (16640, 0.480)):
            saving = cc.prefix_cache_saving(cfg, total, int(total * 0.6))
            self.assertAlmostEqual(saving, expected, places=3)

    def test_fixed_segment_behind_a_variable_one_warns(self):
        """13.8 case 2: retrieval spliced in front of the system prompt."""
        doc = spec()
        doc["segments"] = [doc["segments"][2], doc["segments"][0],
                          doc["segments"][1], doc["segments"][4]]
        bill = cc.build_bill(doc, self.config)
        self.assertEqual(bill["cacheable"]["prefix_tokens"], 0)
        self.assertTrue(bill["warnings"])
        self.assertIn("前缀匹配", bill["warnings"][0])

    def test_verdict_reports_the_saving_not_a_thirty_percent_cutoff(self):
        # 13.6 的判据是「全命中省下的份额 × 请求命中的概率」和可识别线比，
        # 不是按可缓存占比一刀切，所以 verdict 报的是省下的份额本身。
        low = spec()
        low["segments"][2]["items"] = 20
        high = spec()
        high["segments"][2]["items"] = 1
        low_bill = cc.build_bill(low, self.config)
        high_bill = cc.build_bill(high, self.config)
        for b in (low_bill, high_bill):
            self.assertIn("请求命中概率", b["cacheable"]["verdict"])
            self.assertIn("可识别线", b["cacheable"]["verdict"])
            self.assertNotIn("走不通", b["cacheable"]["verdict"])
        self.assertLess(low_bill["cacheable"]["prefill_saving_if_fully_hit"],
                        high_bill["cacheable"]["prefill_saving_if_fully_hit"])


class SensitivityTest(unittest.TestCase):
    def setUp(self):
        self.config = config()

    def test_one_more_item_costs_200_tokens(self):
        bill = cc.build_bill(spec(), self.config)
        one = bill["sensitivity"]["one_more_item"]
        self.assertEqual(one["extra_input_tokens"], 200)
        self.assertGreater(one["extra_ttft_ms"], 0)

    def test_marginal_ttft_cost_grows_with_top_k(self):
        """Each extra segment costs more than the one before it (12.4)."""
        deltas = []
        previous = None
        for items in (3, 4, 10, 11, 20, 21):
            d = spec()
            d["segments"][2]["items"] = items
            ttft = cc.build_bill(d, self.config)["totals"]["estimated_ttft_ms"]
            if previous is not None and items % 2 == 0:
                deltas.append(ttft - previous)
            previous = ttft
        self.assertEqual(deltas, sorted(deltas))

    def test_without_a_retrieval_segment_it_says_so(self):
        doc = spec()
        doc["segments"] = [s for s in doc["segments"] if s["source"] != "retrieval"]
        bill = cc.build_bill(doc, self.config)
        self.assertFalse(bill["sensitivity"]["available"])


class CliTest(unittest.TestCase):
    def test_main_writes_a_bill(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bill.json"
            code = cc.main([
                "--prompt-spec", str(SPEC_PATH),
                "--model-config", str(CONFIG_PATH),
                "--output", str(out),
            ])
            self.assertEqual(code, 0)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(doc["totals"]["input_tokens"], 2630)
            self.assertIn("不评估质量", doc["disclaimer"])

    def test_main_rejects_a_spec_with_quality(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            doc = spec()
            doc["accuracy"] = 0.9
            bad.write_text(json.dumps(doc), encoding="utf-8")
            code = cc.main([
                "--prompt-spec", str(bad),
                "--model-config", str(CONFIG_PATH),
            ])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
