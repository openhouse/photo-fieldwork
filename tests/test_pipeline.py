import tempfile
import unittest
import hashlib
import json
import os
from collections import Counter
from copy import deepcopy
from pathlib import Path

from photo_fieldwork.pipeline import (
    build_catalog_plan,
    evaluate,
    is_hold,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    write_csv,
)
from photo_fieldwork.practice import create_demo_inventory


ROOT = Path(__file__).resolve().parents[1]


def mark_inspected(rows):
    root = Path(tempfile.mkdtemp(prefix="photo-fieldwork-test-inspection-"))
    for row in rows:
        artifact = root / f"{row['uuid']}.txt"
        artifact.write_text(
            f"test-inspection:{row['uuid']}:{row['round_id']}\n", encoding="utf-8"
        )
        row["inspection_path"] = str(artifact)
        row["inspection_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        row["inspection_round_id"] = row["round_id"]
        row["inspection_sample_sha256"] = row["sample_sha256"]


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
        for safety_state in ("human-needs-review", " hold ", " NEEDS-REVIEW "):
            with self.subTest(safety_state=safety_state):
                inventory = deepcopy(self.inventory)
                inventory[0]["safety_status"] = safety_state
                master, holds, _ = select(inventory, self.config)
                self.assertNotIn(inventory[0]["uuid"], {row["uuid"] for row in master})
                self.assertIn(inventory[0]["uuid"], {row["uuid"] for row in holds})

    def test_safety_states_are_trimmed_before_hold_check(self):
        self.assertTrue(is_hold({"safety_status": " hold "}))
        self.assertTrue(is_hold({"safety_status": " NEEDS-REVIEW "}))

    def test_hold_propagates_through_duplicate_and_burst_relations(self):
        inventory = deepcopy(self.inventory)
        inventory[0]["duplicate_group"] = "sensitive-duplicate"
        inventory[0]["safety_status"] = "hold"
        inventory[1]["duplicate_group_id"] = "sensitive-duplicate"
        inventory[1]["burst_group"] = "sensitive-burst"
        inventory[2]["burst_group"] = "sensitive-burst"
        master, holds, _ = select(inventory, self.config)
        held_ids = {row["uuid"] for row in holds}
        self.assertTrue({inventory[0]["uuid"], inventory[1]["uuid"], inventory[2]["uuid"]} <= held_ids)
        self.assertFalse(held_ids & {row["uuid"] for row in master})

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
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "reject"
            row["visible_reason"] = "Synthetic rejection."
        _, passed = evaluate(sample, self.config, master)
        self.assertFalse(passed)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        _, passed = evaluate(sample, self.config, master)
        self.assertTrue(passed)

    def test_evaluation_fails_a_weak_view_even_when_global_precision_passes(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        weak_view = sample[0]["primary_view"]
        for row in sample:
            if row["primary_view"] == weak_view:
                row["judgment"] = "reject"
                row["visible_reason"] = "Synthetic weak-view rejection."
        report, passed = evaluate(sample, self.config, master)
        self.assertGreaterEqual(report["precision"], self.config["minimum_eval_precision"])
        self.assertFalse(report["by_view"][weak_view]["passed"])
        self.assertFalse(passed)
        self.assertIsNotNone(report["by_view"][weak_view]["wilson_95_low"])

    def test_evaluation_requires_a_visible_reason_for_every_judgment(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        sample[0]["visible_reason"] = ""
        report, passed = evaluate(sample, self.config, master)
        self.assertEqual(report["missing_visible_reason_count"], 1)
        self.assertFalse(passed)

    def test_evaluation_fails_when_review_discovers_a_safety_block(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
            row["safety_status"] = "clear"
        for state in ("needs-review", "human-needs-review"):
            with self.subTest(state=state):
                sample[0]["safety_status"] = state
                report, passed = evaluate(sample, self.config, master)
                self.assertEqual(report["safety_block_count"], 1)
                self.assertFalse(passed)

    def test_sparse_hypothesis_view_does_not_require_precision(self):
        config = deepcopy(self.config)
        sparse_view = config["views"][0]["id"]
        for view in config["views"]:
            if view["id"] == sparse_view:
                view["evaluation_mode"] = "sparse-hypothesis"
        master, _, _ = select(self.inventory, config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "reject" if row["primary_view"] == sparse_view else "fit"
            row["visible_reason"] = "Synthetic sparse-view judgment."
        report, passed = evaluate(sample, config, master)
        self.assertTrue(report["by_view"][sparse_view]["passed"])
        self.assertTrue(passed)

    def test_validation_enforces_invariants(self):
        master, holds, _ = select(self.inventory, self.config)
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")

    def test_validation_rejects_safety_state_mutated_inside_master(self):
        master, holds, _ = select(self.inventory, self.config)
        master[0]["hidden"] = "true"
        errors, metrics = validate(master, holds, self.config)
        self.assertTrue(any("review-pending" in error for error in errors))
        self.assertEqual(metrics["status"], "FAIL")

    def test_evaluation_rejects_posthoc_policy_or_source_change(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        changed = deepcopy(self.config)
        changed["views"][0]["evaluation_mode"] = "sparse-hypothesis"
        with self.assertRaisesRegex(ValueError, "config or frozen source"):
            evaluate(sample, changed, master)
        changed = deepcopy(self.config)
        changed["source"]["identifier_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "config or frozen source"):
            evaluate(sample, changed, master)

    def test_evaluation_rejects_cherry_picked_or_stale_inspection_sample(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        with self.assertRaisesRegex(ValueError, "deterministic stratified sample"):
            evaluate(sample[:-1], self.config, master)
        sample[-1]["inspection_round_id"] = "older-round"
        with self.assertRaisesRegex(ValueError, "another round"):
            evaluate(sample, self.config, master)

    def test_evaluation_requires_real_candidate_bound_inspection_artifacts(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["inspection_path"] = str(Path(self.temp.name) / "missing-preview.jpg")
            row["inspection_sha256"] = "f" * 64
            row["inspection_round_id"] = row["round_id"]
            row["inspection_sample_sha256"] = row["sample_sha256"]
        with self.assertRaisesRegex(ValueError, "local inspection artifact"):
            evaluate(sample, self.config, master)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        sample[-1]["inspection_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "artifact digest"):
            evaluate(sample, self.config, master)

    def test_catalog_plan_allows_only_membership_writes(self):
        master, holds, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        evaluation, passed = evaluate(sample, self.config, master)
        self.assertTrue(passed)
        errors, metrics = validate(master, holds, self.config)
        validation_report = dict(metrics, errors=errors)
        plan = build_catalog_plan(
            master,
            holds,
            self.config,
            "practice",
            "Source",
            self.config["source"]["identifier"],
            self.config["source"]["expected_count"],
            self.config["source"]["identifier_sha256"],
            evaluation,
            sample,
            validation_report,
        )
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)

    def test_catalog_plan_rejects_evaluation_for_another_proposal(self):
        master, holds, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        evaluation, _ = evaluate(sample, self.config, master)
        mutated_master = deepcopy(master)
        mutated_master[0]["uuid"] = "OTHER-PROPOSAL-ASSET"
        errors, metrics = validate(mutated_master, holds, self.config)
        with self.assertRaisesRegex(ValueError, "exact master"):
            build_catalog_plan(
                mutated_master,
                holds,
                self.config,
                "practice",
                "Source",
                self.config["source"]["identifier"],
                self.config["source"]["expected_count"],
                self.config["source"]["identifier_sha256"],
                evaluation,
                sample,
                dict(metrics, errors=errors),
            )

    def test_catalog_plan_rejects_fabricated_evaluation_or_validation_reports(self):
        master, holds, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        evaluation, _ = evaluate(sample, self.config, master)
        errors, metrics = validate(master, holds, self.config)
        validation_report = dict(metrics, errors=errors)
        forged_evaluation = dict(evaluation, sample_count=1)
        with self.assertRaisesRegex(ValueError, "exact review feedback"):
            build_catalog_plan(
                master,
                holds,
                self.config,
                "practice",
                "Source",
                self.config["source"]["identifier"],
                self.config["source"]["expected_count"],
                self.config["source"]["identifier_sha256"],
                forged_evaluation,
                sample,
                validation_report,
            )
        forged_validation = dict(validation_report, hold_count=0)
        with self.assertRaisesRegex(ValueError, "exact master and safety manifest"):
            build_catalog_plan(
                master,
                holds,
                self.config,
                "practice",
                "Source",
                self.config["source"]["identifier"],
                self.config["source"]["expected_count"],
                self.config["source"]["identifier_sha256"],
                evaluation,
                sample,
                forged_validation,
            )

    def test_evaluation_rejects_duplicate_or_non_master_feedback_ids(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        for row in sample:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic fit."
        sample[1]["uuid"] = sample[0]["uuid"]
        with self.assertRaisesRegex(ValueError, "unique non-empty UUIDs"):
            evaluate(sample, self.config, master)
        sample = make_sample(master, 3, 20260710)
        mark_inspected(sample)
        sample[0]["uuid"] = "NOT-IN-MASTER"
        with self.assertRaisesRegex(ValueError, "outside the exact master"):
            evaluate(sample, self.config, master)


if __name__ == "__main__":
    unittest.main()
