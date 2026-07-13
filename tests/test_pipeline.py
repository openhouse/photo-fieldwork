import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from photo_fieldwork.pipeline import (
    apply_feedback,
    build_catalog_plan,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    validate_feedback,
)
from photo_fieldwork.practice import create_demo_inventory


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

    def test_perceptual_clusters_are_reduced_before_quota_selection(self):
        baseline, _, _ = select(self.inventory, self.config)
        clustered_ids = {baseline[0]["uuid"], baseline[1]["uuid"]}
        inventory = deepcopy(self.inventory)
        for row in inventory:
            if row["uuid"] in clustered_ids:
                row["perceptual_cluster_id"] = "phash-fixture"
        master, _, _ = select(inventory, self.config)
        selected = {row["uuid"] for row in master}
        self.assertLess(len(selected & clustered_ids), 2)

    def test_sample_covers_every_selected_view(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        self.assertEqual(
            {row["primary_view"] for row in master},
            {row["primary_view"] for row in sample},
        )

    def test_sample_separates_fresh_rows_and_regression_canaries(self):
        master, _, _ = select(self.inventory, self.config)
        canary_id = master[0]["uuid"]
        excluded_id = master[1]["uuid"]
        sample = make_sample(master, 3, 20260710, {excluded_id}, {canary_id})
        by_id = {row["uuid"]: row for row in sample}
        self.assertNotIn(excluded_id, by_id)
        self.assertEqual(by_id[canary_id]["sample_kind"], "canary")

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

    def test_canary_regression_blocks_release(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710, canary_ids={master[0]["uuid"]})
        for row in sample:
            row["judgment"] = "fit"
        canary = next(row for row in sample if row["sample_kind"] == "canary")
        canary["judgment"] = "reject"
        report, passed = evaluate(sample, self.config)
        self.assertEqual(report["canary_failures"], [canary["uuid"]])
        self.assertFalse(passed)

    def test_material_view_failure_blocks_an_overall_pass(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
        material_view = next(
            view["id"]
            for view in self.config["views"]
            if view.get("evaluation_mode") == "material"
            and sum(row["primary_view"] == view["id"] for row in sample) >= 2
        )
        rejected = 0
        for row in sample:
            if row["primary_view"] == material_view and rejected < 2:
                row["judgment"] = "reject"
                rejected += 1
        report, passed = evaluate(sample, self.config)
        self.assertGreaterEqual(report["precision"], self.config["minimum_eval_precision"])
        self.assertEqual(len(report["precision_interval_95"]), 2)
        self.assertFalse(report["by_view"][material_view]["passed"])
        self.assertFalse(passed)

    def test_candidate_hypotheses_cannot_replace_an_assignment(self):
        baseline, _, _ = select(self.inventory, self.config)
        target_uuid = baseline[0]["uuid"]
        expected_view = baseline[0]["assigned_view"]
        inventory = deepcopy(self.inventory)
        target = next(row for row in inventory if row["uuid"] == target_uuid)
        target["candidate_views"] = "04;03" if expected_view not in {"04", "03"} else "01;02"
        master, _, _ = select(inventory, self.config)
        selected = {row["uuid"]: row for row in master}
        self.assertEqual(selected[target_uuid]["primary_view"], expected_view)

    def test_missing_assignment_fails_loudly(self):
        inventory = deepcopy(self.inventory)
        inventory[0]["assigned_view"] = ""
        with self.assertRaisesRegex(ValueError, "lacks assigned_view"):
            select(inventory, self.config)

    def test_validation_enforces_invariants(self):
        master, holds, _ = select(self.inventory, self.config)
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")

    def test_validation_rejects_a_divergent_output_alias(self):
        master, holds, _ = select(self.inventory, self.config)
        master[0]["primary_view"] = "04" if master[0]["assigned_view"] != "04" else "01"
        errors, _ = validate(master, holds, self.config)
        self.assertIn("primary_view must remain an exact output alias of assigned_view", errors)

    def test_catalog_plan_allows_only_membership_writes(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
        evaluation, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", evaluation)
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)
        self.assertEqual(plan["master_sha256"], evaluation["master_sha256"])

    def test_catalog_plan_rejects_post_evaluation_drift(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
        evaluation, _ = evaluate(sample, self.config)
        changed_view = "04" if master[0]["assigned_view"] != "04" else "01"
        master[0]["assigned_view"] = changed_view
        master[0]["primary_view"] = changed_view
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            build_catalog_plan(master, self.config, "drift", "Source", "SOURCE-1", evaluation)

    def test_feedback_schema_and_application_are_explicit(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        feedback = []
        for row in sample:
            feedback.append(
                {
                    "uuid": row["uuid"],
                    "proposal_id": row["proposal_id"],
                    "master_sha256": row["master_sha256"],
                    "judgment": "fit",
                    "evaluation_note": "fixture",
                }
            )
        report = validate_feedback(feedback)
        self.assertEqual(report["status"], "PASS")
        merged = apply_feedback(sample, feedback)
        self.assertTrue(all(row["judgment"] == "fit" for row in merged))


if __name__ == "__main__":
    unittest.main()
