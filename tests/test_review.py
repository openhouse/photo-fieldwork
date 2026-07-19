import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.review import build_review_workbench, serve_review


class ReviewWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previews = self.root / "previews"
        self.previews.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_private_offline_surface_and_marks_missing_preview(self):
        (self.previews / "AVAILABLE.jpg").write_bytes(b"synthetic-preview")
        output = self.root / "review" / "index.html"
        report = build_review_workbench(
            [
                {
                    "uuid": "AVAILABLE",
                    "assigned_view": "work",
                    "sample_role": "holdout",
                    "estimate_included": "true",
                },
                {"uuid": "MISSING/L0/001", "primary_view": "place"},
            ],
            self.previews,
            output,
        )
        document = output.read_text(encoding="utf-8")
        self.assertEqual(report["available"], 1)
        self.assertEqual(report["unavailable"], 1)
        self.assertIn("connect-src 'none'", document)
        self.assertIn("Preview unavailable: HOLD only", document)
        self.assertIn('if(!row.available&&value!=="hold")return', document)
        self.assertIn("sample_role", document)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        assets = list((output.parent / "review-assets").glob("*.jpg"))
        self.assertEqual(len(assets), 1)
        self.assertNotIn("AVAILABLE", assets[0].name)
        self.assertEqual(assets[0].stat().st_mode & 0o777, 0o600)

    def test_empty_sample_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            build_review_workbench([], self.previews, self.root / "review" / "index.html")

    def test_server_rejects_non_loopback_binding(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            serve_review(self.root, "0.0.0.0", 8765)


if __name__ == "__main__":
    unittest.main()
