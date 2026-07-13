import csv
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "curate-apple-photos" / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), SCRIPTS / name)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def run_script(name: str, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *arguments],
        capture_output=True,
        check=False,
        text=True,
    )


class SkillScriptTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is an optional review dependency")
    def test_preview_verifier_fails_after_writing_invalid_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previews = root / "previews"
            previews.mkdir()
            inspection = root / "inspection.jsonl"
            inspection.write_text(
                json.dumps({"asset_identifier": "A/L0/001", "preview_exported": True}) + "\n"
            )
            (previews / "A_L0_001.jpg").write_text("not an image", encoding="utf-8")
            output = root / "invalid.csv"
            completed = run_script(
                "verify_preview_exports.py",
                "--inspection", str(inspection),
                "--previews", str(previews),
                "--output", str(output),
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("preview decode failure", output.read_text())

    def test_album_retrieval_excludes_generated_corpus_titles(self):
        retrieve = load_script("retrieve_candidates.py")
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE asset_album (uuid TEXT, album_title TEXT)")
        conn.executemany(
            "INSERT INTO asset_album VALUES (?, ?)",
            [("A", "Project evidence"), ("B", "Prior generated project field")],
        )
        self.assertEqual(retrieve.album_matches(conn, ["project"], ["generated"]), {"A"})
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            retrieve.validate_retrieval(
                {
                    "minimum_outside_prior_fraction": 1.2,
                    "views": [{"id": "01", "quota": 1}],
                }
            )
        conn.close()

    def test_inventory_source_snapshot_hashes_membership(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "inventory.sqlite"
            conn = sqlite3.connect(database)
            conn.execute("CREATE TABLE asset (uuid TEXT PRIMARY KEY)")
            conn.executemany("INSERT INTO asset VALUES (?)", [("B",), ("A",)])
            conn.commit()
            conn.close()
            output = root / "source-snapshot.json"
            completed = run_script(
                "inventory_source_snapshot.py",
                "--db", str(database),
                "--query-id", "visible://v1",
                "--expected-count", "2",
                "--output", str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            snapshot = json.loads(output.read_text())
            self.assertEqual(snapshot["observed_count"], 2)
            self.assertEqual(len(snapshot["membership_sha256"]), 64)

    def test_inspection_delta_excludes_previously_inspected_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates.csv"
            with candidates.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["uuid", "filename"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"uuid": "A", "filename": "a.jpg"},
                        {"uuid": "B", "filename": "b.jpg"},
                        {"uuid": "C", "filename": "c.jpg"},
                    ]
                )
            inspection = root / "inspection.jsonl"
            inspection.write_text(json.dumps({"asset_identifier": "B/L0/001"}) + "\n")
            output = root / "delta.csv"
            completed = run_script(
                "inspection_delta.py",
                "--candidates", str(candidates),
                "--inspection", str(inspection),
                "--output", str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with output.open(newline="", encoding="utf-8") as handle:
                self.assertEqual([row["uuid"] for row in csv.DictReader(handle)], ["A", "C"])

    def test_combine_inspections_rejects_conflicting_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            first.write_text(json.dumps({"asset_identifier": "A/L0/001", "pixel_available": True}) + "\n")
            second.write_text(json.dumps({"asset_identifier": "A/L0/001", "pixel_available": False}) + "\n")
            completed = run_script(
                "combine_inspections.py",
                "--inspection", str(first),
                "--inspection", str(second),
                "--output", str(root / "combined.jsonl"),
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("conflicting inspection records", completed.stderr)

    def test_human_safety_review_records_actor_and_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.csv"
            decisions = root / "decisions.csv"
            output = root / "reviewed.csv"
            with inventory.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["uuid", "filename", "safety_status"])
                writer.writeheader()
                writer.writerow({"uuid": "A", "filename": "a.jpg", "safety_status": "auto-hold"})
            with decisions.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["uuid", "safety_status", "safety_reason", "safety_actor"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "uuid": "A",
                        "safety_status": "cleared-false-positive",
                        "safety_reason": "public event flyer",
                        "safety_actor": "archive owner",
                    }
                )
            completed = run_script(
                "apply_safety_review.py",
                "--inventory", str(inventory),
                "--decisions", str(decisions),
                "--output", str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with output.open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["safety_status"], "cleared-false-positive")
            self.assertEqual(row["safety_actor"], "archive owner")
            self.assertTrue(row["safety_reviewed_at"])


if __name__ == "__main__":
    unittest.main()
