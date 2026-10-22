#!/usr/bin/env python3
"""Figure tests for Chapter 21.

The numeric assertions recompute every number drawn from
code/ch21/overload_drill.py and the two synthetic drills in
content/ch21/evidence/, so the figures and the text cannot drift apart.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

FIGURE_DIR = Path(__file__).parent
CHAPTER_DIR = FIGURE_DIR.parent
CHAPTER = CHAPTER_DIR / "ch21.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch21"))

FIGURES = {
    "fig21-01_two_collapse_shapes.svg": "过载时的两种垮法",
    "fig21-02_five_controls_on_path.svg": "五项治理在请求路径上的位置",
    "fig21-03_layered_timeouts.svg": "LLM 服务需要分层的超时",
    "fig21-04_retry_loop.svg": "重试把 4% 的失败推成 73%",
}

FORBIDDEN = {
    # 21.1 给的是形状，不是某个万能的准入阈值
    "fig21-01_two_collapse_shapes.svg": ["建议阈值", "推荐容量"],
    # 21.1 的地图只给位置和约束，取值在后面五节
    "fig21-02_five_controls_on_path.svg": ["建议设为", "阈值为", "推荐"],
    # 21.3 的四个超时阈值取决于负载的长度分布，图里不该给具体毫秒数
    "fig21-03_layered_timeouts.svg": ["建议设为", "推荐 30 秒"],
    # 21.5 说这两条式子是形状不是预测值
    "fig21-04_retry_loop.svg": ["预测雪崩时间", "将在 ", "秒后崩溃"],
}


class TestFigureSet(unittest.TestCase):
    def test_every_figure_and_note_exists(self):
        for name in FIGURES:
            self.assertTrue((FIGURE_DIR / name).exists(), f"missing {name}")
            note = FIGURE_DIR / (name[:-4] + ".figure-note.md")
            self.assertTrue(note.exists(), f"missing note for {name}")

    def test_no_orphan_svg(self):
        on_disk = {p.name for p in FIGURE_DIR.glob("*.svg")}
        self.assertEqual(on_disk, set(FIGURES))

    def test_visual_contract(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            root = ET.fromstring(source)
            with self.subTest(figure=name):
                self.assertEqual(root.get("width"), "1280")
                self.assertEqual(root.get("height"), "720")
                self.assertEqual(root.get("data-figure-system"), "part02-v1")
                self.assertEqual(root.get("aria-labelledby"), "fig-title fig-desc")
                ns = "{http://www.w3.org/2000/svg}"
                self.assertIsNotNone(root.find(f"{ns}title"))
                desc = root.find(f"{ns}desc")
                self.assertIsNotNone(desc)
                self.assertGreater(len((desc.text or "").strip()), 20)
                self.assertIn("PingFang SC", source)
                self.assertNotIn("Key Takeaway", source)
                self.assertIn("关键结论", source)

    def test_minimum_font_size(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            sizes = [float(v) for v in
                     re.findall(r"font-size:(\d+(?:\.\d+)?)px", source)]
            with self.subTest(figure=name):
                self.assertTrue(sizes)
                self.assertGreaterEqual(min(sizes), 14)

    def test_notes_carry_the_four_required_lines(self):
        for name in FIGURES:
            note = (FIGURE_DIR / (name[:-4] + ".figure-note.md")).read_text(
                encoding="utf-8")
            with self.subTest(figure=name):
                for field in ("来源段落", "阅读顺序", "关键结论", "表达边界"):
                    self.assertIn(field, note)

    def test_forbidden_terms_stay_out(self):
        for name, terms in FORBIDDEN.items():
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            for term in terms:
                with self.subTest(figure=name, term=term):
                    self.assertNotIn(term, source)

    def test_every_figure_is_referenced_and_numbered_in_order(self):
        text = CHAPTER.read_text(encoding="utf-8")
        positions = []
        for i, name in enumerate(FIGURES, 1):
            with self.subTest(figure=name):
                self.assertIn(name, text, f"{name} 没有出现在正文里")
                caption = f"图21-{i}："
                self.assertIn(caption, text, f"正文缺少图注 {caption}")
                positions.append(text.index(caption))
        self.assertEqual(positions, sorted(positions), "图号与正文出现顺序不一致")

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图21-(\d+)：", text))
        self.assertEqual(found, list(range(1, len(FIGURES) + 1)))

    def test_no_em_dash_and_no_corner_quotes(self):
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertNotIn("——", source)
                self.assertNotIn("「", source)
                self.assertNotIn("」", source)


class TestFiguresMatchTheCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import overload_drill as od
        cls.od = od
        ev = ROOT / "content" / "ch21" / "evidence"
        cls.no_adm = json.loads(
            (ev / "overload-drill-no-admission.json").read_text(encoding="utf-8"))
        cls.with_adm = json.loads(
            (ev / "overload-drill-with-admission.json").read_text(encoding="utf-8"))
        cls.read_no = od.analyze(cls.no_adm)
        cls.read_with = od.analyze(cls.with_adm)
        cls.loop = od.retry_loop([0.04, 0.15, 0.40, 0.73], retries=3)

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_synthetic_data_is_labelled_where_it_is_drawn(self):
        for doc in (self.no_adm, self.with_adm):
            self.assertTrue(doc["synthetic"])
        self.assertIn("合成演练", self.svg("fig21-01_two_collapse_shapes.svg"))

    # --- 图21-1 ---
    def test_the_two_retained_shares_drawn_match_the_drills(self):
        source = self.svg("fig21-01_two_collapse_shapes.svg")
        self.assertIn(f"{self.read_with['goodput_retained'] * 100:.1f}%", source)
        self.assertIn(f"{self.read_no['goodput_retained'] * 100:.1f}%", source)

    def test_the_two_shapes_are_the_ones_the_code_classifies(self):
        self.assertEqual(self.read_with["shape"], "健康")
        self.assertEqual(self.read_no["shape"], "危险")

    def test_the_final_goodputs_drawn_match(self):
        source = self.svg("fig21-01_two_collapse_shapes.svg")
        self.assertIn(f"有准入 {self.with_adm['steps'][-1]['goodput']:.1f}", source)
        self.assertIn(f"没有准入 {self.no_adm['steps'][-1]['goodput']:.1f}", source)

    def test_the_capacity_line_matches_both_drills(self):
        source = self.svg("fig21-01_two_collapse_shapes.svg")
        self.assertEqual(self.no_adm["capacity_qps"], self.with_adm["capacity_qps"])
        self.assertIn(f"容量 {self.no_adm['capacity_qps']:.0f} QPS", source)

    def test_the_rejected_total_drawn_matches(self):
        source = self.svg("fig21-01_two_collapse_shapes.svg")
        self.assertIn(f"{self.read_with['rejected_final_qps']:.1f} QPS", source)

    def test_both_drills_share_every_offered_qps(self):
        """两条曲线只有在同一组横轴上才谈得上对比。"""
        self.assertEqual([s["offered_qps"] for s in self.no_adm["steps"]],
                         [s["offered_qps"] for s in self.with_adm["steps"]])

    # --- 图21-4 ---
    def test_the_four_amplification_factors_drawn_match(self):
        source = self.svg("fig21-04_retry_loop.svg")
        got = [round(r["amplification"], 2) for r in self.loop["rounds"]]
        self.assertEqual(got, [1.04, 1.18, 1.62, 2.65])
        for value in ("1.04", "1.18", "1.62", "2.65"):
            with self.subTest(value=value):
                self.assertIn(value, source)

    def test_the_four_failure_rates_drawn_match(self):
        source = self.svg("fig21-04_retry_loop.svg")
        for rate in ("4%", "15%", "40%", "73%"):
            with self.subTest(rate=rate):
                self.assertIn(rate, source)

    def test_the_availability_drawn_is_computed_not_copied(self):
        source = self.svg("fig21-04_retry_loop.svg")
        self.assertAlmostEqual(self.loop["availability"], 0.716, places=3)
        self.assertIn("28.4%", source)
        self.assertIn("71.6%", source)

    def test_the_attempts_count_drawn_matches_three_retries(self):
        source = self.svg("fig21-04_retry_loop.svg")
        self.assertEqual(self.loop["attempts_per_request"], 4)
        self.assertIn("最多试 4 次", source)

    def test_the_first_round_is_drawn_as_the_harmless_looking_one(self):
        """第 0 轮那 4% 是全图的点，必须出现在关键结论里。"""
        source = self.svg("fig21-04_retry_loop.svg")
        self.assertIn("4% 的额外流量", source)
        self.assertLess(self.loop["rounds"][0]["amplification"], 1.05)

    def test_the_loop_is_drawn_as_a_loop(self):
        source = self.svg("fig21-04_retry_loop.svg")
        for node in ("系统过载", "请求超时", "客户端重试", "负载上升"):
            with self.subTest(node=node):
                self.assertIn(node, source)
        self.assertIn("p 不是常数", source)

    # --- 图21-3 ---
    def test_all_four_timeout_layers_are_drawn(self):
        source = self.svg("fig21-03_layered_timeouts.svg")
        for name in ("排队超时", "首包超时", "流间隔超时", "总超时"):
            with self.subTest(name=name):
                self.assertIn(name, source)

    def test_the_useful_ones_are_called_out(self):
        """四个超时里前三个各自能定位到一个原因，总超时只说明慢（21.3）。"""
        source = self.svg("fig21-03_layered_timeouts.svg")
        self.assertIn("前三个才是真正有用的", source)
        self.assertIn("前三个才是真正有用的", CHAPTER.read_text(encoding="utf-8"))

    def test_the_stream_interval_threshold_points_at_chapter_16(self):
        source = self.svg("fig21-03_layered_timeouts.svg")
        self.assertIn("第 16 章", source)
        self.assertIn("误杀", source)

    def test_the_forty_fold_spread_matches_the_chapter(self):
        source = self.svg("fig21-03_layered_timeouts.svg")
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("耗时差四十倍", source)
        self.assertIn("耗时差四十倍", chapter)

    # --- 图21-2 ---
    def test_the_map_places_all_five_controls(self):
        source = self.svg("fig21-02_five_controls_on_path.svg")
        for name in ("① 准入", "② 超时", "③ 取消", "④ 重试", "⑤ 背压"):
            with self.subTest(name=name):
                self.assertIn(name, source)

    def test_the_map_carries_the_three_constraints_the_text_states(self):
        """图里的三条约束，21.1 正文要逐条说过，图和正文才不会各说各的。"""
        source = self.svg("fig21-02_five_controls_on_path.svg")
        chapter = CHAPTER.read_text(encoding="utf-8")
        intro = chapter[chapter.index("## 21.1"):chapter.index("## 21.2")]
        for fig_says, text_says in (("超时不配取消", "超时不配取消"),
                                    ("不加约束的重试", "不加约束的重试"),
                                    ("用错对象", "用错对象")):
            with self.subTest(constraint=fig_says):
                self.assertIn(fig_says, source)
                self.assertIn(text_says, intro)
        self.assertIn("1 + p + p² + …", source)
        self.assertIn("1 + p + p² + …", intro)

    def test_the_map_points_at_the_timeout_figure_by_its_number(self):
        source = self.svg("fig21-02_five_controls_on_path.svg")
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("图 21-3", source)
        self.assertIn("图21-3：四个超时各管一段", chapter)


if __name__ == "__main__":
    unittest.main()
