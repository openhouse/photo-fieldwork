from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import secrets
from pathlib import Path

from .integrity import canonical_sha256, content_sha256, master_sha256
from .pipeline import read_csv
from .run_state import (
    artifact,
    atomic_json,
    now,
    read_events as read_run_events,
    read_state,
    resolve_artifact,
    sha256_file,
    verify_recorded_artifacts,
    verify_lock,
    workspace_lock,
)


def _valid_digest(value: object) -> bool:
    digest = str(value or "")
    return len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )


def _validate_editor_plan(plan: dict) -> None:
    if plan.get("schema_version") != 2:
        raise ValueError("registered plan schema_version must be 2")
    if plan.get("release_class") != "editor-field":
        raise ValueError("only editor-field plans may be registered for execution")
    if plan.get("safety_mode") != "create-folders-albums-and-add-membership-only":
        raise ValueError("registered plan has an unsafe or unknown safety mode")
    for field in ("master_sha256", "config_sha256", "run_lock_sha256"):
        if not _valid_digest(plan.get(field)):
            raise ValueError(f"registered plan lacks a valid {field}")
    proposal_id = str(plan.get("proposal_id", ""))
    if proposal_id != f"pfp-{plan['master_sha256'][:16]}":
        raise ValueError("registered plan proposal identity is invalid")
    source = plan.get("source", {})
    if (
        not source.get("identifier")
        or not isinstance(source.get("count"), int)
        or source["count"] < 1
    ):
        raise ValueError("registered plan lacks source identity")
    if not _valid_digest(source.get("membership_sha256")):
        raise ValueError("registered plan lacks a valid source membership digest")
    evaluation = plan.get("evaluation", {})
    if (
        not evaluation.get("passed")
        or not evaluation.get("final_holdout")
        or not evaluation.get("relation_clean_holdout")
    ):
        raise ValueError("registered plan lacks a passing final evaluation")
    if not _valid_digest(evaluation.get("report_sha256")) or not _valid_digest(
        evaluation.get("leakage_report_sha256")
    ):
        raise ValueError("registered plan lacks a valid evaluation report digest")
    validation = plan.get("validation", {})
    if validation.get("status") != "PASS" or not _valid_digest(
        validation.get("report_sha256")
    ):
        raise ValueError("registered plan lacks a passing validation identity")
    master_albums = [
        item for item in plan.get("albums", []) if item.get("key") == "master"
    ]
    album_keys = [str(item.get("key", "")).strip() for item in plan.get("albums", [])]
    if any(not key for key in album_keys) or len(album_keys) != len(set(album_keys)):
        raise ValueError("registered plan album keys must be non-empty and unique")
    if len(master_albums) != 1:
        raise ValueError("registered plan requires exactly one master album")
    master_ids = master_albums[0].get("asset_ids", [])
    if not master_ids or len(master_ids) != len(set(master_ids)):
        raise ValueError("registered plan master membership is not unique")
    if len(master_ids) != plan.get("expected_master_count"):
        raise ValueError("registered plan master count is inconsistent")


def _registered_path(workspace: Path, registration: dict) -> Path:
    path = Path(registration["plan"]["path"])
    return path if path.is_absolute() else workspace / path


