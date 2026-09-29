import unittest

from explore import kv_cache_seq_length


class FakeTensor:
    def __init__(self, shape):
        self.shape = shape


class KvCacheSeqLengthTest(unittest.TestCase):
    def test_uses_get_seq_length_when_available(self):
        class FakeCache:
            def get_seq_length(self):
                return 42

        self.assertEqual(kv_cache_seq_length(FakeCache()), 42)

    def test_falls_back_to_legacy_tuple_shape(self):
        # legacy: tuple of (key, value) per layer, key shaped [batch, heads, seq_len, head_dim]
        legacy = ((FakeTensor((1, 2, 17, 64)), FakeTensor((1, 2, 17, 64))),)

        self.assertEqual(kv_cache_seq_length(legacy), 17)


if __name__ == "__main__":
    unittest.main()
