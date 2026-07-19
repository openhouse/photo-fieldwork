from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from .integrity import (
    assignment_sha256,
    base_identifier,
    canonical_json_sha256,
    membership_sha256,
    verify_plan_digest,
)
from .pipeline import evaluate, validate


CLUSTER_FIELDS = {
    "perceptual_cluster_id": "perceptual",
    "duplicate_group": "duplicate",
    "duplicate_group_id": "duplicate",
    "burst_group": "burst",
}
EVENT_SCOPES = {
    "evaluation-judgment": "evaluation",
    "safety-escalated": "safety",
    "safety-cleared": "safety",
    "editorial-assignment": "editorial",
    "publication-review": "publication",
    "publication-approved": "publication",
}
HUMAN_ONLY_EVENTS = {"safety-cleared", "publication-approved"}
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
EVENT_FIELDS = {
    "schema_version", "event_id", "occurred_at", "run_id", "event_type",
    "actor_id", "actor_kind", "authority_scope", "asset_uuid", "primary_view",
    "previous_state", "new_state", "reason", "evidence_sha256",
    "previous_event_sha256", "event_sha256",
}
RELEASE_BINDING_KEYS = {
    "config_sha256", "master_sha256", "master_assignment_sha256",
    "master_membership_sha256", "hold_membership_sha256", "feedback_sha256",
    "evaluation_report_sha256", "validation_report_sha256", "catalog_plan_sha256",
    "decision_ledger_sha256", "holdout_report_sha256", "source_membership_sha256",
    "safety_baseline_sha256",
}
RELEASE_GATE_KEYS = {
    "evaluation_recomputed", "validation_recomputed", "decision_chain",
    "holdout_independence", "catalog_plan_integrity",
}


def canonical_manifest_rows(rows: Iterable[dict]) -> list[dict[str, str]]:
    canonical = []
    seen = set()
    for row in rows:
        identifier = base_identifier(str(row.get("uuid") or ""))
        if not identifier:
            raise ValueError("manifest contains a blank UUID")
        if identifier in seen:
            raise ValueError(f"manifest contains duplicate canonical UUID: {identifier}")
        seen.add(identifier)
        canonical.append({
            "uuid": identifier,
            "primary_view": str(row.get("primary_view") or "").strip(),
            "safety_status": str(row.get("safety_status") or "").strip().lower(),
            "publication_status": str(row.get("publication_status") or "not-approved").strip().lower(),
        })
    return sorted(canonical, key=lambda row: row["uuid"])


def manifest_fingerprint(rows: Iterable[dict]) -> str:
    canonical = canonical_manifest_rows(rows)
    if not canonical:
        raise ValueError("manifest must not be empty")
    return canonical_json_sha256(canonical)


def safety_baseline_fingerprint(rows: Iterable[dict]) -> str:
    canonical = []
    seen = set()
    for row in rows:
        identifier = base_identifier(str(row.get("uuid") or ""))
        if not identifier:
            raise ValueError("safety baseline contains a blank UUID")
        if identifier in seen:
            raise ValueError(f"safety baseline contains duplicate canonical UUID: {identifier}")
        seen.add(identifier)
        canonical.append({
            "uuid": identifier,
            "safety_status": str(row.get("safety_status") or "").strip().lower(),
        })
    if not canonical:
        raise ValueError("safety baseline must not be empty")
    return canonical_json_sha256(sorted(canonical, key=lambda row: row["uuid"]))


def _identifiers(rows: list[dict]) -> list[str]:
    identifiers = [base_identifier(str(row.get("uuid") or "")) for row in rows]
    if any(not identifier for identifier in identifiers):
        raise ValueError("evaluation split contains a blank UUID")
    return identifiers


def _cluster_values(row: dict) -> set[str]:
    return {
        f"{cluster_kind}:{str(row.get(field) or '').strip()}"
        for field, cluster_kind in CLUSTER_FIELDS.items()
        if str(row.get(field) or "").strip()
    }


def _clusters(rows: list[dict]) -> set[str]:
    return {cluster for row in rows for cluster in _cluster_values(row)}


def split_structure_sha256(rows: list[dict]) -> str:
    structure = [
        {
            "uuid": base_identifier(str(row.get("uuid") or "")),
            "clusters": sorted(_cluster_values(row)),
        }
        for row in rows
    ]
    if any(not row["uuid"] for row in structure):
        raise ValueError("evaluation split contains a blank UUID")
    return canonical_json_sha256(sorted(
        structure,
        key=lambda row: (row["uuid"], tuple(row["clusters"])),
    ))


