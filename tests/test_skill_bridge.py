import argparse
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from photo_fieldwork.pipeline import (
    evaluate,
    make_sample,
    master_sha256 as core_master_sha256,
    read_config,
    read_csv,
    select,
    validate,
    write_csv,
)
from photo_fieldwork.practice import create_demo_inventory


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SkillBridgeTests(unittest.TestCase):
    def test_authorization_plan_is_zero_image_read_only_and_offline(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            profile = {
                "default_source": {
                    "identifier": "SYNTHETIC-SOURCE",
                    "expected_count": 12,
                    "identifier_sha256": "a" * 64,
                }
            }
            plan = bridge.authorization_plan(profile, workspace, "authorization-test")
            self.assertEqual(plan["asset_identifiers"], [])
            self.assertFalse(plan["network_access_allowed"])
            self.assertFalse(plan["export_previews"])
            self.assertFalse(plan["ocr_all"])
            self.assertFalse(plan["classify_all"])
            self.assertFalse(plan["detect_faces"])
            self.assertEqual(plan["expected_source_count"], 12)

    def test_wait_for_receipt_survives_early_launcher_return(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt_path = root / "receipt.json"
            old_receipt = {"execution_nonce": "0" * 32}
            bridge.dump_json(receipt_path, old_receipt)
            before = receipt_path.stat().st_mtime_ns
            expected_nonce = "1" * 32

            def finish_after_launcher_returns():
                time.sleep(0.05)
                bridge.dump_json(receipt_path, {"execution_nonce": expected_nonce})

            worker = threading.Thread(target=finish_after_launcher_returns)
            worker.start()
            receipt = bridge.wait_for_fresh_receipt(
                receipt_path,
                before_mtime_ns=before,
                execution_nonce=expected_nonce,
                timeout_seconds=1,
                poll_interval_seconds=0.01,
            )
            worker.join()
            self.assertEqual(receipt["execution_nonce"], expected_nonce)

    def test_wait_for_receipt_rejects_stale_nonce(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            bridge.dump_json(receipt_path, {"execution_nonce": "0" * 32})
            with self.assertRaisesRegex(ValueError, "timed out.*not been refreshed"):
                bridge.wait_for_fresh_receipt(
                    receipt_path,
                    before_mtime_ns=receipt_path.stat().st_mtime_ns,
                    execution_nonce="1" * 32,
                    timeout_seconds=0.03,
                    poll_interval_seconds=0.005,
                )

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

    def test_folder_contract_can_anchor_a_nested_workspace_root(self):
        profile = {
            "workspace_parent": {"title": "Parent", "identifier": "PARENT-ID"},
            "folders": {
                "root": {"title": "Development", "identifier": "ROOT-ID"},
                "private": {"title": "Private", "identifier": None},
                "audit": {"title": "Audit", "identifier": None},
            },
        }
        folders = bridge.folder_specs(profile, "v-test", include_version=True)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["workspace_parent"]["parent_key"], None)
        self.assertEqual(by_key["workspace_parent"]["parent_policy"], "external-anchor")
        self.assertEqual(by_key["root"]["parent_key"], "workspace_parent")
        self.assertEqual(by_key["version"]["parent_key"], "root")
        self.assertEqual(by_key["private"]["parent_key"], "root")
        self.assertEqual(by_key["audit"]["parent_key"], "root")
        positions = {folder["key"]: index for index, folder in enumerate(folders)}
        self.assertLess(positions["workspace_parent"], positions["root"])
        self.assertLess(positions["root"], positions["version"])

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
            artifact.write_text(
                "# Brief\n\nTarget an editor field from the frozen source while preserving safety boundaries.\n",
                encoding="utf-8",
            )
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

    def test_phase_cannot_complete_without_evidence_and_empty_status_is_not_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            state = {
                "schema_version": 2,
                "phases": {phase: {"status": "pending"} for phase in bridge.RUN_PHASES},
                "artifacts": {},
            }
            bridge.dump_json(run / "run-state.json", state)
            with self.assertRaisesRegex(ValueError, "without evidence artifacts"):
                bridge.command_advance(
                    argparse.Namespace(workspace=run, phase="brief", artifact=[])
                )
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(bridge.command_status(argparse.Namespace(workspace=run)), 0)
            self.assertEqual(json.loads(output.getvalue())["artifact_integrity"], "NOT-STARTED")
            empty = run / "empty.md"
            empty.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty"):
                bridge.command_advance(
                    argparse.Namespace(workspace=run, phase="brief", artifact=[empty])
                )
            unrelated = run / "unrelated.md"
            unrelated.write_text("This repository file is intentionally unrelated to the requested phase.\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "recognizable phase evidence"):
                bridge.command_advance(
                    argparse.Namespace(workspace=run, phase="brief", artifact=[unrelated])
                )
            other_run = run / "other-production.json"
            other_run.write_text(
                json.dumps(
                    {
                        "plan_id": "other-v99-production",
                        "source_album_identifier": "OTHER-SOURCE",
                        "source_count": 1,
                        "source_identifier_sha256": "a" * 64,
                        "albums": [{"title": "Other"}],
                    }
                ),
                encoding="utf-8",
            )
            bound_state = {
                "version": "v-test",
                "source_album_identifier": "SOURCE",
                "expected_source_count": 20,
                "source_identifier_sha256": "b" * 64,
            }
            self.assertFalse(
                bridge.phase_evidence_matches("production_commit", [other_run], bound_state)
            )

    def test_write_plan_hash_and_verification_transition_are_not_self_attested(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            phases = {phase: {"status": "pending"} for phase in bridge.RUN_PHASES}
            state = {
                "version": "v-test",
                "source_album_identifier": "SOURCE",
                "expected_source_count": 1,
                "source_identifier_sha256": "a" * 64,
                "phases": phases,
                "release_binding": {
                    "proposal_id": "pfp-0123456789abcdef",
                    "master_sha256": "b" * 64,
                    "feedback_sha256": "c" * 64,
                    "config_sha256": "d" * 64,
                    "sample_sha256": "e" * 64,
                    "safety_sha256": "f" * 64,
                },
            }
            plan = {
                "plan_id": "v-test-production",
                "source_album_identifier": "SOURCE",
                "expected_source_count": 1,
                "source_identifier_sha256": "a" * 64,
                "evaluation": dict(state["release_binding"], passed=True),
                "validation": {
                    "status": "PASS",
                    "master_sha256": "b" * 64,
                    "safety_sha256": "f" * 64,
                },
                "albums": [{"title": "Master", "asset_identifiers": ["A/L0/001"]}],
            }
            plan["evaluation"].pop("safety_sha256")
            plan_path = run / "production-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            state["write_plan_sha256"] = {"production": bridge.file_sha256(plan_path)}
            self.assertTrue(
                bridge.plan_matches_release(
                    plan, state, "v-test-production", bridge.file_sha256(plan_path)
                )
            )
            plan["albums"][0]["asset_identifiers"] = ["HELD/L0/001"]
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            self.assertFalse(
                bridge.plan_matches_release(
                    plan, state, "v-test-production", bridge.file_sha256(plan_path)
                )
            )
            bridge.dump_json(run / "run-state.json", state)
            claimed = run / "claimed-verification.json"
            claimed.write_text('{"status":"PASS"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "verify-phase"):
                bridge.command_advance(
                    argparse.Namespace(
                        workspace=run,
                        phase="independent_verification",
                        artifact=[claimed],
                    )
                )

    def test_release_phases_require_passing_candidate_bound_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            master_sha = "a" * 64
            feedback_sha = "b" * 64
            safety_sha = "c" * 64
            config_sha = "e" * 64
            sample_sha = "f" * 64
            state = {
                "version": "v-test",
                "source_album_identifier": "SOURCE",
                "expected_source_count": 20,
                "source_identifier_sha256": "d" * 64,
                "safety_mode": "create-folders-albums-and-add-membership-only",
                "release_binding": {
                    "proposal_id": "pfp-0123456789abcdef",
                    "master_sha256": master_sha,
                    "feedback_sha256": feedback_sha,
                    "config_sha256": config_sha,
                    "sample_sha256": sample_sha,
                    "safety_sha256": safety_sha,
                },
            }
            failed_evaluation = run / "failed-evaluation.json"
            failed_evaluation.write_text(
                json.dumps(
                    {
                        "passed": False,
                        "proposal_id": "pfp-0123456789abcdef",
                        "master_sha256": master_sha,
                        "feedback_sha256": feedback_sha,
                        "config_sha256": config_sha,
                        "sample_sha256": sample_sha,
                    }
                ),
                encoding="utf-8",
            )
            failed_validation = run / "failed-validation.json"
            failed_validation.write_text(
                json.dumps(
                    {
                        "status": "FAIL",
                        "errors": ["safety failure"],
                        "master_sha256": master_sha,
                        "safety_sha256": safety_sha,
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(
                bridge.phase_evidence_matches("recursive_evaluation", [failed_evaluation], state)
            )
            self.assertFalse(
                bridge.phase_evidence_matches("validation", [failed_validation], state)
            )

            plan = {
                "plan_id": "v-test-production",
                "source_album_identifier": "SOURCE",
                "expected_source_count": 20,
                "source_identifier_sha256": "d" * 64,
                "safety_mode": "create-folders-albums-and-add-membership-only",
                "evaluation": {
                    "passed": True,
                    "proposal_id": "pfp-0123456789abcdef",
                    "master_sha256": master_sha,
                    "feedback_sha256": feedback_sha,
                    "config_sha256": config_sha,
                    "sample_sha256": sample_sha,
                },
                "validation": {
                    "status": "PASS",
                    "master_sha256": master_sha,
                    "safety_sha256": safety_sha,
                },
                "receipt_path": str(run / "production-receipt.json"),
                "folders": [{"key": "root", "title": "Root", "parent_key": None}],
                "albums": [
                    {
                        "title": "Master",
                        "parent_folder_key": "root",
                        "asset_identifiers": ["A/L0/001"],
                    }
                ],
            }
            plan_path = run / "production-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            plan_digest = bridge.file_sha256(plan_path)
            state["write_plan_sha256"] = {"production": plan_digest}
            state["helper_binding"] = {
                "app_binary_sha256": "1" * 64,
                "app_bundle_identifier": "org.example.synthetic",
            }
            state["launch_bindings"] = {
                "production_commit": {"execution_nonce": "1" * 32}
            }
            lifecycle_state = dict(state)
            lifecycle_state["phases"] = {
                phase: {
                    "status": "completed" if phase == "write_test_verification" else "pending"
                }
                for phase in bridge.RUN_PHASES
            }
            bridge.dump_json(run / "run-state.json", lifecycle_state)
            tampered = json.loads(json.dumps(plan))
            tampered["evaluation"]["sample_sha256"] = "0" * 64
            tampered_path = run / "tampered-production-plan.json"
            tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact validated release candidate"):
                bridge.command_run_plan(
                    argparse.Namespace(
                        workspace=run,
                        plan=tampered_path,
                        profile_data={"app_path": str(run / "Synthetic.app")},
                    )
                )
            receipt = {
                "completed_at": "2026-07-19T01:00:00+00:00",
                "execution_nonce": "1" * 32,
                "plan_id": "v-test-production",
                "source_album_identifier": "SOURCE",
                "source_count": 20,
                "source_identifier_sha256": "d" * 64,
                "safety_mode": "create-folders-albums-and-add-membership-only",
                "execution_fingerprint": {
                    "plan_sha256": bridge.file_sha256(plan_path),
                    "app_binary_sha256": "1" * 64,
                    "app_bundle_identifier": "org.example.synthetic",
                },
                "folders": [
                    {
                        "key": "root",
                        "title": "Root",
                        "identifier": "ROOTFOLDER-01/L0/040",
                        "parent_identifier": None,
                    }
                ],
                "albums": [
                    {
                        "title": "Master",
                        "identifier": "MASTERALBUM-01/L0/040",
                        "count": 1,
                        "parent_identifier": "ROOTFOLDER-01/L0/040",
                    }
                ],
            }
            receipt_path = run / "production-receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            self.assertFalse(
                bridge.phase_evidence_matches("production_commit", [receipt_path], state)
            )
            self.assertTrue(
                bridge.phase_evidence_matches(
                    "production_commit", [plan_path, receipt_path], state
                )
            )
            incomplete_receipt = dict(
                receipt,
                albums=[dict(receipt["albums"][0], count=2)],
            )
            incomplete_path = run / "production-receipt-incomplete.json"
            incomplete_path.write_text(json.dumps(incomplete_receipt), encoding="utf-8")
            self.assertFalse(
                bridge.phase_evidence_matches(
                    "production_commit", [plan_path, incomplete_path], state
                )
            )
            state["production_binding"] = {
                "plan_sha256": bridge.file_sha256(plan_path),
                "first_receipt_sha256": bridge.file_sha256(receipt_path),
                "first_completed_at": receipt["completed_at"],
                "first_execution_nonce": receipt["execution_nonce"],
            }
            self.assertFalse(
                bridge.phase_evidence_matches(
                    "production_rerun", [plan_path, receipt_path], state
                )
            )
            second_receipt = dict(
                receipt,
                completed_at="2026-07-19T01:01:00+00:00",
                execution_nonce="2" * 32,
            )
            state["launch_bindings"]["production_rerun"] = {
                "execution_nonce": "2" * 32
            }
            second_path = run / "production-receipt-second.json"
            second_path.write_text(json.dumps(second_receipt), encoding="utf-8")
            self.assertTrue(
                bridge.phase_evidence_matches(
                    "production_rerun", [plan_path, second_path], state
                )
            )
            state["production_binding"]["second_receipt_sha256"] = bridge.file_sha256(second_path)
            verification = run / "verification.json"
            verification.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "verification_kind": "wal-aware-live-snapshot",
                        "plan_id": "v-test-production",
                        "plan_sha256": bridge.file_sha256(plan_path),
                        "receipt_sha256": bridge.file_sha256(second_path),
                        "source_album_identifier": "SOURCE",
                        "source_count": 20,
                        "source_identifier_sha256": "d" * 64,
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(
                bridge.phase_evidence_matches(
                    "independent_verification", [verification], state
                )
            )
            with self.assertRaisesRegex(ValueError, "verify-phase"):
                bridge.command_advance(
                    argparse.Namespace(
                        workspace=run,
                        phase="independent_verification",
                        artifact=[verification],
                    )
                )

    def test_snapshot_plans_require_core_release_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "run"
            for name in ("manifests", "reports", "logs"):
                (workspace / name).mkdir(parents=True, exist_ok=True)
            config_path = root / "config.json"
            config_data = json.loads((ROOT / "config" / "starter.json").read_text(encoding="utf-8"))
            config_data["source"] = {
                "identifier": "SYNTHETIC-SOURCE",
                "expected_count": 30,
                "identifier_sha256": "a" * 64,
            }
            config_path.write_text(json.dumps(config_data), encoding="utf-8")
            inventory_path = root / "inventory.csv"
            create_demo_inventory(inventory_path)
            config = read_config(config_path)
            master, holds, _ = select(read_csv(inventory_path), config)
            master_path = workspace / "manifests" / "master.csv"
            holds_path = workspace / "manifests" / "holds.csv"
            feedback_path = workspace / "manifests" / "feedback.csv"
            write_csv(master_path, master)
            write_csv(holds_path, holds)
            feedback = make_sample(master, 3, 20260710)
            inspection_root = workspace / "previews" / "evaluation"
            inspection_root.mkdir(parents=True)
            for row in feedback:
                row["judgment"] = "fit"
                row["visible_reason"] = "Synthetic fit."
                artifact = inspection_root / f"{row['uuid']}.txt"
                artifact.write_text(
                    f"test-inspection:{row['uuid']}:{row['round_id']}\n", encoding="utf-8"
                )
                row["inspection_path"] = str(artifact)
                row["inspection_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
                row["inspection_round_id"] = row["round_id"]
                row["inspection_sample_sha256"] = row["sample_sha256"]
            write_csv(feedback_path, feedback)
            evaluation, _ = evaluate(feedback, config, master)
            errors, metrics = validate(master, holds, config)
            evaluation_path = workspace / "reports" / "evaluation.json"
            validation_path = workspace / "reports" / "validation.json"
            bridge.dump_json(evaluation_path, evaluation)
            bridge.dump_json(validation_path, dict(metrics, errors=errors))
            phases = {phase: {"status": "pending"} for phase in bridge.RUN_PHASES}
            phases["validation"] = {"status": "completed"}
            bridge.dump_json(
                workspace / "run-state.json",
                {
                    "version": "v-test",
                    "source_album_identifier": "SYNTHETIC-SOURCE",
                    "expected_source_count": 30,
                    "source_identifier_sha256": "a" * 64,
                    "phases": phases,
                    "release_binding": {
                        "proposal_id": evaluation["proposal_id"],
                        "master_sha256": evaluation["master_sha256"],
                        "feedback_sha256": evaluation["feedback_sha256"],
                        "config_sha256": evaluation["config_sha256"],
                        "sample_sha256": evaluation["sample_sha256"],
                        "safety_sha256": metrics["safety_sha256"],
                    },
                },
            )
            app_executable = root / "SyntheticHelper"
            app_executable.write_text("synthetic helper", encoding="utf-8")
            profile = {
                "photo_fieldwork_cli": str(ROOT / "bin" / "photo-fieldwork"),
                "app_executable": str(app_executable),
                "bundle_id": "org.example.synthetic",
                "default_source": {
                    "identifier": "SYNTHETIC-SOURCE",
                    "expected_count": 30,
                    "identifier_sha256": "a" * 64,
                },
                "folders": {
                    "root": {"title": "Root", "identifier": "ROOT-ID"},
                    "private": {"title": "Private", "identifier": "PRIVATE-ID"},
                    "audit": {"title": "Audit", "identifier": "AUDIT-ID"},
                },
            }
            args = argparse.Namespace(
                profile_data=profile,
                workspace=workspace,
                master=master_path,
                holds=holds_path,
                feedback=feedback_path,
                config=config_path,
                evaluation_report=evaluation_path,
                validation_report=validation_path,
                target=12,
                version="v-test",
                folder_title="Synthetic field",
                view_column="primary_view",
                source_id=None,
                source_count=None,
                source_sha256=None,
                batch_size=50,
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(bridge.command_snapshot_plans(args), 0)
            production = json.loads(
                (workspace / "manifests" / "v-test-production-plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(production["evaluation"]["feedback_sha256"], evaluation["feedback_sha256"])
            self.assertEqual(production["validation"]["safety_sha256"], metrics["safety_sha256"])
            bridge.dump_json(evaluation_path, dict(evaluation, sample_count=1))
            with self.assertRaisesRegex(ValueError, "exact passing release bundle"):
                bridge.command_snapshot_plans(args)

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
