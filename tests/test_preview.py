import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from photo_fieldwork.preview import preview_filename, verify_jpeg, verify_preview_exports


def synthetic_jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buffer, "JPEG")
    return buffer.getvalue()


class PreviewIntegrityTests(unittest.TestCase):
    def test_valid_jpeg_reports_dimensions(self):
        self.assertEqual(verify_jpeg(synthetic_jpeg()), (1, 1))

    def test_missing_and_corrupt_previews_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "SYN-VALID.jpg").write_bytes(synthetic_jpeg())
            records = [
                {"uuid": "SYN-VALID", "preview_exported": True},
                {"uuid": "SYN-MISSING", "preview_exported": True},
            ]
            report = verify_preview_exports(records, root)
            self.assertFalse(report["passed"])
            self.assertEqual(report["valid_count"], 1)
            self.assertTrue(any("SYN-MISSING" in error for error in report["errors"]))

            (root / "SYN-VALID.jpg").write_bytes(synthetic_jpeg()[:-2])
            report = verify_preview_exports(records[:1], root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("decode failed" in error for error in report["errors"]))

    def test_filename_collisions_are_rejected(self):
        self.assertEqual(preview_filename("SYN/ONE"), "SYN_ONE.jpg")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                verify_preview_exports(
                    [
                        {"uuid": "SYN/ONE", "preview_exported": True},
                        {"uuid": "SYN_ONE", "preview_exported": True},
                    ],
                    Path(temporary),
                )

    def test_symbolic_links_are_not_accepted_as_preview_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.jpg"
            target.write_bytes(synthetic_jpeg())
            (root / "SYN-LINK.jpg").symlink_to(target)
            report = verify_preview_exports([{"uuid": "SYN-LINK", "preview_exported": True}], root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("symbolic link" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
