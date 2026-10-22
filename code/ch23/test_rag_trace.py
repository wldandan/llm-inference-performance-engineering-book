#!/usr/bin/env python3
"""Tests for code/ch23/rag_trace.py.

23.3's pair is the thing most worth pinning: 3000 token → 600 ms and 9000 token
→ 2350 ms, a 3× token ratio against a 3.9× compute ratio, with the Attention
share going 15% → 35%. All of it comes out of Chapter 11's model, so these tests
also check that the two chapters have not drifted apart.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

import rag_trace as rt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch11"))
import prefill_model as pm  # noqa: E402

SAMPLE = (HERE.parent.parent / "content" / "ch23" / "evidence"
          / "rag-trace-sample.json")
CHAPTER = HERE.parent.parent / "content" / "ch23" / "ch23.md"
CONFIG_PATH = HERE.parent / "ch11" / "model-qwen25-05b.json"


def load_config():
    return pm.load_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def load_sample():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


class TestChapter11Model(unittest.TestCase):
    """23.3 的两个数必须是从第 11 章那个模型里出来的，不是抄上去的。"""

    @classmethod
    def setUpClass(cls):
        cls.config = load_config()

    def test_crossover_is_the_one_ch11_publishes(self):
        self.assertEqual(pm.crossover_tokens(self.config), 16640)

    def test_attention_share_at_3000_is_fifteen_percent(self):
        share = rt.attention_share(self.config, 3000)
        self.assertAlmostEqual(share, 3000 / 19640, places=9)
        self.assertEqual(round(share * 100), 15)

    def test_attention_share_at_9000_is_thirty_five_percent(self):
        share = rt.attention_share(self.config, 9000)
        self.assertAlmostEqual(share, 9000 / 25640, places=9)
        self.assertEqual(round(share * 100), 35)

    def test_three_times_the_tokens_is_three_point_nine_times_the_compute(self):
        ratio = (pm.relative_cost(self.config, 9000)
                 / pm.relative_cost(self.config, 3000))
        self.assertAlmostEqual(ratio, 3.9165, places=4)
        self.assertGreater(ratio, 3.0)

    def test_the_chapters_pair_reproduces_exactly(self):
        """600 ms 在 3000 token 上，代进模型给 9000 token 的 2350 ms。"""
        up = rt.ttft_after_context_change(self.config, 3000, 600.0, 9000)
        self.assertAlmostEqual(up, 2349.9, places=1)
        self.assertEqual(round(up / 50) * 50, 2350)

    def test_and_it_reverses(self):
        down = rt.ttft_after_context_change(self.config, 9000, 2350.0, 3000)
        self.assertAlmostEqual(down, 600.0, places=0)

    def test_the_saving_23_3_states(self):
        """2350 − 600 = 1750 ms，代价最多 300 ms，净收益 1450 到 1700 ms。"""
        saving = 2350.0 - 600.0
        self.assertEqual(saving, 1750.0)
        self.assertEqual(saving - 300, 1450.0)
        self.assertEqual(saving - 50, 1700.0)

    def test_zero_or_negative_tokens_rejected(self):
        for bad in (0, -100):
            with self.assertRaises(rt.TraceError):
                rt.attention_share(self.config, bad)
            with self.assertRaises(rt.TraceError):
                rt.ttft_after_context_change(self.config, 3000, 600.0, bad)


class TestValidation(unittest.TestCase):
    def test_missing_knowledge_base_version(self):
        doc = load_sample()
        doc["knowledge_base"].pop("version")
        with self.assertRaises(rt.TraceError) as ctx:
            rt.analyze(doc)
        self.assertIn("知识库版本", str(ctx.exception))

    def test_missing_cache_status(self):
        doc = load_sample()
        doc.pop("cache_status")
        with self.assertRaises(rt.TraceError) as ctx:
            rt.analyze(doc)
        self.assertIn("三层缓存", str(ctx.exception))

    def test_cache_enabled_without_a_hit_rate(self):
        """开着而不记命中率，这份 Baseline 之后没法和任何一次重测对比。"""
        doc = load_sample()
        doc["cache_status"]["prefix_cache"].pop("hit_rate")
        with self.assertRaises(rt.TraceError) as ctx:
            rt.analyze(doc)
        self.assertIn("命中率", str(ctx.exception))

    def test_cache_disabled_needs_no_hit_rate(self):
        doc = load_sample()
        doc["cache_status"]["prefix_cache"] = {"enabled": False}
        rt.analyze(doc)  # 不该报错

    def test_unlabelled_temperature(self):
        doc = load_sample()
        doc["calls"][0].pop("temperature")
        with self.assertRaises(rt.TraceError) as ctx:
            rt.analyze(doc)
        self.assertIn("冷热", str(ctx.exception))

    def test_all_warm_is_refused(self):
        """只有热查询时看不出冷热差多少，23.6 要求两组都有。"""
        doc = load_sample()
        for call in doc["calls"]:
            call["temperature"] = "warm"
        with self.assertRaises(rt.TraceError) as ctx:
            rt.analyze(doc)
        self.assertIn("两组数据", str(ctx.exception))

    def test_a_missing_stage_is_refused(self):
        doc = load_sample()
        doc["calls"][2]["stages"].pop("rerank")
        with self.assertRaises(rt.TraceError) as ctx:
            rt.analyze(doc)
        self.assertIn("算进别人头上", str(ctx.exception))

    def test_all_seven_stages_are_required(self):
        self.assertEqual(len(rt.STAGES), 7)
        for stage in rt.STAGES:
            doc = load_sample()
            doc["calls"][0]["stages"].pop(stage)
            with self.assertRaises(rt.TraceError):
                rt.analyze(doc)


class TestAnalyzeSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load_sample()
        cls.result = rt.analyze(cls.doc)

    def test_declared_synthetic(self):
        self.assertTrue(self.doc["synthetic"])
        self.assertIn("合成设定", self.doc["_note"])

    def test_shares_sum_to_one(self):
        """占比保留四位小数，七段各自最多差 0.00005，所以容差取 0.0004。"""
        self.assertAlmostEqual(sum(self.result["stage_share"].values()), 1.0,
                               delta=0.0004)

    def test_generation_and_before_generation_partition_the_time(self):
        self.assertAlmostEqual(
            self.result["generation_share"]
            + self.result["before_generation_share"], 1.0, places=4)

    def test_before_generation_is_the_part_this_chapter_is_about(self):
        """23.2：生成那两段已经在第 12、15 章讲过，这一章关注它之前的部分。"""
        self.assertAlmostEqual(self.result["before_generation_share"], 0.138,
                               places=3)

    def test_critical_path_is_the_three_largest_and_ordered(self):
        path = self.result["critical_path"]
        self.assertEqual([p["stage"] for p in path],
                         ["generate", "ttft", "rerank"])
        self.assertGreater(path[0]["ms"], path[1]["ms"])
        self.assertGreater(path[1]["ms"], path[2]["ms"])

    def test_cold_warm_gap_is_concentrated_in_retrieve(self):
        """23.2：检索的冷热差几倍，其他段基本不受影响。"""
        cw = self.result["cold_vs_warm"]
        self.assertEqual(cw["worst_stage"], "retrieve")
        self.assertGreater(cw["per_stage_ratio"]["retrieve"], 3.0)
        self.assertAlmostEqual(cw["per_stage_ratio"]["rerank"], 1.0, places=3)

    def test_the_total_gap_is_much_smaller_than_the_retrieve_gap(self):
        """检索冷起来 3.6 倍，端到端只慢 6.6%：这是占比小的那一段的上限。"""
        cw = self.result["cold_vs_warm"]
        self.assertGreater(cw["per_stage_ratio"]["retrieve"], 3.0)
        self.assertLess(cw["total_ratio"], 1.1)

    def test_all_retrieval_fields_present(self):
        self.assertEqual(self.result["retrieval_fields_missing"], [])

    def test_retrieval_fields_are_23_6_five(self):
        self.assertEqual(len(rt.RETRIEVAL_FIELDS), 5)
        doc = load_sample()
        doc["retrieval"].pop("query_repeat_rate")
        self.assertEqual(rt.analyze(doc)["retrieval_fields_missing"],
                         ["query_repeat_rate"])


class TestWhatIf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()

    def test_final_k_saving_on_the_sample_is_about_900_ms(self):
        """23.7 举的例子：把 final_k 从 15 降到 5 估出来省约 900 ms。"""
        r = rt.whatif(load_sample(), self.config, final_k=5)
        change = r["changes"][0]
        self.assertEqual(change["knob"], "final-k")
        self.assertAlmostEqual(change["saved_ms"], 899.116, places=2)
        self.assertEqual(round(change["saved_ms"] / 100) * 100, 900)

    def test_skip_rewrite_saving_is_180_ms(self):
        """而跳过改写只能省 180 ms，所以先做前者。"""
        r = rt.whatif(load_sample(), self.config, skip_rewrite=True)
        self.assertAlmostEqual(r["estimated_saving_ms"], 180.0)

    def test_priority_puts_final_k_first(self):
        r = rt.whatif(load_sample(), self.config, final_k=5,
                      skip_rewrite=True, rerank_candidates=50)
        self.assertEqual(r["priority"][0], "final-k")
        self.assertIn("按这个顺序动手", r["priority_reading"])

    def test_token_ratio_and_compute_ratio_differ(self):
        """这两个数不相等正是 23.3 的重点。"""
        r = rt.whatif(load_sample(), self.config, final_k=5)
        change = r["changes"][0]
        self.assertNotAlmostEqual(change["token_ratio"],
                                  change["compute_ratio"], places=2)
        self.assertLess(change["compute_ratio"], change["token_ratio"])

    def test_rerank_scales_linearly_with_candidates(self):
        """23.2：候选数翻倍，耗时翻倍。"""
        r = rt.whatif(load_sample(), self.config, rerank_candidates=100)
        self.assertAlmostEqual(r["stages_after_ms"]["rerank"], 105.0)
        r2 = rt.whatif(load_sample(), self.config, rerank_candidates=400)
        self.assertAlmostEqual(r2["stages_after_ms"]["rerank"], 420.0)

    def test_partial_skip_rewrite_share(self):
        r = rt.whatif(load_sample(), self.config, skip_rewrite=True,
                      skip_rewrite_share=0.4)
        self.assertAlmostEqual(r["estimated_saving_ms"], 72.0)

    def test_parallelising_the_main_chain_is_refused(self):
        """23.4：这条主链是串行的，把它并行掉等于卖一份不存在的时间。"""
        for stage in ("rewrite", "retrieve", "rerank", "generate"):
            with self.assertRaises(rt.TraceError) as ctx:
                rt.whatif(load_sample(), self.config, parallelize=[stage])
            self.assertIn("严格串行", str(ctx.exception))

    def test_parallelising_a_side_branch_is_allowed(self):
        r = rt.whatif(load_sample(), self.config,
                      parallelize=["retrieve_keyword"])
        self.assertTrue(r["is_estimate"])

    def test_inconsistent_context_composition_is_refused(self):
        """拼装口径对不上时先对齐，不要在错的基数上估算。"""
        doc = load_sample()
        doc["context_composition"]["tokens_per_chunk"] = 800
        with self.assertRaises(rt.TraceError) as ctx:
            rt.whatif(doc, self.config, final_k=5)
        self.assertIn("对不上", str(ctx.exception))

    def test_final_k_without_composition_is_refused(self):
        doc = load_sample()
        doc.pop("context_composition")
        with self.assertRaises(rt.TraceError):
            rt.whatif(doc, self.config, final_k=5)

    def test_output_always_says_it_is_an_estimate(self):
        r = rt.whatif(load_sample(), self.config, final_k=5)
        self.assertTrue(r["is_estimate"])
        self.assertIn("不替代实测", r["estimate_note"])
        self.assertIn("不能把这里的数字当成结果写进报告", r["estimate_note"])

    def test_no_knob_changes_nothing(self):
        r = rt.whatif(load_sample(), self.config)
        self.assertEqual(r["estimated_saving_ms"], 0.0)
        self.assertEqual(r["changes"], [])

    def test_the_three_knobs_are_additive_on_distinct_stages(self):
        """三个旋钮各动一段，所以总节省就是三项之和。"""
        r = rt.whatif(load_sample(), self.config, final_k=5,
                      skip_rewrite=True, rerank_candidates=50)
        total = sum(c["saved_ms"] for c in r["changes"])
        self.assertAlmostEqual(r["estimated_saving_ms"], total, places=2)


class TestCaseThreeArithmetic(unittest.TestCase):
    """23.8 案例三：12000 → 3200 token，单卡并发 18 → 62。

    并发上限与平均总长度成反比，所以这两个数隐含了一个输出长度：
    18 × (12000 + L) = 62 × (3200 + L) 解出 L = 400。正文要把它写出来，
    否则读者只按输入算会得到 67（Part 5 审阅 P2-6）。
    """

    def test_the_implied_output_length_is_the_one_the_text_states(self):
        implied = (62 * 3200 - 18 * 12000) / (18 - 62)
        self.assertAlmostEqual(implied, 400.0, places=6)
        text = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("按每条约 400 token 的输出算，单卡并发从 18 涨到 62", text)

    def test_input_only_would_give_a_different_number(self):
        self.assertAlmostEqual(18 * 12000 / 3200, 67.5, places=4)


class TestCacheLayers(unittest.TestCase):
    def test_three_layers_in_23_5_order(self):
        """23.5 按「跳过的链路从短到长」排，也就是风险从低到高。

        收益不是这个顺序：单次命中时检索结果缓存省得最少（Part 5 审阅 P0-6）。
        """
        self.assertEqual(rt.CACHE_LAYERS,
                         ("prefix_cache", "retrieval_cache", "answer_cache"))

    def test_the_sample_has_only_the_safest_layer_on(self):
        """23.5：从 Prefix Cache 开始做最安全，它不改变任何输出。"""
        doc = load_sample()
        self.assertTrue(doc["cache_status"]["prefix_cache"]["enabled"])
        self.assertFalse(doc["cache_status"]["retrieval_cache"]["enabled"])
        self.assertFalse(doc["cache_status"]["answer_cache"]["enabled"])


class TestCli(unittest.TestCase):
    def test_analyze_exits_zero(self):
        self.assertEqual(rt.main(["analyze", "--trace", str(SAMPLE)]), 0)

    def test_whatif_exits_zero(self):
        self.assertEqual(rt.main([
            "whatif", "--trace", str(SAMPLE), "--final-k", "5",
            "--skip-rewrite", "--rerank-candidates", "50"]), 0)

    def test_whatif_parallelising_the_main_chain_exits_one(self):
        self.assertEqual(rt.main([
            "whatif", "--trace", str(SAMPLE), "--parallelize", "rerank"]), 1)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(rt.main([]), 2)


class TestNumbersInTheProse(unittest.TestCase):
    """23.4 的扇出和 23.8 案例三的 TTFT，都按正文给出的式子复算。"""

    @classmethod
    def setUpClass(cls):
        cls.config = load_config()

    def test_fan_out_all_within_p95(self):
        self.assertAlmostEqual(0.95 ** 2, 0.9025)
        self.assertAlmostEqual(0.95 ** 3, 0.857, places=3)
        self.assertAlmostEqual(0.95 ** 10, 0.599, places=3)

    def test_per_branch_quantile_for_an_overall_p99(self):
        per_branch = 1 - 0.01 / 3
        self.assertAlmostEqual(per_branch ** 3, 0.99, places=4)

    def test_case_three_ttft_falls_faster_than_tokens(self):
        before = rt.ttft_after_context_change(self.config, 3000, 600.0, 12000)
        after = rt.ttft_after_context_change(self.config, 3000, 600.0, 3200)
        self.assertAlmostEqual(before, 3500, delta=5)
        self.assertAlmostEqual(after, 650, delta=5)
        self.assertGreater(1 - after / before, 1 - 3200 / 12000)

    def test_case_one_is_amdahl(self):
        """生成占 1400/3200，加速 2 倍，端到端最多省约 22%：3.2 秒到 2.5 秒。"""
        f = 1400 / 3200
        self.assertAlmostEqual(3200 * (1 - f * (1 - 1 / 2)), 2500.0)


if __name__ == "__main__":
    unittest.main()
