import argparse
import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.pipeline import (
    build_catalog_plan,
    canonical_json_sha256,
    config_sha256,
    evaluate,
    evaluation_sample_sha256,
    make_sample,
    master_sha256,
    membership_sha256,
    read_config,
    read_csv,
    select,
    validate,
)
from photo_fieldwork.practice import create_demo_inventory
from photo_fieldwork.cli import command_evaluate
from photo_fieldwork.pipeline import write_csv


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.inventory_path = Path(self.temp.name) / "inventory.csv"
        create_demo_inventory(self.inventory_path)
        self.inventory = read_csv(self.inventory_path)
        self.config = read_config(ROOT / "config" / "starter.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_selection_is_deterministic_and_excludes_holds(self):
        first, holds, _ = select(self.inventory, self.config)
        second, _, _ = select(self.inventory, self.config)
        self.assertEqual([row["uuid"] for row in first], [row["uuid"] for row in second])
        self.assertEqual(len(first), 12)
        self.assertTrue({"DEMO-009", "DEMO-024"}.issubset({row["uuid"] for row in holds}))
        self.assertFalse({row["uuid"] for row in first} & {row["uuid"] for row in holds})

    def test_aesthetic_score_only_breaks_cluster_ties(self):
        master, _, _ = select(self.inventory, self.config)
        selected = {row["uuid"] for row in master}
        self.assertFalse({"DEMO-011", "DEMO-012"}.issubset(selected))

    def test_sample_covers_every_selected_view(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        self.assertEqual(
            {row["primary_view"] for row in master},
            {row["primary_view"] for row in sample},
        )

    def test_evaluation_can_fail_and_pass(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "reject"
        _, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        for row in sample:
            row["judgment"] = "fit"
        _, passed = evaluate(sample, self.config)
        self.assertTrue(passed)

    def test_cli_evaluation_binds_multirow_sample_to_master(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 1, 20260710)
        for row in sample:
            row["judgment"] = "fit"
        master_path = Path(self.temp.name) / "master.csv"
        feedback_path = Path(self.temp.name) / "feedback.csv"
        sample_manifest_path = Path(self.temp.name) / "eval-sample-manifest.json"
        output = Path(self.temp.name) / "reports"
        write_csv(master_path, master)
        write_csv(feedback_path, sample)
        sample_manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "master_sha256": master_sha256(master),
                    "per_view": 1,
                    "seed": 20260710,
                    "sample_count": len(sample),
                    "sample_sha256": evaluation_sample_sha256(sample),
                }
            )
        )

        code = command_evaluate(
            argparse.Namespace(
                config=ROOT / "config" / "starter.json",
                master=master_path,
                feedback=feedback_path,
                sample_manifest=sample_manifest_path,
                output=output,
            )
        )

        self.assertEqual(code, 0)
        report = json.loads((output / "evaluation-report.json").read_text())
        self.assertEqual(report["master_sha256"], master_sha256(master))

        foreign = [dict(row) for row in sample]
        foreign[0]["uuid"] = "NOT-IN-MASTER"
        write_csv(feedback_path, foreign)
        with self.assertRaisesRegex(ValueError, "outside the bound master"):
            command_evaluate(
                argparse.Namespace(
                    config=ROOT / "config" / "starter.json",
                    master=master_path,
                    feedback=feedback_path,
                    sample_manifest=sample_manifest_path,
                    output=output,
                )
            )

        write_csv(feedback_path, sample)
        mutated_master = [dict(row) for row in master]
        mutated_master[-1]["selection_reason"] += "; changed after sampling"
        write_csv(master_path, mutated_master)
        with self.assertRaisesRegex(ValueError, "does not bind the current master"):
            command_evaluate(
                argparse.Namespace(
                    config=ROOT / "config" / "starter.json",
                    master=master_path,
                    feedback=feedback_path,
                    sample_manifest=sample_manifest_path,
                    output=output,
                )
            )

    def test_validation_enforces_invariants(self):
        master, holds, _ = select(self.inventory, self.config)
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")

    def test_catalog_plan_allows_only_membership_writes(self):
        master, holds, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
        evaluation, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        evaluation.update(
            {
                "release_class": "editor-field",
                "master_sha256": master_sha256(master),
                "config_sha256": config_sha256(self.config),
                "evaluation_sample_sha256": "a" * 64,
            }
        )
        errors, validation = validate(
            master,
            holds,
            self.config,
            evaluation_report=evaluation,
        )
        validation["errors"] = errors
        plan = build_catalog_plan(
            master,
            holds,
            self.config,
            "practice",
            "Source",
            "SOURCE-1",
            len(self.inventory),
            membership_sha256(self.inventory),
            evaluation,
            validation,
        )
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["release_class"], "editor-field")
        self.assertFalse(plan["publication_clearance"])
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)
        unsigned = {key: value for key, value in plan.items() if key != "plan_sha256"}
        self.assertEqual(plan["plan_sha256"], canonical_json_sha256(unsigned))

        mutated_master = [dict(row) for row in master]
        mutated_master[0]["primary_view"] = "MUTATED"
        with self.assertRaisesRegex(ValueError, "evaluation report does not match"):
            build_catalog_plan(
                mutated_master,
                holds,
                self.config,
                "practice-mutated",
                "Source",
                "SOURCE-1",
                len(self.inventory),
                membership_sha256(self.inventory),
                evaluation,
                validation,
            )

        held_master = [dict(row) for row in master]
        held_master[0]["safety_status"] = "hold"
        with self.assertRaisesRegex(ValueError, "evaluation report does not match"):
            build_catalog_plan(
                held_master,
                holds,
                self.config,
                "practice-held",
                "Source",
                "SOURCE-1",
                len(self.inventory),
                membership_sha256(self.inventory),
                evaluation,
                validation,
            )


if __name__ == "__main__":
    unittest.main()
