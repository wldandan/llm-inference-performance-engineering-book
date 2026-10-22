#!/usr/bin/env python3
"""Tests for code/ch22/serving_choice.py.

The numbers 22.4, 22.5 and 22.8 state are pinned here: 13.3's routing term for
a session prefix (N = 4: 12.5% / 62% / 96% at k = 2 / 10 / 100), the two skew
anchors (0 and 2.0 on the sample-stdev convention), the hottest-instance and
rolling-upgrade loads, and 案例二's before-and-after (90% single instance, about
three tenths on round-robin, about 80% with overflow).
"""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

import serving_choice as sc

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent.parent / "content" / "ch22" / "evidence"
WORKLOAD = EVIDENCE / "workload-knowledge-base.json"
ROUTE_SAMPLE = EVIDENCE / "route-eval-sample.json"


def inst(req, hit, p95):
    return {"requests": req, "cache_hit_rate": hit, "p95_ttft": p95}


class TestRoutingTerm(unittest.TestCase):
    def test_the_rows_22_4_tabulates(self):
        """N = 4：k = 2 是 12.5%，k = 10 约 62%，k = 100 约 96%。"""
        self.assertAlmostEqual(sc.routing_term(4, 2), 0.125)
        self.assertAlmostEqual(sc.routing_term(4, 10), 0.623, places=3)
        self.assertAlmostEqual(sc.routing_term(4, 100), 0.960, places=3)
        self.assertAlmostEqual(sc.routing_term(8, 10), 0.410, places=3)

    def test_one_instance_only_pays_the_first_write(self):
        self.assertAlmostEqual(sc.routing_term(1, 10), 0.9)

    def test_a_shared_prefix_is_barely_touched(self):
        """全体共享的前缀复用次数极大，轮询下照样命中。"""
        self.assertGreater(sc.routing_term(8, 100000), 0.999)

    def test_doubling_replicas_roughly_halves_it_when_reuse_is_low(self):
        """复用少时按副本数的倒数走，不是线性下降。"""
        self.assertAlmostEqual(sc.routing_term(4, 2) / sc.routing_term(8, 2), 2.0)

    def test_same_formula_as_chapter_13(self):
        import importlib.util
        path = HERE.parent / "ch13" / "prefill_optimization_check.py"
        spec = importlib.util.spec_from_file_location("ch13check", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for n, k in ((4, 2), (4, 10), (8, 100)):
            self.assertAlmostEqual(sc.routing_term(n, k), mod.routing_term(n, k))


class TestHitRateCeiling(unittest.TestCase):
    def test_round_robin_is_bounded_only_by_the_cacheable_share(self):
        """1/N 不是天花板：全体共享的前缀轮询下照样命中。"""
        for n in (1, 4, 8):
            self.assertAlmostEqual(
                sc.hit_rate_ceiling(0.60, n, "round-robin"), 0.60)

    def test_prefix_hash_pulls_the_route_cut_back_to_one(self):
        for n in (1, 4, 8, 32):
            self.assertAlmostEqual(
                sc.hit_rate_ceiling(0.60, n, "prefix-hash"), 0.60)

    def test_overflow_costs_the_share_that_does_not_land_back_home(self):
        self.assertAlmostEqual(
            sc.hit_rate_ceiling(0.90, 4, "prefix-hash-with-overflow", 0.1),
            0.90 * (1 - 0.1 * 0.75))

    def test_unknown_strategy_rejected(self):
        with self.assertRaises(sc.ChoiceError):
            sc.hit_rate_ceiling(0.6, 4, "least-connections")

    def test_cacheable_share_out_of_range_rejected(self):
        with self.assertRaises(sc.ChoiceError):
            sc.hit_rate_ceiling(1.2, 4, "round-robin")

    def test_scaling_table_matches_the_chapter(self):
        rows = sc.scaling_table(0.60)
        self.assertEqual([r["instances"] for r in rows], [1, 4, 8])
        self.assertEqual([round(r["routing_term"][2], 4) for r in rows],
                         [0.5, 0.125, 0.0625])
        self.assertAlmostEqual(rows[1]["hit_rate_upper"][2], 0.075)


class TestLoadArithmetic(unittest.TestCase):
    def test_hottest_instance_at_skew_point_three(self):
        """N = 4、平均 0.7、不均衡度 0.3：最热实例最坏约 1.0，已经贴着满载。"""
        self.assertAlmostEqual(sc.hottest_instance_load(0.7, 0.3, 4), 1.015)

    def test_hottest_instance_bound_is_tight_when_one_takes_all(self):
        counts = [4, 0, 0, 0]
        skew = sc.load_skew(counts)
        self.assertAlmostEqual(sc.hottest_instance_load(1.0, skew, 4), 4.0)

    def test_rolling_upgrade_load(self):
        """平时 85%：4 个实例升级时 113%，12 个实例时约 93%。"""
        self.assertAlmostEqual(sc.upgrade_load(0.85, 4), 1.1333, places=4)
        self.assertAlmostEqual(sc.upgrade_load(0.85, 12), 0.9273, places=4)

    def test_modulo_and_consistent_hashing_retention(self):
        """取模哈希 12 → 11 只保住 8%，12 → 4 碰巧和一致性哈希一样保住三分之一。"""
        def modulo_keep(n, m, keys=120000):
            return sum(1 for h in range(keys) if h % n == h % m) / keys
        self.assertAlmostEqual(modulo_keep(12, 11), 1 / 12, places=3)
        self.assertAlmostEqual(modulo_keep(12, 8), 1 / 3, places=3)
        self.assertAlmostEqual(modulo_keep(12, 4), 1 / 3, places=3)


class TestLoadSkew(unittest.TestCase):
    def test_perfectly_balanced_is_zero(self):
        self.assertAlmostEqual(sc.load_skew([25, 25, 25, 25]), 0.0)

    def test_one_instance_taking_everything_is_two(self):
        """22.4：四个实例里有一个接了全部流量是 2.0（样本标准差，和第 7 章同口径）。"""
        self.assertAlmostEqual(sc.load_skew([100, 0, 0, 0]), 2.0, places=6)

    def test_single_instance_has_no_skew(self):
        self.assertEqual(sc.load_skew([100]), 0.0)

    def test_all_zero_rejected(self):
        with self.assertRaises(sc.ChoiceError):
            sc.load_skew([0, 0, 0])

    def test_negative_rejected(self):
        with self.assertRaises(sc.ChoiceError):
            sc.load_skew([10, -1])

    def test_the_two_thresholds_22_4_gives(self):
        self.assertIn("感觉不到", sc.read_skew(0.28))
        self.assertIn("还不决定 P99", sc.read_skew(0.40))
        self.assertIn("决定整体 P99", sc.read_skew(0.71))

    def test_thresholds_are_inclusive_at_zero_point_three(self):
        self.assertIn("感觉不到", sc.read_skew(0.3))
        self.assertNotIn("感觉不到", sc.read_skew(0.3001))


class TestEvaluateStrategy(unittest.TestCase):
    def test_hit_rate_is_weighted_by_requests(self):
        """轻载实例的高命中率不该和满载实例的低命中率等权。"""
        r = sc.evaluate_strategy(
            "prefix-hash",
            [inst(900, 0.90, 500.0), inst(100, 0.10, 500.0)],
            cacheable_share=0.95)
        self.assertAlmostEqual(r["cache_hit_rate"], 0.82, places=6)

    def test_hit_rate_above_the_cacheable_share_is_rejected(self):
        """可缓存占比是天花板；超过说明量错了，不是缓存赢了物理。"""
        with self.assertRaises(sc.ChoiceError) as ctx:
            sc.evaluate_strategy("prefix-hash", [inst(100, 0.95, 500.0)],
                                 cacheable_share=0.60)
        self.assertIn("天花板", str(ctx.exception))

    def test_weighted_rate_above_the_declared_overflow_ceiling_is_rejected(self):
        """溢出比例是配置不是实测，所以它和实际跑出来的数最容易对不上。"""
        with self.assertRaises(sc.ChoiceError) as ctx:
            sc.evaluate_strategy(
                "prefix-hash-with-overflow",
                [inst(100, 0.90, 500.0), inst(100, 0.90, 500.0)],
                cacheable_share=0.91, overflow_share=0.30)
        self.assertIn("溢出比例", str(ctx.exception))

    def test_missing_per_instance_field_rejected(self):
        bad = {"requests": 100, "cache_hit_rate": 0.5}
        with self.assertRaises(sc.ChoiceError) as ctx:
            sc.evaluate_strategy("round-robin", [bad], cacheable_share=0.9)
        self.assertIn("22.5", str(ctx.exception))

    def test_worst_instance_is_by_p95_not_by_load(self):
        """最差实例挑的是最慢的那个，不是接得最多的那个。"""
        r = sc.evaluate_strategy(
            "prefix-hash",
            [inst(2000, 0.9, 700.0), inst(200, 0.9, 1500.0)],
            cacheable_share=0.9, p95_ttft=800.0)
        self.assertEqual(r["worst_instance"]["index"], 1)
        self.assertEqual(r["aggregate_hides"], 700.0)


class TestRouteEvalSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(ROUTE_SAMPLE.read_text(encoding="utf-8"))
        cls.result = sc.route_eval(cls.doc)

    def test_declared_synthetic(self):
        self.assertTrue(self.doc["synthetic"])
        self.assertIn("合成设定", self.doc["_note"])

    def test_case_two_single_instance_baseline(self):
        self.assertEqual(self.doc["single_instance_baseline"]["cache_hit_rate"],
                         0.90)
        self.assertEqual(self.doc["single_instance_baseline"]["p95_ttft"], 600.0)

    def test_case_two_is_a_session_prefix(self):
        """1/N 那一刀只对会话级前缀成立，所以案例二必须是会话级的。"""
        self.assertEqual(self.doc["prefix_scope"], "session")

    def test_round_robin_falls_to_about_three_tenths(self):
        """案例二：轮询打散加上缓存装不下，命中率掉到三成左右。"""
        row = self._row("round-robin")
        self.assertAlmostEqual(row["cache_hit_rate"], 0.296, places=3)
        self.assertLess(row["cache_hit_rate"],
                        sc.routing_term(4, 10) * self.doc["cacheable_share"])

    def test_overflow_returns_to_about_eighty_percent(self):
        row = self._row("prefix-hash-with-overflow")
        self.assertAlmostEqual(row["cache_hit_rate"], 0.799, places=3)
        self.assertEqual(row["p95_ttft"], 680.0)

    def test_pure_prefix_hash_wins_on_hit_rate_and_loses_on_p99(self):
        """22.4：纯按前缀亲和会导致热点，必须有一个溢出机制。"""
        pure = self._row("prefix-hash")
        overflow = self._row("prefix-hash-with-overflow")
        self.assertGreater(pure["cache_hit_rate"], overflow["cache_hit_rate"])
        self.assertGreater(pure["load_skew"], sc.SKEW_P99_DOMINATED)
        self.assertGreater(pure["p95_ttft"], overflow["p95_ttft"])
        self.assertGreater(pure["worst_instance"]["p95_ttft"],
                           overflow["worst_instance"]["p95_ttft"])

    def test_the_conflict_is_real_and_the_practical_pick_is_the_third_form(self):
        self.assertTrue(self.result["conflict"])
        self.assertEqual(self.result["best_hit_rate"], "prefix-hash")
        self.assertEqual(self.result["best_balance"], "round-robin")
        self.assertEqual(self.result["practical"], "prefix-hash-with-overflow")

    def test_aggregate_hides_the_most_under_pure_prefix_hash(self):
        """22.5 那句话的量：聚合和最差实例差 440 ms。"""
        self.assertEqual(self._row("prefix-hash")["aggregate_hides"], 440.0)

    def test_scaling_table_uses_the_chains_own_cacheable_share(self):
        rows = self.result["scaling_table"]
        self.assertAlmostEqual(rows[1]["hit_rate_upper"][2], 0.92 * 0.125)

    def _row(self, name):
        return next(r for r in self.result["strategies"]
                    if r["strategy"] == name)


class TestRouteEvalRefusals(unittest.TestCase):
    def test_missing_cacheable_share(self):
        with self.assertRaises(sc.ChoiceError) as ctx:
            sc.route_eval({"strategies": {}})
        self.assertIn("可缓存比例", str(ctx.exception))

    def test_one_strategy_is_not_a_trade_off(self):
        report = {"cacheable_share": 0.9, "strategies": {
            "round-robin": {"per_instance": [inst(100, 0.2, 500.0)]}}}
        with self.assertRaises(sc.ChoiceError) as ctx:
            sc.route_eval(report)
        self.assertIn("两种策略", str(ctx.exception))


class TestCostArithmetic(unittest.TestCase):
    def test_api_cost_is_per_thousand_tokens(self):
        cost = sc.monthly_api_cost(1.0, 1000, 0.002)
        self.assertAlmostEqual(cost, sc.SECONDS_PER_MONTH * 0.002, places=6)

    def test_selfhost_rounds_gpus_up(self):
        """按峰值配置出，13 QPS 的峰值配不了 1.08 张卡。"""
        cost, gpus = sc.monthly_selfhost_cost(13.0, 12.0, 12000.0)
        self.assertEqual(gpus, 2)
        self.assertEqual(cost, 24000.0)

    def test_selfhost_ignores_the_mean(self):
        """22.1 的第一项：API 按实际用量计费，自建按卡的存在计费。"""
        a, _ = sc.monthly_selfhost_cost(45.0, 12.0, 12000.0)
        b, _ = sc.monthly_selfhost_cost(45.0, 12.0, 12000.0)
        self.assertEqual(a, b)

    def test_breakeven_is_selfhost_over_unit_api_cost(self):
        be = sc.breakeven_mean_qps(48000.0, 1400, 0.002)
        per_qps_month = sc.SECONDS_PER_MONTH * 1400 / 1000 * 0.002  # 7257.6
        self.assertAlmostEqual(per_qps_month, 7257.6, places=4)
        self.assertAlmostEqual(be, 48000.0 / per_qps_month, places=6)
        self.assertAlmostEqual(be, 6.6138, places=4)


class TestDecide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))

    def _decide(self, **kw):
        base = dict(workload=self.workload, peak_qps=45.0, trough_qps=4.0,
                    api_price_per_1k=0.002, gpu_monthly=12000.0,
                    capacity_per_gpu=12.0)
        base.update(kw)
        return sc.decide(**base)

    def test_hard_constraint_short_circuits_the_cost_math(self):
        """22.2 第一条：三条硬约束任何一条成立，直接走自托管，不用再算成本。"""
        r = self._decide(constraints={"data_residency": True},
                         team_capacity="yes")
        self.assertEqual(r["recommendation"], "自托管")
        self.assertFalse(r["cost_is_decisive"])
        self.assertIn("成本不参与这个决定", r["reasons"][0])

    def test_costs_are_still_reported_when_they_do_not_decide(self):
        r = self._decide(constraints={"data_residency": True},
                         team_capacity="yes")
        self.assertAlmostEqual(r["api_monthly"], 101606.4, places=1)
        self.assertEqual(r["selfhost_monthly"], 48000.0)

    def test_a_spiky_workload_goes_to_api_even_though_selfhost_is_cheaper(self):
        """22.1 的主张：成本通常不是自建的真正优势。"""
        r = self._decide()
        self.assertEqual(r["recommendation"], "共享 API")
        self.assertLess(r["selfhost_monthly"], r["api_monthly"])
        self.assertAlmostEqual(r["peak_trough_ratio"], 11.25)

    def test_the_breakeven_utilization_is_reported(self):
        """22.7：平均利用率过 13.8% 自建就和 API 打平，这份负载是 29.2%。"""
        r = self._decide()
        self.assertAlmostEqual(r["breakeven_utilization"], 0.1378, places=4)
        self.assertAlmostEqual(r["utilization"], 0.2917, places=4)
        self.assertGreater(r["utilization"], r["breakeven_utilization"])

    def test_the_peak_trough_line_is_a_parameter_not_physics(self):
        """推荐 API 靠的是经验界 5，调高它，同一组数就推荐专用部署。"""
        r = self._decide(api_peak_trough=20, team_capacity="yes")
        self.assertEqual(r["recommendation"], "专用部署")

    def test_a_tight_ttft_slo_pushes_a_spiky_workload_back(self):
        """22.2 第三条：共享 API 的 P99 受邻居影响，卡紧的 SLO 拿不到保障。"""
        r = self._decide(slo_ttft_ms=1500.0, team_capacity="yes")
        self.assertEqual(r["recommendation"], "专用部署")

    def test_team_capacity_is_a_gate_not_a_note(self):
        with self.assertRaises(sc.ChoiceError) as ctx:
            self._decide(constraints={"data_residency": True})
        self.assertIn("最常被低估", str(ctx.exception))

    def test_a_team_that_cannot_sustain_it_falls_back_to_api(self):
        r = self._decide(slo_ttft_ms=1500.0, team_capacity="no")
        self.assertEqual(r["recommendation"], "共享 API")

    def test_a_hard_constraint_with_no_team_stays_selfhost_and_says_why(self):
        """硬约束成立时养不起不是退回 API 的理由，是一个必须先解决的前置条件。"""
        r = self._decide(constraints={"data_residency": True},
                         team_capacity="no")
        self.assertEqual(r["recommendation"], "自托管")
        self.assertTrue(any("前置条件" in x for x in r["reasons"]))

    def test_steady_traffic_goes_to_dedicated(self):
        r = self._decide(peak_qps=20.0, trough_qps=12.0, team_capacity="yes")
        self.assertEqual(r["recommendation"], "专用部署")

    def test_missing_tokens_per_request_rejected(self):
        with self.assertRaises(sc.ChoiceError) as ctx:
            self._decide(workload={"mean_qps": 14.0})
        self.assertIn("第 6 章", str(ctx.exception))

    def test_unknown_constraint_rejected(self):
        with self.assertRaises(sc.ChoiceError):
            self._decide(constraints={"must_be_fast": True})

    def test_mean_qps_source_is_stated_when_it_was_estimated(self):
        """峰谷取中点估出来的均值必须标明，否则它会被当成量出来的。"""
        r = self._decide(workload={"tokens_per_request": 1400})
        self.assertIn("不是量出来的", r["mean_qps_source"])
        self.assertAlmostEqual(r["mean_qps"], 24.5)

    def test_zero_trough_gives_an_infinite_ratio_not_a_crash(self):
        r = self._decide(trough_qps=0.0)
        self.assertEqual(r["peak_trough_ratio"], "无穷（波谷为 0）")

    def test_four_revisit_conditions(self):
        r = self._decide()
        self.assertEqual(len(r["revisit_when"]), 4)


