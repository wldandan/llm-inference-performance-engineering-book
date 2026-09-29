import unittest

from quality_check import CHECK_PROMPTS, format_report


class FormatReportTest(unittest.TestCase):
    def test_includes_label_and_all_rows(self):
        rows = [{"prompt": "2+2?", "answer": "4"}]

        text = format_report("baseline", rows)

        self.assertIn("baseline", text)
        self.assertIn("2+2?", text)
        self.assertIn("4", text)

    def test_has_a_fixed_prompt_set(self):
        self.assertGreaterEqual(len(CHECK_PROMPTS), 3)


if __name__ == "__main__":
    unittest.main()
