import tempfile
import unittest
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

from photo_fieldwork.cli import command_sample
from photo_fieldwork.handoff import build_public_handoff
from photo_fieldwork.integrity import (
    content_sha256,
    evaluation_sample_sha256,
    membership_sha256,
)
from photo_fieldwork.pipeline import (
    build_catalog_plan,
    effective_final_config,
    evaluate,
    make_final_holdout,
    make_sample,
    read_config,
    read_csv,
    select,
    unsupported_view_gap_report,
    validate,
    wilson_interval,
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

    def test_overlap_aware_assignment_meets_exact_quotas(self):
        inventory = [
            {
                "uuid": f"BOTH-{index}",
                "filename": f"both-{index}.jpg",
                "candidate_views": "A;B",
                "evidence_confidence": "high",
                "safety_status": "clear",
            }
            for index in range(3)
        ]
        inventory.extend(
            [
                {
                    "uuid": "ONLY-A",
                    "filename": "only-a.jpg",
                    "candidate_views": "A",
                    "evidence_confidence": "medium",
                    "safety_status": "clear",
                },
                {
                    "uuid": "ONLY-B",
                    "filename": "only-b.jpg",
                    "candidate_views": "B",
                    "evidence_confidence": "medium",
                    "safety_status": "clear",
                },
            ]
        )
        config = {
            "seed": 4,
            "target_count": 4,
            "unclassified_view": "A",
            "burst_limit": 2,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "exploratory_fraction": 0,
            "minimum_outside_prior_final_fraction": 0,
            "event_cluster_caps": {},
            "views": [
                {"id": "A", "label": "A", "quota": 2},
                {"id": "B", "label": "B", "quota": 2},
            ],
        }
        master, _, summary = select(inventory, config)
        self.assertEqual(summary["capacity"]["status"], "PASS")
        self.assertEqual(summary["view_counts"], {"A": 2, "B": 2})
        self.assertEqual(len({row["uuid"] for row in master}), 4)

    def test_exact_assignment_prioritizes_higher_ranked_singleton_groups(self):
        config = {
            "seed": 1,
            "target_count": 1,
            "unclassified_view": "01",
            "burst_limit": 2,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "exploratory_fraction": 0,
            "minimum_outside_prior_final_fraction": 0,
            "event_cluster_caps": {},
            "views": [{"id": "01", "label": "One", "quota": 1}],
        }
        rows = [
            {
                "uuid": "A",
                "filename": "a.jpg",
                "candidate_views": "01",
                "evidence_confidence": "low",
                "safety_status": "clear",
            },
            {
                "uuid": "Z",
                "filename": "z.jpg",
                "candidate_views": "01",
                "evidence_confidence": "high",
                "favorite": "true",
                "edited": "true",
                "visible_context": "strong visible evidence",
                "safety_status": "clear",
            },
        ]
        selected, _, _ = select(rows, config)
        self.assertEqual([row["uuid"] for row in selected], ["Z"])

    def test_exact_assignment_globally_reassigns_flexible_high_score_asset(self):
        config = {
            "seed": 1,
            "target_count": 2,
            "unclassified_view": "01",
            "burst_limit": 2,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "exploratory_fraction": 0,
            "minimum_outside_prior_final_fraction": 0,
            "event_cluster_caps": {},
            "views": [
                {"id": "01", "label": "One", "quota": 1},
                {"id": "02", "label": "Two", "quota": 1},
            ],
        }
        rows = [
            {
                "uuid": "FLEX",
                "candidate_views": "01;02",
                "evidence_confidence": "high",
                "favorite": "true",
                "edited": "true",
                "safety_status": "clear",
            },
            {
                "uuid": "ONE",
                "candidate_views": "01",
                "evidence_confidence": "high",
                "favorite": "true",
                "safety_status": "clear",
            },
            {
                "uuid": "TWO",
                "candidate_views": "02",
                "evidence_confidence": "low",
                "safety_status": "clear",
            },
        ]
        selected, _, summary = select(rows, config)
        assignments = {row["uuid"]: row["primary_view"] for row in selected}
        self.assertEqual(assignments, {"ONE": "01", "FLEX": "02"})
        self.assertEqual(
            summary["capacity"]["assignment_objective"],
            "maximum-total-deterministic-benefit",
        )

    def test_infeasible_assignment_reports_view_capacity(self):
        inventory = [
            {
                "uuid": f"A-{index}",
                "filename": f"a-{index}.jpg",
                "candidate_views": "A",
                "evidence_confidence": "high",
                "safety_status": "clear",
            }
            for index in range(4)
        ]
        inventory.append(
            {
                "uuid": "B-ONLY",
                "filename": "b.jpg",
                "candidate_views": "B",
                "evidence_confidence": "high",
                "safety_status": "clear",
            }
        )
        config = {
            "seed": 4,
            "target_count": 4,
            "unclassified_view": "A",
            "burst_limit": 2,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "exploratory_fraction": 0,
            "minimum_outside_prior_final_fraction": 0,
            "event_cluster_caps": {},
            "views": [
                {"id": "A", "label": "A", "quota": 2},
                {"id": "B", "label": "B", "quota": 2},
            ],
        }
        with self.assertRaisesRegex(ValueError, "deficits.*eligible_by_view"):
            select(inventory, config)

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
        master, holds, summary = select(self.inventory, self.config)
        errors, validation = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        evaluation = {
            "passed": True,
            "final_holdout": False,
            "master_sha256": summary["master_sha256"],
            "proposal_id": summary["proposal_id"],
            "config_sha256": content_sha256(self.config),
        }
        plan = build_catalog_plan(
            master,
            self.config,
            "practice",
            "Source",
            "SOURCE-1",
            source_count=len(self.inventory),
            source_membership_sha256=membership_sha256(
                row["uuid"] for row in self.inventory
            ),
            evaluation_report=evaluation,
            validation_report=validation,
            run_lock=None,
            run_lock_sha256=None,
            release_class="synthetic-practice",
        )
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(len(plan["plan_sha256"]), 64)
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)
        mismatched_evaluation = dict(evaluation, config_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "evaluation config identity"):
            build_catalog_plan(
                master,
                self.config,
                "practice",
                "Source",
                "SOURCE-1",
                source_count=len(self.inventory),
                source_membership_sha256=membership_sha256(
                    row["uuid"] for row in self.inventory
                ),
                evaluation_report=mismatched_evaluation,
                validation_report=validation,
                run_lock=None,
                run_lock_sha256=None,
                release_class="synthetic-practice",
            )

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

    def test_final_holdout_excludes_recorded_relation_leakage(self):
        master, _, _ = select(self.inventory, self.config)
        master[1]["perceptual_cluster"] = "visual-near-1"
        master[2]["duplicate_group"] = "duplicate-prior"
        master[3]["burst_group"] = "burst-prior"
        prior = [
            {"uuid": "OLD-UUID", "perceptual_cluster": "visual-near-1"},
            {"uuid": "OLD-DUP", "duplicate_group": "duplicate-prior"},
            {"uuid": "OLD-BURST", "burst_group": "burst-prior"},
        ]
        sample = make_final_holdout(master, 6, 1, 88, prior_rows=prior)
        sampled = {row["uuid"] for row in sample}
        self.assertFalse({master[1]["uuid"], master[2]["uuid"], master[3]["uuid"]} & sampled)

    def test_holdout_digest_binds_relation_identifiers(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_final_holdout(master, 6, 1, 88)
        before = evaluation_sample_sha256(sample)
        sample[0]["perceptual_cluster"] = "changed-after-audit"
        self.assertNotEqual(before, evaluation_sample_sha256(sample))

    def test_final_holdout_rejects_prior_feedback_without_relation_columns(self):
        master, _, _ = select(self.inventory, self.config)
        master_path = Path(self.temp.name) / "master.csv"
        prior_path = Path(self.temp.name) / "prior.csv"
        output_path = Path(self.temp.name) / "holdout.csv"
        write_csv(master_path, master)
        prior_path.write_text(
            "uuid,filename,primary_view\nOLD,old.jpg,01\n",
            encoding="utf-8",
        )
        args = SimpleNamespace(
            master=master_path,
            mode="final-holdout",
            exclude_feedback=[prior_path],
            sample_size=6,
            minimum_per_view=1,
            seed=88,
            output=output_path,
            per_view=1,
        )
        with self.assertRaisesRegex(ValueError, "lacks relation columns"):
            command_sample(args)

    def test_evaluation_rejects_duplicate_image_view_edges(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 1, 99)
        for row in sample:
            row["judgment"] = "fit"
        sample.append(dict(sample[0]))
        with self.assertRaisesRegex(ValueError, "duplicate image-view"):
            evaluate(sample, self.config)

    def test_regression_canaries_do_not_inflate_fresh_metrics(self):
        master, _, _ = select(self.inventory, self.config)
        fresh = make_sample(master, 1, 99)
        for row in fresh:
            row["judgment"] = "fit"
        canary = dict(fresh[0])
        canary["uuid"] = "CANARY-ONLY"
        canary["sample_role"] = "regression-canary"
        canary["judgment"] = "reject"
        report, passed = evaluate(fresh + [canary], self.config)
        self.assertEqual(report["sample_count"], len(fresh))
        self.assertEqual(report["regression_canary_failures"], 1)
        self.assertFalse(passed)

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
        for row in reduced:
            row.pop("master_sha256", None)
            row.pop("proposal_id", None)
        intent = dict(self.config)
        intent["views"] = [dict(view) for view in self.config["views"]]
        effective = effective_final_config(intent, reduced)
        by_id = {view["id"]: view for view in effective["views"]}
        self.assertEqual(by_id["04"]["status"], "unsupported")
        self.assertEqual(by_id["04"]["quota"], 0)
        gap_report = unsupported_view_gap_report(effective)
        self.assertEqual(gap_report["unsupported_views"][0]["view_id"], "04")
        self.assertIn("not evidence", gap_report["claim_boundary"])
        self.assertEqual(
            gap_report["production_album_policy"],
            "omit unsupported and deliberately empty view albums",
        )
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

    def test_diversity_floor_swap_preserves_event_cluster_cap(self):
        inventory = [
            {
                "uuid": f"EVENT-EVIDENCE-{index}",
                "filename": f"event-{index}.jpg",
                "candidate_views": "00",
                "evidence_confidence": "high",
                "safety_status": "clear",
                "event_cluster": "event-x",
                "favorite": "true",
                "edited": "true",
            }
            for index in range(2)
        ]
        inventory.extend(
            {
                "uuid": f"OTHER-{index}",
                "filename": f"other-{index}.jpg",
                "candidate_views": "00",
                "evidence_confidence": "high",
                "safety_status": "clear",
                "event_cluster": f"other-{index}",
            }
            for index in range(2)
        )
        inventory.append(
            {
                "uuid": "EVENT-EXPLORATORY",
                "filename": "event-exploratory.jpg",
                "candidate_views": "00",
                "evidence_confidence": "low",
                "safety_status": "clear",
                "event_cluster": "event-x",
                "favorite": "true",
                "edited": "true",
            }
        )
        config = {
            "seed": 1,
            "target_count": 4,
            "unclassified_view": "00",
            "burst_limit": 2,
            "exploratory_fraction": 0.25,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "event_cluster_caps": {"00": 2},
            "views": [{"id": "00", "label": "Editor field", "quota": 4}],
        }
        master, _, _ = select(inventory, config)
        self.assertIn("EVENT-EXPLORATORY", {row["uuid"] for row in master})
        self.assertEqual(
            sum(row["event_cluster"] == "event-x" for row in master),
            2,
        )

    def test_diversity_floors_backtrack_across_view_assignments(self):
        inventory = [
            {
                "uuid": "STRONG-ONE",
                "filename": "strong-one.jpg",
                "candidate_views": "01",
                "evidence_confidence": "high",
                "favorite": "true",
                "edited": "true",
                "safety_status": "clear",
            },
            {
                "uuid": "STRONG-TWO",
                "filename": "strong-two.jpg",
                "candidate_views": "02",
                "evidence_confidence": "high",
                "favorite": "true",
                "edited": "true",
                "safety_status": "clear",
            },
            {
                "uuid": "EXPLORATORY-FLEX",
                "filename": "exploratory.jpg",
                "candidate_views": "01;02",
                "evidence_confidence": "low",
                "safety_status": "clear",
            },
            {
                "uuid": "OUTSIDE-ONE",
                "filename": "outside.jpg",
                "candidate_views": "01",
                "evidence_confidence": "high",
                "outside_prior": "true",
                "safety_status": "clear",
            },
        ]
        config = {
            "seed": 1,
            "target_count": 2,
            "unclassified_view": "01",
            "burst_limit": 2,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "exploratory_fraction": 0.5,
            "minimum_outside_prior_final_fraction": 0.5,
            "event_cluster_caps": {},
            "views": [
                {"id": "01", "label": "One", "quota": 1},
                {"id": "02", "label": "Two", "quota": 1},
            ],
        }
        master, _, summary = select(inventory, config)
        assignments = {row["uuid"]: row["primary_view"] for row in master}
        self.assertEqual(
            assignments,
            {"OUTSIDE-ONE": "01", "EXPLORATORY-FLEX": "02"},
        )
        self.assertEqual(summary["diversity_floors"]["status"], "PASS")

    def test_uncapped_assignment_graph_prunes_dominated_edges_exactly(self):
        inventory = [
            {
                "uuid": f"ASSET-{index:03d}",
                "filename": f"asset-{index:03d}.jpg",
                "candidate_views": "01",
                "evidence_confidence": "high" if index < 2 else "low",
                "safety_status": "clear",
            }
            for index in range(100)
        ]
        config = {
            "seed": 1,
            "target_count": 2,
            "unclassified_view": "01",
            "burst_limit": 2,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "exploratory_fraction": 0,
            "minimum_outside_prior_final_fraction": 0,
            "event_cluster_caps": {},
            "views": [{"id": "01", "label": "One", "quota": 2}],
        }
        master, _, summary = select(inventory, config)
        self.assertEqual(len(master), 2)
        self.assertEqual(summary["capacity"]["input_assignment_edge_count"], 100)
        self.assertEqual(summary["capacity"]["solver_assignment_edge_count"], 2)

    def test_joint_floor_repair_reconsiders_an_initially_satisfied_floor(self):
        inventory = [
            {
                "uuid": "EXPLORATORY-ONE",
                "filename": "exploratory-one.jpg",
                "candidate_views": "01",
                "evidence_confidence": "low",
                "favorite": "true",
                "edited": "true",
                "safety_status": "clear",
            },
            {
                "uuid": "STRONG-TWO",
                "filename": "strong-two.jpg",
                "candidate_views": "02",
                "evidence_confidence": "high",
                "favorite": "true",
                "edited": "true",
                "safety_status": "clear",
            },
            {
                "uuid": "EXPLORATORY-TWO",
                "filename": "exploratory-two.jpg",
                "candidate_views": "02",
                "evidence_confidence": "low",
                "safety_status": "clear",
            },
            {
                "uuid": "OUTSIDE-ONE",
                "filename": "outside-one.jpg",
                "candidate_views": "01",
                "evidence_confidence": "high",
                "outside_prior": "true",
                "safety_status": "clear",
            },
        ]
        config = {
            "seed": 1,
            "target_count": 2,
            "unclassified_view": "01",
            "burst_limit": 2,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "exploratory_fraction": 0.5,
            "minimum_outside_prior_final_fraction": 0.5,
            "event_cluster_caps": {},
            "views": [
                {"id": "01", "label": "One", "quota": 1},
                {"id": "02", "label": "Two", "quota": 1},
            ],
        }
        master, _, _ = select(inventory, config)
        self.assertEqual(
            {row["uuid"]: row["primary_view"] for row in master},
            {"OUTSIDE-ONE": "01", "EXPLORATORY-TWO": "02"},
        )


if __name__ == "__main__":
    unittest.main()
