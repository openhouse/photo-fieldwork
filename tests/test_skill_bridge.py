import importlib.util
import argparse
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SkillBridgeTests(unittest.TestCase):
    def test_init_run_uses_reconcilable_v2_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(
                workspace_root=root,
                version="v-test",
                slug="bridge",
                target=10,
                source_id="SOURCE",
                source_count=42,
                source_profile=None,
            )
            self.assertEqual(bridge.command_init(args), 0)
            run = next(root.iterdir())
            state = json.loads((run / "run-state.json").read_text())
            self.assertEqual(state["schema_version"], 2)
            self.assertEqual(state["source"]["expected_count"], 42)
            self.assertEqual(state["phases"]["retrieval"]["status"], "pending")

    def test_source_profile_can_read_count_from_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "inventory.sqlite"
            conn = sqlite3.connect(inventory)
            conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.executemany(
                "INSERT INTO meta VALUES (?, ?)",
                [("source_identifier", "visible-library-stills://v1"), ("source_count", "123")],
            )
            conn.commit()
            conn.close()
            profile = root / "source.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "visible-library-stills://v1",
                        "inventory": str(inventory),
                    }
                )
            )
            args = argparse.Namespace(source_profile=profile, source_id="unused", source_count=0)
            self.assertEqual(bridge.resolve_source(args), ("visible-library-stills://v1", 123))

    def test_local_identifier_is_canonical(self):
        self.assertEqual(bridge.local_identifier("ABC"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/001"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/040"), "ABC/L0/001")

    def test_folder_contract_uses_protected_identifiers(self):
        folders = bridge.folder_specs("v03 example", include_version=True)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["existing_identifier"], bridge.ROOT_FOLDER_ID)
        self.assertEqual(by_key["private"]["existing_identifier"], bridge.PRIVATE_FOLDER_ID)
        self.assertEqual(by_key["audit"]["existing_identifier"], bridge.AUDIT_FOLDER_ID)
        self.assertEqual(by_key["version"]["title"], "v03 example")


if __name__ == "__main__":
    unittest.main()
