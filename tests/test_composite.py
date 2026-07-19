import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.evaluation_split import audit_evaluation_splits
from photo_fieldwork.pipeline import build_catalog_plan, evaluate, validate
from photo_fieldwork.receipts import compare_idempotent_receipts, verify_write_receipt
from photo_fieldwork.public_audit import audit_public_artifact
from photo_fieldwork.release import (
    build_source_manifest,
    master_sha256,
    plan_sha256,
    sample_sha256,
    validate_plan,
)
from photo_fieldwork.runstate import PHASES, advance, initialize, ledger_path, load, recover, verify


class CompositeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {
            "seed": 9,
            "target_count": 2,
            "unclassified_view": "A",
            "minimum_eval_precision": 1.0,
            "minimum_eval_coverage": 1.0,
            "minimum_view_eval_precision": 1.0,
            "minimum_decisive_per_view": 1,
            "minimum_named_people_fraction": 0,
            "minimum_person_free_fraction": 0,
            "views": [{"id": "A", "label": "A", "quota": 2}],
        }
        self.source_rows = [self.row("a"), self.row("b"), self.row("held", safety_status="hold")]
        self.master = [self.row("a", primary_view="A"), self.row("b", primary_view="A")]
        digest = master_sha256(self.master)
        for row in self.master:
            row["master_sha256"] = digest
            row["proposal_id"] = f"pfp-{digest[:16]}"
        self.holds = [self.row("held", safety_status="hold")]
        self.sample = [dict(row, sample_kind="final-holdout", round_id="final-1") for row in self.master]
        sample_digest = sample_sha256(self.sample)
        for row in self.sample:
            row.update(
                {
                    "evaluation_sample_sha256": sample_digest,
                    "judgment": "fit",
                    "visible_reason": "Visible synthetic evidence",
                    "reviewer_actor": "test-editor",
                    "editorial_safety_status": "clear",
                }
            )
        self.source = build_source_manifest(
            self.source_rows,
            source_adapter="synthetic",
            source_identifier="source-1",
            predicate_version="visible-stills-v1",
        )

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def row(uuid, primary_view="", safety_status="clear"):
        return {
            "uuid": uuid,
            "filename": f"{uuid}.jpg",
            "primary_view": primary_view,
            "candidate_views": "A",
            "safety_status": safety_status,
            "selection_reason": "synthetic test selection",
            "persons": "",
        }

    def plan(self):
        evaluation, passed = evaluate(self.sample, self.config, self.master, self.source, "final-holdout")
        self.assertTrue(passed)
        errors, validation = validate(self.master, self.holds, self.config)
        self.assertEqual(errors, [])
        split = audit_evaluation_splits([], self.sample, [])
        return build_catalog_plan(
            self.master,
            self.config,
            "composite-test",
            self.source,
            self.source_rows,
            self.sample,
            [],
            evaluation,
            validation,
            split,
            self.holds,
        )

    def receipt(self, plan, nonce="attempt-1"):
        return {
            "schema_version": 2,
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "candidate_id": plan["candidate_id"],
            "source_membership_sha256": plan["source_membership_sha256"],
            "execution_nonce": nonce,
            "helper_contract_version": 2,
            "helper": {"bundle_id": "example.helper", "version": "3.0", "binary_sha256": "a" * 64},
            "safety_mode": plan["safety_mode"],
            "albums": [
                {"title": album["title"], "count": len(set(album["asset_identifiers"]))}
                for album in plan["albums"]
            ],
        }

    def test_same_count_source_substitution_is_blocked(self):
        substituted = [self.row("a"), self.row("b"), self.row("different")]
        evaluation, _ = evaluate(self.sample, self.config, self.master, self.source, "final-holdout")
        _, validation = validate(self.master, self.holds, self.config)
        split = audit_evaluation_splits([], self.sample, [])
        with self.assertRaisesRegex(ValueError, "source inventory membership"):
            build_catalog_plan(
                self.master,
                self.config,
                "substituted",
                self.source,
                substituted,
                self.sample,
                [],
                evaluation,
                validation,
                split,
                self.holds,
            )

    def test_holdout_audit_detects_related_image_leakage(self):
        tuning = [dict(self.row("tune"), perceptual_cluster_id="cluster-7")]
        holdout = [dict(self.row("holdout"), perceptual_cluster_id="cluster-7")]
        report = audit_evaluation_splits(tuning, holdout, [])
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["leakage"][0]["relation"], "perceptual_cluster_id")

    def test_plan_seal_rejects_post_authorization_mutation(self):
        plan = self.plan()
        validate_plan(plan)
        plan["albums"][0]["asset_identifiers"].append("outside")
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_plan(plan)

    def test_rehashed_plan_cannot_change_candidate_membership(self):
        plan = self.plan()
        for album in plan["albums"]:
            album["asset_identifiers"] = ["outside" if value == "a" else value for value in album["asset_identifiers"]]
        plan["plan_sha256"] = plan_sha256(plan)
        with self.assertRaisesRegex(ValueError, "release candidate"):
            validate_plan(plan)

    def test_planning_recomputes_reports_instead_of_trusting_pass_fields(self):
        evaluation, _ = evaluate(self.sample, self.config, self.master, self.source, "final-holdout")
        _, validation = validate(self.master, self.holds, self.config)
        split = audit_evaluation_splits([], self.sample, [])
        forged = dict(evaluation)
        forged["precision"] = 0.5
        forged["passed"] = True
        with self.assertRaisesRegex(ValueError, "evaluation report was not recomputed"):
            build_catalog_plan(
                self.master,
                self.config,
                "forged-pass",
                self.source,
                self.source_rows,
                self.sample,
                [],
                forged,
                validation,
                split,
                self.holds,
            )

    def test_receipts_require_complete_identity_and_distinct_attempts(self):
        plan = self.plan()
        first = self.receipt(plan, "attempt-1")
        self.assertEqual(verify_write_receipt(plan, first)["status"], "PASS")
        partial = dict(first)
        partial.pop("candidate_id")
        self.assertEqual(verify_write_receipt(plan, partial)["status"], "FAIL")
        second = self.receipt(plan, "attempt-2")
        self.assertEqual(compare_idempotent_receipts(first, second)["status"], "PASS")
        self.assertEqual(compare_idempotent_receipts(first, dict(second, execution_nonce="attempt-1"))["status"], "FAIL")

    def test_event_ledger_recovers_state_and_detects_chain_tampering(self):
        state_path = self.root / "run-state.json"
        receipt = self.root / "receipt.json"
        receipt.write_text('{"status":"PASS"}\n', encoding="utf-8")
        initialize(state_path, "run-1", 2, "source-1")
        advance(state_path, "inventoried", [receipt], expected_revision=1)
        state_path.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match"):
            load(state_path)
        recovered = recover(state_path)
        self.assertEqual(recovered["phase"], "inventoried")
        self.assertEqual(verify(load(state_path), state_path), [])
        ledger = ledger_path(state_path)
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        events[1]["note"] = "rewritten history"
        ledger.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            recover(state_path)

    def test_attempt_ids_are_required_and_cannot_be_reused(self):
        state_path = self.root / "attempt-state.json"
        receipt = self.root / "phase.json"
        receipt.write_text("{}\n", encoding="utf-8")
        state = initialize(state_path, "run-attempts", 2, "source-1")
        for phase in PHASES[1:PHASES.index("write-test-verified")]:
            state = advance(state_path, phase, [receipt], expected_revision=state["revision"])
        with self.assertRaisesRegex(ValueError, "attempt_id"):
            advance(state_path, "write-test-verified", [receipt], expected_revision=state["revision"])
        state = advance(
            state_path,
            "write-test-verified",
            [receipt],
            expected_revision=state["revision"],
            attempt_id="attempt-1",
        )
        for phase in ("production-planned",):
            state = advance(state_path, phase, [receipt], expected_revision=state["revision"])
        with self.assertRaisesRegex(ValueError, "already been used"):
            advance(
                state_path,
                "production-written",
                [receipt],
                expected_revision=state["revision"],
                attempt_id="attempt-1",
            )

    def test_public_audit_fails_closed_without_mutating_private_artifact(self):
        artifact = self.root / "handoff.json"
        original = {
            "title": "Editor selection",
            "uuid": "PRIVATE-ASSET/L0/001",
            "local_path": "/Users/example/private/preview.jpg",
            "raw_ocr": "private text",
        }
        artifact.write_text(json.dumps(original) + "\n", encoding="utf-8")
        before = artifact.read_bytes()
        report = audit_public_artifact(artifact)
        self.assertEqual(report["status"], "FAIL")
        self.assertGreaterEqual(report["finding_count"], 3)
        self.assertEqual(artifact.read_bytes(), before)
        self.assertFalse(report["source_mutated"])


if __name__ == "__main__":
    unittest.main()
