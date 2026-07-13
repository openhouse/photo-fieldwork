import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts"
sys.path.insert(0, str(SCRIPTS))

try:
    from PIL import Image
    from verify_preview_exports import verify
except ImportError:
    Image = None
    verify = None


@unittest.skipIf(Image is None, "Pillow is optional for the core synthetic workflow")
class PreviewVerificationTests(unittest.TestCase):
    def test_missing_or_corrupt_previews_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previews = root / "previews"
            previews.mkdir()
            inspection = root / "inspection.jsonl"
            rows = [
                {"asset_identifier": "GOOD/L0/001", "preview_exported": True},
                {"asset_identifier": "BAD/L0/001", "preview_exported": True},
                {"asset_identifier": "MISSING/L0/001", "preview_exported": False},
            ]
            inspection.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            Image.new("RGB", (8, 8), "white").save(previews / "GOOD_L0_001.jpg")
            (previews / "BAD_L0_001.jpg").write_text("not an image", encoding="utf-8")
            invalid, report = verify(inspection, previews)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["decoded_previews"], 1)
            self.assertEqual({row["uuid"] for row in invalid}, {"BAD", "MISSING"})


if __name__ == "__main__":
    unittest.main()
