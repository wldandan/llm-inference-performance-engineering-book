import unittest

from timing_stats import describe_timing_pattern


class DescribeTimingPatternTest(unittest.TestCase):
    def test_flags_growing_pattern_when_later_steps_much_slower(self):
        # no-cache: recompute the whole growing sequence every step -> roughly linear growth
        times = [0.05, 0.02, 0.03, 0.08, 0.12, 0.18]

        result = describe_timing_pattern(times)

        self.assertEqual(result["first_token_time_s"], 0.05)
        self.assertTrue(result["is_growing"])

    def test_flags_flat_pattern_when_steps_roughly_constant(self):
        # cached decode: O(1) per step -> first token (prefill) slow, rest roughly flat
        times = [0.05, 0.011, 0.010, 0.012, 0.009, 0.011]

        result = describe_timing_pattern(times)

        self.assertTrue(result["first_token_time_s"] == 0.05)
        self.assertFalse(result["is_growing"])

    def test_computes_avg_of_steps_after_the_first(self):
        times = [1.0, 0.1, 0.3]

        result = describe_timing_pattern(times)

        self.assertAlmostEqual(result["avg_subsequent_step_time_s"], 0.2)

    def test_raises_on_empty_input(self):
        with self.assertRaises(ValueError):
            describe_timing_pattern([])


if __name__ == "__main__":
    unittest.main()