class TestWorkloadSample(unittest.TestCase):
    def test_declared_synthetic(self):
        doc = json.loads(WORKLOAD.read_text(encoding="utf-8"))
        self.assertTrue(doc["synthetic"])
        self.assertIn("合成设定", doc["_note"])

    def test_its_prefix_is_shared_not_session(self):
        """这份负载的前缀是全体共享的 system prompt，轮询打不散它；案例二是会话级前缀。"""
        doc = json.loads(WORKLOAD.read_text(encoding="utf-8"))
        self.assertEqual(doc["prefix_scope"], "shared")

    def test_the_system_prompt_fits_inside_the_input_mean(self):
        """每条请求都带 system prompt，所以它不能比平均输入还长（Part 5 审阅 P2-4）。"""
        doc = json.loads(WORKLOAD.read_text(encoding="utf-8"))
        self.assertLess(doc["system_prompt_tokens"], doc["input_tokens_mean"])
        self.assertEqual(doc["input_tokens_mean"] + doc["output_tokens_mean"],
                         doc["tokens_per_request"])


class TestCli(unittest.TestCase):
    def test_route_eval_exits_zero(self):
        self.assertEqual(
            sc.main(["route-eval", "--report", str(ROUTE_SAMPLE)]), 0)

    def test_decide_exits_zero(self):
        self.assertEqual(sc.main([
            "decide", "--workload", str(WORKLOAD), "--peak-qps", "45",
            "--trough-qps", "4", "--data-residency", "required",
            "--api-price", "0.002", "--gpu-monthly", "12000",
            "--capacity-per-gpu", "12", "--team-capacity", "yes"]), 0)

    def test_decide_without_team_capacity_exits_one(self):
        self.assertEqual(sc.main([
            "decide", "--workload", str(WORKLOAD), "--peak-qps", "45",
            "--trough-qps", "4", "--data-residency", "required",
            "--api-price", "0.002", "--gpu-monthly", "12000",
            "--capacity-per-gpu", "12"]), 1)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(sc.main([]), 2)


if __name__ == "__main__":
    unittest.main()
