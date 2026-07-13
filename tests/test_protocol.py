import argparse
import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.contracts import (
    canonical_asset_id,
    load_source_profile,
    normalize_row,
    seal_plan,
    verify_plan_digest,
)
from photo_fieldwork.pipeline import build_catalog_plan, evaluate, read_config, read_csv, select, validate
from photo_fieldwork.practice import create_demo_inventory
from photo_fieldwork.retrieval import allocate_candidates
from photo_fieldwork.safety import apply_safety_policy
from photo_fieldwork.workflow import (
    apply_feedback,
    build_inspection_ledger,
    completion_report,
    duplicate_audit,
    lint_catalog_plan,
    transition_run_state,
)


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_identifier_and_boolean_normalization(self):
        self.assertEqual(canonical_asset_id("ABC/L0/040"), "ABC")
        self.assertEqual(normalize_row({"uuid": "ABC/L0/001", "favorite": "1"})["favorite"], "true")
        self.assertEqual(normalize_row({"uuid": "ABC", "favorite": "no"})["favorite"], "false")
        with self.assertRaises(ValueError):
            normalize_row({"uuid": "ABC", "favorite": "sometimes"})

    def test_source_profile_is_validated_and_fingerprinted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "id": "visible-library-stills://v1",
                "title": "Visible stills",
                "kind": "visible-library-query",
                "expected_count": 600000,
            }))
            profile = load_source_profile(path)
            self.assertEqual(len(profile["fingerprint"]), 64)

    def test_plan_digest_detects_mutation(self):
        plan = seal_plan({"plan_id": "one", "albums": []})
        self.assertTrue(verify_plan_digest(plan))
        plan["plan_id"] = "two"
        self.assertFalse(verify_plan_digest(plan))

    def test_quality_gate_waiver_requires_a_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            config = json.loads((ROOT / "config" / "starter.json").read_text())
            config["views"][0]["quality_gate_waived"] = True
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "waiver requires a reason"):
                read_config(path)


class RetrievalTests(unittest.TestCase):
    def test_view_reservations_are_independent_of_input_order(self):
        scores = {
            "01": {"SHARED": 10, "A": 9, "B": 8},
            "02": {"SHARED": 10, "C": 9, "D": 8},
        }
        views = [{"id": "01", "quota": 2}, {"id": "02", "quota": 2}]
        first = allocate_candidates(scores, views, 4, multiplier=1)
        second = allocate_candidates(scores, list(reversed(views)), 4, multiplier=1)
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1], second[1])
        self.assertEqual({"01": 2, "02": 2}, first[2]["reserved_by_view"])

    def test_outside_prior_floor_replaces_lower_priority_prior_assets(self):
        scores = {"01": {"A": 10, "B": 9, "C": 8, "D": 7, "E": 6, "F": 5}}
        selected, _, report = allocate_candidates(
            scores,
            [{"id": "01", "quota": 4}],
            4,
            multiplier=1,
            prior_ids={"A", "B", "C", "D"},
            minimum_outside_prior_fraction=0.5,
        )
        self.assertEqual(sum(uuid not in {"A", "B", "C", "D"} for uuid in selected), 2)
        self.assertEqual(report["outside_prior_selected"], 2)

    def test_impossible_outside_prior_floor_fails(self):
        with self.assertRaisesRegex(ValueError, "outside-prior floor unavailable"):
            allocate_candidates(
                {"01": {"A": 10, "B": 9}},
                [{"id": "01", "quota": 2}],
                2,
                multiplier=1,
                prior_ids={"A", "B"},
                minimum_outside_prior_fraction=0.5,
            )