def audit_evaluation_split(
    tuning: list[dict],
    holdout: list[dict],
    canaries: list[dict],
) -> dict:
    tuning_ids = _identifiers(tuning)
    holdout_ids = _identifiers(holdout)
    canary_ids = _identifiers(canaries)
    if not holdout_ids:
        raise ValueError("evaluation holdout must not be empty")

    def duplicate_count(values: list[str]) -> int:
        return sum(count - 1 for count in Counter(values).values() if count > 1)

    leakage = {
        "tuning_duplicate_uuid_count": duplicate_count(tuning_ids),
        "holdout_duplicate_uuid_count": duplicate_count(holdout_ids),
        "canary_duplicate_uuid_count": duplicate_count(canary_ids),
        "tuning_uuid_overlap_count": len(set(holdout_ids) & set(tuning_ids)),
        "canary_uuid_overlap_count": len(set(holdout_ids) & set(canary_ids)),
        "tuning_cluster_overlap_count": len(_clusters(holdout) & _clusters(tuning)),
        "canary_cluster_overlap_count": len(_clusters(holdout) & _clusters(canaries)),
    }
    problems = [name for name, count in leakage.items() if count]
    return {
        "schema_version": 1,
        "status": "FAIL" if problems else "PASS",
        "holdout_independent": not problems,
        "counts": {
            "tuning_rows": len(tuning_ids),
            "holdout_rows": len(holdout_ids),
            "canary_rows": len(canary_ids),
        },
        "digests": {
            "tuning_membership_sha256": membership_sha256(tuning_ids),
            "holdout_membership_sha256": membership_sha256(holdout_ids),
            "canary_membership_sha256": membership_sha256(canary_ids),
            "tuning_structure_sha256": split_structure_sha256(tuning),
            "holdout_structure_sha256": split_structure_sha256(holdout),
            "canary_structure_sha256": split_structure_sha256(canaries),
        },
        "leakage": leakage,
        "problems": problems,
        "private_identifiers_included": False,
    }


def verify_holdout_report(
    report: dict,
    tuning: list[dict],
    holdout: list[dict],
    canaries: list[dict],
) -> list[str]:
    errors = []
    expected_report = audit_evaluation_split(tuning, holdout, canaries)
    if report.get("schema_version") != 1:
        errors.append("unsupported holdout-audit schema")
    if report.get("private_identifiers_included") is not False:
        errors.append("holdout audit must not contain private identifiers")
    counts = report.get("counts") or {}
    if not all(isinstance(counts.get(key), int) and counts[key] >= 0 for key in (
        "tuning_rows", "holdout_rows", "canary_rows",
    )):
        errors.append("holdout audit contains invalid split counts")
    elif counts["holdout_rows"] < 1:
        errors.append("holdout audit has no final holdout rows")
    digests = report.get("digests") or {}
    digest_keys = (
        "tuning_membership_sha256",
        "holdout_membership_sha256",
        "canary_membership_sha256",
        "tuning_structure_sha256",
        "holdout_structure_sha256",
        "canary_structure_sha256",
    )
    if not all(SHA256_PATTERN.fullmatch(str(digests.get(key) or "")) for key in digest_keys):
        errors.append("holdout audit contains invalid membership digests")
    if any(digests.get(key) != expected_report["digests"][key] for key in digest_keys):
        errors.append("holdout audit does not bind to the current split manifests")
    leakage = report.get("leakage") or {}
    expected_leakage_keys = {
        "tuning_duplicate_uuid_count",
        "holdout_duplicate_uuid_count",
        "canary_duplicate_uuid_count",
        "tuning_uuid_overlap_count",
        "canary_uuid_overlap_count",
        "tuning_cluster_overlap_count",
        "canary_cluster_overlap_count",
    }
    if set(leakage) != expected_leakage_keys or not all(
        isinstance(value, int) and value >= 0 for value in leakage.values()
    ):
        errors.append("holdout audit contains invalid leakage counts")
        expected_problems = []
    else:
        expected_problems = [key for key, value in leakage.items() if value]
    problems = report.get("problems")
    if (
        not isinstance(problems, list)
        or len(problems) != len(set(problems))
        or sorted(problems) != sorted(expected_problems)
    ):
        errors.append("holdout audit status does not match its leakage counts")
    expected_pass = not expected_problems
    if report.get("status") != ("PASS" if expected_pass else "FAIL"):
        errors.append("holdout audit has an inconsistent status")
    if report.get("holdout_independent") is not expected_pass:
        errors.append("holdout audit has an inconsistent independence result")
    if not expected_pass:
        errors.append("final evaluation holdout is not independent")
    if canonical_json_sha256(report) != canonical_json_sha256(expected_report):
        errors.append("holdout audit does not match the recomputed split audit")
    return errors


