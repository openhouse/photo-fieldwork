#!/usr/bin/env python3
"""Run recursive, synthetic, fail-closed Photo Fieldwork evaluations."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import itertools
import json
import tempfile
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "src"))

from photo_fieldwork.cli import command_apply_feedback  # noqa: E402
from photo_fieldwork.handoff import render_handoff  # noqa: E402
from photo_fieldwork.integrity import attach_plan_digest, membership_sha256, verify_plan_digest  # noqa: E402
from photo_fieldwork.pipeline import (  # noqa: E402
    build_catalog_plan,
    evaluate,
    evaluation_sample_sha256,
    make_sample,
    select,
    validate,
    write_csv,
)
from photo_fieldwork.runstate import PHASES, checkpoint, initialize_run  # noqa: E402

try:  # The composite evals intentionally predate their implementation during a hill climb.
    from photo_fieldwork.governance import (  # noqa: E402
        audit_evaluation_split,
        build_release_seal,
        seal_decision_event,
        verify_decision_events,
    )
except ImportError:
    audit_evaluation_split = None
    build_release_seal = None
    seal_decision_event = None
    verify_decision_events = None


BRIDGE_PATH = ROOT / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
BRIDGE_SPEC = importlib.util.spec_from_file_location("eval_photo_archive_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(BRIDGE_SPEC)
assert BRIDGE_SPEC.loader is not None
BRIDGE_SPEC.loader.exec_module(bridge)


Result = tuple[bool, str]
Runner = Callable[[tuple[str, ...]], Result]


def small_config(target: int = 4) -> dict:
    return {
        "seed": 17,
        "target_count": target,
        "unclassified_view": "00",
        "allow_unclassified_fallback": False,
        "require_explicit_safety_status": True,
        "require_evaluation_binding": True,
        "require_per_view_sufficiency": True,
        "minimum_eval_coverage": 1.0,
        "minimum_eval_precision": 0.75,
        "minimum_view_precision": 0.65,
        "minimum_decisive_per_view": 2,
        "views": [
            {"id": "00", "label": "Unclassified", "quota": 0 if target == 4 else target},
            {"id": "A", "label": "A", "quota": 2 if target == 4 else 0},
            {"id": "B", "label": "B", "quota": 2 if target == 4 else 0},
        ],
    }


def rows_for_selection() -> list[dict[str, str]]:
    return [
        {"uuid": "AB", "filename": "ab.jpg", "candidate_views": "A;B", "safety_status": "clear"},
        {"uuid": "A1", "filename": "a1.jpg", "candidate_views": "A", "safety_status": "clear"},
        {"uuid": "A2", "filename": "a2.jpg", "candidate_views": "A", "safety_status": "clear"},
        {"uuid": "B1", "filename": "b1.jpg", "candidate_views": "B", "safety_status": "clear"},
        {"uuid": "B2", "filename": "b2.jpg", "candidate_views": "B", "safety_status": "clear"},
    ]


def selection_order(mutations: tuple[str, ...]) -> Result:
    config = small_config()
    baseline, _, _ = select(rows_for_selection(), config)
    rows = rows_for_selection()
    for mutation in mutations:
        if mutation == "reverse":
            rows.reverse()
        elif mutation == "rotate":
            rows = rows[2:] + rows[:2]
        elif mutation == "identifier-suffix":
            for row in rows:
                row["uuid"] += "/L0/040"
        elif mutation == "mixed-identifier-suffix":
            for index, row in enumerate(rows):
                if index % 2 == 0:
                    row["uuid"] += "/L0/040"
    selected, _, summary = select(rows, config)
    actual = {(row["uuid"].split("/", 1)[0], row["primary_view"]) for row in selected}
    expected = {(row["uuid"].split("/", 1)[0], row["primary_view"]) for row in baseline}
    passed = actual == expected and summary["view_counts"] == {"A": 2, "B": 2}
    return passed, f"assignments={sorted(actual)}"


def safety_states(mutations: tuple[str, ...]) -> Result:
    config = small_config(target=1)
    mutation = mutations[0] if mutations else "clear"
    row = {"uuid": "SAFE", "filename": "safe.jpg", "candidate_views": "00"}
    if mutation != "missing-state":
        row["safety_status"] = mutation
    expected_selected = mutation == "clear"
    try:
        master, holds, _ = select([row], config)
        selected = len(master)
        held = len(holds)
        rejected = False
    except ValueError as exception:
        selected = 0
        held = 1
        rejected = True
        error = str(exception)
    passed = (selected == 1) if expected_selected else (held == 1 and selected == 0)
    detail = f"state={mutation} selected={selected} held={held} rejected={rejected}"
    if rejected:
        detail += f" error={error}"
    return passed, detail


def validation_boundary(mutations: tuple[str, ...]) -> Result:
    config = small_config(target=1)
    master = [{
        "uuid": "ASSET/L0/001",
        "filename": "asset.jpg",
        "primary_view": "00",
        "selection_reason": "visible fit",
        "safety_status": "clear",
        "publication_status": "not-approved",
    }]
    holds: list[dict[str, str]] = []
    for mutation in mutations:
        if mutation == "canonical-hold-overlap":
            holds.append({"uuid": "ASSET", "filename": "hold.jpg"})
        elif mutation == "canonical-master-duplicate":
            master.append({**master[0], "uuid": "ASSET/L0/040"})
            config["target_count"] = 2
            config["views"][0]["quota"] = 2
        elif mutation == "publication-approved":
            master[0]["publication_status"] = "publication-approved"
    errors, metrics = validate(master, holds, config)
    passed = (not errors) if not mutations else bool(errors)
    return passed, f"status={metrics['status']} errors={errors}"


def evaluation_integrity(mutations: tuple[str, ...]) -> Result:
    config = small_config()
    master, _, _ = select(rows_for_selection(), config)
    sample = make_sample(master, 2, 17)
    for row in sample:
        row["judgment"] = "fit"
        row["visible_reason"] = "synthetic visible fit"
    for mutation in mutations:
        if mutation == "drop-view":
            dropped = sample[0]["primary_view"]
            sample = [row for row in sample if row["primary_view"] != dropped]
        elif mutation == "underpower-view":
            view = sample[0]["primary_view"]
            changed = False
            for row in sample:
                if row["primary_view"] == view and changed:
                    row["judgment"] = "uncertain"
                elif row["primary_view"] == view:
                    changed = True
        elif mutation == "substitute-uuid":
            sample[0]["uuid"] = "OUTSIDE-SAMPLE"
        elif mutation == "duplicate-uuid":
            sample[-1]["uuid"] = sample[0]["uuid"]
        elif mutation == "swap-view-labels":
            replacements = {"A": "B", "B": "A"}
            for row in sample:
                row["primary_view"] = replacements[row["primary_view"]]
    report, passed_evaluation = evaluate(sample, config)
    passed = passed_evaluation if not mutations else not passed_evaluation
    return passed, f"evaluation_passed={passed_evaluation} integrity={report.get('integrity_errors', [])}"


def feedback_identity(mutations: tuple[str, ...]) -> Result:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        inventory_path = root / "inventory.csv"
        feedback_path = root / "feedback.csv"
        output_path = root / "updated.csv"
        inventory = [
            {"uuid": value, "filename": f"{value.lower()}.jpg", "safety_status": "clear"}
            for value in ("A", "B", "C")
        ]
        feedback = [
            {
                **row,
                "primary_view": "00",
                "judgment": "fit",
            }
            for row in inventory
        ]
        digest = evaluation_sample_sha256(feedback)
        for row in feedback:
            row["evaluation_sample_sha256"] = digest
            row["evaluation_sample_count"] = "3"
        dangerous = False
        for mutation in mutations:
            if mutation == "reverse":
                feedback.reverse()
            elif mutation == "drop-row":
                feedback.pop()
                dangerous = True
            elif mutation == "unknown-uuid":
                feedback[0]["uuid"] = "UNKNOWN"
                dangerous = True
            elif mutation == "duplicate-uuid":
                feedback[-1]["uuid"] = feedback[0]["uuid"]
                dangerous = True
            elif mutation == "strip-binding":
                for row in feedback:
                    row.pop("evaluation_sample_sha256", None)
                    row.pop("evaluation_sample_count", None)
                dangerous = True
        write_csv(inventory_path, inventory)
        write_csv(feedback_path, feedback)
        error = ""
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                command_apply_feedback(
                    argparse.Namespace(inventory=inventory_path, feedback=feedback_path, output=output_path)
                )
        except ValueError as exception:
            error = str(exception).replace(str(root), "<temporary-workspace>")
        rejected = bool(error)
        passed = rejected if dangerous else not rejected
        return passed, f"rejected={rejected} error={error or 'none'}"


def write_run_inputs(root: Path) -> tuple[Path, Path]:
    brief = root / "brief-source.md"
    profile = root / "profile.json"
    brief.write_text("# Synthetic eval brief\n", encoding="utf-8")
    profile.write_text(json.dumps({
        "workspace_root": str(root / "runs"),
        "photos_database": str(root / "Photos.sqlite"),
        "permissioned_app": str(root / "Archive.app"),
        "source": {"kind": "album", "identifier": "SOURCE", "expected_count": 3},
        "folders": {
            "root_identifier": "ROOT",
            "private_identifier": "PRIVATE",
            "audit_identifier": "AUDIT",
        },
    }), encoding="utf-8")
    return brief, profile


def checkpoint_chain(mutations: tuple[str, ...]) -> Result:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        brief, profile = write_run_inputs(root)
        workspace = root / "runs" / "eval"
        initialize_run(workspace, brief, profile, "eval", 3)
        first = workspace / "reports" / "doctor.json"
        first.write_text('{"status":"PASS"}\n', encoding="utf-8")
        checkpoint(workspace, PHASES[0], [first])
        if "tamper-prior-artifact" in mutations:
            first.write_text('{"status":"ALTERED"}\n', encoding="utf-8")
        if "remove-prior-artifact" in mutations:
            first.unlink()
        second = workspace / "reports" / "source.json"
        second.write_text('{"status":"PASS"}\n', encoding="utf-8")
        error = ""
        try:
            checkpoint(workspace, PHASES[1], [second])
        except ValueError as exception:
            error = str(exception).replace(str(root), "<temporary-workspace>")
        rejected = bool(error)
        passed = rejected if mutations else not rejected
        return passed, f"rejected={rejected} error={error or 'none'}"


def inspection_shards(mutations: tuple[str, ...]) -> Result:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        identifiers = ["A/L0/001", "B/L0/001"]
        plan = bridge.attach_plan_digest({
            "operation": "inspect-local-images",
            "schema_version": 1,
            "plan_id": "shard-01",
            "source_album_identifier": "SOURCE",
            "expected_source_count": 3,
            "source_membership_sha256": membership_sha256(["A", "B", "C"]),
            "asset_identifiers": identifiers,
            "output_jsonl_path": str(root / "inspection.jsonl"),
            "receipt_path": str(root / "receipt.json"),
        })
        rows = [{"asset_identifier": value, "pixel_available": True} for value in identifiers]
        receipt = {
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "source_count": 3,
            "source_membership_sha256": plan["source_membership_sha256"],
            "requested_count": 2,
            "completed_count": 2,
            "network_access_allowed": False,
            "external_uploads_performed": False,
        }
        for mutation in mutations:
            if mutation == "substitute-row":
                rows[0]["asset_identifier"] = "OUTSIDE/L0/001"
            elif mutation == "drop-row":
                rows.pop()
            elif mutation == "receipt-count":
                receipt["completed_count"] = 99
            elif mutation == "source-digest":
                receipt["source_membership_sha256"] = "0" * 64
            elif mutation == "source-count":
                receipt["source_count"] = 99
        Path(plan["output_jsonl_path"]).write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        Path(plan["receipt_path"]).write_text(json.dumps(receipt), encoding="utf-8")
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        error = ""
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                bridge.command_combine_inspection(argparse.Namespace(
                    plan=[plan_path],
                    output=root / "combined.jsonl",
                    receipt=root / "combined-receipt.json",
                    expected=2,
                ))
        except ValueError as exception:
            error = str(exception).replace(str(root), "<temporary-workspace>")
        rejected = bool(error)
        passed = rejected if mutations else not rejected
        return passed, f"rejected={rejected} error={error or 'none'}"


def handoff_record() -> dict:
    return {"records": [{
        "id": "material-practice",
        "public_safe_observation": "Reviewed photographs show tools and working documents.",
        "may_corroborate": ["A durable material practice."],
        "does_not_establish": ["Authorship or project outcomes."],
        "publication_boundary": "No image is approved for publication.",
        "related_claim_ids": ["reviewable-artifacts-practice"],
        "status": "draft",
        "reviewed_at": "2026-07-19",
    }]}


def handoff_boundary(mutations: tuple[str, ...]) -> Result:
    data = handoff_record()
    additions = {
        "email": " Contact editor" + "@example.test.",
        "posix-path": " Stored at /" + "Users/example/private.jpg.",
        "windows-path": " Stored at C:\\Private\\photo.jpg.",
        "phone": " Call 212-555-0199.",
        "photos-identifier": " Asset 12345678-1234-" + "1234-1234-123456789ABC/L0/001.",
    }
    for mutation in mutations:
        data["records"][0]["public_safe_observation"] += additions[mutation]
    error = ""
    try:
        render_handoff(data)
    except ValueError as exception:
        error = str(exception)
    rejected = bool(error)
    passed = rejected if mutations else not rejected
    return passed, f"rejected={rejected} error={error or 'none'}"


def plan_binding(mutations: tuple[str, ...]) -> Result:
    config = small_config(target=1)
    master = [{
        "uuid": "A",
        "filename": "a.jpg",
        "primary_view": "00",
        "selection_reason": "visible fit",
        "safety_status": "clear",
    }]
    plan = build_catalog_plan(master, config, "eval", "Source", "SOURCE", ["A", "B"])
    plan["created_at"] = "2026-07-19T00:00:00+00:00"
    plan = attach_plan_digest(plan)
    for mutation in mutations:
        if mutation == "plan-id":
            plan["plan_id"] = "altered"
        elif mutation == "album-membership":
            plan["albums"][0]["asset_ids"] = ["B"]
        elif mutation == "source-membership":
            plan["source"]["membership_sha256"] = "0" * 64
        elif mutation == "publication-default":
            plan["publication_approval_default"] = "approved"
    error = ""
    try:
        verify_plan_digest(plan)
    except ValueError as exception:
        error = str(exception)
    rejected = bool(error)
    passed = rejected if mutations else not rejected
    return passed, f"rejected={rejected} error={error or 'none'}"


def unclassified_honesty(mutations: tuple[str, ...]) -> Result:
    config = small_config(target=1)
    row = {"uuid": "U", "filename": "u.jpg", "candidate_views": "", "safety_status": "clear"}
    rows = [row]
    for mutation in mutations:
        if mutation == "unknown-view":
            row["candidate_views"] = "UNSUPPORTED-PROOF"
        elif mutation == "empty-evidence":
            row["evidence_confidence"] = ""
            row["visible_context"] = ""
        elif mutation == "input-reorder":
            rows.reverse()
    master, _, _ = select(rows, config)
    passed = len(master) == 1 and master[0]["primary_view"] == "00"
    invented = "UNSUPPORTED-PROOF" in master[0].get("selection_reason", "") if master else True
    return passed and not invented, f"view={master[0]['primary_view'] if master else 'none'} invented={invented}"


def decision_ledger(mutations: tuple[str, ...]) -> Result:
    if seal_decision_event is None or verify_decision_events is None:
        return False, "composite decision-ledger API is unavailable"
    events = []
    previous = ""
    for event in (
        {
            "schema_version": 1,
            "event_id": "decision-01",
            "occurred_at": "2026-07-19T00:00:00+00:00",
            "run_id": "eval-run",
            "event_type": "safety-cleared",
            "actor_id": "editor-01",
            "actor_kind": "human",
            "authority_scope": "safety",
            "asset_uuid": "A/L0/001",
            "previous_state": "needs-review",
            "new_state": "clear",
            "reason": "Human review of the synthetic fixture.",
        },
        {
            "schema_version": 1,
            "event_id": "decision-02",
            "occurred_at": "2026-07-19T00:01:00+00:00",
            "run_id": "eval-run",
            "event_type": "editorial-assignment",
            "actor_id": "editor-01",
            "actor_kind": "human",
            "authority_scope": "editorial",
            "asset_uuid": "A",
            "primary_view": "A",
            "previous_state": "candidate",
            "new_state": "assigned",
            "reason": "Visible synthetic evidence fits view A.",
        },
        {
            "schema_version": 1,
            "event_id": "decision-03",
            "occurred_at": "2026-07-19T00:02:00+00:00",
            "run_id": "eval-run",
            "event_type": "evaluation-judgment",
            "actor_id": "reviewer-01",
            "actor_kind": "human",
            "authority_scope": "evaluation",
            "asset_uuid": "B",
            "primary_view": "B",
            "previous_state": "unreviewed",
            "new_state": "fit",
            "reason": "Visible synthetic evidence fits view B.",
        },
    ):
        sealed = seal_decision_event(event, previous)
        events.append(sealed)
        previous = sealed["event_sha256"]
    for mutation in mutations:
        if mutation == "tamper-content":
            events[0]["reason"] = "Altered after sealing."
        elif mutation == "remove-middle":
            if len(events) > 2:
                events.pop(1)
        elif mutation == "duplicate-event-id":
            duplicate = dict(events[-1])
            duplicate["event_sha256"] = ""
            events.append(seal_decision_event(duplicate, events[-1]["event_sha256"]))
        elif mutation == "human-authority-mismatch":
            events[0]["actor_kind"] = "automation"
        elif mutation == "reorder":
            events = list(reversed(events))
    errors = verify_decision_events(events)
    passed = not errors if not mutations else bool(errors)
    return passed, f"errors={errors}"


def holdout_integrity(mutations: tuple[str, ...]) -> Result:
    if audit_evaluation_split is None:
        return False, "composite holdout-audit API is unavailable"
    tuning = [{
        "uuid": "TUNE-A",
        "perceptual_cluster_id": "perceptual-tune",
        "duplicate_group": "duplicate-tune",
        "burst_group": "burst-tune",
    }]
    holdout = [{
        "uuid": "HOLDOUT-A",
        "perceptual_cluster_id": "perceptual-holdout",
        "duplicate_group": "duplicate-holdout",
        "burst_group": "burst-holdout",
    }]
    canaries = [{
        "uuid": "CANARY-A",
        "perceptual_cluster_id": "perceptual-canary",
        "duplicate_group": "duplicate-canary",
        "burst_group": "burst-canary",
    }]
    for mutation in mutations:
        if mutation == "uuid-overlap":
            holdout[0]["uuid"] = tuning[0]["uuid"]
        elif mutation == "duplicate-holdout":
            holdout.append(dict(holdout[0]))
        elif mutation == "perceptual-overlap":
            holdout[0]["perceptual_cluster_id"] = tuning[0]["perceptual_cluster_id"]
        elif mutation == "duplicate-group-overlap":
            holdout[0]["duplicate_group"] = tuning[0]["duplicate_group"]
        elif mutation == "duplicate-alias-overlap":
            tuning.append({"uuid": "TUNE-ALIAS", "duplicate_group": "shared-duplicate-alias"})
            holdout.append({"uuid": "HOLDOUT-ALIAS", "duplicate_group_id": "shared-duplicate-alias"})
        elif mutation == "burst-overlap":
            holdout[0]["burst_group"] = tuning[0]["burst_group"]
        elif mutation == "canary-overlap":
            canaries[0]["uuid"] = holdout[0]["uuid"]
    report = audit_evaluation_split(tuning, holdout, canaries)
    failed = report.get("status") == "FAIL"
    passed = not failed if not mutations else failed
    return passed, f"status={report.get('status')} leakage={report.get('leakage')}"


def release_candidate(mutations: tuple[str, ...]) -> Result:
    if (
        build_release_seal is None
        or audit_evaluation_split is None
        or seal_decision_event is None
    ):
        return False, "composite release-seal API is unavailable"
    config = small_config()
    master, holds, _ = select(rows_for_selection(), config)
    feedback = make_sample(master, 2, 17)
    for row in feedback:
        row["judgment"] = "fit"
        row["visible_reason"] = "Synthetic visible fit."
    feedback[0]["duplicate_group"] = "tuning"
    plan = build_catalog_plan(master, config, "composite-eval", "Source", "SOURCE", [
        "AB", "A1", "A2", "B1", "B2",
    ])
    plan["created_at"] = "2026-07-19T00:00:00+00:00"
    plan = attach_plan_digest(plan)
    decision = seal_decision_event({
        "schema_version": 1,
        "event_id": "release-decision-01",
        "occurred_at": "2026-07-19T00:00:00+00:00",
        "run_id": "composite-eval",
        "event_type": "editorial-assignment",
        "actor_id": "editor-01",
        "actor_kind": "human",
        "authority_scope": "editorial",
        "asset_uuid": master[0]["uuid"],
        "primary_view": master[0]["primary_view"],
        "previous_state": "candidate",
        "new_state": "assigned",
        "reason": "Synthetic release evidence.",
    }, "")
    decisions = [decision]
    holdout_rows = [{"uuid": "HOLDOUT", "duplicate_group": "holdout"}]
    canary_rows = [{"uuid": "CANARY", "duplicate_group": "canary"}]
    safety_baseline = [dict(row) for row in master]
    holdout_report = audit_evaluation_split(feedback, holdout_rows, canary_rows)
    for mutation in mutations:
        if mutation == "master-membership":
            master[0]["uuid"] = "OUTSIDE-MASTER"
        elif mutation == "assignment-drift":
            master[0]["primary_view"] = "B" if master[0]["primary_view"] == "A" else "A"
        elif mutation == "safety-drift":
            master[0]["safety_status"] = "needs-review"
        elif mutation == "config-drift":
            config["views"][1]["quota"] = 1
            config["views"][2]["quota"] = 3
        elif mutation == "feedback-drop":
            feedback.pop()
        elif mutation == "tuning-cluster-drift":
            feedback[0]["duplicate_group"] = "holdout"
        elif mutation == "holdout-cluster-drift":
            holdout_rows[0]["duplicate_group"] = "tuning"
        elif mutation == "canary-cluster-drift":
            canary_rows[0]["duplicate_group"] = "holdout"
        elif mutation == "plan-digest":
            plan["plan_id"] = "altered"
        elif mutation == "plan-album-substitution":
            plan["albums"][0]["asset_ids"][0] = "OUTSIDE-ALBUM"
            plan = attach_plan_digest(plan)
        elif mutation == "holdout-fail":
            holdout_report = audit_evaluation_split(
                feedback,
                [{"uuid": feedback[0]["uuid"]}],
                [],
            )
        elif mutation == "holdout-status-forgery":
            holdout_report["leakage"]["tuning_uuid_overlap_count"] = 1
            holdout_report["status"] = "PASS"
            holdout_report["holdout_independent"] = True
            holdout_report["problems"] = []
        elif mutation == "ledger-tamper":
            decisions[0]["reason"] = "Altered after sealing."
        elif mutation == "publication-approval-event":
            decisions = [seal_decision_event({
                "schema_version": 1,
                "event_id": "publication-decision-01",
                "occurred_at": "2026-07-19T00:00:00+00:00",
                "run_id": "eval-run",
                "event_type": "publication-approved",
                "actor_id": "publisher-01",
                "actor_kind": "human",
                "authority_scope": "publication",
                "asset_uuid": master[0]["uuid"],
                "reason": "Synthetic publication decision outside editor-field scope.",
            }, "")]
        elif mutation == "unrelated-run":
            value = {
                key: item for key, item in decisions[0].items()
                if key not in {"event_sha256", "previous_event_sha256"}
            }
            value["run_id"] = "unrelated-run"
            decisions = [seal_decision_event(value, "")]
        elif mutation == "missing-safety-clearance":
            safety_baseline[0]["safety_status"] = "machine-suspected"
    error = ""
    try:
        build_release_seal(
            config=config,
            master=master,
            holds=holds,
            feedback=feedback,
            holdout=holdout_rows,
            canaries=canary_rows,
            safety_baseline=safety_baseline,
            catalog_plan=plan,
            decision_events=decisions,
            holdout_report=holdout_report,
        )
    except ValueError as exception:
        error = str(exception)
    rejected = bool(error)
    passed = not rejected if not mutations else rejected
    return passed, f"rejected={rejected} error={error or 'none'}"


RUNNERS: dict[str, Runner] = {
    "selection_order": selection_order,
    "safety_states": safety_states,
    "validation_boundary": validation_boundary,
    "evaluation_integrity": evaluation_integrity,
    "feedback_identity": feedback_identity,
    "checkpoint_chain": checkpoint_chain,
    "inspection_shards": inspection_shards,
    "handoff_boundary": handoff_boundary,
    "plan_binding": plan_binding,
    "unclassified_honesty": unclassified_honesty,
    "decision_ledger": decision_ledger,
    "holdout_integrity": holdout_integrity,
    "release_candidate": release_candidate,
}


def mutation_frontier(mutations: list[str], max_depth: int):
    yield ()
    for depth in range(1, max_depth + 1):
        yield from itertools.combinations(mutations, depth)


def run_suite(suite: dict, max_depth: int) -> dict:
    results = []
    for case in suite["cases"]:
        runner = RUNNERS[case["runner"]]
        depth = min(max_depth, int(case.get("max_depth", max_depth)))
        for mutations in mutation_frontier(case.get("mutations", []), depth):
            try:
                passed, evidence = runner(mutations)
            except Exception as exception:  # eval infrastructure must report, not disappear
                passed = False
                evidence = f"unexpected {type(exception).__name__}: {exception}"
            results.append({
                "id": case["id"] + ("::" + "+".join(mutations) if mutations else "::root"),
                "case_id": case["id"],
                "category": case["category"],
                "depth": len(mutations),
                "mutations": list(mutations),
                "passed": passed,
                "evidence": evidence,
            })
    category_counts = {}
    for category in sorted({result["category"] for result in results}):
        rows = [result for result in results if result["category"] == category]
        category_counts[category] = {
            "passed": sum(result["passed"] for result in rows),
            "total": len(rows),
        }
    passed = sum(result["passed"] for result in results)
    return {
        "schema_version": 1,
        "suite": suite["suite"],
        "max_depth": max_depth,
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
        "pass_rate": round(passed / len(results), 4) if results else 0,
        "categories": category_counts,
        "failure_frontier": [result["id"] for result in results if not result["passed"]],
        "results": results,
    }


def render_markdown(report: dict) -> str:
    lines = [
        f"# {report['suite']}",
        "",
        f"- Recursive mutation depth: {report['max_depth']}",
        f"- Passed: {report['passed']} / {report['total']}",
        f"- Pass rate: {report['pass_rate']:.1%}",
        "",
        "## Categories",
        "",
    ]
    for category, counts in report["categories"].items():
        lines.append(f"- `{category}`: {counts['passed']} / {counts['total']}")
    lines.extend(["", "## Failure frontier", ""])
    if report["failure_frontier"]:
        lines.extend(f"- `{identifier}`" for identifier in report["failure_frontier"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=ROOT / "evals" / "system-evals.json")
    parser.add_argument("--max-depth", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "evals" / "report.json")
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    max_depth = args.max_depth if args.max_depth is not None else int(suite["default_max_depth"])
    report = run_suite(suite, max_depth)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(f"evals={report['passed']}/{report['total']} pass_rate={report['pass_rate']:.1%}")
    if report["failure_frontier"]:
        print("failure_frontier=" + ",".join(report["failure_frontier"]))
    print(f"report={args.output}")
    return 0 if report["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
