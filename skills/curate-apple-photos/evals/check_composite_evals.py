#!/usr/bin/env python3
"""Validate the public eval bank and run its executable composite canaries."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVALS = Path(__file__).with_name("evals.json")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

EXECUTABLE_CONTRACTS = [
    "tests.test_eval_split.EvaluationSplitTests.test_uuid_and_perceptual_cluster_leakage_fail",
    "tests.test_eval_split.EvaluationSplitTests.test_disjoint_holdout_passes_without_exposing_identifiers",
    "tests.test_pipeline.PipelineTests.test_selection_reports_exact_view_scarcity_without_rebalancing",
    "tests.test_pipeline.PipelineTests.test_validation_rejects_silent_quota_rebalancing",
    "tests.test_decision_ledger.DecisionLedgerTests.test_append_only_chain_records_supersession",
    "tests.test_decision_ledger.DecisionLedgerTests.test_tampering_breaks_the_chain",
    "tests.test_decision_ledger.DecisionLedgerTests.test_materialization_applies_latest_assignment_and_related_hold",
    "tests.test_decision_ledger.DecisionLedgerTests.test_automation_cannot_record_safety_clearance",
    "tests.test_release.ReleaseTests.test_release_seal_binds_candidate_and_defaults_publication_closed",
    "tests.test_release.ReleaseTests.test_post_seal_config_drift_fails_audit",
    "tests.test_release.ReleaseTests.test_source_fingerprint_must_match_plan",
    "tests.test_release.ReleaseTests.test_publication_review_is_separate_and_default_closed",
    "tests.test_skill_bridge.SkillBridgeTests.test_bridge_rejects_a_receipt_copied_from_another_plan",
    "tests.test_verify_photos_commit.PhotosVerifierTests.test_receipt_identity_mismatch_fails_verification",
]


def validate_bank() -> dict:
    bank = json.loads(EVALS.read_text(encoding="utf-8"))
    cases = bank.get("evals", [])
    errors = []
    if bank.get("skill_name") != "curate-apple-photos":
        errors.append("unexpected skill_name")
    ids = [case.get("id") for case in cases]
    if ids != list(range(1, 19)):
        errors.append("eval IDs must be contiguous from 1 through 18")
    if len({case.get("prompt") for case in cases}) != len(cases):
        errors.append("eval prompts must be unique")
    expectations = 0
    for case in cases:
        if not str(case.get("prompt", "")).strip() or not str(case.get("expected_output", "")).strip():
            errors.append(f"eval {case.get('id')} lacks prompt or expected output")
        case_expectations = case.get("expectations", [])
        expectations += len(case_expectations)
        if len(case_expectations) < 3 or not all(str(item).strip() for item in case_expectations):
            errors.append(f"eval {case.get('id')} lacks a usable expectation contract")
        for relative in case.get("files", []):
            if not (EVALS.parent.parent / relative).is_file():
                errors.append(f"eval {case.get('id')} fixture is missing: {relative}")
    corpus = json.dumps(bank).lower()
    for phrase in (
        "source substitution",
        "perceptual-cluster",
        "exact-quota deficit",
        "diversity-floor swap",
        "release-seal audit",
        "append-only event",
        "copied receipt",
        "related frame cluster",
        "publication review",
        "positive control",
    ):
        if phrase not in corpus:
            errors.append(f"eval coverage is missing: {phrase}")
    positive = next((case for case in cases if case.get("id") == 18), {})
    if "proceeds to the bounded write test" not in str(positive.get("expected_output", "")):
        errors.append("eval bank lacks a proceed-oriented positive control")
    if errors:
        raise ValueError("; ".join(errors))
    return {"cases": len(cases), "expectations": expectations, "positive_controls": 1}


def main() -> int:
    structural = validate_bank()
    suite = unittest.defaultTestLoader.loadTestsFromNames(EXECUTABLE_CONTRACTS)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    report = {
        "structural": {"status": "PASS", **structural},
        "executable": {
            "status": "PASS" if result.wasSuccessful() else "FAIL",
            "contracts": suite.countTestCases(),
            "failures": len(result.failures),
            "errors": len(result.errors),
        },
    }
    print(json.dumps(report, indent=2))
    return 0 if result.wasSuccessful() else 2


if __name__ == "__main__":
    raise SystemExit(main())
