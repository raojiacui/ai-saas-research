import unittest

from run import admission_decision


class AdmissionTests(unittest.TestCase):
    def test_reference_to_video_accepts_yes_or_maybe(self):
        ok, reason = admission_decision({"ai_video_fit": "YES", "reference_to_video_fit": "MAYBE"}, "reference-to-video")
        self.assertTrue(ok)
        self.assertIn("reference_to_video_fit=MAYBE", reason)

    def test_reference_to_video_rejects_generic_ai_video(self):
        ok, reason = admission_decision({"ai_video_fit": "YES", "reference_to_video_fit": "NO"}, "reference-to-video")
        self.assertFalse(ok)
        self.assertEqual(reason, "reference_to_video_fit=NO")

    def test_rejects_non_video(self):
        ok, reason = admission_decision({"ai_video_fit": "NO", "reference_to_video_fit": "NO"}, "reference-to-video")
        self.assertFalse(ok)
        self.assertEqual(reason, "ai_video_fit=NO")

    def test_ai_video_focus_accepts_any_ai_video(self):
        ok, reason = admission_decision({"ai_video_fit": "YES", "reference_to_video_fit": "NO"}, "ai-video")
        self.assertTrue(ok)
        self.assertEqual(reason, "accepted: ai_video_fit=YES")


if __name__ == "__main__":
    unittest.main()
