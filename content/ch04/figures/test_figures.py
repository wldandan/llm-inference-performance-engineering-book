import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


FIGURE_DIR = Path(__file__).parent
CHAPTER_DIR = FIGURE_DIR.parent
SVG_NS = "http://www.w3.org/2000/svg"

EXPECTED_FIGURES = {
    "fig04-01_inference_system_architecture.svg": "LLM 推理系统全局架构",
    "fig04-02_client_gateway_boundary.svg": "Client 与 Gateway 边界",
    "fig04-03_scheduler_responsibility.svg": "三层流量决策",
    "fig04-04_worker_runtime_accelerator.svg": "Worker、Runtime 与 Accelerator",
    "fig04-05_serving_state_types.svg": "推理服务的三类状态",
    "fig04-06_deployment_patterns.svg": "LLM Serving 部署形态",
    "fig04-07_system_layer_mapping.svg": "成熟系统的架构层级映射",
    "fig04-08_architecture_to_analysis.svg": "从现象到组件和观测点",
    "fig04-09_demo_architecture_contract.svg": "架构契约 Demo",
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
                self.assertEqual(
                    root.attrib.get("data-figure-system"), "chapter04-v2"
                )
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

                font_sizes = [
                    int(value)
                    for value in re.findall(r"font-size:\s*(\d+)px", source)
                ]
                self.assertTrue(font_sizes)
                self.assertGreaterEqual(min(font_sizes), 14)

    def test_overview_distinguishes_minimum_and_scale_out_paths(self):
        source = (
            FIGURE_DIR / "fig04-01_inference_system_architecture.svg"
        ).read_text(encoding="utf-8")
        self.assertIn("单实例最小路径", source)
        self.assertIn("规模化可选层", source)

    def test_chapter_carries_at_least_one_worked_example(self):
        source = (CHAPTER_DIR / "ch04.md").read_text(encoding="utf-8")
        # 4.7 把第 2 章 2.9 那条正常请求的 42 ms 拆解搬到组件上：
        # req-ok 的 request_received 0 / queued 2 / scheduled 12 / first_token 42。
        for number in ["2 ms", "10 ms", "30 ms", "42 ms"]:
            self.assertIn(number, source)
        self.assertIn("服务端首 token 等待", source)
        self.assertIn("这几个数来自第 2 章的合成样例", source)
        # 4.3 必须说清同一条请求可能在三处各等一次。
        self.assertIn("同一条请求可能在这三处各等一次", source)


if __name__ == "__main__":
    unittest.main()