class SafetyTests(unittest.TestCase):
    def test_relational_album_rule_propagates_hold(self):
        rows = [{"uuid": "A", "albums": "Public;Private Review 2026", "safety_status": "clear"}]
        policy = {"schema_version": 1, "rules": [{
            "id": "private-family",
            "relation": "albums",
            "match": "contains",
            "values": ["private review"],
            "action": "hold",
            "reason": "protected album family",
        }]}
        updated, decisions = apply_safety_policy(rows, policy)
        self.assertEqual(updated[0]["safety_status"], "hold")
        self.assertEqual(decisions[0]["rule_id"], "private-family")

    def test_positive_source_face_count_survives_detector_zero(self):
        rows = [{"uuid": "A", "source_face_count": "2", "inspected_face_count": "0"}]
        updated, _ = apply_safety_policy(rows, {"schema_version": 1, "rules": []})
        self.assertEqual(updated[0]["known_face_count"], "2")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inventory_path = self.root / "inventory.csv"
        create_demo_inventory(self.inventory_path)
        self.inventory = read_csv(self.inventory_path)
        self.config = read_config(ROOT / "config" / "starter.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_inspection_ledger_reuses_identical_policy_and_rejects_raw_ocr(self):
        inspection = self.root / "inspection.jsonl"
        inspection.write_text(json.dumps({
            "asset_identifier": "A/L0/001",
            "pixel_available": True,
            "preview_exported": False,
        }) + "\n")
        batch = {
            "inspection_jsonl": str(inspection),
            "helper_version": "1",
            "target_long_edge": 1280,
            "classifier_policy": "vision-v1",
            "safety_ruleset_version": "safe-v1",
            "source_fingerprint": "source-v1",
        }
        entries, report = build_inspection_ledger({"schema_version": 1, "batches": [batch, batch]})
        self.assertEqual(len(entries), 1)
        self.assertEqual(report["reused_identical_inspections"], 1)
        inspection.write_text(json.dumps({"asset_identifier": "A", "ocr_text": "private"}) + "\n")
        with self.assertRaisesRegex(ValueError, "raw OCR"):
            build_inspection_ledger({"schema_version": 1, "batches": [batch]})

    def test_duplicate_audit_finds_different_uuids_with_same_preview(self):
        audit, report = duplicate_audit([
            {"uuid": "A", "preview_sha256": "same"},
            {"uuid": "B", "preview_sha256": "same"},
        ])
        self.assertEqual(report["duplicate_clusters"], 1)
        self.assertEqual({row["uuid"] for row in audit}, {"A", "B"})

    def test_per_view_failure_blocks_overall_evaluation_pass(self):
        feedback = []
        for uuid, view, judgment in [
            ("A", "00", "fit"), ("B", "01", "reject"), ("C", "02", "fit"),
            ("D", "03", "fit"), ("E", "04", "fit"),
        ]:
            feedback.append({
                "uuid": uuid, "primary_view": view, "judgment": judgment,
                "visible_reason": "synthetic fixture", "safety_status": "clear",
                "error_category": "visible-fit" if judgment == "fit" else "retrieval-mismatch",
                "round_id": "test-01", "reviewer_lens": "unit-test",
            })
        report, passed = evaluate(feedback, self.config)
        self.assertFalse(passed)
        self.assertEqual(report["failed_views"], ["01"])

    def test_feedback_creates_pending_replacement_audit(self):
        master, _, _ = select(self.inventory, self.config)
        feedback = [{"uuid": master[0]["uuid"], "judgment": "reject", "safety_status": "clear"}]
        next_master, _, decisions, replacements = apply_feedback(master, self.inventory, feedback, self.config)
        self.assertEqual(len(next_master), self.config["target_count"])
        self.assertEqual(len(decisions), 1)
        self.assertTrue(replacements)
        errors, _ = validate(next_master, [], self.config)
        self.assertTrue(any("pending replacement" in error for error in errors))

    def test_feedback_needs_review_is_excluded_from_master(self):
        master, _, _ = select(self.inventory, self.config)
        target = master[0]["uuid"]
        feedback = [{"uuid": target, "judgment": "uncertain", "safety_status": "needs-review"}]
        next_master, holds, _, _ = apply_feedback(master, self.inventory, feedback, self.config)
        self.assertNotIn(target, {row["uuid"] for row in next_master})
        self.assertIn(target, {row["uuid"] for row in holds})

    def test_plan_lint_checks_source_and_inspections(self):
        master, holds, _ = select(self.inventory, self.config)
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", 24)
        profile = {"id": "SOURCE-1", "expected_count": 24}
        report = lint_catalog_plan(
            plan,
            master,
            holds,
            self.config,
            inspected_ids={row["uuid"] for row in master},
            source_profile=profile,
        )
        self.assertEqual(report["status"], "PASS")
        mutated = dict(plan)
        mutated["plan_id"] = "mutated"
        report = lint_catalog_plan(mutated, master, holds, self.config, source_profile=profile)
        self.assertIn("plan digest is missing or does not match", report["errors"])
        report = lint_catalog_plan(
            plan,
            master,
            holds,
            self.config,
            inspected_ids=set(),
            source_profile={"id": "WRONG", "expected_count": 24},
        )
        self.assertEqual(report["status"], "FAIL")

    def test_run_state_is_append_only_and_completed_phases_do_not_regress(self):
        state_path = self.root / "run-state.json"
        state_path.write_text(json.dumps({
            "run_id": "test",
            "status": "initialized",
            "phases": {"brief": "pending"},
        }))
        state = transition_run_state(state_path, "brief", "completed", "brief.md")
        self.assertEqual(state["history"][0]["evidence"], "brief.md")
        with self.assertRaisesRegex(ValueError, "cannot move backward"):
            transition_run_state(state_path, "brief", "in_progress")

    def test_completion_report_is_derived_from_artifacts(self):
        (self.root / "reports").mkdir()
        (self.root / "manifests").mkdir()
        (self.root / "run-state.json").write_text(json.dumps({
            "run_id": "run-one",
            "status": "active",
            "target_count": 12,
            "phases": {"brief": "completed"},
        }))
        (self.root / "reports" / "validation-report.json").write_text(json.dumps({"status": "PASS"}))
        report, markdown = completion_report(self.root)
        self.assertEqual(report["artifacts"]["validation"][0]["data"]["status"], "PASS")
        self.assertIn("Publication clearance", markdown)


if __name__ == "__main__":
    unittest.main()
