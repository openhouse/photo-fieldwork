import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"unable to load skill bridge: {SCRIPT}")
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

    def test_inspection_plan_is_linted_and_digest_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "input.csv"
            inventory.write_text("uuid,filename\nABC,image.jpg\n", encoding="utf-8")
            output = root / "inspection-plan.json"
            args = argparse.Namespace(
                input=inventory,
                workspace=root,
                output=output,
                plan_id="test-inspection",
                source_profile=None,
                source_id="SOURCE/L0/040",
                source_count=1,
                target_long_edge=1280,
                limit=None,
                no_previews=False,
                no_ocr=False,
                no_classify=False,
                no_face_detection=False,
            )
            bridge.command_inspection_plan(args)
            plan = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(plan["lint_status"], "PASS")
            self.assertTrue(bridge.verify_plan_digest(plan))
            plan["expected_source_count"] = 2
            self.assertFalse(bridge.verify_plan_digest(plan))

    def test_source_profile_overrides_legacy_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_path = Path(directory) / "source.json"
            profile_path.write_text(json.dumps({
                "schema_version": 1,
                "id": "visible-library-stills://v1",
                "title": "Visible stills",
                "kind": "visible-library-query",
                "expected_count": 603137,
            }), encoding="utf-8")
            source_id, source_count, profile = bridge.source_contract(argparse.Namespace(
                source_profile=profile_path,
                source_id="legacy",
                source_count=1,
            ))
            self.assertEqual(source_id, "visible-library-stills://v1")
            self.assertEqual(source_count, 603137)
            self.assertIn("fingerprint", profile)


if __name__ == "__main__":
    unittest.main()
