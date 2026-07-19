import importlib.util
import csv
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from photo_fieldwork.contracts import (
    build_source_manifest,
    canonical_sha256,
    finalize_plan,
    identifier_set_sha256,
    validate_plan,
)


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

DUPLICATE_SCRIPT = SCRIPT.parent / "cluster_perceptual_duplicates.py"
DUPLICATE_SPEC = importlib.util.spec_from_file_location("cluster_perceptual_duplicates", DUPLICATE_SCRIPT)
duplicates = importlib.util.module_from_spec(DUPLICATE_SPEC)
DUPLICATE_SPEC.loader.exec_module(duplicates)

EVAL_VALIDATOR_SCRIPT = SCRIPT.parent / "validate_skill_evals.py"
EVAL_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "validate_skill_evals", EVAL_VALIDATOR_SCRIPT
)
eval_validator = importlib.util.module_from_spec(EVAL_VALIDATOR_SPEC)
EVAL_VALIDATOR_SPEC.loader.exec_module(eval_validator)


class SkillBridgeTests(unittest.TestCase):
    def test_skill_eval_bank_and_machine_grader(self):
        eval_path = SCRIPT.parent.parent / "evals" / "evals.json"
        evals = eval_validator.validate_bank(json.loads(eval_path.read_text(encoding="utf-8")))
        self.assertEqual(len(evals), 16)
        control = next(item for item in evals if item["name"] == "clean-editor-field-completion")
        response = {
            "decision": "complete",
            "release_class": "editor-field-verified",
            "controls": {
                "photos_mutation_authorized": False,
                "publication_authorized": False,
                "source_revalidation_required": False,
                "human_safety_review_required": False,
                "fresh_visual_review_required": False,
                "helper_compatibility_required": False,
                "independent_verification_required": False,
            },
            "observed_facts": ["All gates passed."],
            "unknowns": [],
            "blocking_conditions": [],
            "next_actions": ["Record completion."],
            "prohibited_actions": ["Do not claim publication readiness."],
            "claim_boundary": ["The field is editor-field-verified."],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response_dir = root / f"eval-{control['id']:02d}-{control['name']}"
            response_dir.mkdir()
            (response_dir / "response.json").write_text(json.dumps(response), encoding="utf-8")
            result = eval_validator.grade([control], root)
        self.assertEqual(result["summary"]["pass_rate"], 1.0)
        malformed = dict(response)
        malformed.pop("claim_boundary")
        with self.assertRaisesRegex(ValueError, "response fields"):
            eval_validator.validate_response(malformed)

    def test_review_dependency_and_hamming_contract_load(self):
        self.assertEqual(duplicates.hamming(0b1010, 0b0011), 2)

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
            self.assertEqual(updated["phase_records"]["validation"]["status"], "completed")

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

    def test_receipt_must_bind_every_snapshot_hash(self):
        source = build_source_manifest(
            source_adapter="synthetic",
            source_identifier="synthetic://one",
            source_title="One",
            predicate_version="all-v1",
            observed_count=1,
            membership_sha256=identifier_set_sha256(["ABC"]),
        )
        plan = finalize_plan(
            {
                "schema_version": 2,
                "operation": "snapshot-membership",
                "plan_id": "plan",
                "required_helper_revision": bridge.HELPER_REVISION,
                "proposal_id": "pfp-example",
                "master_sha256": "a" * 64,
                "hold_sha256": identifier_set_sha256([]),
                "config_sha256": "c" * 64,
                "source": source,
                "source_fingerprint": source["source_fingerprint"],
                "release_class": "editor-field-verified",
                "expected_source_count": 1,
                "albums": [
                    {"key": "master", "title": "Master", "asset_identifiers": ["ABC/L0/001"]}
                ],
            }
        )
        receipt = {
            "schema_version": 2,
            "plan_id": "plan",
            "helper_revision": bridge.HELPER_REVISION,
            "plan_sha256": plan["plan_sha256"],
            "proposal_id": "pfp-example",
            "master_sha256": "a" * 64,
            "hold_sha256": identifier_set_sha256([]),
            "config_sha256": "c" * 64,
            "source_fingerprint": source["source_fingerprint"],
            "release_class": "editor-field-verified",
            "source_count": 1,
            "albums": [{"key": "master", "title": "Master", "count": 1}],
        }
        bridge.validate_receipt(plan, receipt)
        receipt["master_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "master_sha256"):
            bridge.validate_receipt(plan, receipt)

    def test_bridge_snapshot_plan_uses_the_shared_contract(self):
        source = build_source_manifest(
            source_adapter="synthetic",
            source_identifier="synthetic://one",
            source_title="One",
            predicate_version="all-v1",
            observed_count=1,
            membership_sha256=identifier_set_sha256(["ABC"]),
        )
        with tempfile.TemporaryDirectory() as directory:
            args = Namespace(
                proposal_id="pfp-example",
                master_sha256="a" * 64,
                hold_sha256=identifier_set_sha256([]),
                config_sha256="c" * 64,
                source_manifest_data=source,
                release_class="editor-field-verified",
                evaluation_report_data={
                    "sample_sha256": "b" * 64,
                    "evaluation_scope": "final-stratified-sample",
                },
                batch_size=100,
                workspace=Path(directory),
            )
            plan = bridge.snapshot_plan(
                args,
                "plan",
                [],
                [bridge.album("master", "Master", "version", ["ABC"])],
                "receipt.json",
            )
            self.assertEqual(validate_plan(plan)["plan_sha256"], plan["plan_sha256"])
            self.assertEqual(plan["albums"][0]["key"], "master")

    def test_snapshot_plan_command_binds_source_evaluation_and_holds(self):
        source = build_source_manifest(
            source_adapter="synthetic",
            source_identifier="synthetic://two",
            source_title="Two",
            predicate_version="all-v1",
            observed_count=2,
            membership_sha256=identifier_set_sha256(["ABC", "HOLD"]),
        )
        master_rows = [
            {
                "uuid": "ABC",
                "assigned_view": "00",
                "primary_view": "00",
                "selection_reason": "fixture",
                "persons": "",
                "evidence_confidence": "high",
            }
        ]
        hold_rows = [{"uuid": "HOLD", "safety_status": "hold-human"}]
        digest = bridge.master_sha256(master_rows)
        evaluation = {
            "passed": True,
            "master_bound": True,
            "source_bound": True,
            "source_fingerprint": source["source_fingerprint"],
            "proposal_id": f"pfp-{digest[:16]}",
            "master_sha256": digest,
            "sample_sha256": "b" * 64,
            "evaluation_scope": "final-stratified-sample",
            "release_class": "editor-field-verified",
        }
        config = {
            "eligible_safety_states": ["clear", "clear-automated", "cleared-human"],
            "views": [{"id": "00", "label": "Unclassified"}],
        }
        evaluation["config_sha256"] = canonical_sha256(config)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifests = workspace / "manifests"
            manifests.mkdir()

            def write_rows(path, rows):
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)

            master_path = manifests / "master.csv"
            holds_path = manifests / "holds.csv"
            source_path = manifests / "source.json"
            evaluation_path = workspace / "evaluation.json"
            config_path = workspace / "config.json"
            write_rows(master_path, master_rows)
            write_rows(holds_path, hold_rows)
            source_path.write_text(json.dumps(source), encoding="utf-8")
            evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
            config_path.write_text(json.dumps(config), encoding="utf-8")
            state = {
                "status": "initialized",
                "phases": {phase: "pending" for phase in bridge.RUN_PHASES},
                "phase_records": {},
            }
            (workspace / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
            bridge.command_snapshot_plans(
                Namespace(
                    profile=None,
                    source_manifest=source_path,
                    master=master_path,
                    holds=holds_path,
                    target=1,
                    version="v-test",
                    folder_title="v-test",
                    view_column="primary_view",
                    config=config_path,
                    evaluation_report=evaluation_path,
                    batch_size=100,
                    workspace=workspace,
                )
            )
            plan = json.loads((manifests / "v-test-production-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(validate_plan(plan)["hold_sha256"], identifier_set_sha256(["HOLD"]))
            self.assertEqual(plan["required_helper_revision"], bridge.HELPER_REVISION)


if __name__ == "__main__":
    unittest.main()