def seal_decision_event(event: dict, previous_event_sha256: str) -> dict:
    value = dict(event)
    unknown = sorted(set(value) - EVENT_FIELDS)
    if unknown:
        raise ValueError(f"decision event contains unsupported fields: {', '.join(unknown)}")
    value.pop("event_sha256", None)
    value["previous_event_sha256"] = previous_event_sha256
    required = {
        "schema_version",
        "event_id",
        "occurred_at",
        "run_id",
        "event_type",
        "actor_id",
        "actor_kind",
        "authority_scope",
        "reason",
    }
    missing = sorted(key for key in required if not str(value.get(key) or "").strip())
    if missing:
        raise ValueError(f"decision event is missing: {', '.join(missing)}")
    if value["schema_version"] != 1:
        raise ValueError("unsupported decision-event schema")
    event_type = str(value["event_type"])
    if event_type not in EVENT_SCOPES:
        raise ValueError(f"unsupported decision event type: {event_type}")
    if value["authority_scope"] != EVENT_SCOPES[event_type]:
        raise ValueError("decision event authority scope does not match its event type")
    if value["actor_kind"] not in {"human", "automation"}:
        raise ValueError("decision event actor_kind must be human or automation")
    if event_type in HUMAN_ONLY_EVENTS and value["actor_kind"] != "human":
        raise ValueError(f"{event_type} requires an identified human actor")
    if event_type in {"safety-escalated", "safety-cleared"}:
        if not str(value.get("asset_uuid") or "").strip():
            raise ValueError(f"{event_type} requires an asset UUID")
        if not str(value.get("previous_state") or "").strip() or not str(value.get("new_state") or "").strip():
            raise ValueError(f"{event_type} requires previous and new safety states")
    if event_type == "safety-cleared" and str(value.get("new_state") or "").strip().lower() != "clear":
        raise ValueError("safety-cleared must transition to clear")
    if previous_event_sha256 and not SHA256_PATTERN.fullmatch(previous_event_sha256):
        raise ValueError("previous decision-event SHA-256 is malformed")
    if value.get("asset_uuid"):
        value["asset_uuid"] = base_identifier(str(value["asset_uuid"]))
    value["event_sha256"] = canonical_json_sha256(value)
    return value


def verify_decision_events(events: list[dict]) -> list[str]:
    errors = []
    if not events:
        return ["decision ledger must not be empty"]
    event_ids = set()
    expected_previous = ""
    run_id = str(events[0].get("run_id") or "")
    for index, event in enumerate(events):
        event_id = str(event.get("event_id") or "")
        if event_id in event_ids:
            errors.append(f"decision event {index} repeats event_id {event_id}")
        event_ids.add(event_id)
        if event.get("run_id") != run_id:
            errors.append(f"decision event {index} changes run_id")
        if event.get("previous_event_sha256", "") != expected_previous:
            errors.append(f"decision event {index} breaks the hash chain")
        try:
            expected = seal_decision_event(event, expected_previous)
        except ValueError as error:
            errors.append(f"decision event {index}: {error}")
        else:
            if expected["event_sha256"] != event.get("event_sha256"):
                errors.append(f"decision event {index} content does not match its SHA-256")
        expected_previous = str(event.get("event_sha256") or "")
    return errors


def read_decision_events(path: Path) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"decision ledger not found: {path}")
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid decision event on line {line_number}") from error
    errors = verify_decision_events(events)
    if errors:
        raise ValueError("; ".join(errors))
    return events


