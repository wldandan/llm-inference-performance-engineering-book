#!/usr/bin/env python3
"""Tests for the Chapter 19 Decode scorecard.

Most of these are rejection tests, because the value of the checker is what it
refuses to accept. The rest pin the synthetic five-round sample: each round
demonstrates one situation, and that is an arrangement the tests protect.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import unittest
from pathlib import Path

import decode_experiment as de

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SAMPLE = REPO / "content" / "ch19" / "evidence" / "decode-experiment-sample.json"


def series() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def round_doc(n: int) -> dict:
    return copy.deepcopy(next(r for r in series()["rounds"] if r["round"] == n))


class TestSweepAgainstTheStepFloor(unittest.TestCase):
    """19.3：TPS 那一列由第 15.3 节的搬运模型生成，也由它校验。"""

    @classmethod
    def setUpClass(cls):
        import json as _json
        cls.config = de.dm.load_config(_json.loads(
            (HERE.parent / "ch15" / "model-7b-generic.json").read_text(encoding="utf-8")))
        cls.points = round_doc(0)["sweep"]["points"]

    def test_every_row_is_inside_the_bandwidth_floor(self):
        check = de.check_sweep_floor(self.points, self.config)
        self.assertTrue(check["ok"], check["violations"])
        self.assertAlmostEqual(check["step_floor_ms"], 14.0, places=3)

    def test_a_row_above_the_floor_is_rejected(self):
        """批量 4 时每步至少 14 ms，所以 TPS 不可能到 402。"""
        bad = [dict(p) for p in self.points]
        bad[0]["tps"] = 402
        check = de.check_sweep_floor(bad, self.config)
        self.assertFalse(check["ok"])
        self.assertIn("超过搬运下限", check["violations"][0])

    def test_a_p95_itl_below_the_mean_step_is_rejected(self):
        bad = [dict(p) for p in self.points]
        bad[-1]["itl_p95_ms"] = 5
        check = de.check_sweep_floor(bad, self.config)
        self.assertFalse(check["ok"])
        self.assertIn("小于平均单步", check["violations"][0])

    def test_the_table_in_the_text_is_what_the_model_produces(self):
        attainment = {p["batch"]: p["slo_attainment"] for p in self.points}
        itl = {p["batch"]: p["itl_p95_ms"] for p in self.points}
        regenerated = de.sweep_from_model(
            self.config, [p["batch"] for p in self.points], attainment, itl)
        self.assertEqual([p["tps"] for p in regenerated],
                         [p["tps"] for p in self.points])
        self.assertEqual([p["tps"] for p in regenerated],
                         [271, 515, 938, 1592, 2442, 3332])


class TestGoodputAndSweep(unittest.TestCase):
    """19.3：Goodput = 达标的那部分吞吐，峰值和 TPS 峰值不在一处。"""

    def test_goodput_is_tps_times_attainment(self):
        self.assertAlmostEqual(de.goodput(1592, 0.98), 1560.16, places=1)

    def test_full_attainment_leaves_tps_unchanged(self):
        self.assertEqual(de.goodput(1850, 1.0), 1850)

    def test_an_attainment_outside_zero_to_one_is_rejected(self):
        for bad in (-0.1, 1.5):
            with self.subTest(attainment=bad):
                with self.assertRaises(de.ExperimentError):
                    de.goodput(1850, bad)

    def test_the_197_case_three_numbers(self):
        """批量 32 Goodput 0.98 × TPS，批量 128 达标率 20%，低了近六成。"""
        at32 = de.goodput(1592, 0.98)
        at128 = de.goodput(1592 * 2.09, 0.20)
        self.assertAlmostEqual(1 - at128 / at32, 0.5735, places=3)

    def test_the_sweep_finds_the_goodput_peak_at_32(self):
        sweep = de.analyse_sweep(round_doc(0)["sweep"]["points"])
        self.assertEqual(sweep["peak_batch_by_goodput"], 32)

    def test_the_tps_peak_is_at_128_and_reported_separately(self):
        sweep = de.analyse_sweep(round_doc(0)["sweep"]["points"])
        self.assertEqual(sweep["peak_batch_by_tps"], 128)
        self.assertFalse(sweep["peaks_coincide"])

    def test_the_reading_quantifies_both_sides_of_the_trade(self):
        sweep = de.analyse_sweep(round_doc(0)["sweep"]["points"])
        self.assertIn("名义上高 109%", sweep["reading"])
        self.assertIn("Goodput 反而低 57%", sweep["reading"])

    def test_coinciding_peaks_earn_a_scan_wider_message(self):
        """峰值重合说明扫描区间选窄了，这是 19.4 第 0 轮的 null_criterion。"""
        sweep = de.analyse_sweep([
            {"batch": 4, "tps": 400, "slo_attainment": 1.0},
            {"batch": 8, "tps": 800, "slo_attainment": 1.0},
        ])
        self.assertTrue(sweep["peaks_coincide"])
        self.assertIn("再往上扫", sweep["reading"])

    def test_pareto_candidates_are_kept_not_just_the_winner(self):
        sweep = de.analyse_sweep(round_doc(0)["sweep"]["points"])
        self.assertIn(32, sweep["pareto_candidates"])
        self.assertIn("SLO 一变最优点就换一个", sweep["pareto_note"])

    def test_goodput_is_maximised_only_inside_the_feasible_set(self):
        """19.3 的反例：批量 64 吞吐 1.10 倍、达标 93%，Goodput 更高却违反 SLO。"""
        points = [{"batch": 32, "tps": 1000, "slo_attainment": 0.98},
                  {"batch": 64, "tps": 1100, "slo_attainment": 0.93}]
        sweep = de.analyse_sweep(points)
        self.assertEqual(sweep["feasible_batches"], [32])
        self.assertEqual(sweep["peak_batch_by_goodput"], 32)
        self.assertIn("不在可行集里", sweep["reading"])

    def test_an_empty_feasible_set_is_rejected(self):
        with self.assertRaises(de.ExperimentError):
            de.analyse_sweep([{"batch": 32, "tps": 1000, "slo_attainment": 0.9},
                              {"batch": 64, "tps": 1100, "slo_attainment": 0.8}])

    def test_a_sweep_without_a_valid_design_is_rejected(self):
        doc = round_doc(0)
        doc["sweep"]["design"] = "open_loop_fixed_rate"
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc)
        self.assertIn("开环", str(ctx.exception))

    def test_a_single_point_is_not_a_curve(self):
        with self.assertRaises(de.ExperimentError):
            de.analyse_sweep([{"batch": 4, "tps": 400, "slo_attainment": 1.0}])

    def test_a_point_missing_attainment_is_rejected(self):
        with self.assertRaises(de.ExperimentError):
            de.analyse_sweep([{"batch": 4, "tps": 400},
                              {"batch": 8, "tps": 800, "slo_attainment": 1.0}])


class TestScorecardRequiredDimensions(unittest.TestCase):
    """19.1：latency、throughput、capacity 三项每次都要看，缺一项拒绝。"""

    def test_the_three_required_dimensions(self):
        self.assertEqual(de.REQUIRED_DIMENSIONS,
                         ("latency", "throughput", "capacity"))

    def test_a_missing_required_dimension_is_rejected(self):
        for dim in de.REQUIRED_DIMENSIONS:
            with self.subTest(dim=dim):
                doc = round_doc(1)
                doc["scorecard"][dim] = None
                with self.assertRaises(de.ExperimentError) as ctx:
                    de.check_report(doc)
                self.assertIn("缺一项拒绝出报告", str(ctx.exception))

    def test_latency_needs_all_three_numbers(self):
        for field in de.LATENCY_FIELDS:
            with self.subTest(field=field):
                doc = round_doc(1)
                doc["scorecard"]["latency"].pop(field)
                with self.assertRaises(de.ExperimentError) as ctx:
                    de.check_report(doc)
                self.assertIn("19.2 要三个数", str(ctx.exception))

    def test_capacity_needs_the_preemption_count(self):
        doc = round_doc(1)
        doc["scorecard"]["capacity"].pop("preemptions")
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc)
        self.assertIn("抢占计数接近否决项", str(ctx.exception))

    def test_an_undefined_dimension_is_rejected(self):
        doc = round_doc(1)
        doc["scorecard"]["vibes"] = {"score": 1.0}
        with self.assertRaises(de.ExperimentError):
            de.check_report(doc)

    def test_a_huge_max_itl_earns_a_preemption_note(self):
        """19.2：孤立的巨大尖峰先去查抢占，不要当成噪声。"""
        block = {"tpot_mean_ms": 52, "itl_p95_ms": 95, "itl_max_ms": 2400}
        de.validate_latency(block)
        self.assertTrue(any("先去查抢占" in n for n in block["notes"]))

    def test_a_normal_max_itl_earns_no_note(self):
        """19.2 那组对照：正常请求最大是平均的 4 倍，被抢占过的是 46 倍。"""
        block = {"tpot_mean_ms": 45, "itl_p95_ms": 80, "itl_max_ms": 190}
        de.validate_latency(block)
        self.assertNotIn("notes", block)


class TestQualityIsAVeto(unittest.TestCase):
    """19.6 中间那条闸，也是这一章最重要的一条。"""

    def test_a_precision_change_without_quality_is_rejected(self):
        doc = round_doc(1)
        doc["scorecard"]["quality"] = None
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc)
        self.assertIn("哪怕 TPOT 数字很漂亮", str(ctx.exception))

    def test_a_quality_block_without_a_floor_is_rejected(self):
        doc = round_doc(1)
        doc["scorecard"]["quality"].pop("floor")
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc)
        self.assertIn("底线必须在实验之前写死", str(ctx.exception))

    def test_a_floor_without_a_written_at_is_rejected(self):
        doc = round_doc(1)
        doc["scorecard"]["quality"].pop("floor_written_at")
        with self.assertRaises(de.ExperimentError):
            de.check_report(doc)

    def test_a_quality_block_without_an_evalset_is_rejected(self):
        doc = round_doc(1)
        doc["scorecard"]["quality"].pop("evalset")
        with self.assertRaises(de.ExperimentError):
            de.check_report(doc)

    def test_a_non_precision_change_needs_no_quality(self):
        """19.1：没动精度就不跑质量评测。"""
        result = de.check_report(round_doc(4))
        self.assertIsNone(result["quality"])

    def test_the_veto_is_declared_in_the_report(self):
        result = de.check_report(round_doc(1))
        self.assertTrue(result["quality"]["is_veto"])
        self.assertIn("不是投票项", result["quality"]["reading"])

    def test_a_per_kind_breach_counts_even_when_the_total_passes(self):
        result = de.check_report(round_doc(2))
        self.assertLess(result["quality"]["drop"], result["quality"]["floor"])
        self.assertTrue(result["quality"]["breached"])
        self.assertEqual(result["quality"]["breached_kinds"],
                         ["structured_output"])

    def test_which_keys_count_as_touching_precision(self):
        for key in ("kv_cache_dtype", "weight_dtype", "quantization"):
            with self.subTest(key=key):
                self.assertTrue(
                    de.classify_change({key: "a → b"})["touched_precision"])

    def test_a_config_change_does_not_count_as_precision(self):
        self.assertFalse(
            de.classify_change({"cuda_graph_capture_sizes": "20 → 6"})
            ["touched_precision"])


class TestSpecDecodingNeedsTwoBatches(unittest.TestCase):
    """19.6 第三条：投机解码必须提供两个批量档位的结果。"""

    def test_one_batch_point_is_rejected(self):
        doc = round_doc(3)
        doc["scorecard"]["acceptance"]["gain_by_batch"] = {"8": 0.331}
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc, enabled_before=["kv_cache_dtype"])
        self.assertIn("过于乐观", str(ctx.exception))

    def test_a_missing_acceptance_block_is_rejected(self):
        doc = round_doc(3)
        doc["scorecard"]["acceptance"] = None
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc, enabled_before=["kv_cache_dtype"])
        self.assertIn("唯一的决定因素", str(ctx.exception))

    def test_two_batch_points_are_accepted(self):
        result = de.check_report(round_doc(3),
                                 enabled_before=["kv_cache_dtype"])
        self.assertEqual(result["verdict"]["label"], "低于预期")

    def test_the_sample_shows_offline_and_online_acceptance_differ(self):
        """接受数由内容决定：离线样本 3.6，线上流量 2.1（18.3）。"""
        by_sample = round_doc(3)["scorecard"]["acceptance"]["by_sample"]
        self.assertGreater(by_sample["offline"], by_sample["online"])

    def test_the_two_batch_points_compare_the_gain_not_the_acceptance(self):
        """19.6 要两个批量档位，看的是收益比随批量下降，不是接受数。"""
        acceptance = round_doc(3)["scorecard"]["acceptance"]
        self.assertNotIn("by_batch", acceptance)
        gain = acceptance["gain_by_batch"]
        self.assertGreater(gain["8"], gain["32"])

    def test_which_keys_count_as_enabling_speculation(self):
        for key in ("speculative_decoding", "draft_model",
                    "num_speculative_tokens"):
            with self.subTest(key=key):
                self.assertTrue(de.classify_change({key: "x"})["touched_spec"])


class TestOneChangePerRound(unittest.TestCase):
    def test_two_changes_are_rejected(self):
        doc = round_doc(1)
        doc["changed"]["max_num_seqs"] = "32 → 64"
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc)
        self.assertIn("不知道是谁的功劳", str(ctx.exception))

    def test_an_empty_changed_block_is_rejected(self):
        doc = round_doc(1)
        doc["changed"] = {}
        with self.assertRaises(de.ExperimentError):
            de.check_report(doc)


class TestVerdictMustFollowFromTheData(unittest.TestCase):
    def test_a_mislabelled_verdict_is_rejected(self):
        doc = round_doc(1)
        doc["verdict"]["label"] = "高于预期"
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc)
        self.assertIn("结论要从数据里出来", str(ctx.exception))

    def test_a_label_outside_the_four_is_rejected(self):
        doc = round_doc(1)
        doc["verdict"]["label"] = "很成功"
        with self.assertRaises(de.ExperimentError):
            de.check_report(doc)

    def test_indistinguishable_plus_slight_improvement_is_rejected(self):
        """第 14 章那条：那是在用噪声支撑结论。"""
        doc = round_doc(4)
        doc["verdict"]["note"] = "TPOT 小幅有效"
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc, enabled_before=["kv_cache_dtype"])
        self.assertIn("用噪声支撑结论", str(ctx.exception))

    def test_claiming_passed_while_quality_breached_is_rejected(self):
        doc = round_doc(2)
        doc["verdict"]["passed"] = True
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc, enabled_before=["kv_cache_dtype"])
        self.assertIn("质量越过底线就是失败", str(ctx.exception))

    def test_keeping_a_failed_change_is_rejected(self):
        doc = round_doc(2)
        doc["verdict"]["kept"] = True
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc, enabled_before=["kv_cache_dtype"])
        self.assertIn("失败的改动不该留在配置里", str(ctx.exception))

    def test_a_round_can_be_valid_and_still_not_kept(self):
        """19.4 第 3 轮：结论成立，收益不值得付出的容量代价。"""
        result = de.check_report(round_doc(3),
                                 enabled_before=["kv_cache_dtype"])
        self.assertTrue(result["verdict"]["passed"])
        self.assertFalse(result["verdict"]["kept"])

    def test_a_sweep_only_round_needs_no_verdict_label(self):
        result = de.check_report(round_doc(0))
        self.assertIsNone(result["verdict"])

    def test_a_round_with_results_but_no_verdict_is_rejected(self):
        doc = round_doc(1)
        doc.pop("verdict")
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc)
        self.assertIn("有了对照数据就要写下结论", str(ctx.exception))

    def test_a_round_measuring_nothing_is_rejected(self):
        doc = round_doc(1)
        doc.pop("results")
        doc.pop("verdict")
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc)
        self.assertIn("什么都没测", str(ctx.exception))


class TestDirection(unittest.TestCase):
    """容量类指标越大越好，第 14 章只有越小越好的 TTFT。"""

    def test_higher_is_better_reads_an_increase_as_an_improvement(self):
        v = de.judge_round(baseline=[185, 184, 186], variant=[363, 360, 365],
                           expected_pct=0.96, quality=None,
                           direction="higher_is_better")
        self.assertAlmostEqual(v["observed_pct"], 0.9604, places=3)
        self.assertEqual(v["label"], "符合预期")

    def test_the_same_data_read_the_wrong_way_looks_like_a_regression(self):
        v = de.judge_round(baseline=[185, 184, 186], variant=[363, 360, 365],
                           expected_pct=0.96, quality=None,
                           direction="lower_is_better")
        self.assertLess(v["observed_pct"], 0)

    def test_an_unknown_direction_is_rejected(self):
        with self.assertRaises(de.ExperimentError) as ctx:
            de.judge_round(baseline=[1, 1, 1], variant=[1, 1, 1],
                           expected_pct=0.1, quality=None, direction="up")
        self.assertIn("容量类指标越大越好", str(ctx.exception))

    def test_fewer_than_three_repeats_is_rejected(self):
        with self.assertRaises(de.ExperimentError):
            de.judge_round(baseline=[22.0, 22.3], variant=[13.2, 13.0],
                           expected_pct=0.4, quality=None)


class TestInteractionCheck(unittest.TestCase):
    """19.5：叠加之后要重测全部五个维度。"""

    def test_the_first_round_has_nothing_to_stack_on(self):
        result = de.check_interaction(None, enabled=[])
        self.assertEqual(result["already_enabled"], [])

    def test_a_later_round_without_an_interaction_block_is_rejected(self):
        doc = round_doc(4)
        doc["interaction"] = None
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc, enabled_before=["kv_cache_dtype"])
        self.assertIn("一次只叠加一项", str(ctx.exception))

    def test_not_remeasuring_all_dimensions_is_rejected(self):
        doc = round_doc(4)
        doc["interaction"]["remeasured_all_dimensions"] = False
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc, enabled_before=["kv_cache_dtype"])
        self.assertIn("判断不出有没有抵消", str(ctx.exception))

    def test_an_incomplete_stacked_on_list_is_rejected(self):
        doc = round_doc(4)
        doc["interaction"]["stacked_on"] = []
        with self.assertRaises(de.ExperimentError) as ctx:
            de.check_report(doc, enabled_before=["kv_cache_dtype"])
        self.assertIn("叠加对象要写全", str(ctx.exception))


class TestTheSyntheticSeries(unittest.TestCase):
    """五轮各演示一种情形，这是刻意安排的。"""

    def setUp(self):
        self.result = de.check_series(series())

    def test_it_is_labelled_synthetic(self):
        self.assertTrue(self.result["synthetic"])
        self.assertIn("不是真机结果", series()["_note"])

    def test_all_four_verdicts_appear_across_the_series(self):
        labels = set(self.result["verdict_labels"])
        self.assertEqual(labels, {"符合预期", "低于预期", de.INDISTINGUISHABLE})
        self.assertEqual(len(self.result["verdict_labels"]), 4)

    def test_round_two_is_the_four_improved_one_breached_case(self):
        r2 = next(r for r in self.result["rounds"] if r["round"] == 2)
        self.assertEqual(r2["verdict"]["label"], "符合预期")
        self.assertFalse(r2["verdict"]["passed"])
        self.assertEqual(r2["verdict"]["failed_by"], "quality")
        card = r2["scorecard"]
        self.assertLess(card["latency"]["tpot_mean_ms"], 22.1)
        self.assertGreater(card["throughput"]["tps"], 1920)
        # 引擎按 gpu_memory_utilization 留总量，权重省下的被 KV 池接走：
        # 变的是并发，不是显存总量（16.6、19.5）。
        self.assertAlmostEqual(card["capacity"]["memory_gib"], 72.4, places=1)
        self.assertGreater(card["throughput"]["concurrency"], 363)
        self.assertTrue(r2["quality"]["breached"])

    def test_only_round_two_failed(self):
        self.assertEqual(self.result["rounds_failed"], [2])

    def test_round_three_is_valid_but_not_kept(self):
        self.assertEqual(self.result["rounds_valid_but_not_kept"], [3])

    def test_the_kept_set_at_the_end_is_the_two_that_earned_it(self):
        self.assertEqual(self.result["enabled_at_end"],
                         ["kv_cache_dtype", "cuda_graph_max_capture_size"])

    def test_round_four_is_indistinguishable_yet_worth_keeping(self):
        """主指标测不出来，收益全在容量一列。"""
        r4 = next(r for r in self.result["rounds"] if r["round"] == 4)
        self.assertEqual(r4["verdict"]["label"], de.INDISTINGUISHABLE)
        self.assertTrue(r4["verdict"]["kept"])
        graph = r4["scorecard"]["capacity"]["graph_memory_gib"]
        self.assertLess(graph["after"], graph["before"])
        self.assertEqual(graph["source"], "启动日志（合成设定）")
        self.assertGreater(r4["scorecard"]["throughput"]["concurrency"], 363)

    def test_every_round_shares_the_same_workload_and_protocol(self):
        docs = series()["rounds"]
        first = docs[0]["fixed"]
        for doc in docs[1:]:
            self.assertEqual(doc["fixed"]["workload"], first["fixed"]["workload"]
                             if "fixed" in first else first["workload"])
            self.assertEqual(doc["fixed"]["protocol"], first["protocol"])

    def test_every_expectation_has_a_written_at(self):
        for doc in series()["rounds"]:
            self.assertIn("written_at", doc["expectation"])

    def test_every_magnitude_entry_has_a_basis(self):
        """幅度的每个数都要有出处，不能是感觉（第 14 章）。"""
        for doc in series()["rounds"]:
            for metric, spec in doc["expectation"]["magnitude"].items():
                with self.subTest(round=doc["round"], metric=metric):
                    self.assertIn("basis", spec)
                    self.assertTrue(spec["basis"].strip())

    def test_every_round_has_a_null_criterion(self):
        for doc in series()["rounds"]:
            self.assertTrue(doc["expectation"]["null_criterion"].strip())

    def test_the_protocol_pins_temperature_to_zero_in_every_round(self):
        for doc in series()["rounds"]:
            self.assertEqual(doc["fixed"]["protocol"]["temperature"], 0)

    def test_every_round_carries_all_four_boundary_fields(self):
        for doc in series()["rounds"]:
            for field in ("model", "workload", "hardware", "config"):
                with self.subTest(round=doc["round"], field=field):
                    self.assertTrue(doc["boundary"][field].strip())

    def test_the_model_boundary_names_the_shared_config(self):
        """14.6 那条要求的 Part 4 版本：报告要带上每 token KV 这类具体数字。"""
        for doc in series()["rounds"]:
            self.assertIn("128 KiB", doc["boundary"]["model"])


class TestCli(unittest.TestCase):
    def test_it_runs_on_the_sample(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = de.main(["--report", str(SAMPLE)])
        self.assertEqual(rc, 0)
        printed = out.getvalue()
        self.assertIn("失败轮次  [2]", printed)
        self.assertIn("成立但不留 [3]", printed)

    def test_it_reports_a_rejection_without_a_traceback(self):
        broken = HERE / "_broken-report.json"
        doc = series()
        doc["rounds"][1]["scorecard"]["quality"] = None
        broken.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = de.main(["--report", str(broken)])
            self.assertEqual(rc, 1)
            self.assertIn("REJECTED", out.getvalue())
        finally:
            broken.unlink()

    def test_result_is_json_serialisable(self):
        json.dumps(de.check_series(series()), ensure_ascii=False)

    def test_it_reuses_chapter_14s_detectable_difference(self):
        """两章共用一把尺：可识别线 = t × √(2/n) × 变异系数，不是极差。"""
        values = [22.0, 22.3, 21.8]
        import prefill_experiment as pe
        self.assertAlmostEqual(de.detectable_difference(values),
                               pe.detectable_difference(values), places=12)
        self.assertAlmostEqual(de.detectable_difference(values)
                               / de.coefficient_of_variation(values), 2.267, places=3)


if __name__ == "__main__":
    unittest.main()
