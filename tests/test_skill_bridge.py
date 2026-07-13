import argparse
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from photo_fieldwork.pipeline import master_sha256 as core_master_sha256


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SkillBridgeTests(unittest.TestCase):
    def test_local_identifier_is_canonical(self):
        self.assertEqual(bridge.local_identifier("ABC"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/001"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/040"), "ABC/L0/001")

    def test_bridge_and_core_bind_the_same_master(self):
        rows = [
            {"uuid": "B", "assigned_view": "02"},
            {"uuid": "A", "assigned_view": "01"},
        ]
        self.assertEqual(bridge.master_sha256(rows), core_master_sha256(rows))

    def test_folder_contract_uses_protected_identifiers(self):
        profile = {
            "folders": {
                "root": {"title": "Root", "identifier": "ROOT-ID"},
                "private": {"title": "Private", "identifier": "PRIVATE-ID"},
                "audit": {"title": "Audit", "identifier": "AUDIT-ID"},
            }
        }
        folders = bridge.folder_specs(profile, "v03 example", include_version=True)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["existing_identifier"], "ROOT-ID")
        self.assertEqual(by_key["private"]["existing_identifier"], "PRIVATE-ID")
        self.assertEqual(by_key["audit"]["existing_identifier"], "AUDIT-ID")
        self.assertEqual(by_key["version"]["title"], "v03 example")

    def test_init_run_is_private_and_advance_hashes_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace_root = Path(temporary) / "runs"
            workspace_root.mkdir(mode=0o700)
            profile = {
                "workspace_root": str(workspace_root),
                "default_source": {"identifier": "SOURCE", "expected_count": 20},
            }
            output = io.StringIO()
            with redirect_stdout(output):
                bridge.command_init(
                    argparse.Namespace(
                        profile_data=profile,
                        workspace_root=None,
                        source_id=None,
                        source_count=None,
                        version="v-test",
                        slug="private run",
                        target=4,
                    )
                )
            run = Path(output.getvalue().strip())
            self.assertEqual(os.stat(run).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(run / "run-state.json").st_mode & 0o777, 0o600)
            artifact = run / "brief.md"
            artifact.write_text("brief\n", encoding="utf-8")
            artifact.chmod(0o600)
            with redirect_stdout(io.StringIO()):
                bridge.command_advance(
                    argparse.Namespace(workspace=run, phase="brief", artifact=[artifact])
                )
            state = json.loads((run / "run-state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phases"]["brief"]["status"], "completed")
            self.assertEqual(len(state["artifacts"]["brief.md"]["sha256"]), 64)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    bridge.command_status(argparse.Namespace(workspace=run)),
                    0,
                )
            artifact.write_text("changed\n", encoding="utf-8")
            artifact.chmod(0o600)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    bridge.command_status(argparse.Namespace(workspace=run)),
                    2,
                )

    def test_advance_rejects_out_of_order_phase(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            state = {
                "schema_version": 2,
                "phases": {phase: {"status": "pending"} for phase in bridge.RUN_PHASES},
                "artifacts": {},
            }
            bridge.dump_json(run / "run-state.json", state)
            with self.assertRaisesRegex(ValueError, "earlier phases pending"):
                bridge.command_advance(
                    argparse.Namespace(workspace=run, phase="retrieval", artifact=[])
                )

    def test_machine_profile_must_be_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile.json"
            profile.write_text("{}\n", encoding="utf-8")
            profile.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "mode 0600"):
                bridge.load_profile(profile)

    def test_artifact_ledger_rejects_symlink_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            target = workspace / "target.md"
            target.write_text("private\n", encoding="utf-8")
            link = workspace / "link.md"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                bridge.safe_workspace_file(workspace, link)


if __name__ == "__main__":
    unittest.main()
