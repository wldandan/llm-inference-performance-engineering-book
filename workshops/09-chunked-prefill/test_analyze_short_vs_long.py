import unittest

from analyze_short_vs_long import class_stats, split_by_class


class SplitByClassTest(unittest.TestCase):
    def test_splits_index_0_and_7_as_long_rest_as_short(self):
        results = [{"i": i} for i in range(14)]  # two full cycles of 7

        long_results, short_results = split_by_class(results)

        self.assertEqual([r["i"] for r in long_results], [0, 7])
        self.assertEqual(len(short_results), 12)
        self.assertNotIn({"i": 0}, short_results)


class ClassStatsTest(unittest.TestCase):
    def test_computes_percentiles_from_successful_results_only(self):
        results = [
            {"success": True, "total_latency_ms": 100.0},
            {"success": True, "total_latency_ms": 200.0},
            {"success": False, "error": "boom"},
        ]

        stats = class_stats(results)

        self.assertEqual(stats["count"], 3)
        self.assertAlmostEqual(stats["p50_total_latency_ms"], 150.0)


if __name__ == "__main__":
    unittest.main()
