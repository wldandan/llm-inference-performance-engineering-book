import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


FIGURE_DIR = Path(__file__).parent
SVG_NS = "http://www.w3.org/2000/svg"
EXPECTED_FIGURES = {
    "fig01-01_minimal_service_path.svg": "第一个 LLM 服务的最小运行链路",
    "fig01-02_readiness_evidence.svg": "三层就绪证据",
    "fig01-03_sync_request_acceptance.svg": "同步请求字段与响应验收项",
    "fig01-04_streaming_client_events.svg": "流式调用里客户端能记下的四个时刻",
    "fig01-05_one_number_two_questions.svg": "一个总时长，两个独立的问题",
}


class FigureSystemTests(unittest.TestCase):
    def test_figure_set_is_complete(self):
        self.assertEqual(
            set(EXPECTED_FIGURES),
            {path.name for path in FIGURE_DIR.glob("*.svg")},
        )

    def test_every_figure_uses_v2_visual_contract(self):
        for filename, expected_title in EXPECTED_FIGURES.items():
            with self.subTest(filename=filename):
                path = FIGURE_DIR / filename
                source = path.read_text(encoding="utf-8")
                root = ET.fromstring(source)
                self.assertEqual(root.attrib.get("width"), "1280")
                self.assertEqual(root.attrib.get("height"), "720")
                self.assertEqual(root.attrib.get("viewBox"), "0 0 1280 720")
                self.assertEqual(root.attrib.get("data-figure-system"), "chapter01-v2")
                self.assertIn("aria-labelledby", root.attrib)

                title = root.find(f"{{{SVG_NS}}}title")
                description = root.find(f"{{{SVG_NS}}}desc")
                self.assertIsNotNone(title)
                self.assertIsNotNone(description)
                self.assertIn(expected_title, title.text or "")
                self.assertGreater(len((description.text or "").strip()), 20)
                self.assertIn("PingFang SC", source)
                self.assertIn("关键结论", source)
                self.assertNotIn("Key Takeaway", source)
                self.assertIn("marker-end", source)

                font_sizes = [int(value) for value in re.findall(r"font-size:\s*(\d+)px", source)]
                self.assertTrue(font_sizes)
                self.assertGreaterEqual(min(font_sizes), 14)

                note = path.with_suffix(".figure-note.md")
                self.assertTrue(note.exists())
                note_source = note.read_text(encoding="utf-8")
                self.assertIn("来源段落", note_source)
                self.assertIn("关键结论", note_source)

    def test_readiness_figure_keeps_the_cannot_prove_column(self):
        source = (FIGURE_DIR / "fig01-02_readiness_evidence.svg").read_text(encoding="utf-8")
        for label in ["第一层 · 进程", "第二层 · 模型列表", "第三层 · 真实生成", "仍不能证明什么"]:
            self.assertIn(label, source)
        self.assertNotIn("Gateway", source)

    def test_streaming_figure_stays_on_the_client_side(self):
        source = (FIGURE_DIR / "fig01-04_streaming_client_events.svg").read_text(encoding="utf-8")
        for label in ["请求发出", "首个内容分片", "收到 [DONE]", "stream_chunks"]:
            self.assertIn(label, source)
        for forbidden in ["TTFT", "first_token", "Queue", "Prefill"]:
            self.assertNotIn(forbidden, source)

    def test_comparison_figure_labels_the_real_numbers_as_client_observation(self):
        source = (FIGURE_DIR / "fig01-05_one_number_two_questions.svg").read_text(encoding="utf-8")
        for label in ["29.64 ms", "2345.26 ms", "不是性能结论"]:
            self.assertIn(label, source)
        self.assertNotIn("TTFT =", source)

    def test_chapter_uses_five_continuous_figures_without_mechanism_sections(self):
        chapter_source = (Path(__file__).parent.parent / "ch01.md").read_text(
            encoding="utf-8"
        )
        image_links = re.findall(r"!\[[^\]]*\]\((figures/[^)]+\.svg)\)", chapter_source)
        self.assertEqual(
            image_links,
            [f"figures/{filename}" for filename in EXPECTED_FIGURES],
        )
        captions = re.findall(r"图1-(\d+)[：:]", chapter_source)
        self.assertEqual(captions, ["1", "2", "3", "4", "5"])
        self.assertNotIn("插图占位", chapter_source)
        for heading in ["Gateway", "Queue", "Prefill", "Decode", "KV Cache"]:
            self.assertNotRegex(chapter_source, rf"(?m)^##\s+1\.\d+\s+{heading}")
        self.assertIn("不把客户端观察值归因到某个服务端阶段", chapter_source)
        # 1.8 只禁止冒充服务端 TTFT，不否认它是客户端口径的 TTFT；
        # 否则会与第 5 章 5.2 对客户端 TTFT 的定义互相矛盾。
        self.assertIn("客户端观测到的首个内容分片等待", chapter_source)
        self.assertNotIn("不能叫 TTFT", chapter_source)
        # GX10 是主机名，GB10 是 GPU 型号，第 1 章必须把这两个名字说清。
        self.assertIn("前者是主机名，后者是那台机器上的 GPU 型号", chapter_source)
        # 全书引用最多的那份真机记录必须是独立小节，别的章节才引得到节号。
        self.assertIn("## 1.8 一份在真实 GPU 上跑出来的记录", chapter_source)
        self.assertEqual(
            re.findall(r"(?m)^## (\d+\.\d+) ", chapter_source),
            [f"1.{i}" for i in range(1, 12)],
        )


if __name__ == "__main__":
    unittest.main()
