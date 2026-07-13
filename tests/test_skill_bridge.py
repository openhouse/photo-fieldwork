import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)

WRITER_SCRIPT = SCRIPT.parent / "applescript_writer.py"
WRITER_SPEC = importlib.util.spec_from_file_location("applescript_writer", WRITER_SCRIPT)
writer = importlib.util.module_from_spec(WRITER_SPEC)
WRITER_SPEC.loader.exec_module(writer)


class SkillBridgeTests(unittest.TestCase):
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

    def test_profile_can_replace_machine_specific_folder_contract(self):
        profile = bridge.default_profile()
        profile["protected_folders"] = {
            "root": {"title": "ROOT", "identifier": "ROOT-ID"},
            "private": {"title": "PRIVATE", "identifier": "PRIVATE-ID"},
            "audit": {"title": "AUDIT", "identifier": "AUDIT-ID"},
        }
        folders = bridge.folder_specs("v-test", include_version=True, profile=profile)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["title"], "ROOT")
        self.assertEqual(by_key["private"]["existing_identifier"], "PRIVATE-ID")

    def test_applescript_adapter_renders_fail_closed_membership_plan(self):
        plan = {
            "operation": "snapshot-membership",
            "schema_version": 1,
            "plan_id": "test",
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "source_album_identifier": "source",
            "expected_source_count": 2,
            "batch_size": 2,
            "receipt_path": "receipt.json",
            "folders": [
                {"key": "root", "title": "ROOT", "parent_key": None, "existing_identifier": "ROOT-ID"},
                {"key": "version", "title": "VERSION", "parent_key": "root", "existing_identifier": None},
            ],
            "albums": [
                {
                    "title": "MASTER",
                    "parent_folder_key": "version",
                    "existing_identifier": None,
                    "asset_identifiers": ["A/L0/001", "B/L0/001"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            id_directory = Path(temporary) / "ids"
            script = writer.render(plan, id_directory)
            self.assertIn("contains an unexpected member", script)
            self.assertIn("missing an expected UUID", script)
            self.assertIn("Final count mismatch", script)
            self.assertEqual((id_directory / "album-000.txt").read_text(), "A/L0/001\nB/L0/001")
            self.assertEqual(os.stat(id_directory).st_mode & 0o777, 0o700)

    def test_applescript_adapter_rejects_duplicate_ids(self):
        plan = {
            "operation": "snapshot-membership",
            "schema_version": 1,
            "plan_id": "test",
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "source_album_identifier": "source",
            "expected_source_count": 1,
            "batch_size": 1,
            "receipt_path": "receipt.json",
            "folders": [{"key": "root", "title": "ROOT", "parent_key": None, "existing_identifier": "ROOT-ID"}],
            "albums": [{"title": "MASTER", "parent_folder_key": "root", "existing_identifier": None, "asset_identifiers": ["A/L0/001", "A/L0/001"]}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                writer.render(plan, Path(temporary))

    def test_private_profile_initializer_uses_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "private" / "profile.json"
            args = SimpleNamespace(
                output=output,
                schema=None,
                workspace_root=root / "workspace",
                cli=root / "bin/photo-fieldwork",
                inventory=root / "inventory.sqlite",
                photos_db=root / "Photos.sqlite",
                app=root / "Helper.app",
                bundle_identifier="test.helper",
                executable="Helper",
                source_id="source://test",
                source_count=10,
                source_title="Source",
                root_title="ROOT",
                root_id="ROOT-ID",
                private_title="PRIVATE",
                private_id="PRIVATE-ID",
                audit_title="AUDIT",
                audit_id="AUDIT-ID",
            )
            self.assertEqual(bridge.command_init_profile(args), 0)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            profile = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(profile["source"]["expected_count"], 10)
            with self.assertRaises(ValueError):
                bridge.command_init_profile(args)


if __name__ == "__main__":
    unittest.main()
