import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "retrieve_candidates.py"
SPEC = importlib.util.spec_from_file_location("retrieve_candidates", SCRIPT)
retrieval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(retrieval)


class RetrieveCandidatesTests(unittest.TestCase):
    def test_album_exclusions_prevent_prior_editor_fields_from_matching(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE asset_album (uuid TEXT, album_title TEXT)")
        conn.executemany(
            "INSERT INTO asset_album VALUES (?, ?)",
            [("KEEP", "FairRentNYC source"), ("DROP", "FairRentNYC editor hypothesis")],
        )
        self.assertEqual(
            retrieval.album_matches(conn, ["FairRentNYC"], ["editor hypothesis"]),
            {"KEEP"},
        )
        conn.close()

    def test_signal_coverage_exposes_requested_empty_modalities(self):
        conn = sqlite3.connect(":memory:")
        for table, column in (
            ("asset_person", "person"), ("asset_album", "album_title"),
            ("asset_keyword", "keyword"), ("asset_label", "label_normalized"),
            ("asset_place", "place"), ("asset_search", "normalized_string"),
        ):
            conn.execute(f"CREATE TABLE {table} (uuid TEXT, {column} TEXT)")
        conn.execute("INSERT INTO asset_person VALUES ('A', 'Jamie')")
        result = retrieval.signal_coverage(conn, [{"people": ["Jamie"], "places": ["NYC"]}])
        self.assertEqual(result["people"]["rows"], 1)
        self.assertEqual(result["places"]["rows"], 0)
        self.assertTrue(result["places"]["requested"])
        conn.close()
