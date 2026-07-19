import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate
from photo_fieldwork.practice import create_demo_inventory
from photo_fieldwork.evaluation_split import audit_evaluation_splits
from photo_fieldwork.release import build_source_manifest, validate_plan


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
            row["visible_reason"] = "Visible synthetic practice evidence"
            row["reviewer_actor"] = "test-editor"
        source = build_source_manifest(
            self.inventory,
            source_adapter="synthetic",
            source_identifier="SOURCE-1",
            predicate_version="test-v1",
        )
        evaluation, passed = evaluate(sample, self.config, master, source, "final-holdout")
        self.assertTrue(passed)
        errors, validation = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        split_audit = audit_evaluation_splits([], sample, [])
        plan = build_catalog_plan(
            master,
            self.config,
            "practice",
            source,
            self.inventory,
            sample,
            [],
            evaluation,
            validation,
            split_audit,
            holds,
        )
        validate_plan(plan)
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_identifiers"]), 12)
        self.assertFalse(plan["release_candidate"]["publication_clearance"])


if __name__ == "__main__":
    unittest.main()
