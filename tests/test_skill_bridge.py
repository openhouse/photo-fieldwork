import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from photo_fieldwork.pipeline import content_sha256, master_sha256


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

    def test_snapshot_plan_is_attempt_and_content_bound(self):
        binding = {
            "release_plan_id": "release",
            "proposal_id": "pfp-aaaaaaaaaaaaaaaa",
            "release_plan_sha256": "a" * 64,
            "master_sha256": "b" * 64,
            "config_sha256": "c" * 64,
            "feedback_sha256": "d" * 64,
            "source_membership_sha256": "e" * 64,
            "evaluation_report_sha256": "f" * 64,
            "validation_report_sha256": "0" * 64,
        }
        plan = bridge.snapshot_plan(
            Namespace(batch_size=500, workspace=Path("/private/tmp/synthetic-run")),
            "production-01",
            "attempt-01",
            [{"key": "version", "title": "Version", "parent_key": None, "existing_identifier": None}],
            [bridge.album("00 MASTER", "version", ["ONE", "TWO"])],
            "receipt-01.json",
            "SOURCE",
            2,
            binding,
        )
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["attempt_id"], "attempt-01")
        self.assertEqual(plan["plan_sha256"], content_sha256(plan))

    def test_release_binding_rejects_a_tampered_or_stale_plan(self):
        rows = [
            {"uuid": "ONE", "primary_view": "a"},
            {"uuid": "TWO", "primary_view": "b"},
        ]
        digest = master_sha256(rows)
        config_digest = "d" * 64
        feedback_digest = "e" * 64
        plan = {
            "schema_version": 2,
            "plan_id": "release",
            "proposal_id": f"pfp-{digest[:16]}",
            "master_sha256": digest,
            "config_sha256": config_digest,
            "feedback_sha256": feedback_digest,
            "release_class": "editor-field-verified",
            "publication_state": "publication-review-required",
            "expected_master_count": 2,
            "source": {
                "identifier": "SOURCE",
                "count": 3,
                "membership_sha256": "a" * 64,
            },
            "evaluation": {
                "passed": True,
                "final_field_audit": True,
                "proposal_id": f"pfp-{digest[:16]}",
                "master_sha256": digest,
                "config_sha256": config_digest,
                "feedback_sha256": feedback_digest,
                "report_sha256": "b" * 64,
            },
            "validation": {
                "status": "PASS",
                "proposal_id": f"pfp-{digest[:16]}",
                "master_sha256": digest,
                "config_sha256": config_digest,
                "feedback_sha256": feedback_digest,
                "report_sha256": "c" * 64,
            },
            "albums": [{"key": "master", "asset_ids": ["ONE", "TWO"]}],
        }
        plan["plan_sha256"] = content_sha256(plan)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "release-plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            binding = bridge.release_binding(path, rows, "SOURCE", 3)
            self.assertEqual(binding["master_sha256"], digest)
            plan["albums"][0]["asset_ids"][0] = "CHANGED"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "plan_sha256"):
                bridge.release_binding(path, rows, "SOURCE", 3)

            plan["albums"][0]["asset_ids"][0] = "ONE"
            plan["evaluation"]["final_field_audit"] = False
            plan["plan_sha256"] = content_sha256(plan)
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evaluation binding"):
                bridge.release_binding(path, rows, "SOURCE", 3)


if __name__ == "__main__":
    unittest.main()
