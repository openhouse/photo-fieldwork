from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from photo_fieldwork import pipeline
from photo_fieldwork.runstate import derive_state, init_run, record_phase


ROOT = Path(__file__).resolve().parents[1]


def make_config(quotas: dict[str, int]) -> dict:
    return {
        "schema_version": 1,
        "target_count": sum(quotas.values()),
        "seed": 20260719,
        "unclassified_view": next(iter(quotas)),
        "views": [
            {"id": view_id, "label": view_id.upper(), "quota": quota}
            for view_id, quota in quotas.items()
        ],
        "burst_limit": 2,
        "event_cluster_limit": 0,
        "exploratory_fraction": 0,
        "minimum_named_people_fraction": 0,
        "minimum_person_free_fraction": 0,
        "minimum_eval_precision": 0.75,
        "minimum_eval_coverage": 0.8,
        "minimum_view_precision": 0.75,
        "minimum_view_decisions": 1,
        "require_final_field_audit": True,
    }


def row(uuid: str, views: str, **values: str) -> dict[str, str]:
    item = {
        "uuid": uuid,
        "filename": f"{uuid}.jpg",
        "candidate_views": views,
        "safety_status": "clear",
        "evidence_confidence": "high",
        "visible_context": "synthetic visible evidence",
        "is_photo": "true",
        "pixel_available": "true",
    }
    item.update(values)
    return item


