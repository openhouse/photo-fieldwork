import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)

LINTER_SCRIPT = SCRIPT.parent / "lint_public_report.py"
LINTER_SPEC = importlib.util.spec_from_file_location("lint_public_report", LINTER_SCRIPT)
linter = importlib.util.module_from_spec(LINTER_SPEC)
LINTER_SPEC.loader.exec_module(linter)

VERIFIER_SCRIPT = SCRIPT.parent / "verify_photos_commit.py"
VERIFIER_SPEC = importlib.util.spec_from_file_location("verify_photos_commit", VERIFIER_SCRIPT)
verifier = importlib.util.module_from_spec(VERIFIER_SPEC)
VERIFIER_SPEC.loader.exec_module(verifier)


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

    def test_master_hash_covers_membership_and_assignment(self):
        rows = [{"uuid": "ABC/L0/001", "assigned_view": "01"}]
        first = bridge.master_sha256(rows)
        rows[0]["assigned_view"] = "02"
        self.assertNotEqual(first, bridge.master_sha256(rows))

    def test_run_state_transition_is_atomic_and_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            state = {
                "status": "initialized",
                "phases": {"validation": "pending"},
            }
            (workspace / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
            bridge.update_run_state(workspace, "validation", "completed", proposal_id="pfp-example")
            updated = json.loads((workspace / "run-state.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["phases"]["validation"], "completed")
            self.assertEqual(updated["last_transition"]["proposal_id"], "pfp-example")

    def test_public_report_linter_flags_private_operational_fields(self):
        findings = linter.lint('photos_database: /Users/example/Photos.sqlite\nlatitude: 40.0')
        self.assertEqual({item["rule"] for item in findings}, {"absolute user path", "exact coordinate key"})

    def test_verifier_report_extension_controls_the_serialization(self):
        result = {
            "generated_at": "2026-07-13T00:00:00-04:00",
            "plan_id": "plan",
            "source_title": "Source",
            "source_count": 1,
            "verified_album_count": 1,
            "unexpected_memberships": 0,
            "missing_memberships": 0,
            "members_outside_source": 0,
            "albums": [{"title": "Album", "count": 1, "identifier": "ALBUM"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "report.json"
            markdown_path = Path(directory) / "report.md"
            verifier.write_report(json_path, result)
            verifier.write_report(markdown_path, result)
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["plan_id"], "plan")
            self.assertTrue(markdown_path.read_text(encoding="utf-8").startswith("# Apple Photos"))


if __name__ == "__main__":
    unittest.main()
