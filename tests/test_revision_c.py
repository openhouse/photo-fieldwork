import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import argparse
from pathlib import Path

from photo_fieldwork.ledger import append_event, connect, read_events
from photo_fieldwork.cli import command_round_apply
from photo_fieldwork.pipeline import evaluate, read_csv, select, validate, write_csv
from photo_fieldwork.rounds import apply_feedback
from photo_fieldwork.run_state import PHASES, finalize, initialize, read_run_events, reconcile, recover


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "build_verification_snapshot.py"
VERIFY_SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "verify_photos_commit.py"
RETRIEVE_SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "retrieve_candidates.py"


class LedgerTests(unittest.TestCase):
    def test_events_are_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "decisions.sqlite"
            event_id = append_event(
                ledger,
                run_id="run-1",
                event_type="reviewed-fit",
                actor="test",
                asset_uuid="A",
                new_state="fit",
                payload={"visible_reason": "apparatus"},
            )
            events = read_events(ledger)
            self.assertEqual(events[0]["event_id"], event_id)
            self.assertEqual(events[0]["payload"]["visible_reason"], "apparatus")
            conn = connect(ledger)
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("UPDATE decision_event SET new_state='reject'")
            conn.close()


class LifecycleTests(unittest.TestCase):
    def test_reconcile_is_compare_and_swap_and_event_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            initialized = initialize(
                workspace,
                run_id="run-cas",
                version="v01",
                target_count=1,
                source_identifier="SOURCE",
                expected_source_count=1,
            )
            self.assertEqual(initialized["revision"], 1)
            reconciled = reconcile(workspace, expected_revision=1)
            self.assertEqual(reconciled["revision"], 2)
            with self.assertRaisesRegex(ValueError, "revision conflict"):
                reconcile(workspace, expected_revision=1)

            (workspace / "run-state.json").write_text("{}\n")
            recovered = recover(workspace)
            self.assertEqual(recovered["revision"], 2)
            self.assertEqual([event["revision"] for event in read_run_events(workspace)], [1, 2])

    def test_completed_artifact_drift_blocks_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            initialize(
                workspace,
                run_id="run-drift",
                version="v01",
                target_count=1,
                source_identifier="SOURCE",
                expected_source_count=1,
            )
            (workspace / "brief.md").write_text("approved brief\n")
            (workspace / "retrieval.json").write_text("{}\n")
            (workspace / "config.json").write_text("{}\n")
            state = reconcile(workspace, expected_revision=1)
            self.assertEqual(state["phases"]["brief"]["status"], "complete")

            (workspace / "brief.md").write_text("mutated brief\n")
            state = reconcile(workspace, expected_revision=2)

            self.assertEqual(state["status"], "blocked")
            self.assertEqual(state["phases"]["brief"]["status"], "blocked")
            self.assertIn("SHA-256 changed", " ".join(state["phases"]["brief"]["errors"]))
            original_artifacts = state["phases"]["brief"]["artifacts"]

            state = reconcile(workspace, expected_revision=3)
            self.assertEqual(state["phases"]["brief"]["status"], "blocked")
            self.assertEqual(state["phases"]["brief"]["artifacts"], original_artifacts)

    def test_completed_phase_supersession_requires_explicit_cas_update(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            initialize(
                workspace,
                run_id="run-supersession",
                version="v01",
                target_count=1,
                source_identifier="SOURCE",
                expected_source_count=1,
            )
            first = workspace / "reports" / "round-1" / "evaluation-report.json"
            first.parent.mkdir()
            first.write_text(json.dumps({"passed": True, "round": 1}))
            state = reconcile(workspace, expected_revision=1)
            original = state["phases"]["recursive_evaluation"]["artifacts"]

            second = workspace / "reports" / "round-2" / "evaluation-report.json"
            second.parent.mkdir()
            second.write_text(json.dumps({"passed": True, "round": 2}))
            state = reconcile(workspace, expected_revision=2)
            phase = state["phases"]["recursive_evaluation"]
            self.assertEqual(phase["status"], "blocked")
            self.assertEqual(phase["artifacts"], original)

            with self.assertRaisesRegex(ValueError, "require expected_revision"):
                reconcile(
                    workspace,
                    allow_phase_updates=("recursive_evaluation",),
                )

            state = reconcile(
                workspace,
                expected_revision=3,
                allow_phase_updates=("recursive_evaluation",),
            )
            phase = state["phases"]["recursive_evaluation"]
            self.assertEqual(phase["status"], "complete")
            self.assertEqual(phase["artifacts"][0]["path"], "reports/round-2/evaluation-report.json")

    def test_write_receipt_without_verification_remains_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            initialize(
                workspace,
                run_id="run-1",
                version="v01",
                target_count=1,
                source_identifier="SOURCE",
                expected_source_count=1,
            )
            (workspace / "manifests" / "v01-write-test-receipt.json").write_text("{}")
            state = reconcile(workspace)
            self.assertEqual(state["phases"]["write_test"]["status"], "pending")

    def test_markdown_counts_cannot_authorize_independent_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            initialize(
                workspace,
                run_id="run-1",
                version="v01",
                target_count=1,
                source_identifier="SOURCE",
                expected_source_count=1,
            )
            (workspace / "manifests" / "v01-photo-archive-receipt.json").write_text("{}")
            (workspace / "reports" / "production-verification.md").write_text(
                "Status: FAIL\nMissing memberships: 0\nUnexpected memberships: 0\nOutside source: 1\n"
            )

            state = reconcile(workspace)

            self.assertEqual(state["phases"]["production_commit"]["status"], "complete")
            self.assertEqual(state["phases"]["independent_verification"]["status"], "pending")

    def test_reconcile_and_finalize_from_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            initialize(
                workspace,
                run_id="run-1",
                version="v01",
                target_count=2,
                source_identifier="SOURCE",
                expected_source_count=2,
            )
            (workspace / "brief.md").write_text("brief\n")
            (workspace / "retrieval.json").write_text("{}\n")
            (workspace / "config.json").write_text("{}\n")
            (workspace / "manifests" / "candidate-pool.csv").write_text("uuid,filename\nA,a.jpg\n")
            (workspace / "manifests" / "local-inspection-receipt.json").write_text(
                json.dumps({"completed_count": 1, "requested_count": 1, "external_uploads_performed": False})
            )
            evaluation = workspace / "reports" / "round-1" / "evaluation-report.json"
            evaluation.parent.mkdir()
            evaluation.write_text(json.dumps({"passed": True}))
            validation = workspace / "reports" / "validation" / "validation-report.json"
            validation.parent.mkdir()
            validation.write_text(json.dumps({"status": "PASS"}))
            (workspace / "manifests" / "v01-write-test-receipt.json").write_text("{}")
            (workspace / "manifests" / "v01-photo-archive-receipt.json").write_text("{}")
            (workspace / "reports" / "write-test-verification.json").write_text(
                json.dumps({"status": "PASS", "plan_id": "v01-write-test"})
            )
            (workspace / "reports" / "production-verification.json").write_text(
                json.dumps({"status": "PASS", "plan_id": "v01-production"})
            )

            state = reconcile(workspace)
            self.assertTrue(all(state["phases"][phase]["status"] == "complete" for phase in PHASES))
            self.assertEqual(state["status"], "ready-to-finalize")
            self.assertEqual(finalize(workspace)["status"], "complete")


class RoundTests(unittest.TestCase):
    def test_ledger_rejection_is_enforced_without_prior_feedback_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            master = [{
                "uuid": "OUT", "filename": "out.jpg", "primary_view": "01",
                "score_total": "10", "selection_reason": "selected",
            }]
            inventory = master + [
                {
                    "uuid": "LEDGER-REJECT", "filename": "reject.jpg", "primary_view": "01",
                    "candidate_views": "01", "score_total": "100", "selection_reason": "eligible",
                    "safety_status": "clear", "pixel_available": "true", "preview_exported": "true",
                },
                {
                    "uuid": "CLEAR", "filename": "clear.jpg", "primary_view": "01",
                    "candidate_views": "01", "score_total": "9", "selection_reason": "eligible",
                    "safety_status": "clear", "pixel_available": "true", "preview_exported": "true",
                },
            ]
            feedback = [{"uuid": "OUT", "filename": "out.jpg", "primary_view": "01", "judgment": "reject"}]
            master_path = root / "master.csv"
            inventory_path = root / "inventory.csv"
            feedback_path = root / "feedback.csv"
            output_path = root / "updated.csv"
            ledger = root / "decisions.sqlite"
            write_csv(master_path, master)
            write_csv(inventory_path, inventory)
            write_csv(feedback_path, feedback)
            append_event(
                ledger,
                run_id="run",
                round_id="round-1",
                asset_uuid="LEDGER-REJECT",
                event_type="reviewed-reject",
                actor="editor",
                new_state="rejected",
                payload={"primary_view": "01"},
            )

            command_round_apply(
                argparse.Namespace(
                    master=master_path,
                    inventory=inventory_path,
                    feedback=feedback_path,
                    prior_feedback=[],
                    output=output_path,
                    round_id="round-2",
                    ledger=ledger,
                    run_id="run",
                    actor="editor",
                    config_hash=None,
                    inspection_profile_hash=None,
                    code_version=None,
                    allow_uninspected=False,
                )
            )

            self.assertEqual([row["uuid"] for row in read_csv(output_path)], ["CLEAR"])

    def test_conflicting_feedback_cannot_erase_rejection(self):
        master = [{
            "uuid": "OUT", "filename": "out.jpg", "primary_view": "01",
            "score_total": "10", "selection_reason": "selected",
        }]
        inventory = master + [{
            "uuid": "CLEAR", "filename": "clear.jpg", "primary_view": "01",
            "candidate_views": "01", "score_total": "9", "selection_reason": "eligible",
            "safety_status": "clear", "pixel_available": "true", "preview_exported": "true",
        }]
        feedback = [
            {"uuid": "OUT", "primary_view": "01", "judgment": "reject"},
            {"uuid": "OUT", "primary_view": "02", "judgment": "fit"},
        ]

        updated, _ = apply_feedback(master, inventory, feedback, round_id="round-2")

        self.assertEqual([row["uuid"] for row in updated], ["CLEAR"])
    def test_prior_rejected_image_view_edge_cannot_reenter(self):
        master = [{
            "uuid": "OUT", "filename": "out.jpg", "primary_view": "01",
            "score_total": "10", "selection_reason": "selected",
        }]
        inventory = master + [
            {
                "uuid": "REJECTED-EDGE", "filename": "rejected.jpg",
                "primary_view": "01", "candidate_views": "01;02", "score_total": "100",
                "selection_reason": "eligible", "safety_status": "clear",
                "pixel_available": "true", "preview_exported": "true",
            },
            {
                "uuid": "CLEAR-NEXT", "filename": "next.jpg", "primary_view": "01",
                "candidate_views": "01", "score_total": "9", "selection_reason": "eligible",
                "safety_status": "clear", "pixel_available": "true", "preview_exported": "true",
            },
        ]
        current = [{"uuid": "OUT", "primary_view": "01", "judgment": "reject"}]
        prior = [{"uuid": "REJECTED-EDGE", "primary_view": "01", "judgment": "reject"}]

        updated, _ = apply_feedback(
            master,
            inventory,
            current,
            prior_feedback=prior,
            round_id="round-3",
        )

        self.assertEqual([row["uuid"] for row in updated], ["CLEAR-NEXT"])

    def test_replacement_requires_inspected_clear_candidate(self):
        master = [
            {"uuid": "A", "filename": "a.jpg", "primary_view": "01", "score_total": "9", "selection_reason": "selected"},
            {"uuid": "B", "filename": "b.jpg", "primary_view": "02", "score_total": "8", "selection_reason": "selected"},
        ]
        inventory = master + [
            {
                "uuid": "C", "filename": "c.jpg", "primary_view": "01", "score_total": "7",
                "selection_reason": "eligible", "safety_status": "clear",
                "pixel_available": "true", "preview_exported": "true",
            },
            {
                "uuid": "D", "filename": "d.jpg", "primary_view": "01", "score_total": "10",
                "selection_reason": "eligible", "safety_status": "clear",
                "pixel_available": "false", "preview_exported": "false",
            },
            {
                "uuid": "E", "filename": "e.jpg", "primary_view": "01", "score_total": "12",
                "selection_reason": "eligible", "safety_status": "needs-review",
                "pixel_available": "true", "preview_exported": "true",
            },
        ]
        feedback = [{"uuid": "A", "judgment": "reject", "safety_status": "clear", "visible_reason": "mismatch"}]
        updated, events = apply_feedback(master, inventory, feedback, round_id="round-2")
        self.assertEqual({row["uuid"] for row in updated}, {"B", "C"})
        self.assertEqual([event["event_type"] for event in events], ["reviewed-reject", "replaced"])

    def test_unavailable_feedback_removes_selected_asset(self):
        master = [{
            "uuid": "A", "filename": "a.jpg", "primary_view": "01",
            "score_total": "9", "selection_reason": "selected",
        }]
        inventory = master + [{
            "uuid": "B", "filename": "b.jpg", "primary_view": "01",
            "score_total": "8", "selection_reason": "eligible", "safety_status": "clear",
            "pixel_available": "true", "preview_exported": "true",
        }]
        feedback = [{"uuid": "A", "judgment": "fit", "safety_status": "unavailable"}]

        updated, events = apply_feedback(master, inventory, feedback, round_id="round-3")

        self.assertEqual([row["uuid"] for row in updated], ["B"])
        self.assertEqual(events[0]["event_type"], "placed-on-hold")


class GateTests(unittest.TestCase):
    def test_material_view_fails_its_own_precision_gate(self):
        config = {
            "minimum_eval_coverage": 1,
            "minimum_eval_precision": 0.5,
            "minimum_per_view_precision": 0.8,
            "views": [{"id": "01", "label": "Material view", "quota": 2, "material": True}],
        }
        feedback = [
            {"primary_view": "01", "judgment": "fit"},
            {"primary_view": "01", "judgment": "reject"},
        ]
        report, passed = evaluate(feedback, config)
        self.assertFalse(passed)
        self.assertEqual(report["per_view_failures"][0]["view"], "01")

    def test_hypothesis_view_can_waive_low_per_view_precision(self):
        config = {
            "minimum_eval_coverage": 1,
            "minimum_eval_precision": 0.5,
            "minimum_per_view_precision": 0.8,
            "views": [{"id": "01", "label": "Project - Editor Hypothesis", "quota": 2, "hypothesis": True}],
        }
        feedback = [
            {"primary_view": "01", "judgment": "fit"},
            {"primary_view": "01", "judgment": "reject"},
        ]
        report, passed = evaluate(feedback, config)
        self.assertTrue(passed)
        self.assertEqual(len(report["per_view_waivers"]), 1)

    def test_strict_validation_reports_named_gates(self):
        config = {
            "target_count": 1,
            "person_free_mode": "visible",
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 1,
            "minimum_outside_prior_fraction": 0.4,
            "require_still_only": True,
            "require_pixel_available": True,
            "require_preview_exported": True,
            "views": [{"id": "00", "label": "Unclassified / Editor Field", "quota": 1}],
        }
        master = [{
            "uuid": "A", "selection_reason": "visible material", "primary_view": "00",
            "media_type": "photo", "pixel_available": "true", "preview_exported": "true",
            "safety_status": "clear", "detected_face_count": "0", "visible_context": "apparatus",
        }]
        errors, report = validate(
            master,
            [],
            config,
            candidate_summary={"outside_prior_fraction": 0.5},
        )
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        self.assertIn("pixels-local", {gate["name"] for gate in report["gates"]})


class ConstraintTests(unittest.TestCase):
    def test_exact_assignment_maximizes_global_candidate_score(self):
        config = {
            "seed": 7,
            "target_count": 3,
            "unclassified_view": "A",
            "quota_mode": "exact",
            "views": [
                {"id": view, "label": view, "quota": 1}
                for view in ("A", "B", "C")
            ],
        }
        inventory = [
            {
                "uuid": "TOP-FLEX", "filename": "top.jpg", "candidate_views": "A;B;C",
                "favorite": "true", "edited": "true", "safety_status": "clear",
            },
            {
                "uuid": "A-ONLY", "filename": "a.jpg", "candidate_views": "A",
                "favorite": "true", "safety_status": "clear",
            },
            {
                "uuid": "LOW-AB", "filename": "ab.jpg", "candidate_views": "A;B",
                "visible_context": "material", "safety_status": "clear",
            },
            {
                "uuid": "LOW-BC", "filename": "bc.jpg", "candidate_views": "B;C",
                "safety_status": "clear",
            },
        ]

        master, _, _ = select(inventory, config)

        self.assertEqual({row["uuid"] for row in master}, {"TOP-FLEX", "A-ONLY", "LOW-AB"})

    def test_diversity_floor_swap_minimizes_global_score_loss(self):
        config = {
            "seed": 7,
            "target_count": 2,
            "unclassified_view": "A",
            "quota_mode": "exact",
            "exploratory_fraction": 0.5,
            "views": [
                {"id": "A", "label": "A", "quota": 1},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        inventory = [
            {
                "uuid": "A-HIGH", "filename": "a1.jpg", "candidate_views": "A",
                "favorite": "true", "edited": "true", "evidence_confidence": "high",
                "persons": "P", "visible_context": "material", "safety_status": "clear",
            },
            {
                "uuid": "A-LOW", "filename": "a2.jpg", "candidate_views": "A",
                "favorite": "true", "edited": "true", "evidence_confidence": "unknown",
                "visible_context": "material", "safety_status": "clear",
            },
            {
                "uuid": "B-HIGH", "filename": "b1.jpg", "candidate_views": "B",
                "evidence_confidence": "high", "safety_status": "clear",
            },
            {
                "uuid": "B-LOW", "filename": "b2.jpg", "candidate_views": "B",
                "evidence_confidence": "unknown", "persons": "P",
                "visible_context": "material", "safety_status": "clear",
            },
        ]

        master, _, _ = select(inventory, config)

        self.assertEqual({row["uuid"] for row in master}, {"A-HIGH", "B-LOW"})

    def test_diversity_floor_lookahead_preserves_flexible_assignment_capacity(self):
        config = {
            "seed": 7,
            "target_count": 2,
            "unclassified_view": "A",
            "quota_mode": "exact",
            "exploratory_fraction": 1.0,
            "views": [
                {"id": "A", "label": "A", "quota": 1},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        inventory = [
            {
                "uuid": "A-DONOR", "filename": "a.jpg", "candidate_views": "A",
                "favorite": "true", "evidence_confidence": "medium",
                "visible_context": "material", "safety_status": "clear",
            },
            {
                "uuid": "B-DONOR", "filename": "b.jpg", "candidate_views": "B",
                "favorite": "true", "edited": "true", "evidence_confidence": "high",
                "safety_status": "clear",
            },
            {
                "uuid": "X-FLEX", "filename": "x.jpg", "candidate_views": "A;B",
                "favorite": "true", "edited": "true", "evidence_confidence": "unknown",
                "visible_context": "material", "safety_status": "clear",
            },
            {
                "uuid": "Y-A", "filename": "y.jpg", "candidate_views": "A",
                "favorite": "true", "evidence_confidence": "unknown",
                "visible_context": "material", "safety_status": "clear",
            },
        ]

        master, _, _ = select(inventory, config)

        self.assertEqual(
            {row["uuid"]: row["primary_view"] for row in master},
            {"Y-A": "A", "X-FLEX": "B"},
        )

    def test_overlap_aware_assignment_avoids_first_view_trap(self):
        config = {
            "seed": 7,
            "target_count": 2,
            "unclassified_view": "A",
            "quota_mode": "exact",
            "views": [
                {"id": "A", "label": "A", "quota": 1},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        inventory = [
            {
                "uuid": "FLEX", "filename": "flex.jpg", "candidate_views": "A;B",
                "favorite": "true", "safety_status": "clear",
            },
            {
                "uuid": "A-ONLY", "filename": "a.jpg", "candidate_views": "A",
                "safety_status": "clear",
            },
        ]

        master, _, summary = select(inventory, config)

        self.assertEqual(
            {row["uuid"]: row["primary_view"] for row in master},
            {"A-ONLY": "A", "FLEX": "B"},
        )
        self.assertEqual(summary["assignment_capacity"]["status"], "PASS")

    def test_infeasible_assignment_reports_view_deficits(self):
        config = {
            "seed": 7,
            "target_count": 2,
            "unclassified_view": "A",
            "quota_mode": "exact",
            "views": [
                {"id": "A", "label": "A", "quota": 1},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        inventory = [
            {"uuid": "A1", "filename": "a1.jpg", "candidate_views": "A", "safety_status": "clear"},
            {"uuid": "A2", "filename": "a2.jpg", "candidate_views": "A", "safety_status": "clear"},
        ]

        with self.assertRaisesRegex(ValueError, '"B": 1'):
            select(inventory, config)

    def test_only_recognized_clear_safety_states_are_eligible(self):
        config = {
            "seed": 7,
            "target_count": 1,
            "unclassified_view": "00",
            "quota_mode": "exact",
            "views": [{"id": "00", "label": "Unclassified", "quota": 1}],
        }
        inventory = [
            {
                "uuid": "AUTOMATED-CLEAR", "filename": "clear.jpg",
                "candidate_views": "00", "safety_status": "clear-automated",
            },
            {
                "uuid": "UNKNOWN-HIGH", "filename": "unknown.jpg",
                "candidate_views": "00", "safety_status": "mystery", "favorite": "true",
            },
        ]

        master, holds, _ = select(inventory, config)

        self.assertEqual([row["uuid"] for row in master], ["AUTOMATED-CLEAR"])
        self.assertEqual([row["uuid"] for row in holds], ["UNKNOWN-HIGH"])

    def test_event_limit_prevents_one_event_from_dominating(self):
        config = {
            "seed": 7,
            "target_count": 2,
            "unclassified_view": "00",
            "quota_mode": "exact",
            "event_limit": 1,
            "views": [{"id": "00", "label": "Unclassified", "quota": 2}],
        }
        inventory = [
            {
                "uuid": f"{event}-{index}",
                "filename": f"{event}-{index}.jpg",
                "candidate_views": "00",
                "event_cluster": event,
                "favorite": "true" if index == 0 else "false",
                "safety_status": "clear",
            }
            for event in ("EVENT-A", "EVENT-B")
            for index in range(3)
        ]
        master, _, summary = select(inventory, config)
        self.assertEqual({row["event_cluster"] for row in master}, {"EVENT-A", "EVENT-B"})
        self.assertEqual(summary["eligible_after_cluster_reduction"], 2)

    def test_diversity_floors_preserve_each_other_and_exact_views(self):
        config = {
            "seed": 7,
            "target_count": 4,
            "unclassified_view": "00",
            "quota_mode": "exact",
            "exploratory_fraction": 0.5,
            "minimum_named_people_fraction": 0.5,
            "minimum_person_free_fraction": 0.5,
            "person_free_mode": "no_named_association",
            "views": [
                {"id": "00", "label": "Unclassified", "quota": 2},
                {"id": "01", "label": "Project - Editor Hypothesis", "quota": 2},
            ],
        }
        inventory = []
        for view in ("00", "01"):
            inventory.extend([
                {"uuid": f"{view}-named-high", "filename": "a.jpg", "candidate_views": view, "persons": "Named", "evidence_confidence": "high", "safety_status": "clear"},
                {"uuid": f"{view}-free-high", "filename": "b.jpg", "candidate_views": view, "persons": "", "evidence_confidence": "high", "safety_status": "clear"},
                {"uuid": f"{view}-named-low", "filename": "c.jpg", "candidate_views": view, "persons": "Named", "evidence_confidence": "low", "safety_status": "clear"},
                {"uuid": f"{view}-free-low", "filename": "d.jpg", "candidate_views": view, "persons": "", "evidence_confidence": "low", "safety_status": "clear"},
            ])
        master, _, summary = select(inventory, config)
        self.assertEqual(summary["named_people_count"], 2)
        self.assertEqual(summary["person_free_count"], 2)
        self.assertEqual(summary["exploratory_count"], 2)
        self.assertEqual(summary["view_counts"], {"00": 2, "01": 2})


class RetrievalTests(unittest.TestCase):
    def test_album_exclusions_remove_assets_and_summary_persists_freshness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "inventory.sqlite"
            conn = sqlite3.connect(database)
            conn.executescript(
                """
                CREATE TABLE asset(
                  uuid TEXT PRIMARY KEY, filename TEXT, original_filename TEXT,
                  date_created TEXT, year INT, width INT, height INT, is_photo INT,
                  is_movie INT, favorite INT, edited INT, hidden INT, trashed INT,
                  missing INT, screenshot INT, selfie INT, portrait INT, burst INT,
                  burst_key TEXT, burst_pick_type INT, overall_aesthetic_score REAL,
                  duplicate_group_id TEXT, camera_make TEXT, camera_model TEXT,
                  face_count INT, title TEXT, description TEXT
                );
                CREATE TABLE asset_album(uuid TEXT, album_uuid TEXT, album_title TEXT);
                CREATE TABLE asset_keyword(uuid TEXT, keyword TEXT);
                CREATE TABLE asset_label(uuid TEXT, label TEXT, label_normalized TEXT);
                CREATE TABLE asset_place(uuid TEXT, place_type TEXT, place TEXT);
                CREATE TABLE asset_person(uuid TEXT, person TEXT);
                CREATE TABLE asset_search(
                  uuid TEXT, category INT, category_name TEXT, content_string TEXT,
                  normalized_string TEXT, lookup_identifier TEXT
                );
                """
            )
            for uuid, title, favorite in (
                ("EXCLUDED", "studio work", 0),
                ("PRIOR-ASSET", "studio work", 0),
                ("FRESH-ASSET", "studio work", 0),
                ("FALLBACK-SAFE", "unmatched favorite", 1),
            ):
                conn.execute(
                    """
                    INSERT INTO asset(
                      uuid, filename, title, is_photo, is_movie, favorite, edited,
                      hidden, trashed, missing, screenshot, selfie, portrait, burst,
                      face_count
                    ) VALUES (?, ?, ?, 1, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                    """,
                    (uuid, f"{uuid}.jpg", title, favorite),
                )
            conn.executemany(
                "INSERT INTO asset_album VALUES (?, ?, ?)",
                [
                    ("EXCLUDED", "PRIVATE", "Private family"),
                    ("PRIOR-ASSET", "PRIOR", "Previous corpus"),
                ],
            )
            conn.commit()
            conn.close()
            retrieval = root / "retrieval.json"
            retrieval.write_text(
                json.dumps(
                    {
                        "candidate_multiplier": 1,
                        "excluded_album_terms": ["private"],
                        "prior_corpus_album_title": "Previous corpus",
                        "minimum_outside_prior_fraction": 0.5,
                        "views": [{"id": "00", "quota": 3, "terms": ["studio"]}],
                    }
                )
            )
            output = root / "candidates.csv"
            summary = root / "summary.json"
            subprocess.run(
                [
                    sys.executable, str(RETRIEVE_SCRIPT), "--db", str(database),
                    "--retrieval", str(retrieval), "--target", "3",
                    "--output", str(output), "--summary", str(summary),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            with output.open(newline="", encoding="utf-8") as handle:
                selected = {row["uuid"] for row in csv.DictReader(handle)}
            self.assertEqual(selected, {"PRIOR-ASSET", "FRESH-ASSET", "FALLBACK-SAFE"})
            self.assertNotIn("EXCLUDED", selected)
            report = json.loads(summary.read_text())
            self.assertEqual(report["excluded_assets"], 1)
            self.assertAlmostEqual(report["outside_prior_fraction"], 2 / 3)


class FrozenVerificationTests(unittest.TestCase):
    def test_wal_aware_snapshot_verifies_new_album_and_topology(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photos = root / "Photos.sqlite"
            writer = sqlite3.connect(photos)
            writer.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE ZASSET(
                  Z_PK INT PRIMARY KEY, ZUUID TEXT, ZKIND INT, ZTRASHEDSTATE INT,
                  ZHIDDEN INT, ZVISIBILITYSTATE INT, ZBUNDLESCOPE INT
                );
                CREATE TABLE ZGENERICALBUM(
                  Z_PK INT PRIMARY KEY, ZUUID TEXT, ZTITLE TEXT, ZPARENTFOLDER INT, ZKIND INT
                );
                CREATE TABLE Z_30ASSETS(Z_30ALBUMS INT, Z_3ASSETS INT);
                INSERT INTO ZASSET VALUES (1, 'ASSET-A', 0, 0, 0, 0, 0);
                INSERT INTO ZGENERICALBUM VALUES (10, 'ROOT', 'Root', NULL, 4000);
                """
            )
            writer.commit()
            writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            writer.executescript(
                """
                INSERT INTO ZGENERICALBUM VALUES (11, 'VERSION', 'Version', 10, 4000);
                INSERT INTO ZGENERICALBUM VALUES (20, 'MASTER', '00 MASTER — 1', 11, 2);
                INSERT INTO Z_30ASSETS VALUES (20, 1);
                """
            )
            writer.commit()

            plan = {
                "plan_id": "wal-test", "source_album_identifier": "visible-library-stills://v1",
                "expected_source_count": 1,
                "folders": [
                    {"key": "root", "title": "Root", "parent_key": None},
                    {"key": "version", "title": "Version", "parent_key": "root"},
                ],
                "albums": [{
                    "title": "00 MASTER — 1", "parent_folder_key": "version",
                    "asset_identifiers": ["ASSET-A/L0/001"],
                }],
            }
            master_manifest = root / "master.csv"
            holds_manifest = root / "holds.csv"
            master_manifest.write_text("uuid\nASSET-A\n")
            holds_manifest.write_text("uuid\n")
            plan["manifest_hashes"] = {
                "master_sha256": hashlib.sha256(master_manifest.read_bytes()).hexdigest(),
                "holds_sha256": hashlib.sha256(holds_manifest.read_bytes()).hexdigest(),
            }
            receipt = {
                "plan_id": "wal-test",
                "folders": [
                    {"key": "root", "title": "Root", "identifier": "ROOT/L0/020"},
                    {"key": "version", "title": "Version", "identifier": "VERSION/L0/020"},
                ],
                "albums": [{"title": "00 MASTER — 1", "identifier": "MASTER/L0/040", "count": 1}],
            }
            plan_path = root / "plan.json"
            receipt_path = root / "receipt.json"
            snapshot = root / "verification.sqlite"
            report = root / "verification.md"
            plan_path.write_text(json.dumps(plan))
            receipt_path.write_text(json.dumps(receipt))

            stale = sqlite3.connect(f"file:{photos}?mode=ro&immutable=1", uri=True)
            self.assertEqual(stale.execute("SELECT COUNT(*) FROM ZGENERICALBUM WHERE ZUUID='MASTER'").fetchone()[0], 0)
            stale.close()
            subprocess.run(
                [sys.executable, str(SNAPSHOT_SCRIPT), "--photos-db", str(photos), "--plan", str(plan_path), "--receipt", str(receipt_path), "--output", str(snapshot)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable, str(VERIFY_SCRIPT), "--photos-db", str(snapshot),
                    "--plan", str(plan_path), "--receipt", str(receipt_path),
                    "--master", str(master_manifest), "--holds", str(holds_manifest),
                    "--report", str(report),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(report.with_suffix(".json").read_text())
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["folder_topology_errors"], 0)
            master_manifest.write_text("uuid\nASSET-B\n")
            failed = subprocess.run(
                [
                    sys.executable, str(VERIFY_SCRIPT), "--photos-db", str(snapshot),
                    "--plan", str(plan_path), "--receipt", str(receipt_path),
                    "--master", str(master_manifest), "--holds", str(holds_manifest),
                    "--report", str(root / "changed.md"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("manifest hash mismatch: master_sha256", (root / "changed.md").read_text())
            writer.close()


if __name__ == "__main__":
    unittest.main()
