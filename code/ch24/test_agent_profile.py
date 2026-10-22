#!/usr/bin/env python3
"""Tests for code/ch24/agent_profile.py.

24.2's table and 24.3's two sums are pinned here: 0.95^N at N = 5 / 8 / 15 / 35
gives 77% / 66% / 46% / 17%, the inverse at 15 steps needs 99.66%, the 12-step
example sums to 174500 against a trapezoid estimate of 180000, and 案例二's
8-step task comes to exactly 92000.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import agent_profile as ap

HERE = Path(__file__).resolve().parent
TRACES = (HERE.parent.parent / "content" / "ch24" / "evidence"
          / "agent-traces-sample.jsonl")


def load():
    return ap.load_traces(TRACES)


def task(task_id, per_step_tokens, tools=None, duration=10000, **kw):
    n = len(per_step_tokens)
    tools = tools or [[] for _ in range(n)]
    doc = {"task_id": task_id, "type": "test", "duration_ms": duration,
           "steps": [{"index": i + 1, "llm_ms": 500,
                      "input_tokens": t, "output_tokens": 100,
                      "prefix_hit_rate": 0.7, "tools": tools[i]}
                     for i, t in enumerate(per_step_tokens)]}
    doc.update(kw)
    return doc


class TestStepSloTable(unittest.TestCase):
    def test_the_four_rows_24_2_tabulates(self):
        rows = ap.step_slo_table(0.95)
        self.assertEqual([r["steps"] for r in rows], [5, 8, 15, 35])
        self.assertEqual([r["percent"] for r in rows], [77, 66, 46, 17])

    def test_eight_steps_is_two_thirds(self):
        """单步 95% 达标的系统，八步任务只有三分之二达标。"""
        rate = ap.task_pass_rate(0.95, 8)
        self.assertAlmostEqual(rate, 0.6634, places=4)
        self.assertAlmostEqual(rate, 2 / 3, delta=0.01)

    def test_thirty_five_steps_is_under_two_tenths(self):
        self.assertLess(ap.task_pass_rate(0.95, 35), 0.20)
        self.assertAlmostEqual(ap.task_pass_rate(0.95, 35), 0.1661, places=4)

    def test_the_inverse_24_2_states(self):
        """要让 15 步任务做到 95%，单步需要 99.66%。"""
        need = ap.required_step_pass_rate(0.95, 15)
        self.assertAlmostEqual(need, 0.996586, places=6)
        self.assertEqual(round(need * 100, 2), 99.66)

    def test_inverse_round_trips(self):
        for steps in (3, 8, 15, 35):
            need = ap.required_step_pass_rate(0.95, steps)
            self.assertAlmostEqual(ap.task_pass_rate(need, steps), 0.95,
                                   places=9)

    def test_halving_steps_beats_lifting_the_step_rate(self):
        """砍掉一半步数换来的提升，是“先减步数”那条结论的量。"""
        r = ap.step_slo(0.95, 15, 0.95)
        self.assertEqual(r["halved_steps"], 7)
        self.assertGreater(r["halved_task_pass_rate"], r["task_pass_rate"])

    def test_retries_make_the_multiplicative_model_inapplicable(self):
        """24.2 自己说了带重试不适用，24.6 给了替代定义。"""
        with self.assertRaises(ap.ProfileError) as ctx:
            ap.step_slo(0.95, 15, None, retries_enabled=True)
        self.assertIn("24.6", str(ctx.exception))
        self.assertIn("任务在时限内完成", str(ctx.exception))

    def test_three_caveats_are_always_reported(self):
        caveats = ap.step_slo(0.95, 15, None)["caveats"]
        self.assertEqual(len(caveats), 3)
        self.assertIn("任务总时长", caveats[0])
        self.assertIn("更高", caveats[1])

    def test_correlated_steps_pass_together_more_often(self):
        """24.2：正相关让每一步都达标的比例高于 p^N（8 步、相关 0.3 时约 73%）。"""
        import random
        from statistics import NormalDist
        z = NormalDist().inv_cdf(0.95)
        rng = random.Random(5)
        trials, hits = 40000, 0
        r = 0.3
        for _ in range(trials):
            common = rng.gauss(0, 1)
            if all((r ** 0.5) * common + ((1 - r) ** 0.5) * rng.gauss(0, 1) <= z
                   for _ in range(8)):
                hits += 1
        self.assertAlmostEqual(hits / trials, 0.73, delta=0.015)
        self.assertGreater(hits / trials, ap.task_pass_rate(0.95, 8))

    def test_expected_steps_with_failures(self):
        """24.2：12 步、每步 10% 失败、每次失败多花 3 步，期望约 15.6 步。"""
        self.assertAlmostEqual(12 * (1 + 0.1 * 3), 15.6)

    def test_prefix_cache_collapses_prefill_to_the_last_step(self):
        """24.3：命中时整个任务的 Prefill 约等于末步输入，175000 → 28000。"""
        self.assertAlmostEqual(175000 / 28000, 6.25)

    def test_little_reverse_for_sub_agent_concurrency(self):
        """24.5：满载 12 QPS，从 0.5 推到 0.7，余 2.4 QPS；每个子 Agent 20 步 60 秒。"""
        spare = (0.7 - 0.5) * 12
        per_agent = 20 / 60
        self.assertAlmostEqual(spare / per_agent, 7.2)

    def test_out_of_range_rejected(self):
        for bad in (0.0, -0.1, 1.5):
            with self.assertRaises(ap.ProfileError):
                ap.task_pass_rate(bad, 5)
        with self.assertRaises(ap.ProfileError):
            ap.task_pass_rate(0.95, 0)


class TestTrapezoid(unittest.TestCase):
    def test_24_3_example(self):
        """12 × (2000 + 28000) / 2 = 180000。"""
        self.assertEqual(ap.trapezoid_tokens(12, 2000, 28000), 180000.0)

    def test_case_two_example(self):
        """8 × (3000 + 20000) / 2 = 92000。"""
        self.assertEqual(ap.trapezoid_tokens(8, 3000, 20000), 92000.0)

    def test_exact_when_increments_are_uniform(self):
        inputs = [3000 + k * (17000 / 7) for k in range(8)]
        got = ap.cumulative_tokens(inputs)
        self.assertAlmostEqual(got["exact"], got["trapezoid_estimate"],
                               places=2)

    def test_slightly_high_when_increments_grow(self):
        """增长量越到后面越大时梯形估算略微偏高，这是它的已知方向。"""
        inputs = [2000, 2200, 2600, 3400, 5000, 8200]
        got = ap.cumulative_tokens(inputs)
        self.assertGreater(got["trapezoid_estimate"], got["exact"])

    def test_one_step_task_rejected(self):
        with self.assertRaises(ap.ProfileError) as ctx:
            ap.cumulative_tokens([2000])
        self.assertIn("没有累积", str(ctx.exception))

    def test_naive_estimate_is_the_mistake_case_two_is_about(self):
        """把首步乘以步数，就是案例二那个低估好几倍的算法。"""
        inputs = [3000 + k * (17000 / 7) for k in range(8)]
        got = ap.cumulative_tokens(inputs)
        self.assertEqual(got["naive_first_step_times_steps"], 24000.0)
        self.assertAlmostEqual(got["naive_understates_by"], 92000 / 24000,
                               places=3)


class TestSampleTraces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = load()
        cls.profile = ap.build_profile(cls.tasks)

    def test_the_header_declares_it_synthetic(self):
        text = TRACES.read_text(encoding="utf-8")
        self.assertIn("合成设定", text.splitlines()[0])

    def test_ten_tasks(self):
        self.assertEqual(self.profile["task_count"], 10)

    def test_task_one_is_24_3s_example(self):
        t1 = next(t for t in self.tasks if t["task_id"] == "t-001")
        inputs = [s["input_tokens"] for s in t1["steps"]]
        self.assertEqual(len(inputs), 12)
        self.assertEqual(inputs[0], 2000)
        self.assertEqual(inputs[-1], 28000)
        got = ap.cumulative_tokens(inputs)
        self.assertEqual(got["exact"], 174500.0)
        self.assertEqual(got["trapezoid_estimate"], 180000.0)
        # 正文写的是“≈ 175000”，实际逐步累加是 174500，差 0.3%。
        self.assertAlmostEqual(got["exact"], 175000, delta=600)

    def test_the_estimate_error_on_that_example_is_about_three_percent(self):
        """正文说梯形估和逐步累加差 3%，这就是那 3%。"""
        t1 = next(t for t in self.tasks if t["task_id"] == "t-001")
        got = ap.cumulative_tokens([s["input_tokens"] for s in t1["steps"]])
        self.assertAlmostEqual(got["estimate_error_share"], 0.0315, places=4)

    def test_task_two_is_case_twos_bill(self):
        t2 = next(t for t in self.tasks if t["task_id"] == "t-002")
        inputs = [s["input_tokens"] for s in t2["steps"]]
        self.assertEqual(len(inputs), 8)
        self.assertEqual(inputs[0], 3000)
        self.assertEqual(inputs[-1], 20000)
        self.assertEqual(sum(inputs), 92000)

    def test_case_two_is_six_times_the_naive_estimate(self):
        """案例二 的标题：token 账单是估算的六倍。估算是 5 × 3000 = 15000。"""
        self.assertAlmostEqual(92000 / 15000, 6.133, places=3)

    def test_mean_steps_is_about_eight_but_max_is_forty(self):
        """24.2：步数的分布比平均值重要。"""
        self.assertEqual(self.profile["steps"]["p50"], 8.0)
        self.assertEqual(self.profile["steps"]["max"], 40.0)
        self.assertGreater(self.profile["steps"]["mean"],
                           self.profile["steps"]["p50"])

    def test_small_sample_percentile_warning(self):
        """十个任务时 P95 就是最大值，输出必须把这句话说出来。"""
        self.assertIsNotNone(self.profile["percentile_warning"])
        self.assertEqual(self.profile["steps"]["p95"],
                         self.profile["steps"]["max"])

    def test_no_warning_once_there_are_twenty_tasks(self):
        tasks = [task(f"x-{i}", [1000, 2000]) for i in range(20)]
        self.assertIsNone(ap.build_profile(tasks)["percentile_warning"])

    def test_shares_do_not_sum_to_one_by_construction(self):
        """未归属那一项单独成列，不摊进 LLM 和工具，否则缺口就看不见了。"""
        total = (self.profile["llm_time_share"]
                 + self.profile["tool_time_share"]
                 + self.profile["unaccounted_time_share"])
        self.assertAlmostEqual(total, 1.0, delta=0.001)
        self.assertGreater(self.profile["unaccounted_time_share"], 0.0)

    def test_tool_time_is_broken_down_by_name(self):
        """24.4：每个工具有自己的 Span，所以占比要按工具拆。"""
        by_name = self.profile["tool_time_by_name"]
        self.assertEqual(set(by_name), {"search", "read_file", "run_code"})
        self.assertAlmostEqual(sum(by_name.values()),
                               self.profile["tool_time_share"], delta=0.001)

    def test_code_execution_dominates_tool_time(self):
        """24.4：代码执行和外部 API 是最大的不确定源。"""
        by_name = self.profile["tool_time_by_name"]
        self.assertEqual(max(by_name, key=by_name.get), "run_code")

    def test_abandon_and_step_limit_rates(self):
        self.assertAlmostEqual(self.profile["abandon_rate"], 0.1)
        self.assertAlmostEqual(self.profile["step_limit_rate"], 0.1)
        self.assertEqual(self.profile["abandon_mean_step"], 9.0)

    def test_the_abandoned_step_is_inside_the_recorded_trace(self):
        """放弃之后不该还有步：trace 到哪一步为止，放弃就发生在哪一步（P2-8）。"""
        for task in self.tasks:
            if not task.get("abandoned"):
                continue
            self.assertLessEqual(task["abandoned_at_step"], len(task["steps"]))

    def test_all_the_fields_24_7_lists_are_present(self):
        for field in ap.PROFILE_FIELDS:
            self.assertIn(field, self.profile, field)


class TestProfileRefusals(unittest.TestCase):
    def test_a_step_without_a_tools_field_is_refused(self):
        """24.4：没有按工具拆开的 Span，工具等待这块时间在监控里是不存在的。"""
        bad = task("x", [1000, 2000])
        bad["steps"][1].pop("tools")
        with self.assertRaises(ap.ProfileError) as ctx:
            ap.build_profile([bad])
        self.assertIn("24.4", str(ctx.exception))

    def test_an_empty_tools_list_is_fine(self):
        ap.build_profile([task("x", [1000, 2000])])

    def test_a_tool_without_ms_is_refused(self):
        bad = task("x", [1000, 2000], tools=[[{"name": "search"}], []])
        with self.assertRaises(ap.ProfileError):
            ap.build_profile([bad])

    def test_missing_duration_is_refused(self):
        bad = task("x", [1000, 2000])
        bad.pop("duration_ms")
        with self.assertRaises(ap.ProfileError):
            ap.build_profile([bad])

    def test_all_single_step_tasks_are_refused(self):
        """一步的任务看不出上下文累积，而那是这一章的第二主张。"""
        with self.assertRaises(ap.ProfileError) as ctx:
            ap.build_profile([task("x", [1000]), task("y", [2000])])
        self.assertIn("第二主张", str(ctx.exception))

    def test_no_tasks_refused(self):
        with self.assertRaises(ap.ProfileError):
            ap.build_profile([])


class TestWastePatterns(unittest.TestCase):
    def test_three_consecutive_calls_are_not_a_pattern(self):
        """连续两三次调同一个工具是正常的，门槛设在四次。"""
        t = task("x", [1000] * 3,
                 tools=[[{"name": "read", "ms": 10}]] * 3)
        self.assertEqual(ap.find_waste(t), [])

    def test_four_consecutive_calls_are(self):
        t = task("x", [1000] * 4,
                 tools=[[{"name": "read", "ms": 10}]] * 4)
        found = ap.find_waste(t)
        self.assertEqual(found[0]["pattern"], "repeated_tool")
        self.assertEqual(found[0]["length"], 4)
        self.assertIn("工具粒度太细", found[0]["why"])

    def test_oscillation_between_two_tools(self):
        t = task("x", [1000] * 4,
                 tools=[[{"name": "run", "ms": 10}],
                        [{"name": "read", "ms": 10}],
                        [{"name": "run", "ms": 10}],
                        [{"name": "read", "ms": 10}]])
        patterns = [w["pattern"] for w in ap.find_waste(t)]
        self.assertIn("oscillation", patterns)

    def test_three_alternations_are_not_oscillation(self):
        t = task("x", [1000] * 3,
                 tools=[[{"name": "run", "ms": 10}],
                        [{"name": "read", "ms": 10}],
                        [{"name": "run", "ms": 10}]])
        self.assertNotIn("oscillation",
                         [w["pattern"] for w in ap.find_waste(t)])

    def test_same_resource_across_non_consecutive_steps(self):
        """不必连续：同一份长文档被反复解析，隔着几步也一样要重复付费。"""
        t = task("x", [1000] * 7,
                 tools=[[{"name": "read", "ms": 10, "resource": "big.log"}],
                        [{"name": "search", "ms": 10, "resource": "kb"}],
                        [{"name": "read", "ms": 10, "resource": "big.log"}],
                        [{"name": "search", "ms": 10, "resource": "kb"}],
                        [{"name": "read", "ms": 10, "resource": "big.log"}],
                        [{"name": "search", "ms": 10, "resource": "kb"}],
                        [{"name": "read", "ms": 10, "resource": "big.log"}]])
        found = [w for w in ap.find_waste(t) if w["pattern"] == "same_resource"]
        self.assertEqual(found[0]["resource"], "big.log")
        self.assertEqual(found[0]["length"], 4)

    def test_three_patterns_only(self):
        self.assertEqual(len(ap.WASTE_PATTERNS), 3)


class TestTail(unittest.TestCase):
    def test_shared_patterns_are_the_point(self):
        """修掉一个模式能同时改善很多任务，这是从长尾下手的全部理由。"""
        r = ap.tail(load(), percentile=0.7)
        self.assertGreaterEqual(len(r["shared_patterns"]), 2)
        self.assertIn("修掉一个模式", r["reading"])

    def test_no_shared_pattern_sends_you_to_24_5(self):
        tasks = [task(f"x-{i}", [1000, 2000, 3000]) for i in range(10)]
        r = ap.tail(tasks, percentile=0.9)
        self.assertEqual(r["shared_patterns"], [])
        self.assertIn("24.5", r["reading"])

    def test_tail_by_duration(self):
        r = ap.tail(load(), percentile=0.9, by="duration")
        self.assertEqual(r["by"], "duration")
        self.assertEqual(r["tail_tasks"][0]["task_id"], "t-009")

    def test_unknown_key_rejected(self):
        with self.assertRaises(ap.ProfileError):
            ap.tail(load(), by="tokens")

    def test_the_worst_task_carries_the_longest_repeat(self):
        r = ap.tail(load(), percentile=0.9)
        worst = r["tail_tasks"][0]
        repeats = [w for w in worst["waste"]
                   if w["pattern"] == "repeated_tool"]
        self.assertTrue(repeats)
        self.assertGreaterEqual(repeats[0]["length"], 10)


class TestCli(unittest.TestCase):
    def test_profile_exits_zero(self):
        self.assertEqual(ap.main(["profile", "--traces", str(TRACES)]), 0)

    def test_tail_exits_zero(self):
        self.assertEqual(ap.main(["tail", "--traces", str(TRACES),
                                  "--percentile", "0.7"]), 0)

    def test_step_slo_exits_zero(self):
        self.assertEqual(ap.main(["step-slo", "--steps", "15",
                                  "--task-target", "0.95"]), 0)

    def test_step_slo_with_retries_exits_one(self):
        self.assertEqual(ap.main(["step-slo", "--steps", "15",
                                  "--retries-enabled"]), 1)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(ap.main([]), 2)


if __name__ == "__main__":
    unittest.main()
