import importlib.util
import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SkillBridgeTests(unittest.TestCase):
    def test_empty_hold_manifest_is_valid_when_explicitly_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "holds.csv"
            path.write_text("uuid,filename,safety_status\n", encoding="utf-8")
            self.assertEqual(bridge.read_csv(path, allow_empty=True), [])

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

    def test_snapshot_plan_is_content_addressed(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(
                source_id="visible-library-stills://v1",
                source_count=3,
                source_sha256="source-digest",
                release_seal_fingerprint="sha256:" + "a" * 64,
                batch_size=100,
                workspace=Path(temporary),
            )
            plan = bridge.snapshot_plan(
                args,
                "plan-1",
                bridge.folder_specs("v01", include_version=True),
                [bridge.album("00 MASTER", "version", ["A", "B"])],
                "receipt.json",
            )
            digest_value = {key: value for key, value in plan.items() if key != "plan_sha256"}
            expected = hashlib.sha256(
                json.dumps(digest_value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
            ).hexdigest()
            self.assertEqual(plan["plan_sha256"], expected)
            self.assertEqual(plan["expected_source_membership_sha256"], "source-digest")
            self.assertEqual(plan["release_seal_fingerprint"], "sha256:" + "a" * 64)

    def test_inspection_plan_is_content_addressed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates.csv"
            candidates.write_text("uuid,filename\nA,a.jpg\n", encoding="utf-8")
            output = root / "inspection-plan.json"
            args = argparse.Namespace(
                input=candidates,
                limit=None,
                workspace=root,
                plan_id="inspect-1",
                source_id="visible-library-stills://v1",
                source_count=1,
                target_long_edge=1280,
                no_previews=False,
                no_ocr=False,
                no_classify=False,
                no_face_detection=False,
                output=output,
            )
            self.assertEqual(bridge.command_inspection_plan(args), 0)
            plan = json.loads(output.read_text())
            digest_value = {key: value for key, value in plan.items() if key != "plan_sha256"}
            expected = hashlib.sha256(
                json.dumps(digest_value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
            ).hexdigest()
            self.assertEqual(plan["plan_sha256"], expected)


if __name__ == "__main__":
    unittest.main()
