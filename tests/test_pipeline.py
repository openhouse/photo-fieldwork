import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.artifacts import object_digest
from photo_fieldwork.pipeline import build_catalog_plan, evaluate, is_hold, make_sample, read_config, read_csv, select, validate
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
        _, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        for row in sample:
            row["judgment"] = "fit"
        _, passed = evaluate(sample, self.config)
        self.assertTrue(passed)

    def test_evaluation_enforces_per_view_and_uncertainty_gates(self):
        feedback = [
            {"uuid": "A", "primary_view": "01", "judgment": "fit"},
            {"uuid": "B", "primary_view": "01", "judgment": "fit"},
            {"uuid": "C", "primary_view": "02", "judgment": "reject"},
            {"uuid": "D", "primary_view": "02", "judgment": "reject"},
        ]
        config = {
            "minimum_eval_coverage": 1.0,
            "minimum_eval_precision": 0.4,
            "minimum_view_precision": 0.65,
            "minimum_decisive_samples_per_view": 2,
            "maximum_uncertain_fraction": 0.2,
        }
        report, passed = evaluate(feedback, config)
        self.assertFalse(passed)
        self.assertEqual(report["view_failures"][0]["view"], "02")
        feedback[2]["judgment"] = "fit"
        feedback[3]["judgment"] = "uncertain"
        report, passed = evaluate(feedback, {**config, "minimum_decisive_samples_per_view": 1})
        self.assertFalse(passed)
        self.assertGreater(report["uncertainty_rate"], config["maximum_uncertain_fraction"])

    def test_evaluation_fails_unsampled_configured_view(self):
        feedback = [
            {"uuid": "A", "primary_view": "01", "judgment": "fit"},
            {"uuid": "B", "primary_view": "01", "judgment": "fit"},
        ]
        config = {
            "views": [
                {"id": "01", "quota": 1},
                {"id": "02", "quota": 1},
            ],
            "minimum_eval_coverage": 1.0,
            "minimum_eval_precision": 0.5,
            "minimum_view_precision": 0.5,
            "minimum_decisive_samples_per_view": 1,
            "maximum_uncertain_fraction": 0.5,
        }
        report, passed = evaluate(feedback, config)
        self.assertFalse(passed)
        self.assertIn("02", report["by_view"])
        self.assertIn("no sampled rows", report["view_failures"][0]["reasons"])

    def test_evaluation_rejects_duplicate_sample_uuid(self):
        feedback = [
            {"uuid": "A", "primary_view": "01", "judgment": "fit"},
            {"uuid": "A", "primary_view": "01", "judgment": "fit"},
        ]
        with self.assertRaisesRegex(ValueError, "duplicate UUIDs"):
            evaluate(feedback, self.config)

    def test_provenance_aware_safety_states_block_selection(self):
        self.assertTrue(is_hold({"safety_status": "auto-hold"}))
        self.assertTrue(is_hold({"safety_status": "needs-human-review"}))
        self.assertTrue(is_hold({"safety_status": "human-added-hold"}))
        self.assertFalse(is_hold({"safety_status": "cleared-false-positive"}))

    def test_validation_enforces_invariants(self):
        master, holds, _ = select(self.inventory, self.config)
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")

    def test_validation_enforces_exact_view_quotas(self):
        master, holds, _ = select(self.inventory, self.config)
        master[0]["primary_view"] = master[-1]["primary_view"]
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(metrics["status"], "FAIL")
        self.assertTrue(any("view quota mismatch" in error for error in errors))

    def test_catalog_plan_allows_only_membership_writes(self):
        master, _, _ = select(self.inventory, self.config)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1")
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)
        self.assertEqual(plan["plan_sha256"], object_digest(plan, {"plan_sha256"}))


if __name__ == "__main__":
    unittest.main()
