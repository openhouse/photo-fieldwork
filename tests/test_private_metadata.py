import csv
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "export_private_metadata.py"
SPEC = importlib.util.spec_from_file_location("export_private_metadata", SCRIPT)
metadata_export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata_export)


class PrivateMetadataTests(unittest.TestCase):
    def test_export_preserves_indexed_properties_and_relationships_privately(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "inventory.sqlite"
            connection = sqlite3.connect(database)
            asset_columns = [
                "uuid TEXT PRIMARY KEY",
                "camera_make TEXT",
                "camera_model TEXT",
                "latitude REAL",
                "longitude REAL",
                "date_created TEXT",
            ]
            connection.execute(f"CREATE TABLE asset ({', '.join(asset_columns)})")
            connection.execute(
                "INSERT INTO asset VALUES (?, ?, ?, ?, ?, ?)",
                ("PHOTO-1", "Camera Co", "Model X", 40.1, -73.9, "2026-01-02"),
            )
            for _, (table, fields) in metadata_export.RELATIONS.items():
                connection.execute(
                    f"CREATE TABLE {table} (uuid TEXT, "
                    + ", ".join(f"{field} TEXT" for field in fields)
                    + ")"
                )
            connection.execute("INSERT INTO asset_person VALUES (?, ?)", ("PHOTO-1", "Named Person"))
            connection.execute(
                "INSERT INTO asset_album VALUES (?, ?, ?)",
                ("PHOTO-1", "ALBUM-1", "Private Album"),
            )
            connection.commit()
            connection.close()
            selected = root / "selected.csv"
            with selected.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["uuid"])
                writer.writeheader()
                writer.writerow({"uuid": "PHOTO-1/L0/001"})
            output = root / "private" / "metadata.jsonl"
            self.assertEqual(metadata_export.export(database, selected, output), 1)
            record = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(record["asset"]["camera_model"], "Model X")
            self.assertEqual(record["asset"]["latitude"], 40.1)
            self.assertEqual(record["relationships"]["people"][0]["person"], "Named Person")
            self.assertEqual(record["relationships"]["albums"][0]["album_title"], "Private Album")
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