def append_decision_event(path: Path, event: dict) -> dict:
    events = read_decision_events(path) if path.exists() else []
    previous = events[-1]["event_sha256"] if events else ""
    sealed = seal_decision_event(event, previous)
    if sealed["event_id"] in {item["event_id"] for item in events}:
        raise ValueError(f"decision event ID already exists: {sealed['event_id']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sealed, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return sealed


def _plan_errors(plan: dict, master: list[dict]) -> list[str]:
    errors = []
    try:
        verify_plan_digest(plan)
    except ValueError as error:
        return [str(error)]
    master_ids = [base_identifier(row["uuid"]) for row in master]
    if plan.get("safety_mode") != "create-folders-albums-and-add-membership-only":
        errors.append("catalog plan has an unsafe mutation mode")
    if plan.get("publication_approval_default") != "not-approved":
        errors.append("catalog plan attempts to grant publication approval")
    if plan.get("master_membership_sha256") != membership_sha256(master_ids):
        errors.append("catalog plan does not match current master membership")
    if plan.get("master_assignment_sha256") != assignment_sha256(master):
        errors.append("catalog plan does not match current master assignments or safety states")
    if plan.get("expected_master_count") != len(master_ids):
        errors.append("catalog plan does not match current master count")
    albums = plan.get("albums")
    if not isinstance(albums, list) or not albums:
        return errors + ["catalog plan has no albums"]
    master_album = next((album for album in albums if album.get("key") == "master"), None)
    if not master_album:
        errors.append("catalog plan has no master album")
    for album in albums:
        identifiers = album.get("asset_ids")
        if not isinstance(identifiers, list) or not identifiers:
            errors.append(f"catalog album {album.get('key', 'unknown')} has no membership")
            continue
        if len({base_identifier(value) for value in identifiers}) != len(identifiers):
            errors.append(f"catalog album {album.get('key', 'unknown')} repeats canonical UUIDs")
        if album.get("membership_sha256") != membership_sha256(identifiers):
            errors.append(f"catalog album {album.get('key', 'unknown')} has a stale membership digest")
    if master_album and {base_identifier(value) for value in master_album["asset_ids"]} != set(master_ids):
        errors.append("catalog master album does not equal current master membership")
    expected_views = {
        view: {base_identifier(row["uuid"]) for row in master if row.get("primary_view") == view}
        for view in {str(row.get("primary_view") or "") for row in master}
    }
    planned_views = {
        str(album.get("key"))[5:]: {base_identifier(value) for value in album.get("asset_ids", [])}
        for album in albums
        if str(album.get("key") or "").startswith("view-")
    }
    if expected_views != planned_views:
        errors.append("catalog view albums do not match current master assignments")
    source = plan.get("source") or {}
    if source.get("count", 0) < 1 or not SHA256_PATTERN.fullmatch(str(source.get("membership_sha256") or "")):
        errors.append("catalog plan lacks a valid frozen source identity")
    return errors


def _release_decision_errors(
    events: list[dict],
    expected_run_id: str,
    master: list[dict],
    safety_baseline: list[dict],
) -> list[str]:
    errors = []
    if not expected_run_id:
        errors.append("catalog plan lacks a release run identity")
    if any(event.get("run_id") != expected_run_id for event in events):
        errors.append("decision ledger does not belong to the released run")

    baseline_by_id = {}
    for row in safety_baseline:
        identifier = base_identifier(str(row.get("uuid") or ""))
        if not identifier or identifier in baseline_by_id:
            errors.append("safety baseline requires unique canonical UUIDs")
            continue
        baseline_by_id[identifier] = str(row.get("safety_status") or "").strip().lower()
    master_by_id = {base_identifier(str(row.get("uuid") or "")): row for row in master}
    missing_baseline = sorted(set(master_by_id) - set(baseline_by_id))
    if missing_baseline:
        errors.append("safety baseline does not cover every released master asset")

    clearance_by_id = {}
    for event in events:
        if event.get("event_type") != "safety-cleared":
            continue
        identifier = base_identifier(str(event.get("asset_uuid") or ""))
        clearance_by_id.setdefault(identifier, []).append(event)
        if identifier not in master_by_id:
            errors.append("safety-clearance event does not belong to the released master")
            continue
        baseline_state = baseline_by_id.get(identifier, "")
        if str(event.get("previous_state") or "").strip().lower() != baseline_state:
            errors.append("safety-clearance event does not match the frozen baseline state")
        if str(event.get("new_state") or "").strip().lower() != "clear":
            errors.append("safety-clearance event does not transition the asset to clear")

    for identifier, row in master_by_id.items():
        baseline_state = baseline_by_id.get(identifier)
        current_state = str(row.get("safety_status") or "").strip().lower()
        if baseline_state is not None and baseline_state != current_state:
            matching = [
                event for event in clearance_by_id.get(identifier, [])
                if str(event.get("previous_state") or "").strip().lower() == baseline_state
                and str(event.get("new_state") or "").strip().lower() == current_state == "clear"
                and event.get("actor_kind") == "human"
            ]
            if not matching:
                errors.append(
                    f"asset {identifier} changed from {baseline_state or 'blank'} to clear without a matching human safety-clearance event"
                )
    return errors


def build_release_seal(
    *,
    config: dict,
    master: list[dict],
    holds: list[dict],
    feedback: list[dict],
    holdout: list[dict],
    canaries: list[dict],
    safety_baseline: list[dict],
    catalog_plan: dict,
    decision_events: list[dict],
    holdout_report: dict,
) -> dict:
    evaluation_report, evaluation_passed = evaluate(feedback, config)
    validation_errors, validation_metrics = validate(master, holds, config)
    decision_errors = verify_decision_events(decision_events)
    decision_errors.extend(_release_decision_errors(
        decision_events,
        str(catalog_plan.get("plan_id") or ""),
        master,
        safety_baseline,
    ))
    plan_errors = _plan_errors(catalog_plan, master)
    holdout_errors = verify_holdout_report(holdout_report, feedback, holdout, canaries)
    errors = []
    if not evaluation_passed:
        errors.append("recomputed evaluation does not pass")
    if validation_errors:
        errors.append("recomputed validation does not pass")
    errors.extend(plan_errors)
    errors.extend(decision_errors)
    errors.extend(holdout_errors)
    if any(event.get("event_type") == "publication-approved" for event in decision_events):
        errors.append("editor-field release cannot include publication approval")
    if errors:
        raise ValueError("; ".join(errors))

    bindings = {
        "config_sha256": canonical_json_sha256(config),
        "master_sha256": manifest_fingerprint(master),
        "master_assignment_sha256": assignment_sha256(master),
        "master_membership_sha256": membership_sha256(row["uuid"] for row in master),
        "hold_membership_sha256": membership_sha256(row["uuid"] for row in holds),
        "feedback_sha256": canonical_json_sha256(sorted(feedback, key=lambda row: base_identifier(row["uuid"]))),
        "evaluation_report_sha256": canonical_json_sha256(evaluation_report),
        "validation_report_sha256": canonical_json_sha256({
            "errors": validation_errors,
            "metrics": validation_metrics,
        }),
        "catalog_plan_sha256": catalog_plan["plan_sha256"],
        "decision_ledger_sha256": canonical_json_sha256(decision_events),
        "holdout_report_sha256": canonical_json_sha256(holdout_report),
        "source_membership_sha256": catalog_plan["source"]["membership_sha256"],
        "safety_baseline_sha256": safety_baseline_fingerprint(safety_baseline),
    }
    seal = {
        "schema_version": 1,
        "status": "PASS",
        "release_class": "editor-field",
        "publication_clearance": False,
        "candidate_sha256": canonical_json_sha256(bindings),
        "bindings": bindings,
        "gates": {
            "evaluation_recomputed": "PASS",
            "validation_recomputed": "PASS",
            "decision_chain": "PASS",
            "holdout_independence": "PASS",
            "catalog_plan_integrity": "PASS",
        },
    }
    seal["release_seal_sha256"] = canonical_json_sha256(seal)
    return seal


def verify_release_seal(seal: dict) -> list[str]:
    errors = []
    if seal.get("schema_version") != 1:
        errors.append("unsupported release-seal schema")
    if seal.get("status") != "PASS":
        errors.append("release seal does not record PASS")
    if seal.get("release_class") != "editor-field":
        errors.append("release seal has an unsupported release class")
    if seal.get("publication_clearance") is not False:
        errors.append("release seal must not grant publication clearance")
    gates = seal.get("gates") or {}
    if set(gates) != RELEASE_GATE_KEYS or any(value != "PASS" for value in gates.values()):
        errors.append("release seal contains an unpassed gate")
    bindings = seal.get("bindings") or {}
    if set(bindings) != RELEASE_BINDING_KEYS or not all(
        SHA256_PATTERN.fullmatch(str(value or "")) for value in bindings.values()
    ):
        errors.append("release seal contains incomplete or malformed bindings")
    if seal.get("candidate_sha256") != canonical_json_sha256(bindings):
        errors.append("release candidate digest does not match its bindings")
    payload = {key: value for key, value in seal.items() if key != "release_seal_sha256"}
    if seal.get("release_seal_sha256") != canonical_json_sha256(payload):
        errors.append("release seal digest does not match its contents")
    return errors
