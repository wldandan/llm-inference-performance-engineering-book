import unittest

from kv_cache_math import ArchSummary
from transformer_walkthrough import _get_submodule, architecture_family_diff, expected_stage_shapes

QWEN_ARCH = ArchSummary(
    hidden_size=896,
    num_layers=24,
    num_attention_heads=14,
    num_kv_heads=2,
    head_dim=64,
    query_groups=7,
    uses_gqa=True,
    intermediate_size=4864,
    vocab_size=151936,
    max_position_embeddings=32768,
)


class ExpectedStageShapesTest(unittest.TestCase):
    def test_embedding_matrix_is_vocab_by_hidden(self):
        shapes = expected_stage_shapes(QWEN_ARCH, seq_len=10, batch=1)

        self.assertEqual(shapes["token_embedding_matrix"], (151936, 896))

    def test_hidden_states_shape_after_embedding(self):
        shapes = expected_stage_shapes(QWEN_ARCH, seq_len=10, batch=1)

        self.assertEqual(shapes["hidden_states_after_embedding"], (1, 10, 896))

    def test_query_key_value_shapes_show_gqa_asymmetry(self):
        shapes = expected_stage_shapes(QWEN_ARCH, seq_len=10, batch=1)

        # Raw q_proj/k_proj/v_proj Linear outputs (pre-reshape-into-heads):
        # query's last dim is 14*64=896, key/value's is only 2*64=128 -- this
        # is the concrete shape-level evidence for the GQA story in
        # kv_cache_math.py, visible even before splitting into per-head view.
        self.assertEqual(shapes["query_states"], (1, 10, 896))
        self.assertEqual(shapes["key_states"], (1, 10, 128))
        self.assertEqual(shapes["value_states"], (1, 10, 128))
        self.assertNotEqual(shapes["query_states"][-1], shapes["key_states"][-1])

    def test_attention_scores_are_seq_by_seq_per_query_head(self):
        shapes = expected_stage_shapes(QWEN_ARCH, seq_len=10, batch=1)

        self.assertEqual(shapes["attention_scores_per_head"], (1, 14, 10, 10))

    def test_mlp_uses_gated_swiglu_shape_not_plain_two_layer(self):
        shapes = expected_stage_shapes(QWEN_ARCH, seq_len=10, batch=1)

        # SwiGLU has TWO parallel projections to intermediate_size (gate and
        # up), unlike GPT-2's single up-projection -- see architecture_family_diff.
        self.assertEqual(shapes["mlp_gate_proj"], (1, 10, 4864))
        self.assertEqual(shapes["mlp_up_proj"], (1, 10, 4864))
        self.assertEqual(shapes["mlp_down_proj_output"], (1, 10, 896))

    def test_final_logits_are_vocab_sized(self):
        shapes = expected_stage_shapes(QWEN_ARCH, seq_len=10, batch=1)

        self.assertEqual(shapes["final_logits"], (1, 10, 151936))

    def test_batch_size_propagates(self):
        shapes = expected_stage_shapes(QWEN_ARCH, seq_len=5, batch=3)

        self.assertEqual(shapes["hidden_states_after_embedding"][0], 3)
        self.assertEqual(shapes["final_logits"][0], 3)


class ArchitectureFamilyDiffTest(unittest.TestCase):
    def test_covers_the_four_named_differences(self):
        rows = architecture_family_diff()

        aspects = {row["aspect"] for row in rows}
        self.assertEqual(
            aspects,
            {"位置编码", "Attention", "归一化", "MLP"},
        )
        for row in rows:
            self.assertIn("gpt2", row)
            self.assertIn("qwen", row)


class GetSubmoduleTest(unittest.TestCase):
    def test_walks_dotted_attribute_path(self):
        class Leaf:
            value = "found"

        class Mid:
            attn = Leaf()

        class Root:
            layer = Mid()

        self.assertEqual(_get_submodule(Root(), "layer.attn").value, "found")

    def test_numeric_segment_indexes_into_a_list(self):
        class Root:
            layers = ["zeroth", "first"]

        self.assertEqual(_get_submodule(Root(), "layers.1"), "first")

    def test_matches_real_qwen_module_path_shape(self):
        class Proj:
            name = "q_proj"

        class SelfAttn:
            q_proj = Proj()

        class Layer:
            self_attn = SelfAttn()

        class Inner:
            layers = [Layer()]

        class Root:
            model = Inner()

        found = _get_submodule(Root(), "model.layers.0.self_attn.q_proj")
        self.assertEqual(found.name, "q_proj")


if __name__ == "__main__":
    unittest.main()
