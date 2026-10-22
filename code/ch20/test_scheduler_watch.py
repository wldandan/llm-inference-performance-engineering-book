#!/usr/bin/env python3
"""Tests for code/ch20/scheduler_watch.py.

The numbers in 20.6 and 20.7 are pinned here so the text cannot drift away from
the script: the ρ/(1−ρ) table (1 / 4 / 9 / 19), the order of the three onsets,
and the lead time the sample trace is built to show.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import scheduler_watch as sw

HERE = Path(__file__).resolve().parent
SAMPLE = (HERE.parent.parent / "content" / "ch20" / "evidence"
          / "scheduler-trace-sample.json")


def ramp(values, *, interval=0.5, limit=64, kv=0.5, preempt=0, tokens=1000):
    """A trace from a list of running counts, everything else held flat."""
    samples = []
    for i, running in enumerate(values):
        samples.append({
            "t": round(i * interval, 3),
            "running": running,
            "waiting": 0,
            "running_ratio": round(running / limit, 4),
            "kv_usage": kv,
            "preemption_total": preempt,
            "batched_tokens": tokens,
        })
    return {"interval_s": interval, "running_limit": limit,
            "samples": samples}


class TestAmplification(unittest.TestCase):
    def test_the_four_values_in_20_6(self):
        """0.5 → 1, 0.8 → 4, 0.9 → 9, 0.95 → 19，正文那张表就是这四个数。"""
        self.assertAlmostEqual(sw.amplification(0.5), 1.0)
        self.assertAlmostEqual(sw.amplification(0.8), 4.0)
        self.assertAlmostEqual(sw.amplification(0.9), 9.0)
        self.assertAlmostEqual(sw.amplification(0.95), 19.0)

    def test_table_in_output_matches(self):
        table = sw.queue_model()["table"]
        self.assertEqual([r["rho"] for r in table], [0.5, 0.8, 0.9, 0.95])
        self.assertEqual([r["amplification"] for r in table],
                         [1.0, 4.0, 9.0, 19.0])

    def test_rho_at_or_above_one_is_rejected(self):
        for bad in (1.0, 1.2, 3.0):
            with self.assertRaises(sw.TraceError):
                sw.amplification(bad)

    def test_negative_rho_rejected(self):
        with self.assertRaises(sw.TraceError):
            sw.amplification(-0.1)

    def test_caveats_are_always_present(self):
        """20.6 的三处不符是输出的一部分，不是脚注。"""
        self.assertEqual(len(sw.queue_model()["caveats"]), 3)


class TestQueueModelReading(unittest.TestCase):
    def test_far_off_means_the_bottleneck_is_elsewhere(self):
        r = sw.queue_model(service_time_ms=400, rho=0.5,
                           measured_queue_ms=4000)
        self.assertEqual(r["predicted_queue_ms"], 400.0)
        self.assertEqual(r["measured_over_predicted"], 10.0)
        self.assertIn("瓶颈不在排队", r["reading"])

    def test_well_below_is_the_multi_server_effect(self):
        r = sw.queue_model(service_time_ms=400, rho=0.9,
                           measured_queue_ms=200)
        self.assertEqual(r["predicted_queue_ms"], 3600.0)
        self.assertIn("多服务台", r["reading"])

    def test_same_order_of_magnitude(self):
        r = sw.queue_model(service_time_ms=400, rho=0.8,
                           measured_queue_ms=1500)
        self.assertIn("同一量级", r["reading"])

    def test_no_measurement_says_it_is_not_a_prediction(self):
        r = sw.queue_model(service_time_ms=400, rho=0.8)
        self.assertIn("不是预测值", r["reading"])


class TestQueueTheoryOf20_6(unittest.TestCase):
    """20.6 的每个数都钉在这里：S、Kingman、P99、多服务台、突发消化。"""

    def test_s_and_rho_come_from_full_load_throughput(self):
        rho, s = sw.from_capacity(12, 10.8)
        self.assertAlmostEqual(rho, 0.9, places=6)
        self.assertAlmostEqual(s, 83.33, places=2)

    def test_arrival_at_or_above_capacity_is_refused(self):
        with self.assertRaises(sw.TraceError) as ctx:
            sw.from_capacity(12, 13)
        self.assertIn("线性增长", str(ctx.exception))

    def test_five_percent_more_at_70_and_at_90(self):
        """0.7 → 0.735 排队涨约 19%；0.9 → 0.945 从 9 个 S 涨到约 17 个。"""
        low = sw.amplification(0.735) / sw.amplification(0.7)
        self.assertAlmostEqual(low, 1.19, places=2)
        self.assertAlmostEqual(sw.amplification(0.945), 17.18, places=2)

    def test_kingman_reduces_to_mm1_and_grows_with_service_cv(self):
        self.assertEqual(sw.kingman_factor(1, 1), 1.0)
        self.assertAlmostEqual(sw.kingman_factor(1, 1.5), 1.625)

    def test_p99_wait_shape(self):
        """ρ = 0.9 时 P99 排队约 45 个 S，是平均 9 个的 5 倍。"""
        self.assertAlmostEqual(sw.p99_wait_factor(0.9), 45.0, places=1)
        self.assertEqual(sw.p99_wait_factor(0.005), 0.0)

    def test_p99_limit_bites_long_before_the_mean_limit(self):
        """排队上限 10 个 S：卡平均允许 ρ 到约 0.91，卡 P99 只允许到约 0.59。"""
        self.assertLessEqual(sw.amplification(0.909), 10.0)
        self.assertGreater(sw.amplification(0.92), 10.0)
        self.assertLessEqual(sw.p99_wait_factor(0.59), 10.0)
        self.assertGreater(sw.p99_wait_factor(0.60), 10.0)

    def test_erlang_c_reduces_to_mm1_with_one_server(self):
        self.assertAlmostEqual(sw.erlang_c(1, 0.9), 0.9)
        self.assertAlmostEqual(sw.multi_server_wait_factor(1, 0.9), 9.0)

    def test_sixty_four_slots_are_far_gentler_but_still_steep(self):
        """64 个槽位：0.9 时约 3.1 个 S，0.7 时几乎不排队。"""
        self.assertAlmostEqual(sw.multi_server_wait_factor(64, 0.9), 3.11, places=2)
        self.assertLess(sw.multi_server_wait_factor(64, 0.7), 0.02)
        self.assertGreater(sw.multi_server_wait_factor(64, 0.95),
                           3 * sw.multi_server_wait_factor(64, 0.9))

    def test_burst_drain_times(self):
        """1 分钟的三倍突发：ρ = 0.9 时约 17 分钟消化，0.7 时约 3.7 分钟。"""
        hot = sw.drain_seconds(0.9, 12, 3, 60)
        warm = sw.drain_seconds(0.7, 12, 3, 60)
        self.assertAlmostEqual(hot["drain_s"] / 60, 17.0, places=1)
        self.assertAlmostEqual(warm["drain_s"] / 60, 3.67, places=2)

    def test_burst_under_capacity_leaves_no_backlog(self):
        r = sw.drain_seconds(0.3, 12, 3, 60)
        self.assertEqual(r["backlog_requests"], 0.0)
        self.assertEqual(r["drain_s"], 0.0)

    def test_queue_model_reports_all_of_it(self):
        r = sw.queue_model(service_time_ms=1000 / 12, rho=0.9, slots=64,
                           capacity_qps=12, burst_factor=3, service_cv=1.5)
        self.assertAlmostEqual(r["predicted_queue_ms"], 1218.75, places=1)
        self.assertIn("multi_server_queue_ms", r)
        self.assertAlmostEqual(r["burst"]["drain_s"], 1020.0, places=0)


class TestPoissonCountsDoNotTriple(unittest.TestCase):
    def test_a_threefold_minute_is_thirty_five_sigma(self):
        """20.6：5 QPS 时一分钟到达约 300 条、标准差约 17，三倍是 +35σ。"""
        mean = 5 * 60
        sd = mean ** 0.5
        self.assertAlmostEqual((3 * mean - mean) / sd, 34.6, places=1)


class TestRhoFromTrace(unittest.TestCase):
    def test_time_average_is_the_proxy(self):
        trace = ramp([16, 32, 48])  # 0.25, 0.5, 0.75
        self.assertAlmostEqual(sw.rho_from_trace(trace), 0.5, places=4)

    def test_fully_saturated_trace_is_rejected_not_clamped(self):
        """全程满载时 ρ ≥ 1，悄悄改成 0.99 会给出一个看着合理的假数字。"""
        trace = ramp([64, 64, 64])
        with self.assertRaises(sw.TraceError) as ctx:
            sw.rho_from_trace(trace)
        self.assertIn("队列增长速度", str(ctx.exception))

    def test_no_running_ratio_is_rejected(self):
        trace = {"samples": [{"t": 0.0, "waiting": 0}]}
        with self.assertRaises(sw.TraceError):
            sw.rho_from_trace(trace)


class TestFirstSustained(unittest.TestCase):
    def test_returns_the_start_of_the_run_not_the_end(self):
        """onset 是条件开始的时刻；报确认窗口的末尾会让每个 lead_time 都偏短。"""
        samples = [{"t": float(i), "waiting": w}
                   for i, w in enumerate([0, 0, 1, 1, 1, 1])]
        self.assertEqual(
            sw.first_sustained(samples, "waiting", lambda v: v > 0, 3), 2.0)

    def test_single_spike_is_not_an_onset(self):
        samples = [{"t": float(i), "waiting": w}
                   for i, w in enumerate([0, 5, 0, 0, 0])]
        self.assertIsNone(
            sw.first_sustained(samples, "waiting", lambda v: v > 0, 3))

    def test_run_must_be_consecutive(self):
        samples = [{"t": float(i), "waiting": w}
                   for i, w in enumerate([1, 1, 0, 1, 1])]
        self.assertIsNone(
            sw.first_sustained(samples, "waiting", lambda v: v > 0, 3))

    def test_missing_values_break_the_run(self):
        samples = [{"t": 0.0, "waiting": 1}, {"t": 1.0},
                   {"t": 2.0, "waiting": 1}, {"t": 3.0, "waiting": 1}]
        self.assertEqual(
            sw.first_sustained(samples, "waiting", lambda v: v > 0, 2), 2.0)


class TestAnalyzeRefusals(unittest.TestCase):
    def test_trace_shorter_than_sustain(self):
        trace = ramp([64, 64])
        with self.assertRaises(sw.TraceError) as ctx:
            sw.analyze(trace, sustain=3)
        self.assertIn("确认不了", str(ctx.exception))

    def test_missing_running_ratio_is_refused_not_guessed(self):
        """缺 running_limit 时最早动的那个信号无从计算，20.7 的整条推理就断了。"""
        trace = ramp([64, 64, 64])
        for s in trace["samples"]:
            s.pop("running_ratio")
        with self.assertRaises(sw.TraceError) as ctx:
            sw.analyze(trace)
        self.assertIn("最早动", str(ctx.exception))

    def test_missing_preemption_counter_is_refused(self):
        trace = ramp([64, 64, 64])
        for s in trace["samples"]:
            s.pop("preemption_total")
        with self.assertRaises(sw.TraceError) as ctx:
            sw.analyze(trace)
        self.assertIn("最严重", str(ctx.exception))


class TestVerdicts(unittest.TestCase):
    def test_idle_trace_cannot_be_used_to_set_parameters(self):
        trace = ramp([12, 13, 12, 14, 13], kv=0.3)
        r = sw.analyze(trace)
        self.assertEqual(r["verdict"], "未饱和")
        self.assertIn("不能用来定参数", r["verdict_reason"])
        self.assertIsNone(r["lead_time"])

    def test_preemption_means_kv(self):
        trace = ramp([64, 64, 64, 64], kv=0.6)
        for i, s in enumerate(trace["samples"]):
            s["waiting"] = 2
            s["preemption_total"] = 0 if i == 0 else 4
        r = sw.analyze(trace)
        self.assertEqual(r["verdict"], "KV 不足")
        self.assertIn("第 16 章", r["verdict_reason"])

    def test_high_kv_without_preemption_still_means_kv(self):
        trace = ramp([64, 64, 64, 64], kv=0.94)
        for s in trace["samples"]:
            s["waiting"] = 1
        r = sw.analyze(trace)
        self.assertEqual(r["verdict"], "KV 不足")

    def test_token_budget_binds_when_request_count_does_not(self):
        """请求数没到上限而单步 token 触顶，这是 max_num_batched_tokens 在限制。"""
        trace = ramp([36, 36, 36, 36], kv=0.5, tokens=2040)
        trace["max_num_batched_tokens"] = 2048
        trace["tokens_per_step"] = True
        for s in trace["samples"]:
            s["waiting"] = 3
        r = sw.analyze(trace)
        self.assertEqual(r["verdict"], "token 预算不足")
        self.assertIn("max_num_seqs", r["verdict_reason"])

    def test_interval_sampled_tokens_do_not_trigger_the_budget_verdict(self):
        """collect 的 batched_tokens 是一个采样间隔里所有步的累计，不是单步值。

        拿它和每步的预算比，任何繁忙的服务都会误报，所以没声明按步采的 trace
        不做这项判断（20.8）。
        """
        trace = ramp([36, 36, 36, 36], kv=0.5, tokens=2040)
        trace["max_num_batched_tokens"] = 2048
        for s in trace["samples"]:
            s["waiting"] = 3
        r = sw.analyze(trace)
        self.assertEqual(r["verdict"], "请求数上限约束")

    def test_seq_limit_binds_when_nothing_else_is_at_its_ceiling(self):
        trace = ramp([64, 64, 64, 64], kv=0.5, tokens=800)
        trace["max_num_batched_tokens"] = 2048
        for s in trace["samples"]:
            s["waiting"] = 3
        r = sw.analyze(trace)
        self.assertEqual(r["verdict"], "请求数上限约束")
        self.assertIn("第 19 章", r["verdict_reason"])


class TestLeadTime(unittest.TestCase):
    def test_queue_before_saturation_inverts_the_alerting_advice(self):
        """20.7 的顺序被打破本身就是结论：告警配在 running_ratio 上会失灵。"""
        trace = ramp([20, 20, 20, 64, 64, 64], kv=0.5)
        for s in trace["samples"]:
            s["waiting"] = 4
        r = sw.analyze(trace)
        self.assertIsNotNone(r["lead_time"])
        self.assertLessEqual(r["lead_time"], 0)
        self.assertIn("失灵", r["lead_time_note"])

    def test_saturated_but_never_queued(self):
        trace = ramp([64, 64, 64, 64], kv=0.5, tokens=800)
        r = sw.analyze(trace)
        self.assertIsNone(r["lead_time"])
        self.assertIn("再加流量", r["lead_time_note"])

    def test_slo_itl_only_adds_a_cross_reference(self):
        """这个脚本采的是调度器状态，不是 ITL，不该假装判得了 ITL。"""
        trace = ramp([64, 64, 64], kv=0.5)
        r = sw.analyze(trace, slo_itl_ms=80)
        self.assertEqual(r["slo_itl_ms"], 80)
        self.assertIn("第 19 章", r["itl_note"])


class TestPrometheusParsing(unittest.TestCase):
    def test_comments_and_blanks_skipped(self):
        text = "# HELP x\n# TYPE x gauge\n\nvllm:num_requests_running 7.0\n"
        self.assertEqual(sw.parse_prometheus(text),
                         {"vllm:num_requests_running": 7.0})

    def test_labelled_series_are_summed(self):
        text = ('vllm:num_requests_waiting{model="a"} 3\n'
                'vllm:num_requests_waiting{model="b"} 4\n')
        self.assertEqual(sw.parse_prometheus(text)["vllm:num_requests_waiting"],
                         7.0)

    def test_non_numeric_values_skipped(self):
        self.assertEqual(sw.parse_prometheus("vllm:x NaNish\n"), {})

    def test_candidate_names_are_tried_in_order(self):
        metrics = {"vllm:kv_cache_usage_perc": 0.42}
        self.assertEqual(sw.pick(metrics, "kv_usage"), 0.42)
        self.assertIsNone(sw.pick({}, "kv_usage"))


class TestCollect(unittest.TestCase):
    def _fetch_factory(self, bodies):
        state = {"i": 0}

        def fetch(_url):
            i = min(state["i"], len(bodies) - 1)
            state["i"] += 1
            return bodies[i]
        return fetch

    def test_cumulative_token_counter_is_differenced(self):
        """/metrics 给的是累计值；不差分的话和 20.8 那张表里的“本步”不是一回事。"""
        bodies = [
            "vllm:num_requests_running 32\nvllm:num_requests_waiting 0\n"
            "vllm:prompt_tokens_total 1000\n",
            "vllm:num_requests_running 32\nvllm:num_requests_waiting 0\n"
            "vllm:prompt_tokens_total 1600\n",
        ]
        trace = sw.collect("http://x", interval=0.01, duration=0.01,
                           running_limit=64,
                           fetch=self._fetch_factory(bodies))
        self.assertEqual(len(trace["samples"]), 2)
        # 第一个样本没有前一个可减，所以必须是空，不能是 1000。
        self.assertIsNone(trace["samples"][0]["batched_tokens"])
        self.assertEqual(trace["samples"][1]["batched_tokens"], 600)

    def test_running_ratio_only_when_a_limit_is_given(self):
        body = "vllm:num_requests_running 32\n"
        trace = sw.collect("http://x", interval=0.01, duration=0.0,
                           running_limit=None,
                           fetch=self._fetch_factory([body]))
        self.assertEqual(len(trace["samples"]), 1)
        self.assertNotIn("running_ratio", trace["samples"][0])
        trace = sw.collect("http://x", interval=0.01, duration=0.0,
                           running_limit=64,
                           fetch=self._fetch_factory([body]))
        self.assertEqual(trace["samples"][0]["running_ratio"], 0.5)

    def test_sample_count_is_determined_by_duration_and_interval(self):
        body = "vllm:num_requests_running 8\n"
        trace = sw.collect("http://x", interval=0.001, duration=0.004,
                           running_limit=64,
                           fetch=self._fetch_factory([body]))
        self.assertEqual(len(trace["samples"]), 5)


class TestSampleTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
        cls.result = sw.analyze(cls.doc)

    def test_declared_synthetic(self):
        self.assertTrue(self.doc["synthetic"])
        self.assertIn("合成设定", self.doc["_note"])

    def test_three_onsets_arrive_in_the_order_20_7_states(self):
        r = self.result
        self.assertEqual(r["saturation_onset"], 15.0)
        self.assertEqual(r["queue_onset"], 25.0)
        self.assertEqual(r["preemption_onset"], 40.0)
        self.assertLess(r["saturation_onset"], r["queue_onset"])
        self.assertLess(r["queue_onset"], r["preemption_onset"])

    def test_lead_time_is_ten_seconds(self):
        self.assertEqual(self.result["lead_time"], 10.0)
        self.assertIn("来得及", self.result["lead_time_note"])

    def test_verdict_is_kv(self):
        self.assertEqual(self.result["verdict"], "KV 不足")

    def test_rho_proxy_lands_in_the_steep_part_of_the_curve(self):
        """0.869 的 ρ 放大 6.6 倍，正是 20.6 想让读者看到的那一段。"""
        rho = sw.rho_from_trace(self.doc)
        self.assertAlmostEqual(rho, 0.869, places=3)
        self.assertGreater(sw.amplification(rho), 4.0)
        self.assertLess(sw.amplification(rho), 9.0)

    def test_every_sample_has_all_six_fields(self):
        for s in self.doc["samples"]:
            for field in sw.SAMPLE_FIELDS:
                self.assertIn(field, s)


class TestCli(unittest.TestCase):
    def test_analyze_exits_zero_on_the_sample(self):
        self.assertEqual(sw.main(["analyze", "--trace", str(SAMPLE)]), 0)

    def test_queue_model_exits_zero(self):
        self.assertEqual(sw.main(["queue-model", "--rho", "0.9",
                                  "--service-time-ms", "400"]), 0)

    def test_queue_model_from_capacity_exits_zero(self):
        self.assertEqual(sw.main(["queue-model", "--capacity-qps", "12",
                                  "--arrival-qps", "10.8", "--slots", "64",
                                  "--burst-factor", "3"]), 0)

    def test_overload_exits_one(self):
        self.assertEqual(sw.main(["queue-model", "--capacity-qps", "12",
                                  "--arrival-qps", "12"]), 1)

    def test_bad_rho_exits_one(self):
        self.assertEqual(sw.main(["queue-model", "--rho", "1.0"]), 1)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(sw.main([]), 2)


if __name__ == "__main__":
    unittest.main()
