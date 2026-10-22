import importlib.util
import math
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("mechanics.py")


def load_mechanics():
    if not MODULE_PATH.exists():
        raise AssertionError("code/ch03/mechanics.py must exist")
    spec = importlib.util.spec_from_file_location("chapter03_mechanics", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MechanicsTests(unittest.TestCase):
    def setUp(self):
        self.mechanics = load_mechanics()
        self.config = self.mechanics.ModelConfig(
            hidden_size=896,
            num_layers=24,
            num_attention_heads=14,
            num_kv_heads=2,
            head_dim=64,
            intermediate_size=4864,
            vocab_size=151936,
        )

    def test_stage_shapes_show_gqa_asymmetric_q_and_kv(self):
        shapes = self.mechanics.stage_shapes(self.config, batch_size=1, sequence_length=10)
        self.assertEqual(shapes["hidden_states"], [1, 10, 896])
        self.assertEqual(shapes["query"], [1, 14, 10, 64])
        self.assertEqual(shapes["key"], [1, 2, 10, 64])
        self.assertEqual(shapes["value"], [1, 2, 10, 64])
        self.assertEqual(shapes["logits"], [1, 10, 151936])

    def test_invalid_head_relationship_is_rejected(self):
        bad = self.mechanics.ModelConfig(
            hidden_size=896,
            num_layers=24,
            num_attention_heads=14,
            num_kv_heads=3,
            head_dim=64,
            intermediate_size=4864,
            vocab_size=151936,
        )
        with self.assertRaisesRegex(ValueError, "divisible"):
            self.mechanics.stage_shapes(bad, batch_size=1, sequence_length=10)

    def test_softmax_returns_normalized_probabilities(self):
        probabilities = self.mechanics.softmax([1.0, 2.0, 3.0], temperature=1.0)
        self.assertTrue(math.isclose(sum(probabilities), 1.0, rel_tol=1e-9))
        self.assertGreater(probabilities[2], probabilities[1])
        self.assertGreater(probabilities[1], probabilities[0])

    def test_top_k_masks_tokens_outside_candidate_set(self):
        probabilities = self.mechanics.top_k_probabilities(
            [1.0, 2.0, 3.0, 4.0], temperature=1.0, top_k=2
        )
        self.assertEqual(probabilities[:2], [0.0, 0.0])
        self.assertTrue(math.isclose(sum(probabilities), 1.0, rel_tol=1e-9))

    def test_invalid_sampling_parameters_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "temperature"):
            self.mechanics.softmax([1.0], temperature=0)
        with self.assertRaisesRegex(ValueError, "top_k"):
            self.mechanics.top_k_probabilities([1.0, 2.0], temperature=1.0, top_k=0)

    def test_generation_trace_separates_prefill_and_decode(self):
        trace = self.mechanics.build_execution_trace(prompt_tokens=5, decode_steps=3)
        self.assertEqual(trace[0]["phase"], "prefill")
        self.assertEqual(trace[0]["input_tokens"], 5)
        self.assertEqual(trace[0]["cache_after"], 5)
        self.assertEqual([event["phase"] for event in trace[1:]], ["decode"] * 3)
        self.assertEqual([event["input_tokens"] for event in trace[1:]], [1, 1, 1])
        self.assertEqual(trace[-1]["cache_after"], 8)

    def test_invalid_trace_lengths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "prompt_tokens"):
            self.mechanics.build_execution_trace(prompt_tokens=0, decode_steps=1)
        with self.assertRaisesRegex(ValueError, "decode_steps"):
            self.mechanics.build_execution_trace(prompt_tokens=4, decode_steps=-1)

    def test_report_connects_shapes_sampling_and_execution(self):
        report = self.mechanics.build_report(
            config=self.config,
            prompt_tokens=5,
            decode_steps=2,
            logits=[0.1, 1.4, 0.2, 0.8],
            temperature=1.0,
            top_k=2,
            seed=7,
        )
        self.assertEqual(report["mode"], "synthetic_mechanics")
        self.assertEqual(report["shapes"]["query"], [1, 14, 5, 64])
        self.assertIn(report["sampling"]["selected_token_id"], [1, 3])
        self.assertEqual(report["execution_trace"][-1]["cache_after"], 7)


if __name__ == "__main__":
    unittest.main()


def load_probe():
    path = Path(__file__).with_name("chat_template_probe.py")
    if not path.exists():
        raise AssertionError("code/ch03/chat_template_probe.py must exist")
    spec = importlib.util.spec_from_file_location("chapter03_probe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ChatTemplateProbeTests(unittest.TestCase):
    """3.2 那 30 个 token 的构成。脚本本身要上机跑，这里只钉住它的读法。"""

    def setUp(self):
        self.probe = load_probe()

    def test_the_overhead_is_the_difference_between_the_two_counts(self):
        report = self.probe.analyse({
            "prompt_tokens_with_template": 30,
            "prompt_tokens_bare": 12,
            "rendered": "<|im_start|>user\n请用三句话介绍 LLM 在线推理。<|im_end|>\n"
                        "<|im_start|>assistant\n",
        }, "请用三句话介绍 LLM 在线推理。")
        self.assertEqual(report["template_overhead_tokens"], 18)
        self.assertFalse(report["has_default_system"])
        self.assertIn("控制标记本身", report["reading"])

    def test_a_default_system_prompt_is_called_out(self):
        """模板自己插的那句不是控制标记，3.2 不能把它算进去。"""
        report = self.probe.analyse({
            "prompt_tokens_with_template": 42,
            "prompt_tokens_bare": 12,
            "rendered": "<|im_start|>system\nYou are Qwen, created by Alibaba Cloud."
                        "<|im_end|>\n<|im_start|>user\n请用三句话介绍 LLM 在线推理。"
                        "<|im_end|>\n<|im_start|>assistant\n",
        }, "请用三句话介绍 LLM 在线推理。")
        self.assertTrue(report["has_default_system"])
        self.assertEqual(report["template_overhead_tokens"], 30)
        self.assertIn("默认系统提示", report["reading"])

    def test_a_missing_count_does_not_crash_the_reading(self):
        report = self.probe.analyse({"prompt_tokens_with_template": None,
                                     "prompt_tokens_bare": None,
                                     "rendered": ""}, "x")
        self.assertIsNone(report["template_overhead_tokens"])
        self.assertIn("没拿到计数", report["reading"])

    def test_local_mode_says_what_is_missing_instead_of_failing_late(self):
        import sys
        if "transformers" in sys.modules:
            self.skipTest("transformers 已装，这条只测缺包时的提示")
        with self.assertRaises(self.probe.ProbeError) as ctx:
            self.probe.probe_via_transformers("any/model", "x")
        self.assertIn("transformers", str(ctx.exception))
