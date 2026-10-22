#!/usr/bin/env python3
"""Figure tests for Chapter 20.

Beyond the shared visual contract, the numeric assertions pin every number drawn
in these figures to code/ch20/scheduler_watch.py and
content/ch20/evidence/scheduler-trace-sample.json, so the pictures and the code
cannot drift apart.
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
CHAPTER = CHAPTER_DIR / "ch20.md"
ROOT = FIGURE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "code" / "ch20"))

FIGURES = {
    "fig20-01_three_states.svg": "三个状态，一条路径，两条非常规边",
    "fig20-02_queue_amplification.svg": "接近饱和时排队时间对负载的敏感度急剧上升",
    "fig20-03_three_signals.svg": "三个调度信号的先后顺序与 lead_time",
}

FORBIDDEN = {
    # 20.6 明说这条式子给的是形状和量级，不是预测值，所以图里不该出现毫秒数
    "fig20-02_queue_amplification.svg": ["预测排队 ", "ms 的排队时间"],
    # 20.7 的结论是配在第一个信号上，不是给一个万能阈值
    "fig20-03_three_signals.svg": ["建议阈值设成", "推荐 lead_time"],
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

    def test_every_figure_is_referenced_in_the_chapter(self):
        text = CHAPTER.read_text(encoding="utf-8")
        for i, name in enumerate(FIGURES, 1):
            with self.subTest(figure=name):
                self.assertIn(name, text, f"{name} 没有出现在正文里")
                self.assertIn(f"图20-{i}：", text, f"正文缺少图注 图20-{i}：")

    def test_figure_numbers_are_continuous(self):
        text = CHAPTER.read_text(encoding="utf-8")
        found = sorted(int(m) for m in re.findall(r"图20-(\d+)：", text))
        self.assertEqual(found, list(range(1, len(FIGURES) + 1)))

    def test_no_em_dash_and_no_corner_quotes(self):
        """全书体例：不用破折号，正文与图内都用全角引号。"""
        for name in FIGURES:
            source = (FIGURE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(figure=name):
                self.assertNotIn("——", source)
                self.assertNotIn("「", source)
                self.assertNotIn("」", source)


class TestFiguresMatchTheCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import scheduler_watch as sw
        cls.sw = sw
        cls.trace = json.loads(
            (ROOT / "content" / "ch20" / "evidence"
             / "scheduler-trace-sample.json").read_text(encoding="utf-8"))
        cls.reading = sw.analyze(cls.trace)

    def svg(self, name: str) -> str:
        return (FIGURE_DIR / name).read_text(encoding="utf-8")

    def test_synthetic_data_is_labelled_where_it_is_drawn(self):
        self.assertTrue(self.trace["synthetic"])
        self.assertIn("合成 trace", self.svg("fig20-03_three_signals.svg"))

    # --- 图20-2 ---
    def test_the_four_multipliers_drawn_match_amplification(self):
        source = self.svg("fig20-02_queue_amplification.svg")
        for rho, label in ((0.5, "1 倍"), (0.8, "4 倍"), (0.9, "9 倍"),
                           (0.95, "19 倍")):
            with self.subTest(rho=rho):
                self.assertEqual(round(self.sw.amplification(rho)),
                                 int(label.split()[0]))
                self.assertIn(label, source)

    def test_the_subtitle_states_the_same_four_values(self):
        source = self.svg("fig20-02_queue_amplification.svg")
        self.assertIn("0.5、0.8、0.9、0.95 上分别是 1、4、9、19", source)

    def test_the_three_caveats_are_all_drawn(self):
        """20.6 列的三处不符，一处都不能少。"""
        source = self.svg("fig20-02_queue_amplification.svg")
        for phrase in ("服务台不止一个", "服务时长不服从指数分布", "容量本身会缩"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, source)

    def test_the_utilisation_caveat_is_drawn(self):
        """横轴那个利用率不是 GPU 利用率，这句话必须画出来。"""
        source = self.svg("fig20-02_queue_amplification.svg")
        self.assertIn("不是监控面板上的 GPU 利用率", source)

    def test_the_multi_server_curve_is_drawn_as_the_lower_bound(self):
        """单服务台是上界，64 个槽位的 Erlang C 是下界，两条都要画出来。

        上界只在服务台个数这一维成立，图例要把这个限定写出来：服务时长的波动
        和抢占会把真实排队推到它之上（20.6，Part 5 审阅 P1-4）。
        """
        source = self.svg("fig20-02_queue_amplification.svg")
        self.assertIn("单服务台（按服务台个数的上界）", source)
        self.assertIn("64 个槽位算（Erlang C，下界）", source)
        self.assertLess(self.sw.multi_server_wait_factor(64, 0.9),
                        self.sw.amplification(0.9) / 2)

    # --- 图20-3 ---
    def test_the_three_onsets_drawn_match_the_trace(self):
        source = self.svg("fig20-03_three_signals.svg")
        self.assertEqual(self.reading["saturation_onset"], 15.0)
        self.assertEqual(self.reading["queue_onset"], 25.0)
        self.assertEqual(self.reading["preemption_onset"], 40.0)
        for onset in (15, 25, 40):
            with self.subTest(onset=onset):
                self.assertIn(f"{onset} 秒", source)

    def test_the_lead_time_drawn_matches(self):
        source = self.svg("fig20-03_three_signals.svg")
        self.assertEqual(self.reading["lead_time"], 10.0)
        self.assertIn("lead_time = 10 秒", source)

    def test_the_lead_time_is_the_gap_between_the_first_two(self):
        self.assertEqual(
            self.reading["lead_time"],
            self.reading["queue_onset"] - self.reading["saturation_onset"])

    def test_the_verdict_and_preemption_count_drawn_match(self):
        source = self.svg("fig20-03_three_signals.svg")
        self.assertEqual(self.reading["verdict"], "KV 不足")
        self.assertIn(self.reading["verdict"], source)
        self.assertIn(f"抢占 {self.reading['preemptions_in_window']} 次", source)

    def test_the_onsets_are_drawn_in_20_7s_order(self):
        source = self.svg("fig20-03_three_signals.svg")
        self.assertLess(source.index("15 秒"), source.index("25 秒"))
        self.assertLess(source.index("25 秒"), source.index("40 秒"))

    def test_the_negative_lead_time_branch_is_drawn_too(self):
        """20.7 的顺序被打破本身是一条结论，图里必须留这一半。"""
        source = self.svg("fig20-03_three_signals.svg")
        self.assertIn("lead_time 小于或等于零", source)
        self.assertIn("完全失灵", source)

    # --- 图20-1 ---
    def test_both_non_standard_edges_are_drawn_with_their_chapters(self):
        source = self.svg("fig20-01_three_states.svg")
        self.assertIn("拒绝", source)
        self.assertIn("第 21 章", source)
        self.assertIn("抢占", source)
        self.assertIn("第 16 章", source)

    def test_the_itl_example_drawn_matches_chapter_15(self):
        """图里引的那组数必须和 20.3 正文里写的一致。"""
        source = self.svg("fig20-01_three_states.svg")
        chapter = CHAPTER.read_text(encoding="utf-8")
        self.assertIn("P99 ITL 从 40 涨到 210", source)
        self.assertIn("P99 ITL 从 40 ms 涨到 210 ms", chapter)


if __name__ == "__main__":
    unittest.main()
