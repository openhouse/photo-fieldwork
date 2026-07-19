import importlib.util
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

    def test_snapshot_plan_resolves_workspace_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            args = type("Args", (), {
                "workspace": workspace,
                "source_id": "SOURCE",
                "source_count": 2,
                "source_membership_sha256": "a" * 64,
                "batch_size": 10,
            })()
            plan = bridge.snapshot_plan(args, "test", [], [], "receipt.json")
            self.assertTrue(Path(plan["receipt_path"]).is_absolute())
            self.assertEqual(Path(plan["workspace_path"]), workspace.resolve())
            self.assertEqual(plan["source_membership_sha256"], "a" * 64)
            self.assertEqual(plan["required_helper_revision"], bridge.HELPER_REVISION)

    def test_plan_paths_must_be_absolute_and_inside_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            plan_path = workspace / "manifests" / "plan.json"
            plan_path.parent.mkdir()
            valid = {
                "workspace_path": str(workspace),
                "receipt_path": str(workspace / "manifests" / "receipt.json"),
                "log_path": str(workspace / "logs" / "app.log"),
            }
            bridge.validate_plan_paths(valid, plan_path)
            invalid = dict(valid, receipt_path="relative.json")
            with self.assertRaisesRegex(ValueError, "must be absolute"):
                bridge.validate_plan_paths(invalid, plan_path)
            outside = dict(valid, receipt_path=str(workspace.parent / "outside.json"))
            with self.assertRaisesRegex(ValueError, "inside workspace_path"):
                bridge.validate_plan_paths(outside, plan_path)

    def test_status_reports_next_incomplete_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            bridge.initialize_run(
                workspace,
                run_id="run",
                phases=["brief", "retrieval"],
                metadata={},
            )
            args = type("Args", (), {"workspace": workspace})()
            self.assertEqual(bridge.command_status(args), 0)

    def test_snapshot_receipt_binds_exact_plan_launch_and_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "plan.json"
            plan_path.write_text(
                json.dumps({
                    "plan_id": "plan",
                    "source_album_identifier": "source",
                    "expected_source_count": 2,
                    "source_membership_sha256": "b" * 64,
                    "safety_mode": "create-folders-albums-and-add-membership-only",
                    "required_helper_revision": bridge.HELPER_REVISION,
                }) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
            plan = json.loads(plan_path.read_text())
            receipt = {
                "plan_id": "plan",
                "source_album_identifier": "source",
                "source_count": 2,
                "source_membership_sha256": "b" * 64,
                "safety_mode": "create-folders-albums-and-add-membership-only",
                "required_helper_revision": bridge.HELPER_REVISION,
                "plan_file_sha256": digest,
                "execution_nonce": "a" * 32,
                "helper_revision": bridge.HELPER_REVISION,
            }
            bridge.validate_snapshot_receipt(plan_path, plan, receipt, "a" * 32)
            with self.assertRaisesRegex(ValueError, "plan digest"):
                bridge.validate_snapshot_receipt(
                    plan_path,
                    plan,
                    dict(receipt, plan_file_sha256="0" * 64),
                    "a" * 32,
                )
            with self.assertRaisesRegex(ValueError, "execution nonce"):
                bridge.validate_snapshot_receipt(plan_path, plan, receipt, "b" * 32)

    def test_helper_revision_mismatch_blocks_before_launch(self):
        bridge.validate_helper_contract({
            "required_helper_revision": bridge.HELPER_REVISION,
            "source_membership_sha256": "a" * 64,
        })
        with self.assertRaisesRegex(ValueError, "helper revision"):
            bridge.validate_helper_contract({
                "required_helper_revision": "stale-helper",
                "source_membership_sha256": "a" * 64,
            })


if __name__ == "__main__":
    unittest.main()
