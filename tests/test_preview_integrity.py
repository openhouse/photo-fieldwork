import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load_script(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sheets = load_script("make_contact_sheets", "skills/curate-apple-photos/scripts/make_contact_sheets.py")
previews = load_script("verify_preview_exports", "skills/curate-apple-photos/scripts/verify_preview_exports.py")
review = load_script("build_review_surface", "skills/curate-apple-photos/scripts/build_review_surface.py")


class PreviewIntegrityTests(unittest.TestCase):
    def test_recursive_multi_batch_preview_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "batch-1"
            second = root / "batch-2" / "nested"
            first.mkdir()
            second.mkdir(parents=True)
            Image.new("RGB", (20, 10), "red").save(first / "AAA_L0_001.jpg")
            Image.new("RGB", (10, 20), "blue").save(second / "BBB.jpg")
            index = sheets.recursive_preview_index([first, root / "batch-2"])
            self.assertEqual(set(index), {"AAA", "BBB"})
            verified = previews.preview_paths([first, root / "batch-2"])
            self.assertEqual(set(verified), {"AAA", "BBB"})
            self.assertEqual(len(previews.file_sha256(verified["AAA"])), 64)

    def test_duplicate_preview_across_batches_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "batch-1"
            second = root / "batch-2"
            first.mkdir()
            second.mkdir()
            Image.new("RGB", (10, 10), "red").save(first / "AAA.jpg")
            Image.new("RGB", (10, 10), "blue").save(second / "AAA_L0_001.jpg")
            with self.assertRaisesRegex(ValueError, "duplicate preview"):
                sheets.recursive_preview_index([first, second])
            with self.assertRaisesRegex(ValueError, "duplicate previews"):
                previews.preview_paths([first, second])

    def test_review_surface_uses_verified_previews_and_safe_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AAA.jpg"
            Image.new("RGB", (10, 10), "green").save(path)
            payload = review.build_payload(
                [{"uuid": "AAA/L0/001", "filename": "a.jpg", "primary_view": "01", "raw_ocr": "secret"}],
                [{"uuid": "AAA", "preview_path": str(path), "decode_status": "ok"}],
            )
            self.assertEqual(payload[0]["uuid"], "AAA")
            self.assertNotIn("raw_ocr", payload[0])
            self.assertIn("file://", payload[0]["preview_url"])
            self.assertIn("Export feedback CSV", review.render_html(payload, "Review"))


if __name__ == "__main__":
    unittest.main()
