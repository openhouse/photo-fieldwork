import importlib.util
import argparse
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)

VERIFY_SCRIPT = SCRIPT.with_name("verify_photos_commit.py")
VERIFY_SPEC = importlib.util.spec_from_file_location("verify_photos_commit", VERIFY_SCRIPT)
verify = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(verify)


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

    def test_album_contract_carries_semantic_role_and_visibility(self):
        album = bridge.album(
            "Master",
            "version",
            ["ABC"],
            key="master",
            role="editor-master",
            visibility="private-editor",
        )
        self.assertEqual(album["key"], "master")
        self.assertEqual(album["role"], "editor-master")
        self.assertEqual(album["visibility"], "private-editor")
        self.assertEqual(album["asset_identifiers"], ["ABC/L0/001"])

    def test_bridge_init_creates_recoverable_event_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            bridge.command_init(
                argparse.Namespace(
                    workspace_root=workspace,
                    version="v-test",
                    slug="event ledger",
                    target=10,
                    source_id="SOURCE/L0/040",
                    source_count=20,
                )
            )
            run = next(workspace.iterdir())
            events = [json.loads(line) for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            state = json.loads((run / "run-state.json").read_text(encoding="utf-8"))
            self.assertEqual(events[0]["event"], "run_initialized")
            self.assertEqual(state["revision"], 1)

    def test_report_extension_always_matches_content_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path, markdown_path = verify.output_paths(
                argparse.Namespace(report=root / "verification.json", report_json=None, report_md=None)
            )
            self.assertEqual(json_path.suffix, ".json")
            self.assertEqual(markdown_path.suffix, ".md")


if __name__ == "__main__":
    unittest.main()
