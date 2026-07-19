import json
import hashlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "verify_photos_commit.py"


class PhotosVerifierTests(unittest.TestCase):
    def test_compact_verifier_reads_wal_visible_membership(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "Photos.sqlite"
            conn = sqlite3.connect(database)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE ZASSET (
                  Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZKIND INTEGER,
                  ZTRASHEDSTATE INTEGER, ZHIDDEN INTEGER, ZVISIBILITYSTATE INTEGER,
                  ZBUNDLESCOPE INTEGER
                );
                CREATE TABLE ZGENERICALBUM (Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZTITLE TEXT);
                CREATE TABLE Z_30ASSETS (Z_30ALBUMS INTEGER, Z_3ASSETS INTEGER);
                """
            )
            conn.executemany(
                "INSERT INTO ZASSET VALUES (?, ?, 0, 0, 0, 0, 0)",
                [(1, "A"), (2, "B"), (3, "C")],
            )
            conn.execute("INSERT INTO ZGENERICALBUM VALUES (10, 'MASTER', '00 MASTER - 2')")
            conn.executemany("INSERT INTO Z_30ASSETS VALUES (10, ?)", [(1,), (2,)])
            conn.commit()

            plan = root / "plan.json"
            fingerprint = hashlib.sha256(
                b"visible-library-stills://v1\napple-photos-visible-stills-v1\nA\nB\nC\n"
            ).hexdigest()
            plan.write_text(json.dumps({
                "plan_id": "fixture",
                "proposal_id": "pfp-fixture",
                "master_sha256": "abc123",
                "source_album_identifier": "visible-library-stills://v1",
                "source_predicate_version": "apple-photos-visible-stills-v1",
                "source_fingerprint": fingerprint,
                "expected_source_count": 3,
                "albums": [{"title": "00 MASTER - 2", "asset_identifiers": ["A/L0/001", "B/L0/001"]}],
            }), encoding="utf-8")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "plan_id": "fixture",
                "proposal_id": "pfp-fixture",
                "master_sha256": "abc123",
                "source_album_identifier": "visible-library-stills://v1",
                "source_count": 3,
                "source_fingerprint": fingerprint,
                "execution_nonce": "1" * 32,
                "reviewed_plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
                "albums": [{"title": "00 MASTER - 2", "identifier": "MASTER/L0/040", "count": 2}],
            }), encoding="utf-8")
            report = root / "report.json"
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--plan", str(plan), "--receipt", str(receipt), "--report", str(report), "--photos-db", str(database), "--mode", "compact", "--temp-dir", str(root)],
                check=False, capture_output=True, text=True,
            )
            conn.close()
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["proposal_id"], "pfp-fixture")
            self.assertEqual(result["verification_mode"], "compact")
            self.assertEqual(len(result["plan_sha256"]), 64)
            self.assertEqual(len(result["receipt_sha256"]), 64)
            self.assertFalse(list(root.glob("photo-fieldwork-verify-*")))

    def test_receipt_identity_mismatch_fails_verification(self):
        plan = {
            "plan_id": "plan-a",
            "proposal_id": "proposal-a",
            "master_sha256": "a" * 64,
            "audited_uuid_sha256": "b" * 64,
            "source_album_identifier": "SOURCE/L0/040",
            "expected_source_count": 2,
            "source_fingerprint": "c" * 64,
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "albums": [{"title": "00 MASTER - 1", "asset_identifiers": ["A/L0/001"]}],
        }
        receipt = {
            **{key: plan[key] for key in (
                "proposal_id", "master_sha256", "audited_uuid_sha256",
                "source_album_identifier", "source_fingerprint", "safety_mode",
            )},
            "plan_id": "copied-from-another-plan",
            "source_count": 2,
            "albums": [{"title": "00 MASTER - 1", "identifier": "MASTER/L0/040", "count": 1}],
        }
        sys.path.insert(0, str(SCRIPT.parent))
        import importlib.util
        spec = importlib.util.spec_from_file_location("verify_photos_commit", SCRIPT)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        errors = verifier.receipt_identity_errors(plan, receipt)
        self.assertIn("receipt plan_id does not match plan", errors)


if __name__ == "__main__":
    unittest.main()
