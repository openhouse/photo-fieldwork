import copy
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.pipeline import (
    build_catalog_plan,
    candidate_view_evidence,
    content_sha256,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    validate_feedback,
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

    def passing_evaluation(self, master):
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["safety_status"] = "clear"
        report, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        return report

    def test_selection_is_deterministic_exact_and_excludes_holds(self):
        first, holds, summary = select(self.inventory, self.config)
        second, _, _ = select(self.inventory, self.config)
        self.assertEqual([row["uuid"] for row in first], [row["uuid"] for row in second])
        self.assertEqual(len(first), 12)
        self.assertEqual(summary["view_counts"], {view["id"]: view["quota"] for view in self.config["views"]})
        self.assertTrue({"DEMO-009", "DEMO-024"}.issubset({row["uuid"] for row in holds}))
        self.assertFalse({row["uuid"] for row in first} & {row["uuid"] for row in holds})

    def test_aesthetic_score_only_breaks_cluster_ties(self):
        master, _, _ = select(self.inventory, self.config)
        self.assertFalse({"DEMO-011", "DEMO-012"}.issubset({row["uuid"] for row in master}))

    def test_needs_review_is_protected_and_ids_are_canonical(self):
        inventory = copy.deepcopy(self.inventory)
        inventory[0]["uuid"] += "/L0/001"
        inventory[0]["safety_status"] = "needs-review"
        master, holds, summary = select(inventory, self.config)
        self.assertNotIn("DEMO-001", {row["uuid"] for row in master})
        self.assertIn("DEMO-001", {row["uuid"] for row in holds})
        self.assertEqual(summary["needs_review_count"], 1)

    def test_protected_asset_requires_explicit_human_clearance(self):
        rows = [{"uuid": "1", "filename": "1.jpg", "candidate_views": "A", "safety_status": "needs-review"}]
        config = {"seed": 1, "target_count": 1, "unclassified_view": "A", "views": [{"id": "A", "label": "A", "quota": 1}]}
        feedback = [{"uuid": "1", "primary_view": "A", "judgment": "fit", "safety_status": "clear"}]
        with self.assertRaisesRegex(ValueError, "safety_clearance"):
            select(rows, config, feedback=feedback)
        feedback[0]["safety_clearance"] = "true"
        feedback[0]["reviewer_lens"] = "archive owner"
        master, holds, _ = select(rows, config, feedback=feedback)
        self.assertEqual(len(master), 1)
        self.assertEqual(holds, [])

    def test_overlap_assignment_meets_exact_quotas(self):
        config = {
            "seed": 7,
            "target_count": 3,
            "unclassified_view": "A",
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "views": [
                {"id": "A", "label": "A", "quota": 2},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        rows = [
            {"uuid": "1", "filename": "1.jpg", "candidate_views": "A;B", "safety_status": "clear"},
            {"uuid": "2", "filename": "2.jpg", "candidate_views": "A;B", "safety_status": "clear"},
            {"uuid": "3", "filename": "3.jpg", "candidate_views": "A", "safety_status": "clear"},
        ]
        master, _, summary = select(rows, config)
        self.assertEqual(summary["view_counts"], {"A": 2, "B": 1})
        self.assertEqual(len({row["uuid"] for row in master}), 3)

    def test_infeasible_quotas_report_capacity_without_changing_quota(self):
        config = {
            "seed": 7,
            "target_count": 2,
            "unclassified_view": "A",
            "views": [{"id": "A", "label": "A", "quota": 1}, {"id": "B", "label": "B", "quota": 1}],
        }
        rows = [{"uuid": "1", "filename": "1.jpg"}, {"uuid": "2", "filename": "2.jpg"}]
        edges = [
            {"uuid": "1", "view_id": "A", "status": "eligible"},
            {"uuid": "2", "view_id": "A", "status": "eligible"},
        ]
        with self.assertRaisesRegex(ValueError, '"B".*"eligible_assets": 0'):
            select(rows, config, edges)

    def test_feedback_rejects_only_the_reviewed_image_view_edge(self):
        master, _, _ = select(self.inventory, self.config)
        reviewed = next(row for row in master if row["primary_view"] != self.config["unclassified_view"])
        feedback = [{
            "uuid": reviewed["uuid"],
            "primary_view": reviewed["primary_view"],
            "judgment": "reject",
            "safety_status": "clear",
            "round_id": "r2",
            "visible_reason": "wrong context for this view",
        }]
        revised, _, _ = select(self.inventory, self.config, feedback=feedback)
        self.assertNotIn((reviewed["uuid"], reviewed["primary_view"]), {(row["uuid"], row["primary_view"]) for row in revised})

    def test_uncertainty_propagates_to_master(self):
        config = {"seed": 1, "target_count": 1, "unclassified_view": "A", "views": [{"id": "A", "label": "A", "quota": 1}]}
        rows = [{"uuid": "1", "filename": "1.jpg", "safety_status": "clear"}]
        feedback = [{"uuid": "1", "primary_view": "A", "judgment": "uncertain", "safety_status": "clear", "round_id": "r1"}]
        master, _, _ = select(rows, config, feedback=feedback)
        self.assertEqual(master[0]["assignment_status"], "uncertain")
        self.assertEqual(master[0]["evidence_confidence"], "low")

    def test_novel_sample_has_zero_reused_ids(self):
        master, _, _ = select(self.inventory, self.config)
        first = make_sample(master, 1, 20260710)
        reviewed = {row["uuid"] for row in first}
        second = make_sample(master, 1, 20260710, reviewed, novel_only=True)
        self.assertFalse(reviewed & {row["uuid"] for row in second})
        self.assertTrue(all(row["prior_review_overlap"] == "false" for row in second))

    def test_evaluation_enforces_each_material_view_and_safety(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["safety_status"] = "clear"
        sample[0]["judgment"] = "reject"
        sample[1]["judgment"] = "reject"
        _, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        for row in sample:
            row["judgment"] = "fit"
        sample[0]["safety_status"] = "needs-review"
        report, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        self.assertEqual(report["safety_regressions"], 1)

    def test_validation_enforces_exact_quotas_and_known_rejects(self):
        master, holds, _ = select(self.inventory, self.config)
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")
        feedback = [{"uuid": master[0]["uuid"], "primary_view": master[0]["primary_view"], "judgment": "reject"}]
        errors, _ = validate(master, holds, self.config, feedback)
        self.assertTrue(any("known rejected" in error for error in errors))

    def test_feedback_ledger_keys_judgment_by_image_view_edge(self):
        rows = [
            {"uuid": "1", "primary_view": "A", "proposal_id": "p", "master_sha256": "h", "judgment": "reject"},
            {"uuid": "1", "primary_view": "B", "proposal_id": "p", "master_sha256": "h", "judgment": "fit"},
        ]
        summary = validate_feedback(rows)
        self.assertEqual(summary["unique_edge_count"], 2)
        self.assertEqual(summary["unique_uuid_count"], 1)

    def test_catalog_plan_requires_evaluation_and_is_content_hashed(self):
        master, _, _ = select(self.inventory, self.config)
        report = self.passing_evaluation(master)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", report)
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(plan["plan_sha256"], content_sha256(plan))
        tampered = copy.deepcopy(report)
        tampered["master_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "hash"):
            build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", tampered)

    def test_candidate_view_migration_preserves_unclassified_alternative(self):
        edges = candidate_view_evidence(self.inventory[:1], self.config)
        self.assertEqual({edge["view_id"] for edge in edges}, {"00", "01"})

    def test_empty_hold_manifest_remains_a_valid_contract(self):
        path = Path(self.temp.name) / "empty-holds.csv"
        write_csv(path, [], ["uuid", "filename", "safety_status"])
        self.assertEqual(read_csv(path, {"uuid"}, allow_empty=True), [])


if __name__ == "__main__":
    unittest.main()
