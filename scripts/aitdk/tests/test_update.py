import importlib.util
import pathlib
import sys
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "update.py"
SPEC = importlib.util.spec_from_file_location("aitdk_update", MODULE_PATH)
aitdk_update = importlib.util.module_from_spec(SPEC)
sys.modules["aitdk_update"] = aitdk_update
SPEC.loader.exec_module(aitdk_update)


class AitdkUpdateTests(unittest.TestCase):
    def test_apply_records_matches_by_domain(self):
        rows = [
            {
                "产品名": "Runway",
                "网址": "https://runwayml.com/",
                "AITDK月访问量": "unavailable",
                "Top Keywords": "unavailable",
                "Top Regions": "unavailable",
            }
        ]
        records = [
            aitdk_update.AitdkRecord(
                name="Runway AI",
                domain="www.runwayml.com",
                monthly_visits="12.3M",
                top_keywords="runway ai; ai video generator",
                top_regions="United States; India",
            )
        ]
        updated, unmatched, messages = aitdk_update.apply_records(rows, records)
        self.assertEqual(updated, 1)
        self.assertEqual(unmatched, 0)
        self.assertIn("updated", messages[0])
        self.assertEqual(rows[0]["AITDK月访问量"], "12.3M")
        self.assertEqual(rows[0]["Top Keywords"], "runway ai; ai video generator")
        self.assertEqual(rows[0]["Top Regions"], "United States; India")

    def test_apply_records_does_not_overwrite_by_default(self):
        rows = [
            {
                "产品名": "Runway",
                "网址": "https://runwayml.com/",
                "AITDK月访问量": "10M",
                "Top Keywords": "old",
                "Top Regions": "old",
            }
        ]
        records = [aitdk_update.AitdkRecord("Runway", "runwayml.com", "12M", "new", "new")]
        updated, unmatched, _ = aitdk_update.apply_records(rows, records)
        self.assertEqual(updated, 0)
        self.assertEqual(unmatched, 0)
        self.assertEqual(rows[0]["AITDK月访问量"], "10M")

    def test_apply_records_can_overwrite(self):
        rows = [
            {
                "产品名": "Runway",
                "网址": "https://runwayml.com/",
                "AITDK月访问量": "10M",
                "Top Keywords": "old",
                "Top Regions": "old",
            }
        ]
        records = [aitdk_update.AitdkRecord("Runway", "runwayml.com", "12M", "new", "new")]
        updated, unmatched, _ = aitdk_update.apply_records(rows, records, overwrite=True)
        self.assertEqual(updated, 1)
        self.assertEqual(unmatched, 0)
        self.assertEqual(rows[0]["AITDK月访问量"], "12M")

    def test_apply_records_reports_unmatched(self):
        rows = [
            {
                "产品名": "Runway",
                "网址": "https://runwayml.com/",
                "AITDK月访问量": "unavailable",
                "Top Keywords": "unavailable",
                "Top Regions": "unavailable",
            }
        ]
        records = [aitdk_update.AitdkRecord("Pika", "pika.art", "1M", "pika", "United States")]
        updated, unmatched, messages = aitdk_update.apply_records(rows, records)
        self.assertEqual(updated, 0)
        self.assertEqual(unmatched, 1)
        self.assertIn("unmatched", messages[0])

    def test_parse_pipe_record_normalizes_domain(self):
        record = aitdk_update.parse_pipe_record("Runway|https://www.runwayml.com/path|12M|runway ai|US")
        self.assertEqual(record.domain, "runwayml.com")


if __name__ == "__main__":
    unittest.main()
