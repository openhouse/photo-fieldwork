import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "audit_eval_split.py"


class EvaluationSplitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self, name, rows):
        path = self.root / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["uuid", "perceptual_cluster_id"])
            writer.writeheader()
            writer.writerows(rows)
        return path

    def run_audit(self, tuning, holdout, canary):
        output = self.root / "report.json"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--tuning",
                str(tuning),
                "--holdout",
                str(holdout),
                "--canary",
                str(canary),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result, json.loads(output.read_text(encoding="utf-8"))

    def test_disjoint_holdout_passes_without_exposing_identifiers(self):
        tuning = self.write_manifest("tuning.csv", [{"uuid": "A/1", "perceptual_cluster_id": "old"}])
        canary = self.write_manifest("canary.csv", [{"uuid": "B", "perceptual_cluster_id": "known-failure"}])
        holdout = self.write_manifest("holdout.csv", [{"uuid": "C", "perceptual_cluster_id": "new"}])
        result, report = self.run_audit(tuning, holdout, canary)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["holdout_independent"])
        self.assertNotIn("private_details", report)
        self.assertEqual(len(report["digests"]["holdout_uuid_sha256"]), 64)

    def test_uuid_and_perceptual_cluster_leakage_fail(self):
        tuning = self.write_manifest("tuning.csv", [{"uuid": "A", "perceptual_cluster_id": "seen-scene"}])
        canary = self.write_manifest("canary.csv", [{"uuid": "B", "perceptual_cluster_id": "known-failure"}])
        holdout = self.write_manifest(
            "holdout.csv",
            [
                {"uuid": "A/alternate-resource", "perceptual_cluster_id": "different"},
                {"uuid": "C", "perceptual_cluster_id": "seen-scene"},
            ],
        )
        result, report = self.run_audit(tuning, holdout, canary)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["leakage"]["tuning_uuid_overlap_count"], 1)
        self.assertEqual(report["leakage"]["tuning_cluster_overlap_count"], 1)

    def test_duplicate_holdout_rows_fail(self):
        tuning = self.write_manifest("tuning.csv", [{"uuid": "A", "perceptual_cluster_id": "old"}])
        canary = self.write_manifest("canary.csv", [])
        holdout = self.write_manifest(
            "holdout.csv",
            [
                {"uuid": "C", "perceptual_cluster_id": "new-1"},
                {"uuid": "C/second-resource", "perceptual_cluster_id": "new-2"},
            ],
        )
        result, report = self.run_audit(tuning, holdout, canary)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["leakage"]["holdout_duplicate_uuid_count"], 1)


if __name__ == "__main__":
    unittest.main()
