import unittest

from convert_sharegpt import pick_short_and_long, to_request_rows


class PickShortAndLongTest(unittest.TestCase):
    def test_picks_shortest_and_longest_by_prompt_len(self):
        rows = [
            {"prompt_len": 50, "prompt": "mid"},
            {"prompt_len": 5, "prompt": "short"},
            {"prompt_len": 800, "prompt": "long"},
            {"prompt_len": 10, "prompt": "short2"},
        ]

        picked = pick_short_and_long(rows, short_n=2, long_n=1)

        self.assertEqual([r["prompt"] for r in picked], ["short", "short2", "long"])

    def test_long_n_zero_returns_only_short(self):
        rows = [{"prompt_len": 5, "prompt": "a"}, {"prompt_len": 500, "prompt": "b"}]

        picked = pick_short_and_long(rows, short_n=1, long_n=0)

        self.assertEqual([r["prompt"] for r in picked], ["a"])


class ToRequestRowsTest(unittest.TestCase):
    def test_caps_max_tokens(self):
        rows = [{"prompt": "hi", "expected_output_len": 900}]

        out = to_request_rows(rows, max_tokens_cap=300)

        self.assertEqual(out[0]["max_tokens"], 300)

    def test_uses_expected_output_len_when_under_cap(self):
        rows = [{"prompt": "hi", "expected_output_len": 120}]

        out = to_request_rows(rows, max_tokens_cap=300)

        self.assertEqual(out[0]["max_tokens"], 120)


if __name__ == "__main__":
    unittest.main()
