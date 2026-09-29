import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


CHAPTER_DIR = Path(__file__).parent.parent
FIGURE_DIR = CHAPTER_DIR / "figures"
SVG_NS = "http://www.w3.org/2000/svg"
EXPECTED_FIGURES = {
    "fig03-01_token_generation_pipeline.svg": "从文本到下一个 token",
    "fig03-02_decoder_block.svg": "Decoder-only Transformer Block",
    "fig03-03_causal_self_attention.svg": "Causal Self-Attention",
    "fig03-04_gqa_heads.svg": "MHA 与 GQA",
    "fig03-05_prefill_execution.svg": "Prefill",
    "fig03-06_sampling_pipeline.svg": "Sampling",
    "fig03-07_decode_kv_loop.svg": "Decode 与 KV Cache",
    "fig03-08_demo_mechanics_report.svg": "Demo 输出模型机制报告",
}


class ChapterFourFigureTests(unittest.TestCase):
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
                self.assertEqual(root.attrib.get("data-figure-system"), "chapter03-v2")
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

    def test_chapter_links_eight_continuous_figures(self):
        source = (CHAPTER_DIR / "ch03.md").read_text(encoding="utf-8")
        links = re.findall(r"!\[[^\]]*\]\((figures/[^)]+\.svg)\)", source)
        self.assertEqual(links, [f"figures/{name}" for name in EXPECTED_FIGURES])
        self.assertEqual(re.findall(r"图3-(\d+)[：:]", source), [str(i) for i in range(1, 9)])
        self.assertIn("合成机制报告", source)
        self.assertNotRegex(source, r"(?m)^##\s+4\.\d+\s+.*性能分析")
        self.assertNotRegex(source, r"(?m)^##\s+4\.\d+\s+.*优化")

    def test_kv_bytes_use_binary_units_like_chapter_eleven(self):
        source = (CHAPTER_DIR / "ch03.md").read_text(encoding="utf-8")
        # 2 × 24 × 14 × 64 × 2 = 86016 B = 84 KiB；2 × 24 × 2 × 64 × 2 = 12288 B = 12 KiB。
        # 第 11.3 节定的口径是显存一律二进制单位，第 11 章对同一个量写的就是 12 KiB。
        self.assertIn("84 KiB", source)
        self.assertIn("12 KiB", source)
        self.assertIn("86016 字节", source)
        self.assertIn("12288 字节", source)
        self.assertNotIn("86 KB", source)
        self.assertNotIn("12 KB", source)
        self.assertIn("一律用二进制单位", source)

    def test_pipeline_length_agrees_with_the_figure(self):
        source = (CHAPTER_DIR / "ch03.md").read_text(encoding="utf-8")
        # 图 3-1 画的是七个环节：两端加中间五个动作。
        self.assertIn("七个环节的链", source)
        self.assertIn("中间五个是动作", source)
        self.assertNotIn("压缩成七步", source)

    def test_kv_cache_saving_is_spelled_out(self):
        source = (CHAPTER_DIR / "ch03.md").read_text(encoding="utf-8")
        # 表里两个 285 是同一个式子 30 + 255，不点破读者会当成印错。
        self.assertIn("表里那两个 285 不是巧合", source)
        self.assertIn("0.7%", source)



if __name__ == "__main__":
    unittest.main()
