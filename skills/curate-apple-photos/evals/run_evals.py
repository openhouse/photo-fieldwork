#!/usr/bin/env python3
"""Run deterministic, synthetic contract evals for curate-apple-photos."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from photo_fieldwork.feedback import apply_feedback, sample_fingerprint, validate_feedback  # noqa: E402
from photo_fieldwork.pipeline import assign_exact_quotas, build_catalog_plan, evaluate, select  # noqa: E402
from photo_fieldwork.source import build_source_profile, verify_source_profile  # noqa: E402
from photo_fieldwork.state import initialize_run, recover_state, transition_phase  # noqa: E402


def config(quotas: dict[str, int]) -> dict:
    return {
        "seed": 20260719,
        "target_count": sum(quotas.values()),
        "unclassified_view": next(iter(quotas)),
        "views": [{"id": key, "label": key, "quota": value} for key, value in quotas.items()],
        "minimum_eval_coverage": 1.0,
        "minimum_eval_precision": 0.75,
        "maximum_eval_uncertainty": 0.2,
        "minimum_decisive_per_view": 1,
        "minimum_view_precision": 0.5,
        "maximum_view_uncertainty": 0.5,
    }


def expect_error(operation, contains: str = "") -> str:
    try:
        operation()
    except (OSError, ValueError) as error:
        if contains and contains not in str(error):
            raise AssertionError(f"expected error containing {contains!r}; got {error!r}") from error
        return str(error)
    raise AssertionError("operation unexpectedly succeeded")


def reviewed_rows(rows: list[dict], judgments: list[str]) -> list[dict]:
    fingerprint = sample_fingerprint(rows)
    result = []
    for row, judgment in zip(rows, judgments, strict=True):
        item = dict(row)
        item.update(
            {
                "judgment": judgment,
                "visible_reason": "Synthetic visible evidence",
                "safety_status": "clear_automated",
                "error_category": "visible-fit" if judgment == "fit" else "taxonomy-coercion",
                "round_id": "synthetic-round",
                "reviewer_lens": "contract-eval",
                "sample_hash": fingerprint,
            }
        )
        result.append(item)
    return result


def eval_source_membership_drift() -> dict:
    profile = build_source_profile(
        [{"uuid": "SYN-001"}, {"uuid": "SYN-002"}],
        profile_id="synthetic://source",
        kind="synthetic",
        scope="contract eval",
        inventory="synthetic",
    )
    errors = verify_source_profile(profile, ["SYN-001", "SYN-003"])
    assert len(errors) == 1 and "fingerprint changed" in errors[0]
    return {"same_count": True, "errors": errors}


def eval_overlapping_exact_quotas() -> dict:
    settings = config({"A": 1, "B": 1})
    rows = [
        {"uuid": "SYN-FLEX", "filename": "flex.jpg", "candidate_views": "B;A"},
        {"uuid": "SYN-A", "filename": "a.jpg", "candidate_views": "A"},
    ]
    first, counts = assign_exact_quotas(rows, settings)
    second, _ = assign_exact_quotas(list(reversed(rows)), settings)
    assignments = {row["uuid"]: row["primary_view"] for row in first}
    assert assignments == {row["uuid"]: row["primary_view"] for row in second}
    assert counts == {"A": 1, "B": 1}
    impossible = [
        {"uuid": "SYN-1", "filename": "one.jpg", "candidate_views": "A"},
        {"uuid": "SYN-2", "filename": "two.jpg", "candidate_views": "A"},
    ]
    diagnostic = expect_error(lambda: assign_exact_quotas(impossible, settings), "B: short 1, candidates 0")
    return {"assignments": assignments, "diagnostic": diagnostic}


def eval_stratified_metric_trap() -> dict:
    settings = config({"A": 2, "B": 2})
    sample = [
        {"uuid": "SYN-A1", "primary_view": "A", "score_total": "1"},
        {"uuid": "SYN-A2", "primary_view": "A", "score_total": "2"},
        {"uuid": "SYN-B1", "primary_view": "B", "score_total": "1"},
        {"uuid": "SYN-B2", "primary_view": "B", "score_total": "2"},
    ]
    feedback = reviewed_rows(sample, ["fit", "fit", "uncertain", "uncertain"])
    report, passed = evaluate(feedback, settings)
    assert not passed
    assert report["decisive_precision"] == 1.0
    assert "overall uncertainty rate above maximum" in report["gate_failures"]
    assert "view B has too few decisive judgments" in report["gate_failures"]
    return {"gate_failures": report["gate_failures"]}


def eval_uuid_feedback_integrity() -> dict:
    sample = [
        {"uuid": "SYN-1", "primary_view": "A", "score_total": "1", "safety_status": "clear_automated"},
        {"uuid": "SYN-2", "primary_view": "A", "score_total": "2", "safety_status": "clear_automated"},
    ]
    decisions = list(reversed(reviewed_rows(sample, ["fit", "reject"])))
    reviewed, removed, _ = apply_feedback(sample, sample, decisions)
    assert [row["uuid"] for row in reviewed] == ["SYN-1"]
    assert [row["uuid"] for row in removed] == ["SYN-2"]
    duplicate = [decisions[0], decisions[0]]
    expect_error(lambda: validate_feedback(sample, duplicate), "duplicate UUIDs")
    stale = deepcopy(decisions)
    stale[0]["sample_hash"] = "sha256:" + "0" * 64
    expect_error(lambda: validate_feedback(sample, stale), "sample_hash")
    return {"reviewed": ["SYN-1"], "removed": ["SYN-2"]}


def eval_relational_safety_propagation() -> dict:
    settings = config({"A": 2})
    inventory = [
        {
            "uuid": "SYN-HOLD",
            "filename": "hold.jpg",
            "candidate_views": "A",
            "duplicate_group": "DUP-1",
            "safety_status": "restricted_private",
        },
        {
            "uuid": "SYN-RELATED",
            "filename": "related.jpg",
            "candidate_views": "A",
            "duplicate_group": "DUP-1",
            "safety_status": "clear_automated",
        },
        {
            "uuid": "SYN-BURST-HOLD",
            "filename": "burst-hold.jpg",
            "candidate_views": "A",
            "burst_group": "BURST-1",
            "safety_status": "review_sensitive",
        },
        {
            "uuid": "SYN-BURST-RELATED",
            "filename": "burst-related.jpg",
            "candidate_views": "A",
            "burst_group": "BURST-1",
            "safety_status": "clear_automated",
        },
        {"uuid": "SYN-CLEAR-1", "filename": "clear-1.jpg", "candidate_views": "A"},
        {"uuid": "SYN-CLEAR-2", "filename": "clear-2.jpg", "candidate_views": "A"},
    ]
    master, holds, _ = select(inventory, settings)
    held = {row["uuid"] for row in holds}
    assert {"SYN-HOLD", "SYN-RELATED", "SYN-BURST-HOLD", "SYN-BURST-RELATED"} <= held
    assert not held & {row["uuid"] for row in master}
    return {"held": sorted(held)}


def eval_post_review_drift_seal() -> dict:
    from photo_fieldwork.integrity import create_evaluation_seal, verify_evaluation_seal

    settings = config({"A": 2})
    master = [
        {"uuid": "SYN-1", "primary_view": "A", "safety_status": "clear_automated"},
        {"uuid": "SYN-2", "primary_view": "A", "safety_status": "clear_automated"},
    ]
    report = {"passed": True, "decisive_precision": 1.0, "uncertainty_rate": 0.0}
    seal = create_evaluation_seal(master, settings, report)
    assert verify_evaluation_seal(seal, master, settings) == []
    plan = build_catalog_plan(
        master,
        settings,
        "synthetic-plan",
        "Synthetic source",
        "SYNTHETIC-SOURCE",
        evaluation_seal=seal,
        evaluation_report=report,
    )
    assert plan["candidate_binding"]["evaluation_seal_fingerprint"] == seal["seal_fingerprint"]
    changed_master = deepcopy(master)
    changed_master[1]["uuid"] = "SYN-3"
    assert any("master" in error for error in verify_evaluation_seal(seal, changed_master, settings))
    expect_error(
        lambda: build_catalog_plan(
            changed_master,
            settings,
            "synthetic-drifted-plan",
            "Synthetic source",
            "SYNTHETIC-SOURCE",
            evaluation_seal=seal,
            evaluation_report=report,
        ),
        "does not authorize this plan",
    )
    changed_config = deepcopy(settings)
    changed_config["seed"] += 1
    assert any("config" in error for error in verify_evaluation_seal(seal, master, changed_config))
    changed_report = deepcopy(report)
    changed_report["uncertainty_rate"] = 0.5
    expect_error(
        lambda: build_catalog_plan(
            master,
            settings,
            "synthetic-report-drift-plan",
            "Synthetic source",
            "SYNTHETIC-SOURCE",
            evaluation_seal=seal,
            evaluation_report=changed_report,
        ),
        "does not authorize this plan",
    )
    return {"seal": seal["seal_fingerprint"], "plan_binding": plan["candidate_binding"]}


def eval_preview_decode_integrity() -> dict:
    from photo_fieldwork.preview import verify_preview_exports
    from PIL import Image

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        valid = root / "SYN-VALID.jpg"
        buffer = io.BytesIO()
        Image.new("RGB", (1, 1), "white").save(buffer, "JPEG")
        valid.write_bytes(buffer.getvalue())
        records = [
            {"uuid": "SYN-VALID", "preview_exported": True},
            {"uuid": "SYN-MISSING", "preview_exported": True},
        ]
        report = verify_preview_exports(records, root)
        assert not report["passed"]
        assert report["valid_count"] == 1
        assert any("SYN-MISSING" in error for error in report["errors"])
        valid.write_bytes(
            bytes.fromhex(
                "FFD8FFC00011080001000103012200021101031101FFDA000C03010002110311003F0000FFD9"
            )
        )
        corrupt = verify_preview_exports(records[:1], root)
        assert not corrupt["passed"] and any("SYN-VALID" in error for error in corrupt["errors"])
        return {"missing_errors": report["errors"], "corrupt_errors": corrupt["errors"]}


def eval_final_holdout_freshness() -> dict:
    from photo_fieldwork.integrity import evaluate_freshness

    report = evaluate_freshness(
        ["SYN-NEW-1", "SYN-OLD-1", "SYN-NEW-2"],
        ["SYN-OLD-1", "SYN-OLD-2"],
        minimum_fresh_fraction=1.0,
        require_disjoint=True,
    )
    assert not report["passed"]
    assert report["fresh_count"] == 2
    assert report["reused_identifiers"] == ["SYN-OLD-1"]
    return report


def eval_resumable_ledger_cas() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary) / "run"
        initial = initialize_run(run, "synthetic-run", ["review"])
        artifact = run / "review.json"
        artifact.write_text("{}\n", encoding="utf-8")
        completed = transition_phase(run, "review", "completed", initial["revision"], artifact)
        (run / "run-state.json").write_text("{broken", encoding="utf-8")
        recovered = recover_state(run)
        assert recovered["revision"] == completed["revision"]
        assert recovered["artifacts"]["review"]["sha256"].startswith("sha256:")
        expect_error(
            lambda: transition_phase(run, "review", "started", initial["revision"]),
            "revision conflict",
        )
        return {"revision": recovered["revision"], "status": recovered["status"]}


def eval_four_thousand_item_scale() -> dict:
    quotas = {"A": 1000, "B": 1000, "C": 1000, "D": 1000}
    settings = config(quotas)
    rows = []
    for view in quotas:
        for index in range(1000):
            rows.append(
                {
                    "uuid": f"SYN-{view}-{index:04d}",
                    "filename": f"{view}-{index:04d}.jpg",
                    "candidate_views": view,
                }
            )
    started = time.perf_counter()
    selected, counts = assign_exact_quotas(list(reversed(rows)), settings)
    elapsed = time.perf_counter() - started
    assert len(selected) == 4000
    assert len({row["uuid"] for row in selected}) == 4000
    assert counts == quotas
    assert elapsed < 5.0, f"4,000-item assignment took {elapsed:.3f}s"
    return {"selected_count": len(selected), "elapsed_seconds": round(elapsed, 4), "threshold_seconds": 5.0}


def eval_cluster_clean_holdout() -> dict:
    from photo_fieldwork.eval_split import audit_eval_split

    tuning = [
        {"uuid": "SYN-TUNE", "perceptual_cluster_id": "P-1"},
        {"uuid": "SYN-TUNE-2", "duplicate_group": "D-1"},
    ]
    holdout = [
        {"uuid": "SYN-FRESH-1", "perceptual_cluster_id": "P-1"},
        {"uuid": "SYN-FRESH-2", "burst_group": "B-1", "duplicate_group": "D-HOLDOUT"},
        {"uuid": "SYN-FRESH-3", "duplicate_group": "D-HOLDOUT"},
    ]
    canaries = [{"uuid": "SYN-CANARY", "burst_group": "B-1"}]
    report = audit_eval_split(tuning, holdout, canaries)
    assert not report["passed"]
    assert report["leakage"]["tuning_cluster_overlap_count"] == 1
    assert report["leakage"]["canary_cluster_overlap_count"] == 1
    assert report["leakage"]["holdout_duplicate_cluster_count"] == 1
    assert "private_details" not in report
    rendered = json.dumps(report)
    assert "SYN-FRESH" not in rendered and "P-1" not in rendered
    return {"leakage": report["leakage"], "digests": report["digests"]}


def eval_ordered_release_attempts() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary) / "ordered-run"
        initial = initialize_run(run, "synthetic-ordered-run", ["brief", "review", "write"])
        artifact = run / "artifact.json"
        artifact.write_text("{}\n", encoding="utf-8")
        expect_error(
            lambda: transition_phase(
                run,
                "review",
                "completed",
                initial["revision"],
                artifact,
                attempt_id="ATTEMPT-1",
            ),
            "earlier phase",
        )
        first = transition_phase(
            run,
            "brief",
            "completed",
            initial["revision"],
            artifact,
            attempt_id="ATTEMPT-1",
        )
        expect_error(
            lambda: transition_phase(
                run,
                "review",
                "completed",
                first["revision"],
                artifact,
                attempt_id="ATTEMPT-1",
            ),
            "attempt_id already recorded",
        )
        artifact.write_text('{"changed": true}\n', encoding="utf-8")
        expect_error(
            lambda: transition_phase(
                run,
                "review",
                "completed",
                first["revision"],
                artifact,
                attempt_id="ATTEMPT-2",
            ),
            "completed artifact changed",
        )
        return {"revision": first["revision"], "attempt_ids": first["attempt_ids"]}


def synthetic_helper_profile() -> dict:
    return {
        "schema_version": 1,
        "bundle_identifier": "org.openhouse.synthetic-photo-helper",
        "binary_sha256": "sha256:" + "1" * 64,
        "capabilities": [
            "membership-only-write",
            "receipt-plan-digest",
            "launch-nonce",
            "exact-folder-topology",
        ],
        "supported_plan_schema_versions": [2],
    }


def eval_helper_capability_negotiation() -> dict:
    from photo_fieldwork.release import validate_helper_profile

    profile = synthetic_helper_profile()
    required = ["membership-only-write", "receipt-plan-digest", "launch-nonce"]
    assert validate_helper_profile(profile, required, plan_schema_version=2) == []
    missing = deepcopy(profile)
    missing["capabilities"].remove("membership-only-write")
    errors = validate_helper_profile(missing, required, plan_schema_version=2)
    assert any("membership-only-write" in error for error in errors)
    unsupported = deepcopy(profile)
    unsupported["supported_plan_schema_versions"] = [1]
    assert any("schema" in error for error in validate_helper_profile(unsupported, required, 2))
    return {"required_capabilities": required, "rejected_errors": errors}


def synthetic_release_plan() -> dict:
    helper = synthetic_helper_profile()
    return {
        "schema_version": 2,
        "plan_id": "SYN-PLAN",
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source": {
            "id": "synthetic://source",
            "actual_count": 2,
            "fingerprint": "sha256:" + "2" * 64,
        },
        "helper_requirement": {
            "bundle_identifier": helper["bundle_identifier"],
            "binary_sha256": helper["binary_sha256"],
            "required_capabilities": helper["capabilities"],
            "plan_schema_version": 2,
        },
        "folders": [
            {"key": "version", "title": "Synthetic version", "parent_key": None},
        ],
        "albums": [
            {
                "key": "master",
                "role": "editor-master",
                "title": "00 MASTER - 2",
                "parent_folder_key": "version",
                "asset_identifiers": ["SYN-1", "SYN-2"],
            }
        ],
    }


def synthetic_receipt(plan: dict, nonce: str, completed_at: str) -> dict:
    from photo_fieldwork.integrity import canonical_json_fingerprint

    helper = synthetic_helper_profile()
    return {
        "schema_version": 1,
        "completed_at": completed_at,
        "execution_nonce": nonce,
        "plan_file_sha256": "sha256:" + "4" * 64,
        "plan_id": plan["plan_id"],
        "plan_fingerprint": canonical_json_fingerprint(plan),
        "source_id": plan["source"]["id"],
        "source_count": plan["source"]["actual_count"],
        "source_fingerprint": plan["source"]["fingerprint"],
        "helper": {
            "bundle_identifier": helper["bundle_identifier"],
            "binary_sha256": helper["binary_sha256"],
        },
        "folders": [
            {
                "key": "version",
                "title": "Synthetic version",
                "identifier": "SYN-FOLDER-ID",
                "parent_identifier": None,
            }
        ],
        "albums": [
            {
                "key": "master",
                "title": "00 MASTER - 2",
                "identifier": "SYN-ALBUM-ID",
                "parent_identifier": "SYN-FOLDER-ID",
                "count": 2,
            }
        ],
    }


def eval_plan_receipt_binding() -> dict:
    from photo_fieldwork.release import verify_execution_receipt

    plan = synthetic_release_plan()
    helper = synthetic_helper_profile()
    receipt = synthetic_receipt(plan, "a" * 32, "2026-07-19T10:00:00+00:00")
    assert verify_execution_receipt(receipt, plan, helper) == []
    altered = deepcopy(receipt)
    altered["plan_fingerprint"] = "sha256:" + "0" * 64
    errors = verify_execution_receipt(altered, plan, helper)
    assert any("plan fingerprint" in error for error in errors)
    changed_topology = deepcopy(receipt)
    changed_topology["albums"][0]["parent_identifier"] = "SYN-OTHER-FOLDER"
    assert any("topology" in error for error in verify_execution_receipt(changed_topology, plan, helper))
    substituted_helper = deepcopy(helper)
    substituted_helper["binary_sha256"] = "sha256:" + "3" * 64
    substituted_receipt = deepcopy(receipt)
    substituted_receipt["helper"]["binary_sha256"] = substituted_helper["binary_sha256"]
    assert any(
        "authorized helper" in error
        for error in verify_execution_receipt(substituted_receipt, plan, substituted_helper)
    )
    return {"rejected_errors": errors}


def eval_distinct_idempotence_executions() -> dict:
    from photo_fieldwork.release import compare_execution_receipts

    plan = synthetic_release_plan()
    helper = synthetic_helper_profile()
    first = synthetic_receipt(plan, "a" * 32, "2026-07-19T10:00:00+00:00")
    second = synthetic_receipt(plan, "b" * 32, "2026-07-19T10:05:00+00:00")
    report = compare_execution_receipts(first, second, plan, helper)
    assert report["passed"]
    copied = deepcopy(first)
    copied["completed_at"] = second["completed_at"]
    copied_report = compare_execution_receipts(first, copied, plan, helper)
    assert not copied_report["passed"] and any("nonce" in error for error in copied_report["errors"])
    divergent = deepcopy(second)
    divergent["albums"][0]["identifier"] = "SYN-DIFFERENT-ALBUM"
    divergent_report = compare_execution_receipts(first, divergent, plan, helper)
    assert not divergent_report["passed"] and any("topology" in error for error in divergent_report["errors"])
    return {"distinct_execution": report["execution_fingerprints"]}


def eval_closed_public_handoff() -> dict:
    from photo_fieldwork.handoff import build_public_handoff

    rows = [
        {
            "uuid": "SYN-PRIVATE-CLEARED",
            "primary_view": "A",
            "publication_status": "cleared-for-specific-use",
            "rights_status": "owner-verified",
            "consent_status": "not-applicable",
            "claim_status": "visible-only",
            "caption": "Visible synthetic scene",
            "alt_text": "Synthetic scene",
            "people_names": "Private Person",
            "raw_ocr": "PRIVATE OCR",
            "local_path": "/private/archive/SYN-PRIVATE-CLEARED.jpg",
        },
        {
            "uuid": "SYN-UNKNOWN-RIGHTS",
            "publication_status": "cleared-for-specific-use",
            "rights_status": "unknown",
            "consent_status": "ask",
            "claim_status": "caption-review",
        },
        {
            "uuid": "SYN-CONTENT-LEAK",
            "primary_view": "A",
            "publication_status": "cleared-for-specific-use",
            "rights_status": "owner-verified",
            "consent_status": "cleared-for-use",
            "claim_status": "visible-only",
            "caption": "Open /Users/private/archive/SYN-CONTENT-LEAK.jpg",
            "alt_text": "PRIVATE OCR account number 1234",
        },
        {
            "uuid": "SYN-EDITOR-ONLY",
            "publication_status": "candidate",
            "rights_status": "owner-verified",
            "consent_status": "cleared-for-use",
            "claim_status": "provenance-backed",
        },
    ]
    handoff, errors = build_public_handoff(rows, "synthetic-publication-salt")
    assert len(handoff) == 1
    assert errors and any("rights" in error for error in errors)
    assert any("public content" in error for error in errors)
    public_row = handoff[0]
    assert "uuid" not in public_row and public_row["public_id"] != rows[0]["uuid"]
    serialized = json.dumps(handoff)
    assert "Private Person" not in serialized and "PRIVATE OCR" not in serialized and "/Users/" not in serialized
    return {"published_count": len(handoff), "public_fields": sorted(public_row), "blocked_count": 3}


EVALS = {
    "source-membership-drift": eval_source_membership_drift,
    "overlapping-exact-quotas": eval_overlapping_exact_quotas,
    "stratified-metric-trap": eval_stratified_metric_trap,
    "uuid-feedback-integrity": eval_uuid_feedback_integrity,
    "relational-safety-propagation": eval_relational_safety_propagation,
    "post-review-drift-seal": eval_post_review_drift_seal,
    "preview-decode-integrity": eval_preview_decode_integrity,
    "final-holdout-freshness": eval_final_holdout_freshness,
    "resumable-ledger-cas": eval_resumable_ledger_cas,
    "four-thousand-item-scale": eval_four_thousand_item_scale,
    "cluster-clean-holdout": eval_cluster_clean_holdout,
    "ordered-release-attempts": eval_ordered_release_attempts,
    "helper-capability-negotiation": eval_helper_capability_negotiation,
    "plan-receipt-binding": eval_plan_receipt_binding,
    "distinct-idempotence-executions": eval_distinct_idempotence_executions,
    "closed-public-handoff": eval_closed_public_handoff,
}


def run() -> dict:
    definition = json.loads((Path(__file__).with_name("evals.json")).read_text(encoding="utf-8"))
    declared = [item["id"] for item in definition["evals"]]
    if declared != list(EVALS):
        raise ValueError("eval definitions and executable evals differ or are out of order")
    results = []
    started = time.perf_counter()
    for eval_id, operation in EVALS.items():
        eval_started = time.perf_counter()
        try:
            evidence = operation()
            passed = True
            error = ""
        except Exception as caught:  # Deliberately keep a complete benchmark record.
            evidence = {}
            passed = False
            error = f"{type(caught).__name__}: {caught}"
        results.append(
            {
                "id": eval_id,
                "passed": passed,
                "elapsed_seconds": round(time.perf_counter() - eval_started, 4),
                "error": error,
                "evidence": evidence,
            }
        )
    passed_count = sum(item["passed"] for item in results)
    return {
        "schema_version": 1,
        "skill_name": definition["skill_name"],
        "eval_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "passed": passed_count == len(results),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run()
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
