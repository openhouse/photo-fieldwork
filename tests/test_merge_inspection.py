import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "merge_inspection.py"


class MergeInspectionTests(unittest.TestCase):
    def test_human_sensitive_and_unavailable_assets_are_held(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates.csv"
            with candidates.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["uuid", "filename", "safety_status"])
                writer.writeheader()
                writer.writerows([
                    {"uuid": "A", "filename": "a.jpg", "safety_status": "clear-automated"},
                    {"uuid": "B", "filename": "b.jpg", "safety_status": "clear-automated"},
                ])
            inspection = root / "inspection.jsonl"
            inspection.write_text("".join([
                json.dumps({"asset_identifier": "A/L0/001", "pixel_available": True, "preview_exported": True, "vision_labels": ["Child"], "detected_face_count": 1, "safety_state": "clear-automated"}) + "\n",
                json.dumps({"asset_identifier": "B/L0/001", "pixel_available": True, "preview_exported": False, "vision_labels": [], "detected_face_count": 0, "safety_state": "clear-automated"}) + "\n",
            ]), encoding="utf-8")
            output = root / "ready.csv"
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--candidates", str(candidates), "--inspection", str(inspection), "--output", str(output)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = {row["uuid"]: row for row in csv.DictReader(handle)}
            self.assertEqual(rows["A"]["safety_status"], "hold-human-sensitive")
            self.assertEqual(rows["B"]["safety_status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
