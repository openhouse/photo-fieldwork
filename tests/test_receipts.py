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
                CREATE TABLE ZGENERICALBUM(
                    Z_PK INTEGER PRIMARY KEY,
                    ZUUID TEXT,
                    ZTITLE TEXT,
                    ZKIND INTEGER,
                    ZPARENTFOLDER INTEGER
                );
                CREATE TABLE ZASSET(Z_PK INTEGER PRIMARY KEY, ZUUID TEXT);
                CREATE TABLE Z_30ASSETS(Z_30ALBUMS INTEGER, Z_3ASSETS INTEGER);
                INSERT INTO ZGENERICALBUM VALUES (4, 'SYSTEM-ROOT', NULL, 3999, NULL);
                INSERT INTO ZGENERICALBUM VALUES (1, 'ROOT', 'Root', 4000, 4);
                INSERT INTO ZGENERICALBUM VALUES (2, 'SOURCE', 'Source', 2, 1);
                INSERT INTO ZGENERICALBUM VALUES (3, 'MASTER', 'Master', 2, 1);
                INSERT INTO ZASSET VALUES (10, 'A');
                INSERT INTO ZASSET VALUES (11, 'B');
                INSERT INTO Z_30ASSETS VALUES (2, 10);
                INSERT INTO Z_30ASSETS VALUES (2, 11);
                INSERT INTO Z_30ASSETS VALUES (3, 10);
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
                "folders": [{"key": "root", "title": "Root", "parent_key": None}],
                "albums": [
                    {
                        "title": "Master",
                        "parent_folder_key": "root",
                        "asset_identifiers": ["A/L0/001"],
                        "safety_role": "editor",
                    }
                ],
            }
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            receipt = {
                "completed_at": "2026-07-19T01:00:00+00:00",
                "execution_nonce": "1" * 32,
                "plan_id": "plan",
                "source_album_identifier": "SOURCE/L0/040",
                "source_count": 2,
                "source_identifier_sha256": source_digest,
                "folders": [
                    {
                        "key": "root",
                        "title": "Root",
                        "identifier": "ROOT/L0/040",
                        "parent_identifier": None,
                    }
                ],
                "albums": [{"title": "Master", "identifier": "MASTER/L0/040", "count": 1, "parent_identifier": "ROOT/L0/040"}],
                "execution_fingerprint": {
                    "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest()
                },
            }
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            report = root / "private" / "report.md"
            with redirect_stdout(io.StringIO()):
                verified_identifiers = verify_photos_commit.verify(
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
            self.assertEqual(
                verified_identifiers,
                {"ROOT/L0/040", "MASTER/L0/040"},
            )
            connection = sqlite3.connect(database)
            connection.execute("UPDATE ZGENERICALBUM SET ZPARENTFOLDER = 999 WHERE ZUUID = 'ROOT'")
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(RuntimeError, "folder parent mismatch"):
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

            plan["folders"][0]["parent_policy"] = "external-anchor"
            plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            receipt["execution_fingerprint"]["plan_sha256"] = hashlib.sha256(
                plan_path.read_bytes()
            ).hexdigest()
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
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

    def test_idempotence_comparison_ignores_completion_time(self):
        source_sha = "a" * 64
        binary_sha = "b" * 64
        plan_sha = "c" * 64
        plan = {
            "plan_id": "plan",
            "source_album_identifier": "source",
            "expected_source_count": 10,
            "source_identifier_sha256": source_sha,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root"}],
            "albums": [{"title": "Master", "asset_identifiers": ["A", "B", "C", "D"]}],
        }
        receipt = {
            "completed_at": "2026-07-19T01:00:00+00:00",
            "execution_nonce": "1" * 32,
            "plan_id": "plan",
            "source_album_identifier": "source",
            "source_count": 10,
            "source_identifier_sha256": source_sha,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root", "identifier": "FOLDER-01/L0/040"}],
            "albums": [{"title": "Master", "identifier": "ALBUM-01/L0/040", "count": 4}],
            "execution_fingerprint": {
                "app_bundle_identifier": "org.example.synthetic",
                "app_binary_sha256": binary_sha,
                "plan_sha256": plan_sha,
            },
        }
        second = dict(
            receipt,
            completed_at="2026-07-19T01:01:00+00:00",
            execution_nonce="2" * 32,
        )
        verified = {"FOLDER-01/L0/040", "ALBUM-01/L0/040"}
        arguments = (plan, plan_sha, "org.example.synthetic", binary_sha, verified)
        self.assertEqual(
            compare_receipts.normalized(receipt, *arguments),
            compare_receipts.normalized(second, *arguments),
        )
        changed = dict(second, albums=[{"title": "Master", "identifier": "ALBUM-01/L0/040", "count": 3}])
        with self.assertRaisesRegex(ValueError, "planned membership"):
            compare_receipts.normalized(changed, *arguments)

    def test_idempotence_rejects_two_identically_incomplete_receipts(self):
        incomplete = {
            "completed_at": "2026-07-19T01:00:00+00:00",
            "execution_nonce": "1" * 32,
            "plan_id": "plan",
            "source_album_identifier": "source",
            "source_count": 10,
            "source_identifier_sha256": "a" * 64,
            "safety_mode": "membership-only",
            "folders": [],
            "albums": [],
            "execution_fingerprint": {},
        }
        with self.assertRaisesRegex(ValueError, "execution_fingerprint"):
            compare_receipts.require_receipt(incomplete)

    def test_idempotence_requires_two_distinct_execution_receipts(self):
        first = Path("first.json")
        receipt = {
            "completed_at": "2026-07-19T01:00:00+00:00",
            "execution_nonce": "1" * 32,
        }
        with self.assertRaisesRegex(ValueError, "distinct receipt files"):
            compare_receipts.require_distinct_executions(first, first, receipt, receipt)
        with self.assertRaisesRegex(ValueError, "distinct execution timestamps"):
            compare_receipts.require_distinct_executions(
                first,
                Path("second.json"),
                receipt,
                dict(receipt),
            )

    def test_changed_timestamp_cannot_fake_a_second_launch(self):
        first = {
            "completed_at": "2026-07-19T01:00:00+00:00",
            "execution_nonce": "1" * 32,
        }
        copied = dict(first, completed_at="2026-07-19T01:01:00+00:00")
        with self.assertRaisesRegex(ValueError, "distinct bridge launch nonces"):
            compare_receipts.require_distinct_executions(
                Path("first.json"), Path("copied.json"), first, copied
            )

    def test_receipt_must_match_exact_plan_membership(self):
        plan_sha = "c" * 64
        plan = {
            "plan_id": "plan",
            "source_album_identifier": "source",
            "expected_source_count": 10,
            "source_identifier_sha256": "a" * 64,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root"}],
            "albums": [{"title": "Master", "asset_identifiers": ["A", "B", "C", "D"]}],
        }
        receipt = {
            "completed_at": "2026-07-19T01:00:00+00:00",
            "execution_nonce": "1" * 32,
            "plan_id": "plan",
            "source_album_identifier": "source",
            "source_count": 10,
            "source_identifier_sha256": "a" * 64,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root", "identifier": "FOLDER-01/L0/040"}],
            "albums": [{"title": "Master", "identifier": "ALBUM-01/L0/040", "count": 3}],
            "execution_fingerprint": {
                "app_bundle_identifier": "org.example.synthetic",
                "app_binary_sha256": "b" * 64,
                "plan_sha256": plan_sha,
            },
        }
        with self.assertRaisesRegex(ValueError, "planned membership"):
            compare_receipts.normalized(
                receipt,
                plan,
                plan_sha,
                "org.example.synthetic",
                "b" * 64,
                {"FOLDER-01/L0/040", "ALBUM-01/L0/040"},
            )

    def test_receipt_rejects_dummy_hashes_and_zero_counts(self):
        receipt = {
            "completed_at": "2026-07-19T01:00:00+00:00",
            "execution_nonce": "1" * 32,
            "plan_id": "plan",
            "source_album_identifier": "source",
            "source_count": 0,
            "source_identifier_sha256": "x",
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root", "identifier": "FOLDER"}],
            "albums": [{"title": "Master", "identifier": "ALBUM", "count": 0}],
            "execution_fingerprint": {
                "app_bundle_identifier": "x",
                "app_binary_sha256": "x",
                "plan_sha256": "x",
            },
        }
        with self.assertRaisesRegex(ValueError, "positive integer"):
            compare_receipts.require_receipt(receipt)

    def test_receipt_must_match_configured_helper_identity(self):
        plan_sha = "c" * 64
        binary_sha = "b" * 64
        plan = {
            "plan_id": "plan",
            "source_album_identifier": "source",
            "expected_source_count": 10,
            "source_identifier_sha256": "a" * 64,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root"}],
            "albums": [{"title": "Master", "asset_identifiers": ["A"]}],
        }
        receipt = {
            "completed_at": "2026-07-19T01:00:00+00:00",
            "execution_nonce": "1" * 32,
            "plan_id": "plan",
            "source_album_identifier": "source",
            "source_count": 10,
            "source_identifier_sha256": "a" * 64,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root", "identifier": "FOLDER-01/L0/040"}],
            "albums": [{"title": "Master", "identifier": "ALBUM-01/L0/040", "count": 1}],
            "execution_fingerprint": {
                "app_bundle_identifier": "org.example.synthetic",
                "app_binary_sha256": "d" * 64,
                "plan_sha256": plan_sha,
            },
        }
        with self.assertRaisesRegex(ValueError, "configured helper"):
            compare_receipts.normalized(
                receipt,
                plan,
                plan_sha,
                "org.example.synthetic",
                binary_sha,
                {"FOLDER-01/L0/040", "ALBUM-01/L0/040"},
            )

    def test_receipt_rejects_unverified_catalog_identifiers(self):
        plan = {
            "plan_id": "plan",
            "source_album_identifier": "source",
            "expected_source_count": 10,
            "source_identifier_sha256": "a" * 64,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root"}],
            "albums": [{"title": "Master", "asset_identifiers": ["A"]}],
        }
        receipt = {
            "completed_at": "2026-07-19T01:00:00+00:00",
            "execution_nonce": "1" * 32,
            "plan_id": "plan",
            "source_album_identifier": "source",
            "source_count": 10,
            "source_identifier_sha256": "a" * 64,
            "safety_mode": "membership-only",
            "folders": [{"key": "root", "title": "Root", "identifier": "FOLDER-01/L0/040"}],
            "albums": [{"title": "Master", "identifier": "ALBUM-01/L0/040", "count": 1}],
            "execution_fingerprint": {
                "app_bundle_identifier": "org.example.synthetic",
                "app_binary_sha256": "b" * 64,
                "plan_sha256": "c" * 64,
            },
        }
        with self.assertRaisesRegex(ValueError, "independent verification"):
            compare_receipts.normalized(
                receipt,
                plan,
                "c" * 64,
                "org.example.synthetic",
                "b" * 64,
                {"DIFFERENT-ID/L0/040"},
            )

    def test_source_identifier_digest_is_order_independent(self):
        first = verify_photos_commit.identifier_digest({"B", "A"})
        second = verify_photos_commit.identifier_digest({"A", "B"})
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)


if __name__ == "__main__":
    unittest.main()
