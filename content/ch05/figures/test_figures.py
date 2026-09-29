import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


CHAPTER_DIR = Path(__file__).parent.parent
FIGURE_DIR = CHAPTER_DIR / "figures"
SVG_NS = "http://www.w3.org/2000/svg"
EXPECTED_FIGURES = {
    "fig05-01_metric_question_map.svg": "指标先回答问题",
    "fig05-02_measurement_boundaries.svg": "客户端与服务端测量边界",
    "fig05-03_ttft_tpot_itl_timeline.svg": "TTFT、TPOT 与 ITL",
    "fig05-04_throughput_and_goodput.svg": "吞吐率与 Goodput",
    "fig05-05_percentiles_and_tail.svg": "P50、P95 与 P99",
    "fig05-06_resource_vs_outcome.svg": "资源指标与结果指标",
    "fig05-07_cost_denominators.svg": "成本指标的分母",
    "fig05-08_metric_contract.svg": "可比较的指标合同",
    "fig05-09_demo_metrics_report.svg": "Demo 输出指标报告",
}


class ChapterSixFigureTests(unittest.TestCase):
    def test_figure_set_matches_approved_storyboard(self):
        self.assertEqual(
            set(EXPECTED_FIGURES),
            {path.name for path in FIGURE_DIR.glob("*.svg")},
        )

    def test_every_figure_uses_visual_contract(self):
        for filename, expected_title in EXPECTED_FIGURES.items():
            with self.subTest(filename=filename):
                path = FIGURE_DIR / filename
                source = path.read_text(encoding="utf-8")
                root = ET.fromstring(source)
                self.assertEqual(root.attrib.get("width"), "1280")
                self.assertEqual(root.attrib.get("height"), "720")
                self.assertEqual(root.attrib.get("viewBox"), "0 0 1280 720")
                self.assertEqual(root.attrib.get("data-figure-system"), "chapter05-v2")
                self.assertIn("aria-labelledby", root.attrib)
                title = root.find(f"{{{SVG_NS}}}title")
                description = root.find(f"{{{SVG_NS}}}desc")
                self.assertIsNotNone(title)
                self.assertIsNotNone(description)
                self.assertIn(expected_title, title.text or "")
                self.assertGreater(len((description.text or "").strip()), 20)
                self.assertIn("PingFang SC", source)
                self.assertIn("关键结论", source)
                self.assertIn("marker-end", source)
                font_sizes = [int(value) for value in re.findall(r"font-size:\s*(\d+)px", source)]
                self.assertTrue(font_sizes)
                self.assertGreaterEqual(min(font_sizes), 14)
                note = path.with_suffix(".figure-note.md")
                self.assertTrue(note.exists())
                note_source = note.read_text(encoding="utf-8")
                self.assertIn("来源段落", note_source)
                self.assertIn("关键结论", note_source)

    def test_chapter_links_nine_continuous_figures(self):
        source = (CHAPTER_DIR / "ch05.md").read_text(encoding="utf-8")
        links = re.findall(r"!\[[^\]]*\]\((figures/[^)]+\.svg)\)", source)
        self.assertEqual(links, [f"figures/{name}" for name in EXPECTED_FIGURES])
        self.assertEqual(re.findall(r"图5-(\d+)[：:]", source), [str(i) for i in range(1, 10)])
        self.assertIn("nearest-rank", source)
        self.assertIn("Goodput", source)
        self.assertIn("成本分母", source)

    def test_latency_budget_table_closes_against_the_slo(self):
        source = (CHAPTER_DIR / "ch05.md").read_text(encoding="utf-8")
        # 20 + 20 + 60 + 130 + 500 + 40 = 770 已分配；800 − 770 = 30 余量；
        # 250 − 230 = 20 必须落在首 token 之前；剩下 10 落在之后。
        for text in ["770 ms", "30 ms", "20 ms", "10 ms", "230"]:
            self.assertIn(text, source)
        # 把七行一起相加会得出 820，正文必须点名这个错误而不是制造它。
        self.assertIn("820 ms", source)
        self.assertIn("余量只有一份", source)
        self.assertNotIn("| TTFT 未分配余量 |", source)
        self.assertNotIn("| E2E 未分配余量 |", source)
        # 阶段名与第 2 章对齐，不再用 Client/Gateway 这个跨边界的混合名。
        self.assertIn("| Admission |", source)
        self.assertNotIn("Client/Gateway", source)
        # 第 2 章 2.7 立过的那一段必须在预算里有位置，并标为不可得。
        self.assertIn("first_chunk_received", source)

    def test_cost_section_names_both_denominators_the_demo_outputs(self):
        source = (CHAPTER_DIR / "ch05.md").read_text(encoding="utf-8")
        self.assertIn("usd_per_good_request", source)
        self.assertIn("0.00175", source)
        self.assertIn("0.00117", source)

    def test_core_terms_are_annotated_where_they_are_defined(self):
        source = (CHAPTER_DIR / "ch05.md").read_text(encoding="utf-8")
        # 5.3 与 5.4 是 TPOT、SLO、Goodput 的唯一主场，注释必须在这里，
        # 不能像以前那样落在 ch15 和 ch19。
        for marker in ["> **TPOT**", "> **SLO**", "> **Goodput**"]:
            self.assertIn(marker, source)
        # Goodput 的三个条件缺一不可，尤其是质量那一条。
        goodput = source[source.index("> **Goodput**"):]
        goodput = goodput[: goodput.index("\n\n")]
        for cond in ["成功", "质量达标", "SLO"]:
            self.assertIn(cond, goodput)
        self.assertIn("否决项", goodput)

    def test_the_two_reminder_chapters_no_longer_redefine_them(self):
        root = CHAPTER_DIR.parent
        ch15 = (root / "ch15" / "ch15.md").read_text(encoding="utf-8")
        ch19 = (root / "ch19" / "ch19.md").read_text(encoding="utf-8")
        self.assertNotIn("> **TPOT**", ch15)
        self.assertNotIn("> **Goodput**", ch19)
        self.assertIn("第 5.3 节", ch15)
        self.assertIn("第 5.4 节", ch19)

    def test_slo_is_not_used_before_it_is_defined(self):
        root = CHAPTER_DIR.parent
        for number in range(0, 5):
            earlier = (root / f"ch0{number}" / f"ch0{number}.md").read_text(encoding="utf-8")
            with self.subTest(chapter=number):
                self.assertNotIn("SLO", earlier)

    def test_contract_section_carries_a_worked_example(self):
        source = (CHAPTER_DIR / "ch05.md").read_text(encoding="utf-8")
        # 5.8 交付的是本章承诺的产出物，本轮之前它是全书最短的一节且没有算例。
        section = source[source.index("## 5.8 "): source.index("## 5.9 ")]
        for number in ["120、190、300 ms", "60、90、150 ms", "300 ms", "150 ms"]:
            self.assertIn(number, section)
        self.assertIn("不是任何一段真实耗时", section)

    def test_the_lookalike_field_warning_moved_into_the_pitfalls(self):
        source = (CHAPTER_DIR / "ch05.md").read_text(encoding="utf-8")
        budget = source[source.index("## 5.9 "): source.index("## 5.10 ")]
        pitfalls = source[source.index("### 两个不会写进指标合同的误区"):]
        self.assertNotIn("time_to_first_token_ms", budget)
        self.assertIn("time_to_first_token_ms", pitfalls)



if __name__ == "__main__":
    unittest.main()
