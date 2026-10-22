#!/usr/bin/env python3
"""Tests for content/reference: 附录 F 与术语表。

附录 F 的价值在“正文用在哪里”那一列能点得过去，所以每个节号都要在正文里真的存在；
术语表是脚本生成的索引，所以它必须和正文的注释同步。
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APPENDIX_F = HERE / "appendix-f.md"
GLOSSARY = HERE / "glossary.md"


def chapter_sections() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "content").glob("ch*/ch*.md"):
        for line in path.read_text(encoding="utf-8").split("\n"):
            m = re.match(r"## (\d+\.\d+) ", line)
            if m:
                found.add(m.group(1))
    appendix_a = (ROOT / "content" / "advanced" / "appendix-a-gpu-architecture"
                  / "appendix-a.md").read_text(encoding="utf-8")
    for m in re.finditer(r"^## (A\.\d+) ", appendix_a, re.M):
        found.add(f"附录 {m.group(1)}")
    return found


class TestAppendixF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = APPENDIX_F.read_text(encoding="utf-8")
        cls.rows = [l for l in cls.text.split("\n")
                    if l.startswith("| ") and not l.startswith("| 式子")]

    def test_five_groups_follow_the_three_laws_method_and_cost(self):
        heads = re.findall(r"^## (F\.\d) (.+)$", self.text, re.M)
        self.assertEqual([h[0] for h in heads], ["F.1", "F.2", "F.3", "F.4", "F.5"])
        self.assertIn("写比读贵", heads[0][1])
        self.assertIn("满载拉长等待", heads[1][1])
        self.assertIn("规律只给假设", heads[3][1])
        self.assertIn("有用的产出", heads[4][1])

    def test_every_row_has_four_filled_columns(self):
        self.assertGreaterEqual(len(self.rows), 30)
        for row in self.rows:
            cells = [c.strip() for c in row.strip("|").split(" | ")]
            with self.subTest(row=row[:30]):
                self.assertEqual(len(cells), 4)
                for c in cells:
                    self.assertTrue(c)

    def test_every_section_it_points_to_exists(self):
        sections = chapter_sections()
        for row in self.rows:
            where = row.rstrip(" |").split(" | ")[-1]
            for ref in re.split(r"、", where):
                ref = ref.strip()
                if ref.startswith("part0"):
                    self.assertTrue((ROOT / "content" / f"{ref}.md").exists(), ref)
                    continue
                if re.fullmatch(r"\d+\.\d+", ref) and ref.startswith("0."):
                    # 第 0 章的小节号
                    ch00 = (ROOT / "content" / "ch00" / "ch00.md").read_text(encoding="utf-8")
                    self.assertIn(f"## {ref} ", ch00, ref)
                    continue
                with self.subTest(ref=ref):
                    self.assertIn(ref, sections)

    def test_the_queueing_row_names_its_server_premise(self):
        """P0-2 的教训：单服务台排队式必须带着它的服务台口径出现。"""
        row = next(r for r in self.rows if "Ca²" in r)
        self.assertIn("一个服务台", row)
        self.assertIn("Erlang C", row)

    def test_style(self):
        for bad in ("——", "「", "」"):
            self.assertNotIn(bad, self.text)


class TestGlossary(unittest.TestCase):
    def test_it_is_up_to_date_with_the_chapters(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "build_glossary.py"),
                            "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_it_covers_every_annotation(self):
        text = GLOSSARY.read_text(encoding="utf-8")
        rows = [l for l in text.split("\n") if l.startswith("| ")
                and not l.startswith("| 首选写法")]
        self.assertGreaterEqual(len(rows), 60)
        for term in ("Goodput", "可识别线", "负载率", "峰均比", "Little's Law",
                     "GEMM", "logits", "报告契约"):
            with self.subTest(term=term):
                self.assertTrue(any(r.startswith(f"| {term} ") for r in rows))

    @staticmethod
    def cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split(" | ")]

    def rows(self) -> dict[str, list[str]]:
        text = GLOSSARY.read_text(encoding="utf-8")
        return {self.cells(l)[0]: self.cells(l) for l in text.split("\n")
                if l.startswith("| ") and not l.startswith("| 首选写法")}

    def test_the_review_s_distance_cases_are_visible(self):
        """首次出现早于定义所在的几条，表里要能看出来。"""
        row = self.rows()["Chunked Prefill"]
        self.assertEqual(row[3], "13.5")
        self.assertEqual(row[4], "第 2 章")

    def test_every_row_has_six_columns(self):
        for term, row in self.rows().items():
            with self.subTest(term=term):
                self.assertEqual(len(row), 6)

    def test_each_family_points_at_a_section_that_holds_its_table(self):
        """同族一列指向的那一节，正文里要真有那张对照表，而且一族至少两个词。"""
        families: dict[str, list[str]] = {}
        for term, row in self.rows().items():
            if row[5] != "—":
                families.setdefault(row[5], []).append(term)
        self.assertEqual(len(families), 6)
        sections = chapter_sections()
        for name, terms in families.items():
            ref = re.search(r"（(\d+\.\d+)）", name).group(1)
            with self.subTest(family=name):
                self.assertGreaterEqual(len(terms), 2)
                self.assertIn(ref, sections)
                chapter = ROOT / "content" / f"ch{int(ref.split('.')[0]):02d}"
                text = (chapter / f"{chapter.name}.md").read_text(encoding="utf-8")
                body = text.split(f"## {ref} ", 1)[1].split("\n## ", 1)[0]
                self.assertRegex(body, r"\n\|---")

    def test_terms_explained_in_a_relation_table_keep_their_section(self):
        """写作规则 9：关系表里说清的词不再挂注释，但术语表要指回那一节。"""
        rows = self.rows()
        for term, where in (("Request ID", "8.3"), ("槽位占用率", "20.7"),
                            ("灰度发布", "28.5"), ("在途", "20.3")):
            with self.subTest(term=term):
                self.assertEqual(rows[term][3], where)
        self.assertEqual(rows["槽位占用率"][1], "Slot Occupancy")

    def test_rows_follow_the_order_of_their_sections(self):
        """插回来的 EXTRA 条目不能打乱“按定义所在的先后排列”。"""
        keys = []
        for row in self.rows().values():
            m = re.fullmatch(r"(\d+)\.(\d+)", row[3])
            if m:
                keys.append((int(m.group(1)), int(m.group(2))))
        self.assertEqual(keys, sorted(keys))


class TestEnvironmentPage(unittest.TestCase):
    """实验环境与版本：正文里“默认/当前版本”的说法都挂在这一页上。"""

    @classmethod
    def setUpClass(cls):
        cls.text = (HERE / "environment.md").read_text(encoding="utf-8")
        cls.version_table = cls.text.split("## 二、版本相关的说法")[1].split("## 三、")[0]

    def evidence(self, name):
        import json
        return json.loads((ROOT / "content" / "ch01" / "evidence" / name)
                          .read_text(encoding="utf-8"))

    def test_it_records_the_five_environment_fields_chapter_one_asks_for(self):
        """1.1 要求记五项：Python、vLLM、驱动、GPU、模型。"""
        for field in ("Python", "vLLM", "驱动", "GPU", "模型"):
            with self.subTest(field=field):
                self.assertIn(field, self.text)

    def test_both_machines_match_their_evidence(self):
        for name in ("gx10-streaming-client-report.json",
                     "rtx3080ti-streaming-client-report.json"):
            ev = self.evidence(name)
            env = ev["validation_environment"]
            with self.subTest(report=name):
                self.assertIn(name, self.text)
                for value in (env["host"], env["gpu"], env["driver_version"]):
                    self.assertIn(value, self.text)

    def test_the_first_report_keeps_its_missing_version_as_a_teaching_gap(self):
        first = self.evidence("gx10-streaming-client-report.json")
        second = self.evidence("rtx3080ti-streaming-client-report.json")
        self.assertIsNone(first["validation_environment"]["vllm_version"])
        self.assertEqual(second["validation_environment"]["vllm_version"], "0.10.2")
        self.assertIn("报告里是空的", self.text)
        self.assertIn("0.10.2", self.text)

    def test_the_two_runs_are_marked_as_not_comparable_on_time(self):
        """两台的首包差一个数量级，第二台是冷启动，页面要挡住这个比较。"""
        first = self.evidence("gx10-streaming-client-report.json")
        second = self.evidence("rtx3080ti-streaming-client-report.json")
        a = first["summary"]["time_to_first_content_chunk_avg_ms"]
        b = second["summary"]["time_to_first_content_chunk_avg_ms"]
        self.assertGreater(b, a * 10)
        self.assertIn("两份不能混着比", self.text)
        self.assertIn("冷启动", self.text)

    def test_the_prompt_token_difference_is_explained(self):
        """同一句话两台报 30 和 40，差额要在页面上说清来处。"""
        second = self.evidence("rtx3080ti-streaming-client-report.json")
        self.assertEqual(second["results"][0]["prompt_tokens"], 40)
        probe = __import__("json").loads(
            (ROOT / "content" / "ch03" / "evidence" / "chat-template-probe.json")
            .read_text(encoding="utf-8"))
        self.assertEqual(probe["prompt_tokens_with_template"], 40)
        self.assertTrue(probe["has_default_system"])
        self.assertEqual(probe["prompt_tokens_bare"]
                         + probe["template_overhead_tokens"], 40)
        self.assertIn("Chat Template", self.text)
        self.assertIn("默认系统提示", self.text)

    def test_every_version_dependent_row_points_at_a_real_section(self):
        sections = chapter_sections()
        refs = set()
        for row in self.version_table.split("\n"):
            if not row.startswith("| ") or row.startswith("| 说法") or row.startswith("|---"):
                continue
            where = [c.strip() for c in row.strip("|").split(" | ")][1]
            refs.update(re.findall(r"(?<![\d.])(\d+\.\d+)(?![\d.])", where))
        self.assertGreaterEqual(len(refs), 8)
        for ref in sorted(refs):
            with self.subTest(ref=ref):
                self.assertIn(ref, sections)

    def test_the_chapters_point_back_at_it(self):
        for path in ("ch01/ch01.md", "part01.md", "ch03/ch03.md"):
            text = (ROOT / "content" / path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertIn("reference/environment.md", text)


class TestAnnotationCheck(unittest.TestCase):
    def test_no_annotations_are_stacked_in_one_block(self):
        """一个引用块里连着两条注释，读者拿到的是并列定义，写作规则 9 要求拆开。"""
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_annotations.py"),
                            "--strict"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stacked 0 处", r.stdout)


if __name__ == "__main__":
    unittest.main()
