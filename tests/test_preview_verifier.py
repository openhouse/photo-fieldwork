import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PIL_AVAILABLE = importlib.util.find_spec("PIL") is not None


@unittest.skipUnless(PIL_AVAILABLE, "Pillow is optional outside the Apple Photos integration")
class PreviewVerifierTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previews = self.root / "previews"
        self.previews.mkdir()
        self.inspection = self.root / "inspection.jsonl"
        self.output = self.root / "invalid.csv"
        script = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "verify_preview_exports.py"
        spec = importlib.util.spec_from_file_location("verify_preview_exports", script)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.Image = Image

    def tearDown(self):
        self.temp.cleanup()

    def run_verifier(self, identifier: str) -> int:
        import sys

        self.inspection.write_text(
            json.dumps({"asset_identifier": identifier, "preview_exported": True}) + "\n",
            encoding="utf-8",
        )
        original = sys.argv
        sys.argv = [
            "verify-preview-exports",
            "--inspection", str(self.inspection),
            "--previews", str(self.previews),
            "--output", str(self.output),
        ]
        try:
            return self.module.main()
        finally:
            sys.argv = original

    def test_complete_preview_set_passes(self):
        identifier = "ASSET/L0/001"
        self.Image.new("RGB", (12, 12), "white").save(
            self.module.preview_path(self.previews, identifier), "JPEG"
        )
        self.assertEqual(self.run_verifier(identifier), 0)

    def test_corrupt_preview_set_fails_closed(self):
        identifier = "BROKEN/L0/001"
        self.module.preview_path(self.previews, identifier).write_bytes(b"not a jpeg")
        self.assertEqual(self.run_verifier(identifier), 2)
