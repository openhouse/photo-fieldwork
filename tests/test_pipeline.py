import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate, wilson_interval
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
            row["evaluation_note"] = "Visible evidence does not support this view."
        _, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        for row in sample:
            row["judgment"] = "fit"
            row["evaluation_note"] = "Visible evidence supports this view."
        _, passed = evaluate(sample, self.config)
        self.assertTrue(passed)

    def test_evaluation_names_decisive_precision_and_uncertainty(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["evaluation_note"] = "Visible evidence supports this view."
        sample[0]["judgment"] = "uncertain"
        report, _ = evaluate(sample, self.config)
        self.assertIn("decisive_precision", report)
        self.assertIn("uncertainty_rate", report)
        self.assertIn("population_weighted_fit_rate", report)
        self.assertEqual(len(report["decisive_precision_interval_95"]), 2)
        self.assertGreater(report["uncertainty_rate"], 0)
        self.assertEqual(report["by_view"][sample[0]["primary_view"]]["population"], 2)

    def test_wilson_interval_is_bounded_and_conservative(self):
        interval = wilson_interval(61, 62)
        self.assertGreater(interval[0], 0)
        self.assertLess(interval[0], 61 / 62)
        self.assertLessEqual(interval[1], 1)

    def test_review_required_and_unknown_safety_states_fail_closed(self):
        review = dict(self.inventory[0], uuid="REVIEW", safety_status="needs-review")
        unknown = dict(self.inventory[1], uuid="UNKNOWN", safety_state="surprise")
        config = dict(self.config, target_count=12)
        master, holds, _ = select(self.inventory + [review, unknown], config)
        held_ids = {row["uuid"] for row in holds}
        self.assertTrue({"REVIEW", "UNKNOWN"}.issubset(held_ids))
        self.assertFalse({"REVIEW", "UNKNOWN"} & {row["uuid"] for row in master})

    def test_validation_rejects_non_clear_master_state_even_without_hold_manifest(self):
        master, holds, _ = select(self.inventory, self.config)
        master[0]["safety_state"] = "review_required"
        errors, metrics = validate(master, holds, self.config)
        self.assertIn("master contains 1 non-clear safety states", errors)
        self.assertEqual(metrics["unsafe_master_count"], 1)

    def test_validation_enforces_invariants(self):
        master, holds, _ = select(self.inventory, self.config)
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")

    def test_catalog_plan_allows_only_membership_writes(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["evaluation_note"] = "Visible evidence supports this view."
        report, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", report)
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)
        self.assertFalse(plan["publication_clearance"])

    def test_catalog_plan_is_bound_to_passing_evaluation(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["evaluation_note"] = "Visible evidence supports this view."
        report, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", report)
        self.assertEqual(plan["master_sha256"], report["master_sha256"])
        bad = dict(report, master_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", bad)


if __name__ == "__main__":
    unittest.main()
