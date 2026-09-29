import unittest

from kv_cache_math import (
    ArchSummary,
    bytes_to_mb,
    kv_cache_bytes_per_token,
    kv_cache_bytes_for_context,
    mha_equivalent_savings,
    summarize_architecture,
)


class KvCacheBytesPerTokenTest(unittest.TestCase):
    def test_matches_qwen2_5_0_5b_shape(self):
        # Qwen2.5-0.5B: 24 layers, 2 KV heads (GQA), head_dim 64, fp16 (2 bytes)
        per_token = kv_cache_bytes_per_token(num_layers=24, num_kv_heads=2, head_dim=64, dtype_bytes=2)

        # 2 (K and V) * 24 * 2 * 64 * 2 bytes = 12288 bytes/token
        self.assertEqual(per_token, 12288)

    def test_scales_linearly_with_num_kv_heads(self):
        one_head = kv_cache_bytes_per_token(num_layers=1, num_kv_heads=1, head_dim=64, dtype_bytes=2)
        four_heads = kv_cache_bytes_per_token(num_layers=1, num_kv_heads=4, head_dim=64, dtype_bytes=2)

        self.assertEqual(four_heads, one_head * 4)


class KvCacheBytesForContextTest(unittest.TestCase):
    def test_multiplies_per_token_by_context_length(self):
        total = kv_cache_bytes_for_context(
            context_len=8192, num_layers=24, num_kv_heads=2, head_dim=64, dtype_bytes=2
        )
        per_token = kv_cache_bytes_per_token(num_layers=24, num_kv_heads=2, head_dim=64, dtype_bytes=2)

        self.assertEqual(total, per_token * 8192)


class BytesToMbTest(unittest.TestCase):
    def test_converts_correctly(self):
        self.assertAlmostEqual(bytes_to_mb(1024 * 1024), 1.0)


class MhaEquivalentSavingsTest(unittest.TestCase):
    def test_gqa_saves_relative_to_full_mha(self):
        # Qwen2.5-0.5B: 14 attention heads, only 2 KV heads -> 7x savings on KV side
        result = mha_equivalent_savings(
            num_attention_heads=14, num_kv_heads=2, num_layers=24, head_dim=64, dtype_bytes=2
        )

        self.assertEqual(result["mha_bytes_per_token"], result["gqa_bytes_per_token"] * 7)
        self.assertAlmostEqual(result["reduction_pct"], (1 - 1 / 7) * 100, places=1)

    def test_no_savings_when_kv_heads_equals_attention_heads(self):
        result = mha_equivalent_savings(
            num_attention_heads=8, num_kv_heads=8, num_layers=1, head_dim=64, dtype_bytes=2
        )

        self.assertEqual(result["reduction_pct"], 0.0)
        self.assertEqual(result["mha_bytes_per_token"], result["gqa_bytes_per_token"])


class SummarizeArchitectureTest(unittest.TestCase):
    def test_builds_summary_from_a_config_like_object(self):
        class FakeConfig:
            hidden_size = 896
            num_hidden_layers = 24
            num_attention_heads = 14
            num_key_value_heads = 2
            intermediate_size = 4864
            vocab_size = 151936
            max_position_embeddings = 32768

        summary = summarize_architecture(FakeConfig())

        self.assertIsInstance(summary, ArchSummary)
        self.assertEqual(summary.head_dim, 896 // 14)
        self.assertEqual(summary.query_groups, 14 // 2)
        self.assertTrue(summary.uses_gqa)

    def test_uses_gqa_is_false_when_kv_heads_missing(self):
        class FakeConfigNoGqa:
            hidden_size = 768
            num_hidden_layers = 12
            num_attention_heads = 12
            intermediate_size = 3072
            vocab_size = 50257
            max_position_embeddings = 1024

        summary = summarize_architecture(FakeConfigNoGqa())

        self.assertFalse(summary.uses_gqa)
        self.assertEqual(summary.num_kv_heads, summary.num_attention_heads)


if __name__ == "__main__":
    unittest.main()
