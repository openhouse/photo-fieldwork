import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.cli import command_evaluate, command_sample
from photo_fieldwork.pipeline import (
    build_catalog_plan,
    config_sha256,
    evaluate,
    master_sha256,
    membership_sha256,
    read_csv,
    select,
    validate,
    write_csv,
)
from photo_fieldwork.rounds import apply_feedback
from photo_fieldwork.run_state import initialize, read_run_events, reconcile, recover


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "curate-apple-photos"
EVALS = SKILL / "evals" / "evals.json"
BRIDGE_SPEC = importlib.util.spec_from_file_location(
    "eval_photo_archive_bridge",
    SKILL / "scripts" / "photo_archive_bridge.py",
)
BRIDGE = importlib.util.module_from_spec(BRIDGE_SPEC)
BRIDGE_SPEC.loader.exec_module(BRIDGE)


class SkillEvalBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = json.loads(EVALS.read_text(encoding="utf-8"))

    def test_eval_bank_has_stable_unique_cases(self):
        self.assertEqual(self.bank["skill_name"], "curate-apple-photos")
        evals = self.bank["evals"]
        self.assertGreaterEqual(len(evals), 8)
        self.assertLessEqual(len(evals), 12)
        self.assertEqual(len({case["id"] for case in evals}), len(evals))
        self.assertEqual(len({case["name"] for case in evals}), len(evals))
        for case in evals:
            self.assertIsInstance(case["id"], int)
            self.assertTrue(case["prompt"].strip())
            self.assertTrue(case["expected_output"].strip())
            self.assertGreaterEqual(len(case["expectations"]), 4)
            self.assertEqual(len(case["tags"]), len(set(case["tags"])))

    def test_eval_files_are_repo_local_and_present(self):
        for case in self.bank["evals"]:
            for relative in case["files"]:
                path = Path(relative)
                self.assertFalse(path.is_absolute())
                self.assertNotIn("..", path.parts)
                fixture = SKILL / path
                self.assertTrue(fixture.is_file(), f"missing eval fixture: {relative}")
                self.assertIn(fixture.suffix, {".csv", ".json", ".py"})
                if fixture.suffix == ".json":
                    json.loads(fixture.read_text(encoding="utf-8"))

    def test_eval_bank_covers_release_boundaries(self):
        tags = {tag for case in self.bank["evals"] for tag in case["tags"]}
        required = {
            "source-integrity",
            "safety",
            "evaluation",
            "verification",
            "resumability",
            "publication",
            "privacy",
            "human-gate",
        }
        self.assertEqual(required - tags, set())
        self.assertIn("positive-path", tags)

    def test_fixtures_are_synthetic_and_public_safe(self):
        fixtures = (SKILL / "evals" / "files").glob("*")
        forbidden = ("/Users/", "/Volumes/", "Library/Photos", "@gmail.com")
        for path in fixtures:
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden:
                self.assertNotIn(fragment, text, f"private locator in {path.name}")

    def test_positive_path_fake_adapter_proves_order_and_idempotence(self):
        scenario = SKILL / "evals" / "files" / "safe-happy-path.json"
        adapter = SKILL / "evals" / "files" / "fake_catalog_adapter.py"
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for operation in (
                "ten-item-test",
                "production",
                "production-idempotence-rerun",
                "verify",
            ):
                subprocess.run(
                    [
                        sys.executable,
                        str(adapter),
                        "--scenario",
                        str(scenario),
                        "--workspace",
                        str(workspace),
                        "--operation",
                        operation,
                    ],
                    check=True,
                )
            trace = json.loads((workspace / "invocation-trace.json").read_text())
            self.assertEqual([item["operation"] for item in trace], [
                "ten-item-test",
                "production",
                "production-idempotence-rerun",
                "verify",
            ])
            self.assertFalse(trace[2]["changed"])
            verification = json.loads((workspace / "verification.json").read_text())
            self.assertEqual(verification["status"], "PASS")

    def test_composite_eval_executes_assignment_lineage_and_cas(self):
        scenario = json.loads(
            (SKILL / "evals" / "files" / "composite-release-scenario.json").read_text()
        )
        assignment = scenario["assignment"]
        master, _, summary = select(assignment["inventory"], assignment["config"])
        self.assertEqual(
            {row["uuid"]: row["primary_view"] for row in master},
            assignment["expected_assignments"],
        )
        self.assertEqual(summary["assignment_capacity"]["status"], "PASS")
        floor = scenario["diversity_floor"]
        floor_master, _, _ = select(floor["inventory"], floor["config"])
        self.assertEqual(
            sorted(row["uuid"] for row in floor_master),
            sorted(floor["score_preserving_result"]),
        )

        feedback = scenario["feedback"]
        updated, _ = apply_feedback(
            feedback["master"],
            feedback["inventory"],
            feedback["current_feedback"],
            prior_feedback=feedback["prior_feedback"],
            round_id="composite-round",
        )
        self.assertEqual([row["uuid"] for row in updated], feedback["expected_master"])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "run"
            state = initialize(
                workspace,
                run_id="eval-composite",
                version="v01",
                target_count=2,
                source_identifier="SYNTHETIC",
                expected_source_count=2,
            )
            self.assertEqual(state["revision"], scenario["transaction"]["initial_revision"])
            state = reconcile(workspace, expected_revision=state["revision"])
            self.assertEqual(
                state["revision"], scenario["transaction"]["first_reconcile_revision"]
            )
            with self.assertRaisesRegex(ValueError, scenario["transaction"]["expected_result"]):
                reconcile(
                    workspace,
                    expected_revision=scenario["transaction"]["stale_expected_revision"],
                )

            (workspace / "brief.md").write_text("approved\n")
            (workspace / "retrieval.json").write_text("{}\n")
            (workspace / "config.json").write_text("{}\n")
            state = reconcile(workspace, expected_revision=state["revision"])
            (workspace / "brief.md").write_text("mutated\n")
            state = reconcile(workspace, expected_revision=state["revision"])
            self.assertEqual(state["phases"]["brief"]["status"], "blocked")
            state = reconcile(workspace, expected_revision=state["revision"])
            self.assertEqual(state["phases"]["brief"]["status"], "blocked")
            (workspace / "run-state.json").write_text("{}\n")
            recovered = recover(workspace)
            self.assertEqual(recovered["revision"], read_run_events(workspace)[-1]["revision"])

            mutations = set(scenario["release_mutation"]["mutations"])
            self.assertIn("supersede-completed-phase-without-explicit-cas-update", mutations)
            phase_workspace = root / "phase-update-run"
            phase_state = initialize(
                phase_workspace,
                run_id="eval-phase-update",
                version="v01",
                target_count=2,
                source_identifier="SYNTHETIC",
                expected_source_count=2,
            )
            first_eval = phase_workspace / "reports" / "round-1" / "evaluation-report.json"
            first_eval.parent.mkdir()
            first_eval.write_text(json.dumps({"passed": True, "round": 1}))
            phase_state = reconcile(
                phase_workspace,
                expected_revision=phase_state["revision"],
            )
            second_eval = phase_workspace / "reports" / "round-2" / "evaluation-report.json"
            second_eval.parent.mkdir()
            second_eval.write_text(json.dumps({"passed": True, "round": 2}))
            phase_state = reconcile(
                phase_workspace,
                expected_revision=phase_state["revision"],
            )
            self.assertEqual(
                phase_state["phases"]["recursive_evaluation"]["status"],
                "blocked",
            )

            holds = [{"uuid": "HOLD", "filename": "hold.jpg", "safety_status": "hold"}]
            source = [*assignment["inventory"], *holds]
            review_rows = [dict(row, judgment="fit") for row in master]
            evaluation, passed = evaluate(review_rows, assignment["config"])
            self.assertTrue(passed)
            evaluation.update(
                {
                    "release_class": "editor-field",
                    "master_sha256": master_sha256(master),
                    "config_sha256": config_sha256(assignment["config"]),
                    "evaluation_sample_sha256": "a" * 64,
                }
            )
            errors, validation = validate(
                master,
                holds,
                assignment["config"],
                evaluation_report=evaluation,
            )
            validation["errors"] = errors
            release = build_catalog_plan(
                master,
                holds,
                assignment["config"],
                "composite-release",
                "Synthetic source",
                "SYNTHETIC",
                len(source),
                membership_sha256(source),
                evaluation,
                validation,
            )
            self.assertFalse(release["publication_clearance"])
            paths = {
                "master": root / "master.csv",
                "holds": root / "holds.csv",
                "source_membership": root / "source.csv",
                "config": root / "release-config.json",
                "evaluation_report": root / "evaluation.json",
                "validation_report": root / "validation.json",
                "release_plan": root / "release.json",
            }
            write_csv(paths["master"], master)
            write_csv(paths["holds"], holds)
            write_csv(paths["source_membership"], source)
            paths["config"].write_text(json.dumps(assignment["config"]))
            paths["evaluation_report"].write_text(json.dumps(evaluation))
            paths["validation_report"].write_text(json.dumps(validation))
            paths["release_plan"].write_text(json.dumps(release))

            eval_master = [
                *master,
                dict(master[0], uuid="A-UNSAMPLED", filename="a-unsampled.jpg"),
            ]
            eval_master_path = root / "eval-master.csv"
            eval_feedback_path = root / "eval-feedback.csv"
            eval_manifest_path = root / "eval-sample-manifest.json"
            write_csv(eval_master_path, eval_master)
            command_sample(
                argparse.Namespace(
                    master=eval_master_path,
                    output=eval_feedback_path,
                    manifest=eval_manifest_path,
                    per_view=1,
                    seed=7,
                )
            )
            eval_feedback = read_csv(eval_feedback_path)
            for row in eval_feedback:
                row["judgment"] = "fit"
            write_csv(eval_feedback_path, eval_feedback)
            eval_output = root / "sample-eval-report"
            self.assertEqual(
                command_evaluate(
                    argparse.Namespace(
                        config=paths["config"],
                        master=eval_master_path,
                        feedback=eval_feedback_path,
                        sample_manifest=eval_manifest_path,
                        output=eval_output,
                    )
                ),
                0,
            )
            sampled_ids = {row["uuid"] for row in eval_feedback}
            mutated_eval_master = [dict(row) for row in eval_master]
            nonsampled = next(row for row in mutated_eval_master if row["uuid"] not in sampled_ids)
            nonsampled["selection_reason"] += "; changed after sampling"
            write_csv(eval_master_path, mutated_eval_master)
            with self.assertRaisesRegex(
                ValueError,
                scenario["evaluation_binding"]["expected_result"],
            ):
                command_evaluate(
                    argparse.Namespace(
                        config=paths["config"],
                        master=eval_master_path,
                        feedback=eval_feedback_path,
                        sample_manifest=eval_manifest_path,
                        output=eval_output,
                    )
                )
            args = argparse.Namespace(
                source_id="SYNTHETIC",
                source_count=len(source),
                source_profile=None,
                **paths,
            )
            BRIDGE.release_authorization(args, master, holds)
            writer_invocations = []

            def attempt_writer() -> None:
                BRIDGE.release_authorization(
                    args,
                    read_csv(paths["master"]),
                    read_csv(paths["holds"]),
                )
                writer_invocations.append("writer")

            self.assertIn("change-master-view-assignment-after-evaluation", mutations)
            write_csv(paths["master"], [dict(master[0], primary_view="MUTATED"), *master[1:]])
            with self.assertRaises(ValueError):
                attempt_writer()
            write_csv(paths["master"], master)

            self.assertIn("change-frozen-source-membership", mutations)
            write_csv(paths["source_membership"], [*source[:-1], {"uuid": "X", "filename": "x.jpg"}])
            with self.assertRaises(ValueError):
                attempt_writer()
            write_csv(paths["source_membership"], source)

            self.assertIn("change-evaluation-report", mutations)
            paths["evaluation_report"].write_text(json.dumps(dict(evaluation, passed=False)))
            with self.assertRaises(ValueError):
                attempt_writer()
            paths["evaluation_report"].write_text(json.dumps(evaluation))

            self.assertIn("change-validation-report", mutations)
            paths["validation_report"].write_text(json.dumps(dict(validation, status="FAIL")))
            with self.assertRaises(ValueError):
                attempt_writer()
            paths["validation_report"].write_text(json.dumps(validation))

            self.assertIn("change-sealed-writer-plan", mutations)
            paths["release_plan"].write_text(json.dumps(dict(release, expected_master_count=999)))
            with self.assertRaises(ValueError):
                attempt_writer()
            paths["release_plan"].write_text(json.dumps(release))

            self.assertIn("self-rehash-writer-plan-with-outside-asset", mutations)
            authorization = BRIDGE.release_authorization(args, master, holds)
            forged_writer_plan = {
                "operation": "snapshot-membership",
                "schema_version": 1,
                "plan_id": "forged-production",
                "safety_mode": "create-folders-albums-and-add-membership-only",
                "source_album_identifier": "SYNTHETIC",
                "expected_source_count": len(source),
                "batch_size": 1,
                "log_path": str(root / "writer.log"),
                "receipt_path": str(root / "writer-receipt.json"),
                "folders": [],
                "albums": [
                    {
                        "title": "FORGED",
                        "parent_folder_key": "version",
                        "existing_identifier": None,
                        "asset_identifiers": ["OUTSIDE/L0/001"],
                    }
                ],
                "manifest_hashes": {
                    "master_sha256": BRIDGE.file_hash(paths["master"]),
                    "holds_sha256": BRIDGE.file_hash(paths["holds"]),
                    "config_sha256": BRIDGE.file_hash(paths["config"]),
                },
                "authorization": authorization,
            }
            forged_writer_plan["plan_sha256"] = BRIDGE.canonical_json_sha256(
                forged_writer_plan
            )
            forged_path = root / "forged-writer-plan.json"
            forged_path.write_text(json.dumps(forged_writer_plan))
            with self.assertRaisesRegex(ValueError, "outside the authorized master/HOLD set"):
                BRIDGE.command_run_plan(argparse.Namespace(plan=forged_path, **vars(args)))

            self.assertEqual(
                len(writer_invocations),
                scenario["release_mutation"]["expected_writer_invocations"],
            )

    def test_hash_fixtures_are_computable_and_discriminating(self):
        files = SKILL / "evals" / "files"
        happy = json.loads((files / "safe-happy-path.json").read_text())
        membership = "".join(f"{uuid}\n" for uuid in happy["source"]["observed_members"])
        self.assertEqual(
            hashlib.sha256(membership.encode()).hexdigest(),
            happy["source"]["frozen_membership_sha256"],
        )

        verification = json.loads((files / "verification-scenario.json").read_text())
        approved = verification["approved_plan"]
        for file_key, hash_key in (
            ("master_file", "master_sha256"),
            ("holds_file", "holds_sha256"),
            ("config_file", "config_sha256"),
        ):
            payload = (files / approved[file_key]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), approved[hash_key])
        current = (files / verification["current_master_file"]).read_bytes()
        self.assertNotEqual(hashlib.sha256(current).hexdigest(), approved["master_sha256"])

        resume = json.loads((files / "resume-scenario.json").read_text())
        for phase in ("brief", "retrieval"):
            artifact = resume["phases"][phase]
            payload = (files / artifact["artifact"]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), artifact["recorded_sha256"])
        inspected = {
            uuid
            for attempt in resume["phases"]["local_inspection"]["attempts"]
            for uuid in attempt["completed_ids"]
        }
        self.assertEqual(inspected, set("ABCDEFGH"))

        holdout = json.loads((files / "holdout-scenario.json").read_text())
        current_sample = "".join(f"{uuid}\n" for uuid in holdout["final_sample_ids"])
        self.assertEqual(holdout["sample_hash_serialization"], "utf8-lines-final-lf")
        self.assertNotEqual(
            hashlib.sha256(current_sample.encode()).hexdigest(),
            holdout["recorded_sample_sha256"],
        )

        source_rows = (files / verification["snapshot_receipt"]["source_membership_file"]).read_text().splitlines()[1:]
        source_payload = (files / verification["snapshot_receipt"]["source_membership_file"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(source_payload).hexdigest(),
            verification["snapshot_receipt"]["source_membership_sha256"],
        )
        prior_payload = (files / verification["protected_digests"]["prior_versions_file"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(prior_payload).hexdigest(),
            verification["protected_digests"]["prior_versions_before"],
        )
        current_rows = (files / verification["current_master_file"]).read_text().splitlines()[1:]
        approved_rows = (files / approved["master_file"]).read_text().splitlines()[1:]
        self.assertEqual(set(approved_rows) - set(current_rows), {"D"})
        self.assertEqual(set(current_rows) - set(approved_rows), {"X"})
        self.assertEqual(set(current_rows) - set(source_rows), {"X"})


if __name__ == "__main__":
    unittest.main()
