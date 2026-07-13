import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SkillBridgeTests(unittest.TestCase):
    def test_local_identifier_is_canonical(self):
        self.assertEqual(bridge.local_identifier("ABC"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/001"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/040"), "ABC/L0/001")

    def test_inventory_metadata_supports_json_and_plain_values(self):
        self.assertEqual(bridge.decode_meta_value('"album-id"'), "album-id")
        self.assertEqual(bridge.decode_meta_value("visible-library-stills://v1"), "visible-library-stills://v1")

    def test_folder_contract_uses_protected_identifiers(self):
        folders = bridge.folder_specs("v03 example", include_version=True)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["existing_identifier"], bridge.ROOT_FOLDER_ID)
        self.assertEqual(by_key["private"]["existing_identifier"], bridge.PRIVATE_FOLDER_ID)
        self.assertEqual(by_key["audit"]["existing_identifier"], bridge.AUDIT_FOLDER_ID)
        self.assertEqual(by_key["version"]["title"], "v03 example")

    def test_snapshot_plan_is_v2_and_content_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                source_id="visible-library-stills://v1",
                source_count=42,
                batch_size=10,
                workspace=Path(directory),
            )
            plan = bridge.snapshot_plan(
                args,
                "test-plan",
                bridge.folder_specs("v99", include_version=True),
                [bridge.album("00 MASTER", "version", ["ABC"])],
                "receipt.json",
            )
            self.assertEqual(plan["schema_version"], 2)
            self.assertEqual(plan["adapter"]["name"], "apple-photos-photokit")
            self.assertEqual(plan["plan_sha256"], bridge.content_sha256(plan))
            plan["batch_size"] = 11
            self.assertNotEqual(plan["plan_sha256"], bridge.content_sha256(plan))

    def test_release_seal_hashes_inputs_and_updates_run_state_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest = workspace / "master.csv"
            manifest.write_text("uuid\nABC\n", encoding="utf-8")
            phases = {phase: "completed" for phase in bridge.PHASE_ORDER}
            state = {
                "run_id": "qa-run",
                "status": "validation",
                "source_album_identifier": "visible-library-stills://v1",
                "expected_source_count": 42,
                "target_count": 1,
                "phases": phases,
            }
            (workspace / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
            original_app = bridge.APP_EXECUTABLE
            original_plist = bridge.APP_PLIST
            try:
                bridge.APP_EXECUTABLE = workspace / "missing-app"
                bridge.APP_PLIST = workspace / "missing-plist"
                with redirect_stdout(io.StringIO()):
                    code = bridge.command_seal(
                        SimpleNamespace(workspace=workspace, input=[manifest], output=None)
                    )
            finally:
                bridge.APP_EXECUTABLE = original_app
                bridge.APP_PLIST = original_plist
            self.assertEqual(code, 0)
            seal = json.loads((workspace / "manifests" / "release-seal.json").read_text())
            updated = json.loads((workspace / "run-state.json").read_text())
            self.assertEqual(seal["seal_sha256"], bridge.content_sha256(seal, "seal_sha256"))
            self.assertEqual(updated["status"], "sealed")


if __name__ == "__main__":
    unittest.main()
