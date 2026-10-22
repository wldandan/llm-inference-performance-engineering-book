#!/usr/bin/env python3
"""Tests for code/ch30/project/verify.py.

30.1 那五项交付物、30.3 那九块契约、30.4 那八条自查，各自都有一组。两份样例项目
之间只差一组有针对性的改动，所以每一条自查都能被单独验证：pass 那份全绿，
incomplete 那份八条全响。
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import verify as v

HERE = Path(__file__).resolve().parent
OK = HERE / "samples" / "sample-pass"
BAD = HERE / "samples" / "sample-incomplete"


class TestTheLists(unittest.TestCase):
    def test_five_deliverables_in_the_order_30_1_gives(self):
        self.assertEqual([k for k, _, _ in v.DELIVERABLES],
                         ["runnable", "observable", "explainable",
                          "optimizable", "gated"])

    def test_nine_report_blocks_in_the_order_30_3_gives(self):
        self.assertEqual(len(v.REPORT_BLOCKS), 9)
        self.assertEqual(v.REPORT_BLOCKS[0], "system")
        self.assertEqual(v.REPORT_BLOCKS[-1], "boundary")

    def test_the_ninth_block_is_the_boundary_one(self):
        """30.3：第九块是整份报告里最能体现水平的一块。"""
        self.assertEqual(v.REPORT_BLOCKS[8], "boundary")
        self.assertEqual(len(v.BOUNDARY_ITEMS), 5)
        self.assertIn("chain_structure", v.BOUNDARY_ITEMS)

    def test_eight_self_checks(self):
        self.assertEqual([n for n, _, _ in v.SELF_CHECKS], list(range(1, 9)))

    def test_four_are_structural_and_four_heuristic(self):
        kinds = [k for _, _, k in v.SELF_CHECKS]
        self.assertEqual(kinds.count("structural"), 4)
        self.assertEqual(kinds.count("heuristic"), 4)

    def test_the_four_structural_ones_are_the_cost_facing_ones(self):
        """30.4 末尾：护栏、一次只改一项、质量否决、边界，查的是同一件事。"""
        structural = [n for n, _, k in v.SELF_CHECKS if k == "structural"]
        self.assertEqual(structural, [5, 6, 7, 8])

    def test_seven_stage_files(self):
        self.assertEqual(len(v.PROJECT_FILES), 7)
        for rel in v.PROJECT_FILES.values():
            with self.subTest(rel=rel):
                self.assertTrue(rel.endswith(".json"))


class TestPassingSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = v.verify(OK, "base")

    def test_it_passes(self):
        self.assertEqual(self.r["verdict"], "pass")
        self.assertEqual(self.r["blocking"], [])

    def test_all_seven_files_are_there(self):
        self.assertEqual(self.r["missing_files"], [])

    def test_all_five_deliverables(self):
        self.assertEqual(self.r["deliverables"]["missing"], [])

    def test_all_nine_blocks_present_and_none_empty(self):
        c = self.r["report_contract"]
        self.assertEqual(c["missing"], [])
        self.assertEqual(c["empty"], [])

    def test_all_eight_self_checks_green(self):
        self.assertEqual(self.r["self_check"]["failed"], [])
        self.assertEqual(self.r["self_check"]["warned"], [])

    def test_it_keeps_one_indistinguishable_round(self):
        """30.4 第四条：全是明确结论反而可疑，所以样例里留了一轮不可分辨。"""
        rounds = json.loads(
            (OK / "experiment" / "rounds.json").read_text(encoding="utf-8"))
        verdicts = [r["verdict"] for r in rounds["rounds"]]
        self.assertTrue(any("不可分辨" in x for x in verdicts))

    def test_all_five_seams_line_up(self):
        self.assertEqual(self.r["cross_check"]["mismatched"], [])
        self.assertEqual(self.r["cross_check"]["unknown"], [])


class TestIncompleteSample(unittest.TestCase):
    """这一组是这个文件的主体：八条自查逐条响。"""

    @classmethod
    def setUpClass(cls):
        cls.r = v.verify(BAD, "base")

    def test_it_is_incomplete(self):
        self.assertEqual(self.r["verdict"], "incomplete")

    def test_the_four_structural_checks_all_fail(self):
        self.assertEqual(self.r["self_check"]["failed"], [5, 6, 7, 8])

    def test_the_four_heuristic_checks_all_warn(self):
        self.assertEqual(self.r["self_check"]["warned"], [1, 2, 3, 4])

    def by_no(self, num):
        return next(i for i in self.r["self_check"]["items"] if i["no"] == num)

    def test_check_one_names_the_stages_written_as_zero(self):
        item = self.by_no(1)
        self.assertIn("client_queue", item["detail"])
        self.assertIn("tokenizer_internal", item["detail"])

    def test_check_two_catches_the_network_time_phrase(self):
        self.assertIn("网络耗时", self.by_no(2)["detail"])

    def test_check_three_names_the_round_without_conditions(self):
        self.assertIn("r1", self.by_no(3)["detail"])

    def test_check_four_fires_because_every_round_concluded(self):
        self.assertIn("反而可疑", self.by_no(4)["detail"])

    def test_check_five_names_the_round_without_guardrails(self):
        self.assertIn("r2", self.by_no(5)["detail"])

    def test_check_six_names_the_round_that_changed_two_things(self):
        self.assertIn("r1", self.by_no(6)["detail"])

    def test_check_seven_names_the_precision_round_without_quality(self):
        self.assertIn("r3", self.by_no(7)["detail"])

    def test_check_eight_names_the_missing_boundary_item(self):
        self.assertIn("chain_structure", self.by_no(8)["detail"])

    def test_every_heuristic_warning_says_it_needs_a_human(self):
        for item in self.r["self_check"]["items"]:
            if item["kind"] == "heuristic" and item["status"] == "warn":
                with self.subTest(no=item["no"]):
                    self.assertIn("需人工确认", item["detail"])

    def test_the_gate_deliverable_is_missing_because_assertions_are_empty(self):
        self.assertEqual(self.r["deliverables"]["missing"], ["gated"])

    def test_the_first_seam_does_not_line_up(self):
        self.assertEqual(self.r["cross_check"]["mismatched"], ["context_length"])

    def test_the_seam_carries_its_consequence_from_ch29(self):
        row = next(x for x in self.r["cross_check"]["rows"]
                   if x["key"] == "context_length")
        self.assertEqual(row["consequence"]["instances_needed"], 3)

    def test_the_report_contract_itself_is_still_complete(self):
        """这份样例踩的是自查和接缝，不是缺块。两件事要分开报。"""
        self.assertEqual(self.r["report_contract"]["missing"], [])


class TestContractIsNotATemplate(unittest.TestCase):
    def read_report(self):
        return json.loads(
            (OK / "report" / "report.json").read_text(encoding="utf-8"))

    def test_a_missing_block_blocks(self):
        report = self.read_report()
        report.pop("capacity")
        r = v.check_report_contract({"report": report})
        self.assertEqual(r["missing"], ["capacity"])
        self.assertFalse(r["ok"])

    def test_an_empty_block_also_blocks(self):
        """30.3：契约的强制力在于不写不算交付，写成空的也不算。"""
        report = self.read_report()
        report["capacity"] = {}
        r = v.check_report_contract({"report": report})
        self.assertEqual(r["empty"], ["capacity"])
        self.assertFalse(r["ok"])

    def test_the_note_says_why(self):
        r = v.check_report_contract({"report": self.read_report()})
        self.assertIn("模板", r["note"])


class TestContractCoversPartSix(unittest.TestCase):
    """30.3 第 7、8 块把第 27 章的弹性和第 29 章的上线并了进来。

    补这两项之前，一个没有回滚预案的项目能通过基本验收，而 part06 的篇级清单
    里它是一件物证（Part 7 审阅 P1-2）。
    """

    def test_the_passing_sample_carries_both(self):
        self.assertEqual(v.verify(OK, "base")["report_contract"]["thin"], [])

    def test_a_rollback_plan_without_a_rehearsed_duration_blocks(self):
        r = v.verify(BAD, "base")
        thin = r["report_contract"]["thin"]
        self.assertTrue(any("rehearsed_duration_min" in t for t in thin))
        self.assertTrue(any("cache_warmup_min" in t for t in thin))
        self.assertTrue(any("第 7、8 块缺项" in b for b in r["blocking"]))

    def test_the_elasticity_fields_come_from_chapter_27(self):
        docs = v.load_project(OK)
        for field in ("scale_trigger_metric", "cold_start_s", "loop_lag_s"):
            with self.subTest(field=field):
                self.assertIn(field, docs["capacity"])

    def test_the_headroom_and_the_card_count_agree(self):
        """P2-2：1320 ÷ 742 ≈ 1.78 张，加 12% 余量正好 2 张。"""
        cap = v.load_project(OK)["capacity"]
        minimum = cap["peak_output_tps"] / cap["per_card_output_tps"]
        import math
        self.assertEqual(math.ceil(minimum * (1 + cap["headroom_share"])),
                         cap["instances"])


class TestLevels(unittest.TestCase):
    def test_base_asks_for_nothing_extra(self):
        self.assertTrue(v.check_level({}, "base")["ok"])

    def test_extended_wants_one_of_the_four_comparisons(self):
        r = v.check_level({}, "extended")
        self.assertFalse(r["ok"])
        self.assertIn("30.5", r["detail"])

    def test_any_one_of_them_is_enough(self):
        for key in v.EXTENDED_EVIDENCE:
            with self.subTest(key=key):
                r = v.check_level({"capacity": {key: {"efficiency": 0.86}}},
                                  "extended")
                self.assertTrue(r["ok"])

    def test_pd_disaggregation_is_not_yet_required(self):
        """附录 E 未写：PD 分离给了照样计入，但扩展验收不要求它。"""
        r = v.check_level({}, "extended")
        self.assertIn("pd_disaggregation", r["not_yet_required"])
        self.assertIn("暂不要求", r["detail"])

    def test_the_old_tier_names_are_gone(self):
        with self.assertRaises(v.VerifyError):
            v.check_level({}, "advanced")

    def test_the_passing_sample_is_not_extended(self):
        self.assertEqual(v.verify(OK, "extended")["verdict"], "incomplete")

    def test_unknown_level_rejected(self):
        with self.assertRaises(v.VerifyError):
            v.check_level({}, "expert")


class TestSeamsComeFromChapter29(unittest.TestCase):
    def test_it_uses_the_same_five_seams(self):
        rc = v._load_release_check()
        self.assertEqual(len(rc.CROSS_CHECKS), 5)
        r = v.verify(OK, "base")
        self.assertEqual([x["key"] for x in r["cross_check"]["rows"]],
                         [k for k, _, _ in rc.CROSS_CHECKS])

    def test_a_seam_with_one_side_missing_is_not_a_pass(self):
        """把缺数据读成没问题，是这类检查最常见的坏掉方式。"""
        rc = v._load_release_check()
        docs = {"workload": {}, "capacity": {"context_tokens": 1800},
                "baseline": {}, "gate": {}, "report": {}}
        r = v.cross_check(docs, rc)
        self.assertIn("context_length", r["unknown"])
        self.assertEqual(r["mismatched"], [])


class TestRefusals(unittest.TestCase):
    def test_a_missing_directory_is_refused(self):
        with self.assertRaises(v.VerifyError):
            v.verify(HERE / "samples" / "no-such-project")

    def test_missing_files_are_reported_not_ignored(self):
        r = v.verify(HERE / "samples", "base")
        self.assertEqual(r["verdict"], "incomplete")
        self.assertEqual(len(r["missing_files"]), 7)


class TestSamples(unittest.TestCase):
    def test_both_declared_synthetic(self):
        for base in (OK, BAD):
            for rel in v.PROJECT_FILES.values():
                doc = json.loads((base / rel).read_text(encoding="utf-8"))
                with self.subTest(file=f"{base.name}/{rel}"):
                    self.assertIn("合成设定", doc["_note"])

    def test_the_two_samples_differ_only_where_intended(self):
        """两份样例只在 workload、gate、experiment、report 四处不同。"""
        same, differ = [], []
        for key, rel in v.PROJECT_FILES.items():
            a = json.loads((OK / rel).read_text(encoding="utf-8"))
            b = json.loads((BAD / rel).read_text(encoding="utf-8"))
            a.pop("_note"), b.pop("_note")
            (same if a == b else differ).append(key)
        self.assertEqual(sorted(differ),
                         ["experiment", "gate", "report", "workload"])
        self.assertEqual(sorted(same), ["baseline", "capacity", "observe"])

    def test_every_stage_directory_has_a_readme(self):
        for name in ("workload", "baseline", "observe", "experiment",
                     "capacity", "gate", "report"):
            with self.subTest(dir=name):
                self.assertTrue((HERE / name / "README.md").exists())


class TestCli(unittest.TestCase):
    def test_pass_exits_zero(self):
        self.assertEqual(v.main(["--project-dir", str(OK)]), 0)

    def test_incomplete_exits_one(self):
        self.assertEqual(v.main(["--project-dir", str(BAD)]), 1)

    def test_a_bad_directory_exits_one(self):
        self.assertEqual(
            v.main(["--project-dir", str(HERE / "samples" / "nope")]), 1)

    def test_extended_on_the_base_sample_exits_one(self):
        self.assertEqual(
            v.main(["--project-dir", str(OK), "--level", "extended"]), 1)


if __name__ == "__main__":
    unittest.main()
