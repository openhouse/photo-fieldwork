import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "enrich_exiftool_metadata.py"
SPEC = importlib.util.spec_from_file_location("enrich_exiftool_metadata", SCRIPT)
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)


class ExiftoolMetadataTests(unittest.TestCase):
    def test_resource_paths_cover_variants_without_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.jpg"
            raw = root / "original.dng"
            live = root / "live.mov"
            for path in (original, raw, live):
                path.write_bytes(b"private")
            record = {
                "path": str(original),
                "path_raw": str(raw),
                "path_live_photo": str(live),
                "path_derivatives": [str(original)],
                "adjustments": {"data_path": str(root / "missing.aae")},
            }
            self.assertEqual(metadata.resource_paths(record), [original, live, raw])

    def test_secure_output_keeps_full_private_record_at_0600(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "private" / "metadata.json"
            data = [{"uuid": "PRIVATE", "EXIF:SerialNumber": "SECRET"}]
            metadata.secure_write(output, data)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), data)


if __name__ == "__main__":
    unittest.main()
