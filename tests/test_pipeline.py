import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.integrity import membership_sha256, verify_plan_digest
from photo_fieldwork.pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate
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
        self.assertEqual(
            {view["id"]: view["quota"] for view in self.config["views"]},
            {view: sum(row["primary_view"] == view for row in first) for view in {item["primary_view"] for item in first}},
        )

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
        master, _, _ = select(self.inventory, self.config)
        source = [row["uuid"] for row in self.inventory]
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", source)
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["source"]["membership_sha256"], membership_sha256(source))
        verify_plan_digest(plan)
        plan["plan_id"] = "tampered"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_plan_digest(plan)

    def test_equal_count_source_substitution_changes_digest(self):
        self.assertNotEqual(
            membership_sha256(["A", "B", "C"]),
            membership_sha256(["A", "B", "D"]),
        )

    def test_catalog_plan_rejects_master_outside_frozen_source(self):
        master, _, _ = select(self.inventory, self.config)
        with self.assertRaisesRegex(ValueError, "outside frozen source"):
            build_catalog_plan(
                master,
                self.config,
                "practice",
                "Source",
                "SOURCE-1",
                ["NOT-IN-MASTER"],
            )

    def test_capacity_flow_resolves_overlapping_quotas(self):
        config = {
            "seed": 1,
            "target_count": 3,
            "unclassified_view": "00",
            "allow_unclassified_fallback": False,
            "views": [
                {"id": "00", "label": "Unclassified", "quota": 0},
                {"id": "A", "label": "A", "quota": 2},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        inventory = [
            {"uuid": "AB-1", "filename": "1.jpg", "candidate_views": "A;B", "safety_status": "clear"},
            {"uuid": "A-1", "filename": "2.jpg", "candidate_views": "A", "safety_status": "clear"},
            {"uuid": "A-2", "filename": "3.jpg", "candidate_views": "A", "safety_status": "clear"},
        ]
        master, _, summary = select(inventory, config)
        self.assertEqual(summary["allocation"], "deterministic capacity flow")
        self.assertEqual(sum(row["primary_view"] == "B" for row in master), 1)
        self.assertEqual(sum(row["primary_view"] == "A" for row in master), 2)

    def test_capacity_flow_reports_infeasible_view(self):
        config = {
            "seed": 1,
            "target_count": 2,
            "unclassified_view": "00",
            "allow_unclassified_fallback": False,
            "views": [
                {"id": "00", "label": "Unclassified", "quota": 0},
                {"id": "A", "label": "A", "quota": 1},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        inventory = [
            {"uuid": "A-1", "filename": "1.jpg", "candidate_views": "A", "safety_status": "clear"},
            {"uuid": "A-2", "filename": "2.jpg", "candidate_views": "A", "safety_status": "clear"},
        ]
        with self.assertRaisesRegex(ValueError, '"B": 1'):
            select(inventory, config)

    def test_evaluation_reports_denominators_and_uncertainty(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["error_category"] = "visible-fit"
        report, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        self.assertEqual(report["decisive_count"], len(sample))
        self.assertEqual(len(report["precision_wilson_95"]), 2)
        self.assertTrue(all("decisive" in view for view in report["by_view"].values()))


if __name__ == "__main__":
    unittest.main()
