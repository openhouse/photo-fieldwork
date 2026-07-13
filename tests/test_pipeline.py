import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from photo_fieldwork.pipeline import (
    assign_exact_quotas,
    build_catalog_plan,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
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
            row["visible_reason"] = "Visible synthetic mismatch"
            row["error_category"] = "retrieval-mismatch"
            row["round_id"] = "round-01"
            row["reviewer_lens"] = "test"
        report, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        self.assertEqual(report["decisive_precision"], 0.0)
        for row in sample:
            row["judgment"] = "fit"
            row["error_category"] = "visible-fit"
        report, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        self.assertEqual(report["fit_rate"], 1.0)
        self.assertEqual(report["uncertainty_rate"], 0.0)

    def test_validation_enforces_invariants(self):
        master, holds, _ = select(self.inventory, self.config)
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")

    def test_catalog_plan_allows_only_membership_writes(self):
        master, _, _ = select(self.inventory, self.config)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1")
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(plan["albums"][0]["role"], "editor-master")
        self.assertEqual(plan["albums"][0]["visibility"], "private-editor")
        self.assertEqual(len(plan["albums"][0]["asset_identifiers"]), 12)

    def test_assignment_meets_exact_quotas_with_overlapping_views(self):
        config = {
            "seed": 1,
            "target_count": 2,
            "unclassified_view": "A",
            "views": [
                {"id": "A", "label": "A", "quota": 1},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        rows = [
            {"uuid": "one", "filename": "one.jpg", "candidate_views": "B;A"},
            {"uuid": "two", "filename": "two.jpg", "candidate_views": "A"},
        ]
        selected, counts = assign_exact_quotas(rows, config)
        self.assertEqual(counts, {"A": 1, "B": 1})
        self.assertEqual({row["uuid"]: row["primary_view"] for row in selected}, {"one": "B", "two": "A"})

        reordered = deepcopy(rows)
        reordered[0]["candidate_views"] = "A;B"
        selected_again, _ = assign_exact_quotas(reordered, config)
        self.assertEqual(
            {row["uuid"]: row["primary_view"] for row in selected_again},
            {row["uuid"]: row["primary_view"] for row in selected},
        )

    def test_assignment_reports_per_view_capacity_shortfall(self):
        config = {
            "seed": 1,
            "target_count": 2,
            "unclassified_view": "A",
            "views": [
                {"id": "A", "label": "A", "quota": 1},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        rows = [
            {"uuid": "one", "filename": "one.jpg", "candidate_views": "A"},
            {"uuid": "two", "filename": "two.jpg", "candidate_views": "A"},
        ]
        with self.assertRaisesRegex(ValueError, r"B: short 1, candidates 0, quota 1"):
            assign_exact_quotas(rows, config)

    def test_validation_checks_exact_view_counts(self):
        master, holds, _ = select(self.inventory, self.config)
        master[0]["primary_view"] = master[-1]["primary_view"]
        errors, metrics = validate(master, holds, self.config)
        self.assertTrue(any("view quotas differ" in error for error in errors))
        self.assertTrue(metrics["quota_errors"])

    def test_high_decisive_precision_does_not_hide_uncertainty(self):
        config = deepcopy(self.config)
        config["maximum_eval_uncertainty"] = 0.2
        config["minimum_decisive_per_view"] = 0
        config["minimum_view_precision"] = 0
        master, _, _ = select(self.inventory, config)
        sample = make_sample(master, 3, 20260710)
        for index, row in enumerate(sample):
            row["judgment"] = "fit" if index < 2 else "uncertain"
            row["visible_reason"] = "Visible but context remains unresolved"
            row["error_category"] = "visible-fit" if index < 2 else "taxonomy-coercion"
            row["round_id"] = "round-uncertain"
            row["reviewer_lens"] = "test"
        report, passed = evaluate(sample, config)
        self.assertEqual(report["decisive_precision"], 1.0)
        self.assertGreater(report["uncertainty_rate"], 0.2)
        self.assertFalse(passed)
        self.assertIn("overall uncertainty rate above maximum", report["gate_failures"])

    def test_sample_carries_a_stable_manifest_hash(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        self.assertEqual(len({row["sample_hash"] for row in sample}), 1)
        reordered = list(reversed(master))
        self.assertEqual(
            {row["sample_hash"] for row in sample},
            {row["sample_hash"] for row in make_sample(reordered, 3, 20260710)},
        )


if __name__ == "__main__":
    unittest.main()
