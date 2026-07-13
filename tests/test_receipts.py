import argparse
import hashlib
import io
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare_receipts = load("compare_receipts")
verify_photos_commit = load("verify_photos_commit")
freeze_source_profile = load("freeze_source_profile")


class ReceiptTests(unittest.TestCase):
    def test_verifier_binds_plan_receipt_source_and_membership(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "snapshot.sqlite"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE ZGENERICALBUM(Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZTITLE TEXT);
                CREATE TABLE ZASSET(Z_PK INTEGER PRIMARY KEY, ZUUID TEXT);
                CREATE TABLE Z_30ASSETS(Z_30ALBUMS INTEGER, Z_3ASSETS INTEGER);
                INSERT INTO ZGENERICALBUM VALUES (1, 'SOURCE', 'Source');
                INSERT INTO ZGENERICALBUM VALUES (2, 'MASTER', 'Master');
                INSERT INTO ZASSET VALUES (10, 'A');
                INSERT INTO ZASSET VALUES (11, 'B');
                INSERT INTO Z_30ASSETS VALUES (1, 10);
                INSERT INTO Z_30ASSETS VALUES (1, 11);
                INSERT INTO Z_30ASSETS VALUES (2, 10);
                """
            )
            connection.commit()
            connection.close()
            source_digest = verify_photos_commit.identifier_digest({"A", "B"})
            frozen_profile = root / "profile" / "source.json"
            with redirect_stdout(io.StringIO()):
                freeze_source_profile.freeze(
                    argparse.Namespace(
                        source_identifier="SOURCE/L0/040",
                        expected_count=2,
                        output=frozen_profile,
                    ),
                    database,
                )
            frozen = json.loads(frozen_profile.read_text(encoding="utf-8"))
            self.assertEqual(frozen["identifier_sha256"], source_digest)
            plan = {
                "plan_id": "plan",
                "source_album_identifier": "SOURCE/L0/040",
                "expected_source_count": 2,
                "source_identifier_sha256": source_digest,
                "hold_asset_identifiers": ["B/L0/001"],
                "albums": [
                    {
                        "title": "Master",
                        "asset_identifiers": ["A/L0/001"],
                        "safety_role": "editor",
                    }
                ],
            }
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            receipt = {
                "plan_id": "plan",
                "source_album_identifier": "SOURCE/L0/040",
                "source_count": 2,
                "source_identifier_sha256": source_digest,
                "albums": [{"title": "Master", "identifier": "MASTER/L0/040", "count": 1}],
                "execution_fingerprint": {
                    "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest()
                },
            }
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            report = root / "private" / "report.md"
            with redirect_stdout(io.StringIO()):
                verify_photos_commit.verify(
                    argparse.Namespace(
                        plan=plan_path,
                        receipt=receipt_path,
                        report=report,
                        include_identifiers=False,
                    ),
                    database,
                    {"snapshot_bytes": database.stat().st_size},
                )
            self.assertIn("Albums exactly verified: 1", report.read_text(encoding="utf-8"))
            self.assertNotIn("MASTER/L0/040", report.read_text(encoding="utf-8"))

    def test_idempotence_comparison_ignores_completion_time(self):
        receipt = {
            "completed_at": "first",
            "plan_id": "plan",
            "source_album_identifier": "source",
            "source_count": 10,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root", "identifier": "FOLDER"}],
            "albums": [{"title": "Master", "identifier": "ALBUM", "count": 4}],
            "execution_fingerprint": {"plan_sha256": "abc"},
        }
        second = dict(receipt, completed_at="second")
        self.assertEqual(compare_receipts.normalized(receipt), compare_receipts.normalized(second))
        changed = dict(second, albums=[{"title": "Master", "identifier": "ALBUM", "count": 3}])
        self.assertNotEqual(compare_receipts.normalized(receipt), compare_receipts.normalized(changed))

    def test_source_identifier_digest_is_order_independent(self):
        first = verify_photos_commit.identifier_digest({"B", "A"})
        second = verify_photos_commit.identifier_digest({"A", "B"})
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)


if __name__ == "__main__":
    unittest.main()
