import importlib.util
import argparse
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
LINTER_SPEC = importlib.util.spec_from_file_location("lint_public_report", SCRIPT.parent / "lint_public_report.py")
linter = importlib.util.module_from_spec(LINTER_SPEC)
LINTER_SPEC.loader.exec_module(linter)


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

    def test_init_run_records_hashed_source_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            args = argparse.Namespace(
                slug="test",
                version="v99",
                target=12,
                workspace_root=workspace,
                source_manifest=None,
                source_id="SOURCE/L0/040",
                source_count=20,
                source_title="Fixture source",
            )
            self.assertEqual(bridge.command_init(args), 0)
            run = next(workspace.iterdir())
            state = json.loads((run / "run-state.json").read_text(encoding="utf-8"))
            phase = state["phases"]["initialize"]
            self.assertEqual(phase["status"], "complete")
            self.assertEqual({item["path"] for item in phase["artifacts"]}, {"README.md", "source.json"})

    def test_master_hash_covers_membership_and_assignment(self):
        rows = [{"uuid": "ABC/L0/001", "assigned_view": "01"}]
        first = bridge.master_sha256(rows)
        rows[0]["assigned_view"] = "02"
        self.assertNotEqual(first, bridge.master_sha256(rows))

    def test_public_report_linter_flags_private_operational_fields(self):
        findings = linter.lint("photos_database: /Users/example/Photos.sqlite\nlatitude: 40.0")
        self.assertEqual(
            {item["rule"] for item in findings},
            {"absolute user path", "exact coordinate key"},
        )

    def test_snapshot_plan_requires_and_preserves_evaluated_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "manifests").mkdir()
            master = workspace / "master.csv"
            row = {
                "uuid": "A",
                "filename": "a.jpg",
                "assigned_view": "01",
                "primary_view": "01",
                "selection_reason": "reviewed fixture",
                "evidence_confidence": "high",
                "persons": "",
            }
            with master.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            holds = workspace / "holds.csv"
            holds.write_text("uuid,filename\n", encoding="utf-8")
            digest = bridge.master_sha256([row])
            evaluation = workspace / "evaluation.json"
            evaluation.write_text(json.dumps({
                "passed": True,
                "full_master_audit": True,
                "master_sha256": digest,
                "proposal_id": f"pfp-{digest[:16]}",
                "audited_uuid_sha256": bridge.uuid_sha256([row]),
            }), encoding="utf-8")
            args = argparse.Namespace(
                workspace=workspace, master=master, holds=holds, target=1,
                version="v99", folder_title="v99 fixture", view_column="primary_view",
                config=None, evaluation_report=evaluation, source_manifest=None,
                source_id="SOURCE/L0/040", source_count=3, source_title="Fixture source",
                batch_size=50,
            )
            self.assertEqual(bridge.command_snapshot_plans(args), 0)
            plan = json.loads(
                (workspace / "manifests" / "v99-production-plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(plan["master_sha256"], digest)
            self.assertTrue(plan["evaluation"]["full_master_audit"])


if __name__ == "__main__":
    unittest.main()
