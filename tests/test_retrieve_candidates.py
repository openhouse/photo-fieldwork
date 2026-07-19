import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "retrieve_candidates.py"
BASE_COLUMNS = [
    "uuid", "filename", "original_filename", "date_created", "year", "width", "height",
    "is_photo", "is_movie", "favorite", "edited", "hidden", "trashed", "missing",
    "screenshot", "selfie", "portrait", "burst", "burst_key", "burst_pick_type",
    "overall_aesthetic_score", "duplicate_group_id", "camera_make", "camera_model",
    "face_count", "title", "description",
]


class RetrievalTests(unittest.TestCase):
    def build_inventory(self, path: Path) -> None:
        conn = sqlite3.connect(path)
        numeric = {"year", "width", "height", "is_photo", "is_movie", "favorite", "edited", "hidden", "trashed", "missing", "screenshot", "selfie", "portrait", "burst", "burst_pick_type", "face_count", "overall_aesthetic_score"}
        columns = ",".join(f"{name} {'REAL' if name == 'overall_aesthetic_score' else 'INTEGER' if name in numeric else 'TEXT'}" for name in BASE_COLUMNS)
        conn.execute(f"CREATE TABLE asset ({columns})")
        for table, declaration in [
            ("asset_album", "uuid TEXT, album_uuid TEXT, album_title TEXT"),
            ("asset_person", "uuid TEXT, person TEXT"),
            ("asset_keyword", "uuid TEXT, keyword TEXT"),
            ("asset_search", "uuid TEXT, normalized_string TEXT"),
            ("asset_label", "uuid TEXT, label TEXT, label_normalized TEXT"),
            ("asset_place", "uuid TEXT, place TEXT"),
        ]:
            conn.execute(f"CREATE TABLE {table} ({declaration})")
        for index, uuid in enumerate("ABCDEF", start=1):
            row = {column: "" for column in BASE_COLUMNS}
            row.update({
                "uuid": uuid,
                "filename": f"{uuid}.jpg",
                "original_filename": f"{uuid}.jpg",
                "year": 2020,
                "width": 100,
                "height": 100,
                "is_photo": 1,
                "is_movie": 0,
                "favorite": 1 if index <= 3 else 0,
                "edited": 0,
                "hidden": 0,
                "trashed": 0,
                "missing": 0,
                "face_count": 0,
                "title": f"context evidence {uuid}",
            })
            conn.execute(
                f"INSERT INTO asset VALUES ({','.join('?' for _ in BASE_COLUMNS)})",
                [row[column] for column in BASE_COLUMNS],
            )
        conn.executemany(
            "INSERT INTO asset_album VALUES (?, ?, ?)",
            [(uuid, "PRIOR", "Prior corpus") for uuid in "ABCD"]
            + [("F", "GEN", "v04 editor field")],
        )
        conn.commit()
        conn.close()

    def test_context_and_discovery_channels_remain_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "inventory.sqlite"
            self.build_inventory(database)
            retrieval = root / "retrieval.json"
            retrieval.write_text(json.dumps({
                "candidate_multiplier": 1,
                "outside_prior_discovery_fraction": 0.25,
                "prior_corpus_album_identifiers": ["PRIOR"],
                "excluded_album_identifiers": ["GEN"],
                "excluded_album_terms": ["editor field"],
                "views": [{"id": "01", "quota": 4, "terms": ["context"]}],
            }), encoding="utf-8")
            output = root / "candidates.csv"
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--db", str(database), "--retrieval", str(retrieval), "--target", "4", "--output", str(output)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4)
            self.assertEqual(sum(row["prior_corpus_member"] == "true" for row in rows), 3)
            discovered = [row for row in rows if "outside-prior-discovery" in row["retrieval_channels"]]
            self.assertEqual(len(discovered), 1)
            self.assertTrue(all("v04 editor field" not in row["albums"] for row in rows))


if __name__ == "__main__":
    unittest.main()
