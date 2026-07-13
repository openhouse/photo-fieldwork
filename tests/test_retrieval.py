import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETRIEVER_PATH = ROOT / "skills/curate-apple-photos/scripts/retrieve_candidates.py"
SPEC = importlib.util.spec_from_file_location("retrieve_candidates", RETRIEVER_PATH)
retriever = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(retriever)


class RetrievalTests(unittest.TestCase):
    def test_album_matching_excludes_generated_lineage(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE asset_album (uuid TEXT, album_title TEXT, lineage TEXT)"
        )
        conn.executemany(
            "INSERT INTO asset_album VALUES (?, ?, ?)",
            [
                ("A", "Project source", "project_source"),
                ("B", "Project generated master", "fieldwork_generated"),
                ("C", "Project private review", "private_review"),
            ],
        )
        matched = retriever.album_matches(
            conn,
            ["project"],
            [],
            ["fieldwork_generated", "private_review"],
            True,
        )
        self.assertEqual(matched, {"A"})

    def test_safe_album_values_do_not_export_private_titles(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE asset_album (uuid TEXT, album_title TEXT, lineage TEXT)"
        )
        conn.executemany(
            "INSERT INTO asset_album VALUES (?, ?, ?)",
            [
                ("A", "Human project", "human_source"),
                ("A", "PRIVATE REVIEW - address", "private_review"),
                ("A", "Generated MASTER", "fieldwork_generated"),
            ],
        )
        titles, lineages = retriever.safe_album_values(
            conn,
            ["A"],
            ["master"],
            ["private_review", "fieldwork_generated"],
            True,
        )
        self.assertEqual(titles["A"], ["Human project"])
        self.assertEqual(lineages["A"], ["human_source"])

    def test_event_cluster_is_a_retrieval_signal_not_an_event_name(self):
        row = {
            "burst_key": "BURST-1",
            "date_created": "2026-01-02 03:04:05",
            "camera_model": "Camera",
        }
        self.assertEqual(retriever.event_cluster(row), "burst:BURST-1")
        row["burst_key"] = ""
        self.assertEqual(
            retriever.event_cluster(row),
            "capture-hour:2026-01-02 03:camera",
        )

    def test_whole_library_builder_has_no_compiled_observed_count(self):
        source = (
            ROOT / "skills/curate-apple-photos/scripts/build_visible_library_inventory.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("603137", source)
        self.assertIn("--expected-count", source)


if __name__ == "__main__":
    unittest.main()
