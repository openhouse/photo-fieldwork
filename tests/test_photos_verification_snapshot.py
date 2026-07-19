import importlib.util
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "snapshot_photos_verification.py"
SPEC = importlib.util.spec_from_file_location("snapshot_photos_verification", SCRIPT)
snapshotter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshotter)


class PhotosVerificationSnapshotTests(unittest.TestCase):
    def test_snapshot_sees_committed_uncheckpointed_wal_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live_path = root / "Photos.sqlite"
            writer = sqlite3.connect(live_path)
            writer.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE ZASSET (
                  Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZKIND INTEGER, ZTRASHEDSTATE INTEGER,
                  ZHIDDEN INTEGER, ZVISIBILITYSTATE INTEGER, ZBUNDLESCOPE INTEGER
                );
                CREATE TABLE ZGENERICALBUM (
                  Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZTITLE TEXT,
                  ZPARENTFOLDER INTEGER, ZTRASHEDSTATE INTEGER
                );
                CREATE TABLE Z_30ASSETS (Z_30ALBUMS INTEGER, Z_3ASSETS INTEGER);
                """
            )
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("INSERT INTO ZASSET VALUES (1, 'ASSET', 0, 0, 0, 0, 0)")
            writer.execute("INSERT INTO ZGENERICALBUM VALUES (9, 'FOLDER', 'Version', NULL, 0)")
            writer.execute("INSERT INTO ZGENERICALBUM VALUES (10, 'ALBUM', 'Master', 9, 0)")
            writer.execute("INSERT INTO Z_30ASSETS VALUES (10, 1)")
            writer.commit()

            plan = root / "plan.json"
            receipt = root / "receipt.json"
            output = root / "snapshot.sqlite"
            plan.write_text(
                json.dumps({
                    "plan_id": "test",
                    "source_album_identifier": snapshotter.VISIBLE_LIBRARY_STILLS,
                    "expected_source_count": 1,
                    "source_membership_sha256": hashlib.sha256(b"ASSET\n").hexdigest(),
                    "folders": [{"key": "version", "title": "Version"}],
                    "albums": [{
                        "title": "Master",
                        "parent_folder_key": "version",
                        "asset_identifiers": ["ASSET/L0/001"],
                    }],
                }),
                encoding="utf-8",
            )
            receipt.write_text(
                json.dumps({
                    "folders": [{"key": "version", "identifier": "FOLDER/L0/020", "title": "Version"}],
                    "albums": [{"identifier": "ALBUM/L0/040", "title": "Master", "count": 1}],
                }),
                encoding="utf-8",
            )
            metadata = snapshotter.build_snapshot(plan, receipt, live_path, output)
            writer.close()

            snapshot = sqlite3.connect(output)
            self.assertEqual(snapshot.execute("SELECT count(*) FROM ZASSET").fetchone()[0], 1)
            self.assertEqual(snapshot.execute("SELECT count(*) FROM Z_30ASSETS").fetchone()[0], 1)
            self.assertEqual(metadata["live_checkpoint_requested"], "false")
            snapshot.close()

            report = root / "verification.md"
            verifier = SCRIPT.with_name("verify_photos_commit.py")
            completed = subprocess.run(
                [
                    sys.executable, str(verifier),
                    "--plan", str(plan),
                    "--receipt", str(receipt),
                    "--previous-receipt", str(receipt),
                    "--photos-db", str(output),
                    "--report", str(report),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            contents = report.read_text(encoding="utf-8")
            self.assertIn("Duplicate album titles within intended parent folders: 0", contents)
            self.assertIn("Previous and current receipts identical: True", contents)
