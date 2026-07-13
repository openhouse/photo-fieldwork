import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from photo_fieldwork.handoff import build_public_handoff
from photo_fieldwork.pipeline import (
    build_catalog_plan,
    effective_final_config,
    evaluate,
    make_final_holdout,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    wilson_interval,
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

    def test_packaged_starter_matches_repository_config(self):
        packaged = files("photo_fieldwork").joinpath("resources/starter.json")
        self.assertEqual(
            (ROOT / "config" / "starter.json").read_text(encoding="utf-8"),
            packaged.read_text(encoding="utf-8"),
        )

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
        master, _, _ = select(self.inventory, self.config)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1")
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)

    def test_needs_review_is_excluded_before_ranking(self):
        self.inventory[0]["safety_status"] = "needs-review"
        master, holds, _ = select(self.inventory, self.config)
        self.assertIn(self.inventory[0]["uuid"], {row["uuid"] for row in holds})
        self.assertNotIn(self.inventory[0]["uuid"], {row["uuid"] for row in master})

    def test_final_holdout_is_deterministic_and_excludes_tuning_rows(self):
        master, _, _ = select(self.inventory, self.config)
        excluded = {master[0]["uuid"]}
        first = make_final_holdout(master, 8, 1, 44, excluded)
        second = make_final_holdout(master, 8, 1, 44, excluded)
        self.assertEqual([row["uuid"] for row in first], [row["uuid"] for row in second])
        self.assertGreaterEqual(len(first), 8)
        self.assertEqual(sum(row["estimate_included"] == "true" for row in first), 8)
        self.assertFalse(excluded & {row["uuid"] for row in first})
        self.assertTrue(all(row["sample_role"].startswith("final-holdout") for row in first))

    def test_final_evaluation_reports_honest_metric_names_and_interval(self):
        master, _, _ = select(self.inventory, self.config)
        feedback = make_final_holdout(master, 12, 1, 52)
        for row in feedback:
            row["judgment"] = "fit"
        report, passed = evaluate(feedback, self.config)
        self.assertTrue(passed)
        self.assertEqual(report["review_completion"], 1.0)
        self.assertEqual(report["view_sampling_coverage"], 1.0)
        self.assertEqual(report["decisive_fit_rate"], 1.0)
        self.assertLess(report["decisive_fit_wilson_95_lower"], 1.0)
        self.assertGreater(report["field_audit_rate"], 0)
        self.assertTrue(report["final_holdout"])

    def test_wilson_interval_is_not_a_point_estimate(self):
        lower, upper = wilson_interval(71, 71)
        self.assertAlmostEqual(lower, 0.9487, places=4)
        self.assertEqual(upper, 1.0)

    def test_effective_config_records_unsupported_views_and_replays(self):
        master, holds, _ = select(self.inventory, self.config)
        reduced = [row for row in master if row["primary_view"] != "04"]
        intent = dict(self.config)
        intent["views"] = [dict(view) for view in self.config["views"]]
        effective = effective_final_config(intent, reduced)
        by_id = {view["id"]: view for view in effective["views"]}
        self.assertEqual(by_id["04"]["status"], "unsupported")
        self.assertEqual(by_id["04"]["quota"], 0)
        errors, _ = validate(reduced, holds, effective)
        self.assertEqual(errors, [])

    def test_public_handoff_excludes_private_fields_and_requires_clearance(self):
        row = dict(self.inventory[0])
        row.update(
            {
                "primary_view": "01",
                "publication_status": "cleared-for-specific-use",
                "rights_status": "owner-verified",
                "consent_status": "cleared-for-use",
                "claim_status": "provenance-backed",
                "persons": "Private Person",
                "local_path": "/private/example.jpg",
                "alt_text": "A worktable.",
            }
        )
        handoff, errors = build_public_handoff([row], "private-salt")
        self.assertEqual(errors, [])
        self.assertEqual(len(handoff), 1)
        self.assertNotIn("uuid", handoff[0])
        self.assertNotIn("persons", handoff[0])
        self.assertNotIn("local_path", handoff[0])

    def test_event_cluster_cap_limits_concentration(self):
        inventory = []
        for index in range(6):
            inventory.append(
                {
                    "uuid": f"EVENT-{index}",
                    "filename": f"{index}.jpg",
                    "candidate_views": "00",
                    "evidence_confidence": "high",
                    "safety_status": "clear",
                    "event_cluster": "same-event" if index < 4 else f"other-{index}",
                }
            )
        config = {
            "seed": 1,
            "target_count": 4,
            "unclassified_view": "00",
            "burst_limit": 2,
            "exploratory_fraction": 0,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "event_cluster_caps": {"00": 2},
            "views": [{"id": "00", "label": "Editor field", "quota": 4}],
        }
        master, holds, _ = select(inventory, config)
        self.assertEqual(holds, [])
        self.assertEqual(
            sum(row["event_cluster"] == "same-event" for row in master),
            2,
        )
        errors, metrics = validate(master, holds, config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["event_cap_violations"], {})


if __name__ == "__main__":
    unittest.main()
