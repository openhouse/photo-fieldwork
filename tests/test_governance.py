import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.governance import (
    append_decision_event,
    audit_evaluation_split,
    build_release_seal,
    read_decision_events,
    seal_decision_event,
    verify_decision_events,
    verify_release_seal,
)
from photo_fieldwork.integrity import attach_plan_digest
from photo_fieldwork.pipeline import build_catalog_plan, make_sample, select


def config() -> dict:
    return {
        "seed": 17,
        "target_count": 2,
        "unclassified_view": "00",
        "allow_unclassified_fallback": False,
        "require_explicit_safety_status": True,
        "require_evaluation_binding": True,
        "require_per_view_sufficiency": True,
        "minimum_eval_coverage": 1.0,
        "minimum_eval_precision": 0.75,
        "minimum_view_precision": 0.65,
        "minimum_decisive_per_view": 1,
        "views": [
            {"id": "00", "label": "Unclassified", "quota": 0},
            {"id": "A", "label": "A", "quota": 1},
            {"id": "B", "label": "B", "quota": 1},
        ],
    }


def decision(previous: str = "") -> dict:
    return seal_decision_event({
        "schema_version": 1,
        "event_id": "decision-01",
        "occurred_at": "2026-07-19T00:00:00+00:00",
        "run_id": "test",
        "event_type": "safety-cleared",
        "actor_id": "editor-01",
        "actor_kind": "human",
        "authority_scope": "safety",
        "asset_uuid": "A/L0/001",
        "previous_state": "needs-review",
        "new_state": "clear",
        "reason": "Human review of a synthetic fixture.",
    }, previous)


