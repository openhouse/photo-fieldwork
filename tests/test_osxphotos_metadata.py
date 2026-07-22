import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "export_osxphotos_metadata.py"
SPEC = importlib.util.spec_from_file_location("export_osxphotos_metadata", SCRIPT)
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)


class OsxphotosMetadataTests(unittest.TestCase):
    def test_full_records_are_reconciled_to_requested_order(self):
        records = [
            {"uuid": "B", "person_info": [{"name": "Person B"}]},
            {"uuid": "A", "search_info": {"activity": ["Gathering"]}},
        ]
        ordered = metadata.validate_records(records, ["A", "B"])
        self.assertEqual([row["uuid"] for row in ordered], ["A", "B"])
        self.assertIn("search_info", ordered[0])
        self.assertIn("person_info", ordered[1])

    def test_missing_or_duplicate_records_fail_closed(self):
        with self.assertRaises(ValueError):
            metadata.validate_records([{"uuid": "A"}], ["A", "B"])
        with self.assertRaises(ValueError):
            metadata.validate_records([{"uuid": "A"}, {"uuid": "A"}], ["A"])

    def test_private_output_is_mode_0600(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "private" / "records.json"
            metadata.secure_output(output, json.dumps([{"uuid": "PRIVATE"}]))
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
