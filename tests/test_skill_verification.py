import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "verify_photos_commit.py"
SPEC = importlib.util.spec_from_file_location("verify_photos_commit", SCRIPT)
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class CompactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.photos = self.root / "Photos.sqlite"
        conn = sqlite3.connect(self.photos)
        conn.executescript(
            """
            CREATE TABLE ZASSET(
              Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZKIND INTEGER,
              ZTRASHEDSTATE INTEGER, ZHIDDEN INTEGER, ZVISIBILITYSTATE INTEGER,
              ZBUNDLESCOPE INTEGER
            );
            CREATE TABLE ZGENERICALBUM(Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZTITLE TEXT);
            CREATE TABLE Z_30ASSETS(Z_30ALBUMS INTEGER, Z_3ASSETS INTEGER);
            INSERT INTO ZASSET VALUES (1, 'A', 0, 0, 0, 0, 0);
            INSERT INTO ZASSET VALUES (2, 'B', 0, 0, 0, 0, 0);
            INSERT INTO ZASSET VALUES (3, 'C', 0, 0, 0, 0, 0);
            INSERT INTO ZGENERICALBUM VALUES (10, 'ALBUM', '00 MASTER - 2');
            INSERT INTO Z_30ASSETS VALUES (10, 1);
            INSERT INTO Z_30ASSETS VALUES (10, 2);
            """
        )
        conn.commit()
        conn.close()
        self.plan = {
            "plan_id": "test-plan",
            "source_album_identifier": verify.VISIBLE_LIBRARY_STILLS,
            "expected_source_count": 3,
            "albums": [{
                "title": "00 MASTER - 2",
                "parent_folder_key": "version",
                "asset_identifiers": ["A/L0/001", "B/L0/001"],
            }],
        }
        self.receipt = {
            "plan_id": "test-plan",
            "source_album_identifier": verify.VISIBLE_LIBRARY_STILLS,
            "source_count": 3,
            "albums": [{
                "title": "00 MASTER - 2",
                "identifier": "ALBUM/L0/040",
                "count": 2,
            }]
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_compact_evidence_round_trip(self):
        evidence = self.root / "evidence.sqlite"
        verify.extract_evidence(
            self.photos,
            evidence,
            self.plan,
            self.receipt,
            "plan-hash",
            "receipt-hash",
        )
        verified, source_count = verify.verify_evidence(evidence, self.plan, self.receipt)
        self.assertEqual(source_count, 3)
        self.assertEqual(verified[0][1], 2)
        self.assertLess(evidence.stat().st_size, self.photos.stat().st_size * 5)

    def test_outside_source_fails_closed(self):
        self.plan["albums"][0]["asset_identifiers"].append("MISSING/L0/001")
        evidence = self.root / "outside.sqlite"
        verify.extract_evidence(
            self.photos,
            evidence,
            self.plan,
            self.receipt,
            "plan-hash",
            "receipt-hash",
        )
        with self.assertRaises(RuntimeError):
            verify.verify_evidence(evidence, self.plan, self.receipt)


if __name__ == "__main__":
    unittest.main()