class GovernanceTests(unittest.TestCase):
    def test_decision_chain_detects_tampering_and_reserves_human_authority(self):
        event = decision()
        self.assertEqual(verify_decision_events([event]), [])
        event["reason"] = "Changed later."
        self.assertTrue(verify_decision_events([event]))
        with self.assertRaisesRegex(ValueError, "identified human"):
            seal_decision_event({**decision(), "actor_kind": "automation"}, "")
        incomplete = {key: value for key, value in decision().items() if key not in {
            "asset_uuid", "event_sha256", "previous_event_sha256",
        }}
        with self.assertRaisesRegex(ValueError, "asset UUID"):
            seal_decision_event(incomplete, "")
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            seal_decision_event({**decision(), "ambient_note": "not in contract"}, "")

    def test_decision_ledger_appends_and_revalidates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            append_decision_event(path, {key: value for key, value in decision().items() if key not in {
                "event_sha256", "previous_event_sha256",
            }})
            self.assertEqual(len(read_decision_events(path)), 1)
            path.write_text(path.read_text(encoding="utf-8").replace("Human review", "Edited review"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                read_decision_events(path)

    def test_holdout_audit_detects_asset_and_cluster_leakage(self):
        clean = audit_evaluation_split(
            [{"uuid": "T", "duplicate_group": "one"}],
            [{"uuid": "H", "duplicate_group": "two"}],
            [{"uuid": "C", "duplicate_group": "three"}],
        )
        self.assertEqual(clean["status"], "PASS")
        leaky = audit_evaluation_split(
            [{"uuid": "T", "perceptual_cluster_id": "shared"}],
            [{"uuid": "H", "perceptual_cluster_id": "shared"}],
            [],
        )
        self.assertEqual(leaky["status"], "FAIL")
        self.assertEqual(leaky["leakage"]["tuning_cluster_overlap_count"], 1)
        self.assertFalse(leaky["private_identifiers_included"])
        alias_leak = audit_evaluation_split(
            [{"uuid": "T2", "duplicate_group": "shared"}],
            [{"uuid": "H2", "duplicate_group_id": "shared"}],
            [],
        )
        self.assertEqual(alias_leak["status"], "FAIL")
        self.assertEqual(alias_leak["leakage"]["tuning_cluster_overlap_count"], 1)

    def test_release_seal_recomputes_and_binds_candidate(self):
        cfg = config()
        inventory = [
            {"uuid": "A", "filename": "a.jpg", "candidate_views": "A", "safety_status": "clear"},
            {"uuid": "B", "filename": "b.jpg", "candidate_views": "B", "safety_status": "clear"},
        ]
        master, holds, _ = select(inventory, cfg)
        feedback = make_sample(master, 1, 17)
        for row in feedback:
            row["judgment"] = "fit"
            row["visible_reason"] = "Synthetic visible fit."
        plan = build_catalog_plan(master, cfg, "test", "Source", "SOURCE", ["A", "B"])
        plan["created_at"] = "2026-07-19T00:00:00+00:00"
        plan = attach_plan_digest(plan)
        holdout_rows = [{"uuid": "HOLDOUT", "duplicate_group": "holdout"}]
        canary_rows = [{"uuid": "CANARY", "duplicate_group": "canary"}]
        safety_baseline = [dict(row) for row in master]
        safety_baseline[0]["safety_status"] = "needs-review"
        holdout = audit_evaluation_split(feedback, holdout_rows, canary_rows)
        seal = build_release_seal(
            config=cfg,
            master=master,
            holds=holds,
            feedback=feedback,
            holdout=holdout_rows,
            canaries=canary_rows,
            safety_baseline=safety_baseline,
            catalog_plan=plan,
            decision_events=[decision()],
            holdout_report=holdout,
        )
        self.assertEqual(verify_release_seal(seal), [])
        self.assertEqual(seal["release_class"], "editor-field")
        self.assertFalse(seal["publication_clearance"])

        forged = json.loads(json.dumps(holdout))
        forged["leakage"]["tuning_uuid_overlap_count"] = 1
        with self.assertRaisesRegex(ValueError, "leakage counts"):
            build_release_seal(
                config=cfg,
                master=master,
                holds=holds,
                feedback=feedback,
                holdout=holdout_rows,
                canaries=canary_rows,
                safety_baseline=safety_baseline,
                catalog_plan=plan,
                decision_events=[decision()],
                holdout_report=forged,
            )

        changed = [dict(row) for row in master]
        changed[0]["safety_status"] = "needs-review"
        with self.assertRaisesRegex(ValueError, "validation|master"):
            build_release_seal(
                config=cfg,
                master=changed,
                holds=holds,
                feedback=feedback,
                holdout=holdout_rows,
                canaries=canary_rows,
                safety_baseline=safety_baseline,
                catalog_plan=plan,
                decision_events=[decision()],
                holdout_report=holdout,
            )

        stale_feedback = [dict(row) for row in feedback]
        stale_feedback[0]["duplicate_group"] = "holdout"
        with self.assertRaisesRegex(ValueError, "current split|recomputed split"):
            build_release_seal(
                config=cfg,
                master=master,
                holds=holds,
                feedback=stale_feedback,
                holdout=holdout_rows,
                canaries=canary_rows,
                safety_baseline=safety_baseline,
                catalog_plan=plan,
                decision_events=[decision()],
                holdout_report=holdout,
            )

        publication_decision = seal_decision_event({
            "schema_version": 1,
            "event_id": "publication-decision-01",
            "occurred_at": "2026-07-19T00:00:00+00:00",
            "run_id": "test",
            "event_type": "publication-approved",
            "actor_id": "publisher-01",
            "actor_kind": "human",
            "authority_scope": "publication",
            "asset_uuid": master[0]["uuid"],
            "reason": "Synthetic publication decision outside editor-field scope.",
        }, "")
        with self.assertRaisesRegex(ValueError, "cannot include publication approval"):
            build_release_seal(
                config=cfg,
                master=master,
                holds=holds,
                feedback=feedback,
                holdout=holdout_rows,
                canaries=canary_rows,
                safety_baseline=safety_baseline,
                catalog_plan=plan,
                decision_events=[publication_decision],
                holdout_report=holdout,
            )

        unrelated = {key: value for key, value in decision().items() if key not in {
            "event_sha256", "previous_event_sha256",
        }}
        unrelated["run_id"] = "unrelated-run"
        with self.assertRaisesRegex(ValueError, "released run"):
            build_release_seal(
                config=cfg,
                master=master,
                holds=holds,
                feedback=feedback,
                holdout=holdout_rows,
                canaries=canary_rows,
                safety_baseline=safety_baseline,
                catalog_plan=plan,
                decision_events=[seal_decision_event(unrelated, "")],
                holdout_report=holdout,
            )

        with self.assertRaisesRegex(ValueError, "without a matching human safety-clearance"):
            build_release_seal(
                config=cfg,
                master=master,
                holds=holds,
                feedback=feedback,
                holdout=holdout_rows,
                canaries=canary_rows,
                safety_baseline=safety_baseline,
                catalog_plan=plan,
                decision_events=[seal_decision_event({
                    "schema_version": 1,
                    "event_id": "editorial-only",
                    "occurred_at": "2026-07-19T00:00:00+00:00",
                    "run_id": "test",
                    "event_type": "editorial-assignment",
                    "actor_id": "editor-01",
                    "actor_kind": "human",
                    "authority_scope": "editorial",
                    "reason": "No safety authority is claimed.",
                }, "")],
                holdout_report=holdout,
            )


if __name__ == "__main__":
    unittest.main()
