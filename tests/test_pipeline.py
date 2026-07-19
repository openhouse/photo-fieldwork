import tempfile
import unittest
from collections import Counter
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
        first, holds, summary = select(self.inventory, self.config)
        second, _, _ = select(self.inventory, self.config)
        self.assertEqual([row["uuid"] for row in first], [row["uuid"] for row in second])
        self.assertEqual(len(first), 12)
        self.assertEqual(summary["view_counts"], summary["view_quotas"])
        self.assertEqual(summary["assignment_method"], "reviewed-exclusive-exact-quota")
        self.assertTrue({"DEMO-009", "DEMO-024"}.issubset({row["uuid"] for row in holds}))
        self.assertFalse({row["uuid"] for row in first} & {row["uuid"] for row in holds})

    def test_unresolved_safety_states_fail_closed(self):
        inventory = deepcopy(self.inventory)
        counts = Counter(
            row.get("assigned_view") for row in inventory
            if row.get("safety_status", "clear") == "clear"
        )
        quotas = {view["id"]: int(view["quota"]) for view in self.config["views"]}
        target = next(
            row for row in inventory
            if row.get("safety_status", "clear") == "clear"
            and counts[row.get("assigned_view")] > quotas[row.get("assigned_view")]
        )
        target["safety_status"] = "review-required"
        master, holds, _ = select(inventory, self.config)
        self.assertNotIn(target["uuid"], {row["uuid"] for row in master})
        self.assertIn(target["uuid"], {row["uuid"] for row in holds})

    def test_selection_reports_exact_view_scarcity_without_rebalancing(self):
        scarce = [row for row in self.inventory if row.get("assigned_view") != "04"]
        with self.assertRaisesRegex(ValueError, '"04".*"deficit"'):
            select(scarce, self.config)

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
        self.assertLess(len({row["uuid"] for row in master} & clustered_ids), 2)

    def test_retrieval_hypotheses_cannot_replace_reviewed_assignment(self):
        baseline, _, _ = select(self.inventory, self.config)
        target_uuid = baseline[0]["uuid"]
        expected = baseline[0]["assigned_view"]
        inventory = deepcopy(self.inventory)
        target = next(row for row in inventory if row["uuid"] == target_uuid)
        target["candidate_views"] = "04;03" if expected not in {"04", "03"} else "01;02"
        master, _, _ = select(inventory, self.config)
        self.assertEqual({row["uuid"]: row for row in master}[target_uuid]["primary_view"], expected)

    def test_missing_assignment_fails_loudly(self):
        inventory = deepcopy(self.inventory)
        inventory[0]["assigned_view"] = ""
        with self.assertRaisesRegex(ValueError, "lacks assigned_view"):
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
            row["visible_reason"] = "visible mismatch"
            row["evaluation_safety_state"] = "clear"
            row["error_category"] = "context-mismatch"
        _, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "visible match"
            row["error_category"] = ""
        _, passed = evaluate(sample, self.config)
        self.assertTrue(passed)

    def test_evaluation_fails_a_weak_view_even_when_global_precision_passes(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        weak_view = sample[0]["primary_view"]
        for row in sample:
            row["judgment"] = "reject" if row["primary_view"] == weak_view else "fit"
            row["visible_reason"] = "visible evidence reviewed"
            row["evaluation_safety_state"] = "clear"
            row["error_category"] = "context-mismatch" if row["judgment"] == "reject" else ""
        report, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        self.assertIn(weak_view, report["failed_views"])

    def test_targeted_sample_records_round_and_view(self):
        master, _, _ = select(self.inventory, self.config)
        view = master[0]["primary_view"]
        sample = make_sample(master, 2, 20260710, views={view}, round_id="round-02")
        self.assertEqual({row["primary_view"] for row in sample}, {view})
        self.assertEqual({row["round_id"] for row in sample}, {"round-02"})
        scores = [float(row["score_total"]) for row in sample]
        selected_scores = [float(row["score_total"]) for row in master if row["primary_view"] == view]
        if len(selected_scores) > 1:
            self.assertEqual({min(scores), max(scores)}, {min(selected_scores), max(selected_scores)})

    def test_evaluation_fails_missing_view_and_missing_safety_state(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        missing_view = sample[0]["primary_view"]
        sample = [row for row in sample if row["primary_view"] != missing_view]
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "visible match"
            row["evaluation_safety_state"] = ""
        report, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        self.assertIn(missing_view, report["failed_views"])
        self.assertEqual(report["missing_safety_states"], len(sample))

    def test_validation_enforces_invariants(self):
        master, holds, _ = select(self.inventory, self.config)
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")
        self.assertEqual(metrics["view_counts"], metrics["view_quotas"])

    def test_validation_rejects_silent_quota_rebalancing(self):
        master, holds, _ = select(self.inventory, self.config)
        source_view = master[0]["primary_view"]
        master[0]["primary_view"] = next(
            row["primary_view"] for row in master if row["primary_view"] != source_view
        )
        errors, metrics = validate(master, holds, self.config)
        self.assertTrue(any("exact view quota mismatch" in error for error in errors))
        self.assertTrue(metrics["quota_mismatches"])

    def test_header_only_hold_manifest_is_valid(self):
        path = Path(self.temp.name) / "empty-holds.csv"
        path.write_text("uuid,filename\n", encoding="utf-8")
        self.assertEqual(read_csv(path, allow_empty=True), [])

    def test_catalog_plan_allows_only_membership_writes(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row.update({
                "judgment": "fit", "visible_reason": "visible match",
                "evaluation_safety_state": "clear", "error_category": "",
            })
        evaluation, passed = evaluate(sample, self.config, master=master)
        self.assertTrue(passed)
        self.assertTrue(evaluation["full_master_audit"])
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", evaluation)
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)
        self.assertEqual(plan["master_sha256"], evaluation["master_sha256"])

    def test_catalog_plan_rejects_targeted_audit_and_post_evaluation_drift(self):
        master, _, _ = select(self.inventory, self.config)
        view = master[0]["primary_view"]
        sample = make_sample(master, 3, 20260710, views={view})
        for row in sample:
            row.update({
                "judgment": "fit", "visible_reason": "visible match",
                "evaluation_safety_state": "clear", "error_category": "",
            })
        evaluation, _ = evaluate(sample, self.config, master=master)
        self.assertFalse(evaluation["full_master_audit"])
        with self.assertRaisesRegex(ValueError, "full audit"):
            build_catalog_plan(master, self.config, "targeted", "Source", "SOURCE-1", evaluation)

        full = make_sample(master, 3, 20260710)
        for row in full:
            row.update({
                "judgment": "fit", "visible_reason": "visible match",
                "evaluation_safety_state": "clear", "error_category": "",
            })
        full_evaluation, _ = evaluate(full, self.config, master=master)
        master[0]["assigned_view"] = "04" if master[0]["assigned_view"] != "04" else "01"
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            build_catalog_plan(master, self.config, "drift", "Source", "SOURCE-1", full_evaluation)

    def test_feedback_schema_and_application_are_explicit(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        feedback = [
            {
                "uuid": row["uuid"],
                "filename": row["filename"],
                "proposal_id": row["proposal_id"],
                "master_sha256": row["master_sha256"],
                "judgment": "fit",
                "visible_reason": "visible fixture",
                "evaluation_safety_state": "clear",
                "error_category": "",
                "round_id": "round-01",
                "reviewer_lens": "fixture",
            }
            for row in sample
        ]
        self.assertEqual(validate_feedback(feedback)["status"], "PASS")
        merged = apply_feedback(sample, feedback)
        self.assertTrue(all(row["judgment"] == "fit" for row in merged))


if __name__ == "__main__":
    unittest.main()
