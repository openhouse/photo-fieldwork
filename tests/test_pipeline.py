import tempfile
import unittest
import json
import os
from collections import Counter
from copy import deepcopy
from pathlib import Path

from photo_fieldwork.pipeline import (
    build_catalog_plan,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    write_csv,
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
        self.assertTrue(all(row["assigned_view"] == row["primary_view"] for row in first))
        self.assertEqual(
            Counter(row["primary_view"] for row in first),
            Counter({view["id"]: view["quota"] for view in self.config["views"]}),
        )

    def test_config_reports_missing_contract_fields(self):
        path = Path(self.temp.name) / "bad-config.json"
        path.write_text(json.dumps({"views": []}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            read_config(path)

    def test_private_csv_writer_enforces_directory_and_file_modes(self):
        path = Path(self.temp.name) / "private" / "manifest.csv"
        write_csv(path, [{"uuid": "A", "filename": "a.jpg"}])
        self.assertEqual(os.stat(path.parent).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_aesthetic_score_only_breaks_cluster_ties(self):
        master, _, _ = select(self.inventory, self.config)
        selected = {row["uuid"] for row in master}
        self.assertFalse({"DEMO-011", "DEMO-012"}.issubset(selected))

    def test_human_needs_review_is_excluded_before_ranking(self):
        inventory = deepcopy(self.inventory)
        inventory[0]["safety_status"] = "human-needs-review"
        master, holds, _ = select(inventory, self.config)
        self.assertNotIn(inventory[0]["uuid"], {row["uuid"] for row in master})
        self.assertIn(inventory[0]["uuid"], {row["uuid"] for row in holds})

    def test_incomplete_explicit_assignments_cannot_drift_quotas(self):
        inventory = deepcopy(self.inventory)
        for row in inventory:
            row["assigned_view"] = "00"
            row["assignment_status"] = "assigned"
        with self.assertRaisesRegex(ValueError, "view counts do not match"):
            select(inventory, self.config)

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
            row["visible_reason"] = "Synthetic rejection."
        _, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        _, passed = evaluate(sample, self.config)
        self.assertTrue(passed)

    def test_evaluation_fails_a_weak_view_even_when_global_precision_passes(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        weak_view = sample[0]["primary_view"]
        for row in sample:
            if row["primary_view"] == weak_view:
                row["judgment"] = "reject"
                row["visible_reason"] = "Synthetic weak-view rejection."
        report, passed = evaluate(sample, self.config)
        self.assertGreaterEqual(report["precision"], self.config["minimum_eval_precision"])
        self.assertFalse(report["by_view"][weak_view]["passed"])
        self.assertFalse(passed)
        self.assertIsNotNone(report["by_view"][weak_view]["wilson_95_low"])

    def test_evaluation_requires_a_visible_reason_for_every_judgment(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        sample[0]["visible_reason"] = ""
        report, passed = evaluate(sample, self.config)
        self.assertEqual(report["missing_visible_reason_count"], 1)
        self.assertFalse(passed)

    def test_sparse_hypothesis_view_does_not_require_precision(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        sparse_view = sample[0]["primary_view"]
        config = deepcopy(self.config)
        for view in config["views"]:
            if view["id"] == sparse_view:
                view["evaluation_mode"] = "sparse-hypothesis"
        for row in sample:
            row["judgment"] = "reject" if row["primary_view"] == sparse_view else "fit"
            row["visible_reason"] = "Synthetic sparse-view judgment."
        report, passed = evaluate(sample, config)
        self.assertTrue(report["by_view"][sparse_view]["passed"])
        self.assertTrue(passed)

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
            row["visible_reason"] = "Synthetic fit."
        evaluation, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", evaluation)
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)

    def test_catalog_plan_rejects_evaluation_for_another_proposal(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        evaluation, _ = evaluate(sample, self.config)
        evaluation["master_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "evaluated master hash"):
            build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", evaluation)


if __name__ == "__main__":
    unittest.main()
