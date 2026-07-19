import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.holdout import audit_holdout_split


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "photo-fieldwork"


class HoldoutAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self, name, rows):
        path = self.root / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["uuid", "perceptual_cluster_id", "duplicate_group", "burst_group"],
            )
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_disjoint_holdout_passes_without_identifiers(self):
        report = audit_holdout_split(
            [{"uuid": "PRIVATE-TUNING-ID/1", "perceptual_cluster_id": "private-old-cluster"}],
            [{"uuid": "PRIVATE-HOLDOUT-ID", "perceptual_cluster_id": "private-new-cluster"}],
            [{"uuid": "PRIVATE-CANARY-ID", "perceptual_cluster_id": "private-known-failure"}],
        )
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["holdout_independent"])
        self.assertNotIn("private_details", report)
        self.assertEqual(len(report["digests"]["holdout_uuid_sha256"]), 64)
        rendered = json.dumps(report)
        for private_value in (
            "PRIVATE-TUNING-ID",
            "PRIVATE-HOLDOUT-ID",
            "PRIVATE-CANARY-ID",
            "private-old-cluster",
            "private-new-cluster",
            "private-known-failure",
        ):
            self.assertNotIn(private_value, rendered)

    def test_uuid_and_relation_leakage_fail(self):
        report = audit_holdout_split(
            [{"uuid": "A", "perceptual_cluster_id": "seen", "burst_group": "burst-1"}],
            [
                {"uuid": "A/alternate-resource", "perceptual_cluster_id": "different"},
                {"uuid": "C", "perceptual_cluster_id": "seen", "burst_group": "burst-1"},
            ],
            [],
            include_identifiers=True,
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["leakage"]["tuning_uuid_overlap_count"], 1)
        self.assertEqual(report["leakage"]["tuning_cluster_overlap_count"], 2)
        self.assertEqual(report["private_details"]["tuning_uuid_overlap"], ["A"])

    def test_duplicate_holdout_uuid_fails(self):
        report = audit_holdout_split(
            [],
            [{"uuid": "C"}, {"uuid": "C/second-resource"}],
            [],
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["leakage"]["holdout_duplicate_uuid_count"], 1)

    def test_cli_writes_private_failure_report_and_returns_two(self):
        tuning = self.write_manifest("tuning.csv", [{"uuid": "A", "perceptual_cluster_id": "seen"}])
        holdout = self.write_manifest("holdout.csv", [{"uuid": "A/1", "perceptual_cluster_id": "other"}])
        canary = self.write_manifest("canary.csv", [])
        output = self.root / "private" / "holdout.json"
        result = subprocess.run(
            [
                str(CLI),
                "audit-holdout",
                "--tuning",
                str(tuning),
                "--holdout",
                str(holdout),
                "--canary",
                str(canary),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(output.read_text())["status"], "FAIL")
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