def _artifact_from_bytes(path: Path, workspace: Path, payload: bytes) -> dict:
    resolved = path.resolve()
    try:
        recorded_path = str(resolved.relative_to(workspace.resolve()))
    except ValueError:
        recorded_path = str(resolved)
    return {
        "path": recorded_path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def _latest_complete_attempt(state: dict, phase: str) -> dict:
    attempts = [
        attempt
        for attempt in state["phases"][phase].get("attempts", [])
        if attempt.get("status") == "complete"
    ]
    if state["phases"][phase].get("status") != "complete" or not attempts:
        raise ValueError(f"release requires completed {phase} evidence")
    return attempts[-1]


def _json_artifact(workspace: Path, record: dict, label: str) -> dict:
    path = resolve_artifact(workspace, record)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read recorded {label}: {path}") from error


def _base_identifier(value: object) -> str:
    return str(value).split("/", 1)[0].strip()


def _read_optional_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _validate_candidate_bindings(
    workspace: Path,
    plan: dict,
) -> tuple[dict, dict, list[dict[str, str]], list[dict[str, str]]]:
    lock_errors, _ = verify_lock(workspace)
    if lock_errors:
        raise ValueError("run lock verification failed: " + "; ".join(lock_errors))
    state = read_state(workspace)
    artifact_errors = verify_recorded_artifacts(workspace, state)
    if artifact_errors:
        raise ValueError(
            "recorded artifact drift blocks release: " + "; ".join(artifact_errors)
        )
    run_lock_path = workspace / "run-lock.json"
    if sha256_file(run_lock_path) != plan["run_lock_sha256"]:
        raise ValueError("registered plan does not identify this workspace run lock")
    run_lock = json.loads(run_lock_path.read_text(encoding="utf-8"))
    locked = run_lock.get("artifacts", {})
    required_locked = {"master", "holds", "effective_config", "replay_validation"}
    if not required_locked <= set(locked):
        raise ValueError("run lock does not contain every release-candidate artifact")

    master_rows = read_csv(resolve_artifact(workspace, locked["master"]))
    hold_rows = _read_optional_csv(resolve_artifact(workspace, locked["holds"]))
    config = _json_artifact(workspace, locked["effective_config"], "effective config")
    candidate_digest = master_sha256(master_rows)
    if candidate_digest != plan["master_sha256"]:
        raise ValueError("registered plan master differs from the locked candidate")
    if content_sha256(config) != plan["config_sha256"]:
        raise ValueError("registered plan config differs from the locked candidate")

    expected_albums = {"master": [row["uuid"] for row in master_rows]}
    for view in sorted({row["primary_view"] for row in master_rows}):
        expected_albums[f"view-{view}"] = [
            row["uuid"] for row in master_rows if row["primary_view"] == view
        ]
    actual_albums = {
        str(item.get("key", "")): item.get("asset_ids", [])
        for item in plan.get("albums", [])
    }
    if actual_albums != expected_albums:
        raise ValueError("registered plan albums differ from the locked candidate")

    evaluation_outputs = _latest_complete_attempt(state, "evaluation").get("outputs", {})
    validation_outputs = _latest_complete_attempt(state, "validation").get("outputs", {})
    if "report" not in evaluation_outputs or "leakage" not in evaluation_outputs:
        raise ValueError("evaluation phase must record report and leakage outputs")
    if "report" not in validation_outputs:
        raise ValueError("validation phase must record a report output")
    evaluation = _json_artifact(workspace, evaluation_outputs["report"], "evaluation report")
    leakage = _json_artifact(workspace, evaluation_outputs["leakage"], "leakage report")
    validation = _json_artifact(workspace, validation_outputs["report"], "validation report")
    if content_sha256(evaluation) != plan["evaluation"]["report_sha256"]:
        raise ValueError("registered plan evaluation digest is not recorded run evidence")
    if content_sha256(leakage) != plan["evaluation"]["leakage_report_sha256"]:
        raise ValueError("registered plan leakage digest is not recorded run evidence")
    if content_sha256(validation) != plan["validation"]["report_sha256"]:
        raise ValueError("registered plan validation digest is not recorded run evidence")
    expected_identity = {
        "master_sha256": candidate_digest,
        "proposal_id": f"pfp-{candidate_digest[:16]}",
        "config_sha256": plan["config_sha256"],
    }
    if any(evaluation.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("recorded evaluation does not identify the locked candidate")
    if any(validation.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("recorded validation does not identify the locked candidate")
    if not (
        evaluation.get("passed")
        and evaluation.get("final_holdout")
        and evaluation.get("relation_clean_holdout")
        and leakage.get("status") == "PASS"
        and not leakage.get("collisions")
        and validation.get("status") == "PASS"
    ):
        raise ValueError("recorded evaluation or validation is not release-passing")
    return state, run_lock, master_rows, hold_rows


def _verify_registered_plan(workspace: Path) -> tuple[dict, dict]:
    registration_path = workspace / "registered-plan.json"
    if not registration_path.is_file():
        raise ValueError("registered plan not found")
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    plan_path = _registered_path(workspace, registration)
    if not plan_path.is_file():
        raise ValueError("registered plan file is missing")
    plan_bytes = plan_path.read_bytes()
    if hashlib.sha256(plan_bytes).hexdigest() != registration["plan"]["sha256"]:
        raise ValueError("registered plan file changed after registration")
    plan = json.loads(plan_bytes)
    actual_content_digest = content_sha256(plan, "plan_sha256")
    if plan.get("plan_sha256") != actual_content_digest:
        raise ValueError("registered plan content digest is invalid")
    if plan["plan_sha256"] != registration["plan_sha256"]:
        raise ValueError("registered plan identity changed")
    return registration, plan


def register_plan(workspace: Path, plan_path: Path) -> dict:
    with workspace_lock(workspace):
        plan_bytes = plan_path.read_bytes()
        plan = json.loads(plan_bytes)
        _validate_editor_plan(plan)
        digest = content_sha256(plan, "plan_sha256")
        if plan.get("plan_sha256") != digest:
            raise ValueError("plan content digest is invalid")
        state, run_lock, _, _ = _validate_candidate_bindings(workspace, plan)
        source = plan["source"]
        if run_lock.get("source") != {
            "identifier": source["identifier"],
            "expected_count": source["count"],
            "membership_sha256": source["membership_sha256"],
        }:
            raise ValueError("registered plan source differs from the frozen run lock")
        registration_path = workspace / "registered-plan.json"
        previous = None
        if registration_path.exists():
            previous = json.loads(registration_path.read_text(encoding="utf-8"))
            if previous.get("plan_sha256") == digest:
                raise ValueError("this plan is already registered for the run")
            run_events = read_run_events(workspace)
            invalidations = [
                event
                for event in run_events
                if event.get("event_type") == "artifact_invalidation"
                and event.get("sequence", 0) > previous.get("run_event_count", 0)
            ]
            if (
                not invalidations
                or previous.get("run_lock_sha256") == plan["run_lock_sha256"]
            ):
                raise ValueError(
                    "a replacement plan requires post-registration invalidation and refreeze"
                )
        registration = {
            "schema_version": 1,
            "registered_at": now(),
            "plan_id": plan["plan_id"],
            "proposal_id": plan["proposal_id"],
            "master_sha256": plan["master_sha256"],
            "plan_sha256": digest,
            "run_lock_sha256": plan["run_lock_sha256"],
            "run_revision": state["revision"],
            "run_event_count": state["event_count"],
            "run_ledger_head": state["ledger_head"],
            "plan": _artifact_from_bytes(plan_path, workspace, plan_bytes),
        }
        if previous is not None:
            _append_event(
                workspace,
                {
                    "event_type": "plan_superseded",
                    "previous_registration": previous,
                    "replacement_plan_sha256": digest,
                },
            )
        _append_event(
            workspace,
            {
                "event_type": "plan_registered",
                "plan_sha256": digest,
                "run_lock_sha256": plan["run_lock_sha256"],
            },
        )
        atomic_json(registration_path, registration)
        return registration


def _read_events(workspace: Path) -> list[dict]:
    path = workspace / "execution-events.jsonl"
    if not path.exists():
        return []
    events = []
    previous_hash = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        event = json.loads(line)
        if event.get("sequence") != len(events) + 1:
            raise ValueError(f"execution event sequence mismatch at line {line_number}")
        if event.get("previous_hash") != previous_hash:
            raise ValueError(f"execution event linkage failed at line {line_number}")
        payload = dict(event)
        actual_hash = payload.pop("event_hash", None)
        if actual_hash != canonical_sha256(payload):
            raise ValueError(f"execution event hash mismatch at line {line_number}")
        events.append(event)
        previous_hash = actual_hash
    return events


def _append_event(workspace: Path, value: dict) -> dict:
    events = _read_events(workspace)
    event = {
        "schema_version": 1,
        "sequence": len(events) + 1,
        "recorded_at": now(),
        "previous_hash": events[-1]["event_hash"] if events else None,
        **value,
    }
    event["event_hash"] = canonical_sha256(event)
    path = workspace / "execution-events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return event


def _write_test_ids(master_rows: list[dict[str, str]], count: int) -> set[str]:
    selected = [
        _base_identifier(row["uuid"])
        for row in master_rows
        if str(
            row.get("evidence_confidence", row.get("project_confidence", ""))
        ).lower()
        in {"high", "frozen-eval"}
    ][:count]
    for row in master_rows:
        value = _base_identifier(row["uuid"])
        if len(selected) == count:
            break
        if value not in selected:
            selected.append(value)
    return set(selected)


def _validate_adapter_plan(
    adapter: dict,
    kind: str,
    catalog: dict,
    master_rows: list[dict[str, str]],
    hold_rows: list[dict[str, str]],
) -> None:
    if adapter.get("operation") != "snapshot-membership":
        raise ValueError("execution adapter plan must be a membership snapshot")
    if adapter.get("execution_kind") != kind:
        raise ValueError("adapter plan execution kind does not match the requested nonce")
    if adapter.get("catalog_plan_sha256") != catalog["plan_sha256"]:
        raise ValueError("adapter plan does not identify the registered catalog plan")
    source = catalog["source"]
    if (
        adapter.get("source_album_identifier") != source["identifier"]
        or adapter.get("expected_source_count") != source["count"]
        or adapter.get("source_membership_sha256") != source["membership_sha256"]
    ):
        raise ValueError("adapter plan source differs from the registered catalog plan")
    albums = adapter.get("albums", [])
    if not albums:
        raise ValueError("adapter plan has no album memberships")
    titles = [str(album.get("title", "")).strip() for album in albums]
    if any(not title for title in titles) or len(titles) != len(set(titles)):
        raise ValueError("adapter plan album titles must be non-empty and unique")
    roles = [str(album.get("role", "")).strip() for album in albums]
    if any(not role for role in roles) or len(roles) != len(set(roles)):
        raise ValueError("adapter plan album roles must be non-empty and unique")
    actual_by_role = {}
    for album in albums:
        identifiers = [
            _base_identifier(identifier)
            for identifier in album.get("asset_identifiers", [])
        ]
        if not identifiers or len(identifiers) != len(set(identifiers)):
            raise ValueError("adapter album memberships must be non-empty and unique")
        actual_by_role[str(album["role"])] = set(identifiers)

    catalog_by_role = {
        f"catalog:{album['key']}": {
            _base_identifier(identifier)
            for identifier in album.get("asset_ids", [])
        }
        for album in catalog["albums"]
    }
    master_ids = {
        _base_identifier(identifier)
        for identifier in next(
            album for album in catalog["albums"] if album.get("key") == "master"
        ).get("asset_ids", [])
    }
    test_ids = _write_test_ids(master_rows, catalog["write_test_count"])
    if kind == "write-test":
        if actual_by_role != {"aux:write-test": test_ids}:
            raise ValueError("write-test adapter plan differs from the bound test membership")
        return

    named = {
        _base_identifier(row["uuid"])
        for row in master_rows
        if row.get("persons", "").strip()
    }
    uncertain = {
        _base_identifier(row["uuid"])
        for row in master_rows
        if str(
            row.get("evidence_confidence", row.get("project_confidence", "unknown"))
        ).lower()
        in {"unknown", "low", "low-context", "visible-general"}
    }
    holds = {_base_identifier(row["uuid"]) for row in hold_rows}
    required_by_role = {
        **catalog_by_role,
        **({"aux:named": named} if named else {}),
        **({"aux:uncertain": uncertain} if uncertain else {}),
        **({"aux:holds": holds} if holds else {}),
        **({"aux:write-test": test_ids} if test_ids else {}),
    }
    if actual_by_role != required_by_role:
        unexpected = set(actual_by_role) - set(required_by_role)
        missing = set(required_by_role) - set(actual_by_role)
        changed = {
            role
            for role in set(actual_by_role) & set(required_by_role)
            if actual_by_role[role] != required_by_role[role]
        }
        raise ValueError(
            "production adapter roles differ from bound memberships: "
            f"unexpected={len(unexpected)} missing={len(missing)} changed={len(changed)}"
        )


def _validate_write_test_evidence(workspace: Path, state: dict, plan: dict) -> None:
    attempt = _latest_complete_attempt(state, "write_test")
    outputs = attempt.get("outputs", {})
    if "receipt" not in outputs or "verification" not in outputs:
        raise ValueError(
            "production requires write-test receipt and independent verification outputs"
        )
    receipt = _json_artifact(workspace, outputs["receipt"], "write-test receipt")
    verification = _json_artifact(
        workspace,
        outputs["verification"],
        "write-test verification",
    )
    events = _read_events(workspace)
    completions = [
        event
        for event in events
        if event.get("event_type") == "execution_completed"
        and event.get("kind") == "write-test"
        and event.get("plan_sha256") == plan["plan_sha256"]
        and event.get("receipt", {}).get("sha256") == outputs["receipt"].get("sha256")
    ]
    if len(completions) != 1:
        raise ValueError("write-test evidence lacks one completed current-plan nonce")
    completion = completions[0]
    starts = [
        event
        for event in events
        if event.get("event_type") == "execution_started"
        and event.get("execution_nonce") == completion.get("execution_nonce")
        and event.get("kind") == "write-test"
        and event.get("plan_sha256") == plan["plan_sha256"]
    ]
    if len(starts) != 1:
        raise ValueError("write-test completion lacks one immutable start")
    start = starts[0]
    expected = {
        "execution_nonce": completion["execution_nonce"],
        "plan_sha256": plan["plan_sha256"],
        "adapter_plan_sha256": start["adapter_plan"]["sha256"],
        "source_membership_sha256": plan["source"]["membership_sha256"],
        "receipt_sha256": outputs["receipt"]["sha256"],
    }
    if receipt.get("execution_nonce") != expected["execution_nonce"]:
        raise ValueError("recorded write-test receipt nonce differs from completion")
    if not _valid_digest(receipt.get("runtime_plan_sha256")):
        raise ValueError("recorded write-test receipt lacks runtime-plan identity")
    expected["runtime_plan_sha256"] = receipt["runtime_plan_sha256"]
    if any(verification.get(key) != value for key, value in expected.items()):
        raise ValueError("write-test verification identity differs from execution evidence")
    if not (
        verification.get("status") == "PASS"
        and verification.get("execution_kind") == "write-test"
        and verification.get("independent_read_only") is True
        and verification.get("missing_membership_count") == 0
        and verification.get("unexpected_membership_count") == 0
        and verification.get("outside_source_count") == 0
        and int(verification.get("verified_album_count", 0)) > 0
    ):
        raise ValueError("write-test independent verification is not release-passing")


def begin_execution(workspace: Path, kind: str, adapter_plan_path: Path) -> dict:
    if kind not in {"write-test", "production"}:
        raise ValueError("execution kind must be write-test or production")
    with workspace_lock(workspace):
        _, plan = _verify_registered_plan(workspace)
        state, _, master_rows, hold_rows = _validate_candidate_bindings(workspace, plan)
        required_phase = "validation" if kind == "write-test" else "write_test"
        if state["phases"][required_phase]["status"] != "complete":
            raise ValueError(
                f"{kind} execution requires completed {required_phase} phase"
            )
        if kind == "production":
            _validate_write_test_evidence(workspace, state, plan)
        adapter_bytes = adapter_plan_path.read_bytes()
        adapter = json.loads(adapter_bytes)
        _validate_adapter_plan(adapter, kind, plan, master_rows, hold_rows)
        adapter_artifact = _artifact_from_bytes(
            adapter_plan_path,
            workspace,
            adapter_bytes,
        )
        nonce = secrets.token_hex(16)
        event = _append_event(
            workspace,
            {
                "event_type": "execution_started",
                "kind": kind,
                "execution_nonce": nonce,
                "plan_sha256": plan["plan_sha256"],
                "adapter_plan": adapter_artifact,
            },
        )
        return {
            "kind": kind,
            "execution_nonce": nonce,
            "plan_sha256": plan["plan_sha256"],
            "adapter_plan_sha256": adapter_artifact["sha256"],
            "event_hash": event["event_hash"],
        }


def complete_execution(workspace: Path, nonce: str, receipt_path: Path) -> dict:
    with workspace_lock(workspace):
        _, plan = _verify_registered_plan(workspace)
        _, _, master_rows, hold_rows = _validate_candidate_bindings(workspace, plan)
        events = _read_events(workspace)
        starts = [
            event
            for event in events
            if event.get("event_type") == "execution_started"
            and event.get("execution_nonce") == nonce
        ]
        completions = [
            event
            for event in events
            if event.get("event_type") == "execution_completed"
            and event.get("execution_nonce") == nonce
        ]
        if len(starts) != 1 or completions:
            raise ValueError("execution nonce is unknown, duplicated, or already completed")
        receipt_bytes = receipt_path.read_bytes()
        receipt = json.loads(receipt_bytes)
        if receipt.get("execution_nonce") != nonce:
            raise ValueError("receipt execution nonce does not match the launch")
        if receipt.get("plan_sha256") != plan["plan_sha256"]:
            raise ValueError("receipt plan identity does not match the registered plan")
        if receipt.get("adapter_plan_sha256") != starts[0]["adapter_plan"]["sha256"]:
            raise ValueError("receipt adapter-plan identity does not match the launch")
        if not _valid_digest(receipt.get("runtime_plan_sha256")):
            raise ValueError("receipt lacks a valid runtime-plan identity")
        source = plan["source"]
        if receipt.get("source_album_identifier") != source["identifier"]:
            raise ValueError("receipt source identifier does not match the registered plan")
        if receipt.get("source_count") != source["count"]:
            raise ValueError("receipt source count does not match the registered plan")
        if receipt.get("source_membership_sha256") != source["membership_sha256"]:
            raise ValueError("receipt source membership does not match the registered plan")
        if receipt.get("status") != "completed":
            raise ValueError("receipt does not report completed status")
        adapter_path = resolve_artifact(workspace, starts[0]["adapter_plan"])
        adapter_bytes = adapter_path.read_bytes()
        if (
            hashlib.sha256(adapter_bytes).hexdigest()
            != starts[0]["adapter_plan"]["sha256"]
        ):
            raise ValueError("started adapter plan changed before completion")
        adapter = json.loads(adapter_bytes)
        _validate_adapter_plan(
            adapter,
            starts[0]["kind"],
            plan,
            master_rows,
            hold_rows,
        )
        if receipt.get("plan_id") != adapter.get("plan_id"):
            raise ValueError("receipt plan ID does not match the started adapter plan")
        if receipt.get("execution_kind") != starts[0]["kind"]:
            raise ValueError("receipt execution kind does not match the launch")
        if receipt.get("safety_mode") != adapter.get("safety_mode"):
            raise ValueError("receipt safety mode does not match the adapter plan")
        if receipt.get("independent_verification_required") is not True:
            raise ValueError("receipt must preserve the independent-verification gate")
        expected_folders = [
            (str(item.get("key", "")), str(item.get("title", "")))
            for item in adapter.get("folders", [])
        ]
        received_folders = [
            (str(item.get("key", "")), str(item.get("title", "")))
            for item in receipt.get("folders", [])
        ]
        folder_ids = [str(item.get("identifier", "")) for item in receipt.get("folders", [])]
        if (
            received_folders != expected_folders
            or any(not value for value in folder_ids)
            or len(folder_ids) != len(set(folder_ids))
        ):
            raise ValueError("receipt folder outcomes do not match the adapter plan")
        expected_albums = [
            (str(item.get("title", "")), len(item.get("asset_identifiers", [])))
            for item in adapter.get("albums", [])
        ]
        received_albums = [
            (str(item.get("title", "")), item.get("count"))
            for item in receipt.get("albums", [])
        ]
        album_ids = [str(item.get("identifier", "")) for item in receipt.get("albums", [])]
        if (
            received_albums != expected_albums
            or any(not value for value in album_ids)
            or len(album_ids) != len(set(album_ids))
        ):
            raise ValueError("receipt album outcomes do not match the adapter plan")
        event = _append_event(
            workspace,
            {
                "event_type": "execution_completed",
                "kind": starts[0]["kind"],
                "execution_nonce": nonce,
                "plan_sha256": plan["plan_sha256"],
                "receipt": _artifact_from_bytes(
                    receipt_path,
                    workspace,
                    receipt_bytes,
                ),
            },
        )
        return copy.deepcopy(event)


def idempotence_report(workspace: Path) -> dict:
    _, plan = _verify_registered_plan(workspace)
    events = _read_events(workspace)
    completed = [
        event
        for event in events
        if event.get("event_type") == "execution_completed"
        and event.get("kind") == "production"
        and event.get("plan_sha256") == plan["plan_sha256"]
    ]
    receipt_errors = []
    valid_completed = []
    adapter_hashes = set()
    for event in completed:
        receipt_path = Path(event["receipt"]["path"])
        if not receipt_path.is_absolute():
            receipt_path = workspace / receipt_path
        if not receipt_path.is_file():
            receipt_errors.append(f"missing receipt for event {event['sequence']}")
        elif sha256_file(receipt_path) != event["receipt"]["sha256"]:
            receipt_errors.append(f"changed receipt for event {event['sequence']}")
        else:
            starts = [
                start
                for start in events
                if start.get("event_type") == "execution_started"
                and start.get("execution_nonce") == event["execution_nonce"]
                and start.get("kind") == "production"
                and start.get("plan_sha256") == plan["plan_sha256"]
            ]
            if len(starts) != 1:
                receipt_errors.append(
                    f"missing or ambiguous start for event {event['sequence']}"
                )
                continue
            adapter_digest = starts[0].get("adapter_plan", {}).get("sha256")
            if not _valid_digest(adapter_digest):
                receipt_errors.append(
                    f"invalid adapter identity for event {event['sequence']}"
                )
                continue
            adapter_hashes.add(adapter_digest)
            valid_completed.append(event)
    nonces = {event["execution_nonce"] for event in valid_completed}
    receipt_hashes = {event["receipt"]["sha256"] for event in valid_completed}
    passed = (
        len(valid_completed) >= 2
        and len(nonces) >= 2
        and len(receipt_hashes) >= 2
        and len(adapter_hashes) == 1
        and not receipt_errors
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "plan_sha256": plan["plan_sha256"],
        "completed_production_attempts": len(valid_completed),
        "distinct_execution_nonces": len(nonces),
        "distinct_receipts": len(receipt_hashes),
        "distinct_adapter_plans": len(adapter_hashes),
        "independent_verification_required": True,
        "errors": receipt_errors,
    }
