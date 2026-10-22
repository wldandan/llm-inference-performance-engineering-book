import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


FIGURE_DIR = Path(__file__).parent
CHAPTER_DIR = FIGURE_DIR.parent
SVG_NS = "http://www.w3.org/2000/svg"
EXPECTED_FIGURES = {
    "fig02-01_request_lifecycle_timeline.svg": "推理请求生命周期与关键时间点",
    "fig02-02_task_call_request.svg": "业务任务、LLM 调用与推理请求",
    "fig02-03_normalized_state_machine.svg": "归一化请求状态机",
    "fig02-04_queue_schedule_boundary.svg": "Queue 与首次调度的边界",
    "fig02-05_prefill_first_token.svg": "Prefill 与首 token 的边界",
    "fig02-06_decode_steps_kv_growth.svg": "Decode step 与 KV Cache 增长",
    "fig02-07_server_client_observation.svg": "服务端事件与客户端观测",
    "fig02-08_terminal_cleanup.svg": "三类终态与资源清理",
    "fig02-09_demo_event_report.svg": "真实 vLLM 请求生成生命周期证据报告",
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
                self.assertEqual(root.attrib.get("data-figure-system"), "chapter02-v2")
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

    def test_demo_figure_shows_the_real_vllm_evidence_path(self):
        source = (FIGURE_DIR / "fig02-09_demo_event_report.svg").read_text(
            encoding="utf-8"
        )
        self.assertIn("真实 vLLM 请求", source)
        self.assertIn("请求级 Metrics", source)
        self.assertIn("Prometheus 增量", source)
        self.assertIn("证据分级报告", source)


    def test_client_first_chunk_wait_is_not_denied_the_ttft_name(self):
        source = (CHAPTER_DIR / "ch02.md").read_text(encoding="utf-8")
        # 2.7 只禁止冒充服务端 TTFT；ch01 1.9 与 ch05 5.2 都按这个口径写，
        # 全称否定会让三章互相矛盾。
        self.assertIn("这个数不能当成服务端 TTFT", source)
        self.assertNotIn("不能改名叫 TTFT", source)
        self.assertIn("客户端口径的 TTFT", source)

    def test_agent_is_explained_where_it_carries_the_argument(self):
        source = (CHAPTER_DIR / "ch02.md").read_text(encoding="utf-8")
        # 2.1 用 Agent 搭起 Task / LLM Call / Inference Request 三层，
        # 这是全书第一处让 Agent 承重的地方。
        self.assertIn("> **Agent**（智能体）", source)

    def test_promise_about_chapter_five_matches_the_contract_fields(self):
        source = (CHAPTER_DIR / "ch02.md").read_text(encoding="utf-8")
        contract = (CHAPTER_DIR.parent / "ch05" / "ch05.md").read_text(encoding="utf-8")
        for field in ["Boundary", "Window", "Clock"]:
            self.assertIn(field, source)
            self.assertIn(f"| {field} |", contract)
        self.assertNotIn("写清名称、时间点、公式和采集位置", source)



if __name__ == "__main__":
    unittest.main()
