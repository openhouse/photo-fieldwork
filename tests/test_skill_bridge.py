import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SkillBridgeTests(unittest.TestCase):
    def test_local_identifier_is_canonical(self):
        self.assertEqual(bridge.local_identifier("ABC"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/001"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/040"), "ABC/L0/001")

    def test_folder_contract_uses_protected_identifiers(self):
        profile = {
            "protected_folders": {
                "root": {"title": "Root", "identifier": "ROOT/L0/020"},
                "private": {"title": "Private", "identifier": "PRIVATE/L0/020"},
                "audit": {"title": "Audit", "identifier": "AUDIT/L0/020"},
            }
        }
        folders = bridge.folder_specs("v03 example", include_version=True, profile=profile)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["existing_identifier"], "ROOT/L0/020")
        self.assertEqual(by_key["private"]["existing_identifier"], "PRIVATE/L0/020")
        self.assertEqual(by_key["audit"]["existing_identifier"], "AUDIT/L0/020")
        self.assertEqual(by_key["version"]["title"], "v03 example")


if __name__ == "__main__":
    unittest.main()
