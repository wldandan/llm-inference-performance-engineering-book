import unittest

from bench_naive import extract_token_text, parse_sse_line


class ParseSseLineTest(unittest.TestCase):
    def test_parses_data_line(self):
        line = b'data: {"token": " a", "sequence_id": "abc"}\n\n'
        self.assertEqual(parse_sse_line(line), {"token": " a", "sequence_id": "abc"})

    def test_ignores_blank_line(self):
        self.assertIsNone(parse_sse_line(b"\n"))

    def test_ignores_non_data_line(self):
        self.assertIsNone(parse_sse_line(b": comment\n"))


class ExtractTokenTextTest(unittest.TestCase):
    def test_returns_token_field(self):
        self.assertEqual(extract_token_text({"token": "hello", "sequence_id": "x"}), "hello")

    def test_missing_token_is_empty_string(self):
        self.assertEqual(extract_token_text({"sequence_id": "x"}), "")


if __name__ == "__main__":
    unittest.main()
