import unittest

from validate import validate_product_row


class ValidateTests(unittest.TestCase):
    def test_missing_url_fails(self):
        row = {"产品名": "Example", "source_url": "https://source.example"}
        errors = validate_product_row(row)
        self.assertTrue(any("website" in item for item in errors))

    def test_valid_minimal_row(self):
        row = {
            "产品名": "Example",
            "网址": "https://example.com",
            "给谁用": "unavailable",
            "输入": "unavailable",
            "输出": "unavailable",
            "价格": "unavailable",
            "解决什么问题": "unavailable",
            "为什么值得继续看": "unavailable",
            "AITDK月访问量": "unavailable",
            "Top Keywords": "unavailable",
            "Top Regions": "unavailable",
            "source_url": "https://source.example",
        }
        self.assertEqual(validate_product_row(row), [])


if __name__ == "__main__":
    unittest.main()
