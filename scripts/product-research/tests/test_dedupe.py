import unittest

from dedupe import build_index, normalize_domain, normalize_name


class DedupeTests(unittest.TestCase):
    def test_normalize_domain(self):
        self.assertEqual(normalize_domain("https://www.example.com/path?utm_source=x"), "example.com")

    def test_normalize_name(self):
        self.assertEqual(normalize_name("Runway AI Studio"), "runway")

    def test_index_skips_marker_rows(self):
        index = build_index([
            {"产品名": "", "网址": ""},
            {"产品名": "以下是Agent的自动化写的", "网址": ""},
            {"产品名": "Runway", "网址": "https://runway.com/"},
        ])
        self.assertIsNotNone(index.check("Runway", "https://runway.com"))
        self.assertIsNone(index.check("Other", "https://other.example"))


if __name__ == "__main__":
    unittest.main()