class ReleaseContractEvals(unittest.TestCase):
    def test_prompt_bank_is_specific_and_assertable(self):
        bank = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(bank["skill_name"], "curate-apple-photos")
        ids = [item["id"] for item in bank["evals"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 8)
        self.assertTrue(all(len(item["assertions"]) >= 4 for item in bank["evals"]))

    def test_overlap_aware_assignment_recovers_a_feasible_quota(self):
        config = make_config({"a": 1, "b": 1})
        inventory = [
            row("FLEX", "a;b", favorite="true"),
            row("A-ONLY", "a"),
        ]
        master, _, summary = pipeline.select(inventory, config)
        self.assertEqual(summary["view_counts"], {"a": 1, "b": 1})
        self.assertEqual({item["uuid"] for item in master}, {"FLEX", "A-ONLY"})

    def test_infeasible_assignment_reports_deficits_without_changing_quotas(self):
        config = make_config({"a": 1, "b": 1})
        inventory = [row("A-1", "a"), row("A-2", "a")]
        with self.assertRaisesRegex(ValueError, "deficit"):
            pipeline.select(inventory, config)

    def _release_evidence(self, master: list[dict]) -> tuple[dict, dict, str]:
        self.assertTrue(hasattr(pipeline, "master_sha256"), "master identity is not implemented")
        digest = pipeline.master_sha256(master)
        proposal_id = f"pfp-{digest[:16]}"
        evaluation = {
            "passed": True,
            "final_field_audit": True,
            "master_sha256": digest,
            "proposal_id": proposal_id,
        }
        validation = {
            "status": "PASS",
            "master_sha256": digest,
            "proposal_id": proposal_id,
        }
        return evaluation, validation, digest

    def _build_plan(self, master: list[dict], evaluation: dict, validation: dict) -> dict:
        source_ids = ["SOURCE-1", "SOURCE-2", "SOURCE-3"]
        self.assertTrue(
            hasattr(pipeline, "membership_sha256"),
            "source membership identity is not implemented",
        )
        return pipeline.build_catalog_plan(
            master,
            make_config({"a": 1, "b": 1}),
            "eval-plan",
            "Synthetic source",
            "synthetic://visible-stills",
            evaluation_report=evaluation,
            validation_report=validation,
            source_count=len(source_ids),
            source_membership_sha256=pipeline.membership_sha256(source_ids),
        )

    def test_catalog_plan_is_bound_to_final_evaluation_validation_and_source(self):
        master, _, _ = pipeline.select(
            [row("FLEX", "a;b"), row("A-ONLY", "a")],
            make_config({"a": 1, "b": 1}),
        )
        evaluation, validation, digest = self._release_evidence(master)
        plan = self._build_plan(master, evaluation, validation)
        self.assertEqual(plan["master_sha256"], digest)
        self.assertTrue(plan["evaluation"]["final_field_audit"])
        self.assertEqual(
            plan["evaluation"]["report_sha256"],
            pipeline.content_sha256(evaluation, digest_field="report_sha256"),
        )
        self.assertEqual(plan["validation"]["status"], "PASS")
        self.assertEqual(
            plan["validation"]["report_sha256"],
            pipeline.content_sha256(validation, digest_field="report_sha256"),
        )
        self.assertEqual(plan["source"]["count"], 3)
        self.assertTrue(plan["source"]["membership_sha256"])
        self.assertEqual(plan["plan_sha256"], pipeline.content_sha256(plan))

    def test_catalog_plan_rejects_a_stale_master(self):
        master, _, _ = pipeline.select(
            [row("FLEX", "a;b"), row("A-ONLY", "a")],
            make_config({"a": 1, "b": 1}),
        )
        evaluation, validation, _ = self._release_evidence(master)
        changed = deepcopy(master)
        changed[0]["uuid"] = "REPLACEMENT"
        with self.assertRaisesRegex(ValueError, "master"):
            self._build_plan(changed, evaluation, validation)

    def test_catalog_plan_rejects_a_non_final_evaluation(self):
        master, _, _ = pipeline.select(
            [row("FLEX", "a;b"), row("A-ONLY", "a")],
            make_config({"a": 1, "b": 1}),
        )
        evaluation, validation, _ = self._release_evidence(master)
        evaluation["final_field_audit"] = False
        with self.assertRaisesRegex(ValueError, "final"):
            self._build_plan(master, evaluation, validation)

    def test_plan_digest_exposes_membership_tampering(self):
        master, _, _ = pipeline.select(
            [row("FLEX", "a;b"), row("A-ONLY", "a")],
            make_config({"a": 1, "b": 1}),
        )
        evaluation, validation, _ = self._release_evidence(master)
        plan = self._build_plan(master, evaluation, validation)
        changed = deepcopy(plan)
        changed["albums"][0]["asset_ids"][0] = "UNREVIEWED"
        self.assertNotEqual(changed["plan_sha256"], pipeline.content_sha256(changed))

    def test_master_identity_is_order_independent_and_assignment_sensitive(self):
        master = [
            {"uuid": "ONE", "primary_view": "a"},
            {"uuid": "TWO", "primary_view": "b"},
        ]
        self.assertEqual(pipeline.master_sha256(master), pipeline.master_sha256(reversed(master)))
        reassigned = deepcopy(master)
        reassigned[0]["primary_view"] = "b"
        self.assertNotEqual(pipeline.master_sha256(master), pipeline.master_sha256(reassigned))

    def test_evaluation_rejects_partially_missing_master_identity(self):
        config = make_config({"a": 1})
        feedback = [
            {
                "uuid": "ONE",
                "primary_view": "a",
                "judgment": "fit",
                "master_sha256": "a" * 64,
                "proposal_id": "pfp-aaaaaaaaaaaaaaaa",
            },
            {"uuid": "TWO", "primary_view": "a", "judgment": "fit"},
        ]
        with self.assertRaisesRegex(ValueError, "identity"):
            pipeline.evaluate(feedback, config, final_field=True)

    def test_validation_rejects_a_stale_evaluation_identity(self):
        config = make_config({"a": 1})
        master, holds, _ = pipeline.select([row("ONE", "a")], config)
        sample = pipeline.make_sample(master, 1, 20260719)
        sample[0]["judgment"] = "fit"
        evaluation, passed = pipeline.evaluate(sample, config, final_field=True)
        self.assertTrue(passed)
        evaluation["master_sha256"] = "0" * 64
        errors, _ = pipeline.validate(master, holds, config, evaluation, sample)
        self.assertTrue(any("evaluation" in error and "identity" in error for error in errors))

    def test_overall_precision_cannot_hide_a_weak_view(self):
        config = make_config({"a": 1, "b": 1})
        feedback = [
            {"uuid": f"A-{index}", "primary_view": "a", "judgment": "fit"}
            for index in range(10)
        ]
        feedback.append({"uuid": "B-1", "primary_view": "b", "judgment": "reject"})
        report, passed = pipeline.evaluate(feedback, config)
        self.assertGreater(report["precision"], config["minimum_eval_precision"])
        self.assertFalse(report["by_view"]["b"]["passed"])
        self.assertFalse(passed)

    def test_final_audit_cannot_omit_a_replacement(self):
        config = make_config({"a": 1})
        feedback = [
            {"uuid": f"A-{index}", "primary_view": "a", "judgment": "fit"}
            for index in range(8)
        ]
        feedback.append(
            {"uuid": "REPLACEMENT", "primary_view": "a", "judgment": "", "replacement": "true"}
        )
        report, passed = pipeline.evaluate(feedback, config, final_field=True)
        self.assertEqual(report["replacement_coverage"], 0)
        self.assertFalse(passed)

    def test_protected_assets_are_excluded_before_assignment(self):
        config = make_config({"a": 1, "b": 1})
        inventory = [
            row("CLEAR-A", "a"),
            row("CLEAR-B", "b"),
            row("HOLD", "a", safety_status="hold"),
            row("REVIEW", "b", safety_status="needs-review"),
        ]
        master, holds, _ = pipeline.select(inventory, config)
        self.assertEqual({item["uuid"] for item in master}, {"CLEAR-A", "CLEAR-B"})
        self.assertEqual({item["uuid"] for item in holds}, {"HOLD", "REVIEW"})

    def test_event_capacity_failure_is_reported_as_an_exact_quota_deficit(self):
        config = make_config({"a": 1, "b": 1})
        config["event_cluster_limit"] = 1
        inventory = [
            row("ONE", "a;b", event_cluster="same-event"),
            row("TWO", "a;b", event_cluster="same-event"),
        ]
        with self.assertRaisesRegex(ValueError, "deficit"):
            pipeline.select(inventory, config)

    def test_production_shaped_4000_item_assignment_is_exact_and_deterministic(self):
        quotas = {f"v{index}": 800 for index in range(5)}
        config = make_config(quotas)
        inventory = []
        for view_id in quotas:
            inventory.extend(
                row(f"{view_id}-{index:04d}", view_id)
                for index in range(600)
            )
        for index, view_id in enumerate(quotas):
            next_view = f"v{(index + 1) % len(quotas)}"
            inventory.extend(
                row(f"FLEX-{view_id}-{item:04d}", f"{view_id};{next_view}")
                for item in range(400)
            )
        first, _, first_summary = pipeline.select(inventory, config)
        second, _, second_summary = pipeline.select(list(reversed(inventory)), config)
        self.assertEqual(first_summary["view_counts"], quotas)
        self.assertEqual(second_summary["view_counts"], quotas)
        self.assertEqual(
            {(item["uuid"], item["primary_view"]) for item in first},
            {(item["uuid"], item["primary_view"]) for item in second},
        )

    def test_source_membership_identity_rejects_duplicates(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            pipeline.membership_sha256(["ONE", "ONE"])

    def test_artifact_drift_blocks_receipt_derived_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_run(root, "v01", "eval", 1, "SOURCE", 1)
            artifact = workspace / "reports" / "preflight.json"
            artifact.write_text('{"status":"PASS"}\n', encoding="utf-8")
            record_phase(workspace, "preflight", "pass", outputs=[artifact])
            artifact.write_text('{"status":"CHANGED"}\n', encoding="utf-8")
            state = derive_state(workspace)
            self.assertEqual(state["status"], "blocked")
            self.assertEqual(state["integrity"]["status"], "FAIL")

    def test_artifact_drift_prevents_a_later_passing_phase(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_run(root, "v01", "eval", 1, "SOURCE", 1)
            artifact = workspace / "reports" / "preflight.json"
            artifact.write_text('{"status":"PASS"}\n', encoding="utf-8")
            record_phase(workspace, "preflight", "pass", outputs=[artifact])
            artifact.write_text('{"status":"CHANGED"}\n', encoding="utf-8")
            retrieval = workspace / "reports" / "retrieval.json"
            retrieval.write_text('{"status":"PASS"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity"):
                record_phase(workspace, "retrieval", "pass", outputs=[retrieval])

    def test_missing_receipt_artifact_blocks_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = init_run(root, "v01", "eval", 1, "SOURCE", 1)
            artifact = workspace / "reports" / "preflight.json"
            artifact.write_text('{"status":"PASS"}\n', encoding="utf-8")
            record_phase(workspace, "preflight", "pass", outputs=[artifact])
            artifact.unlink()
            state = derive_state(workspace)
            self.assertEqual(state["status"], "blocked")
            self.assertEqual(state["integrity"]["issues"][0]["kind"], "artifact-missing")


if __name__ == "__main__":
    unittest.main()
