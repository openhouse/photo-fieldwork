import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "curate-apple-photos" / "scripts"
SCRIPT = SCRIPTS / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


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

    def test_whole_library_source_and_optional_vision_controls_are_public(self):
        swift = (ROOT / "integrations" / "jamie-photo-archive" / "JamiePhotoArchive.swift").read_text(encoding="utf-8")
        inventory = (SCRIPTS / "build_visible_library_inventory.py").read_text(encoding="utf-8")
        retrieve = (SCRIPTS / "retrieve_candidates.py").read_text(encoding="utf-8")
        self.assertIn('visible-library-stills://v1', swift)
        self.assertIn("includeHiddenAssets = false", swift)
        self.assertIn("classify_all", swift)
        self.assertIn("detect_faces", swift)
        self.assertIn("mode=ro&immutable=1", inventory)
        self.assertIn("retrieval_provenance_json", retrieve)


if __name__ == "__main__":
    unittest.main()
