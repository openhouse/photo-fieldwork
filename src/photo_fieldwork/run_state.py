from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import platform
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import __version__


PHASES = (
    "brief",
    "source",
    "retrieval",
    "inspection",
    "final_freeze",
    "evaluation",
    "validation",
    "write_test",
    "production_commit",
    "independent_verification",
)
PHASE_STATUSES = {"pending", "in-progress", "complete", "failed", "skipped"}
REQUIRED_PHASES = {
    "source",
    "inspection",
    "evaluation",
    "final_freeze",
    "validation",
    "write_test",
    "production_commit",
    "independent_verification",
}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@contextmanager
def workspace_lock(workspace: Path) -> Iterator[None]:
    lock_path = workspace / ".run-state.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def secure_workspace(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    path.chmod(0o700)
    for name in (
        "inventory",
        "manifests",
        "reports",
        "logs",
        "previews",
        "contact-sheets",
        "scripts",
        "review",
        "final",
    ):
        child = path / name
        child.mkdir(mode=0o700)


def event_payload(event: dict) -> dict:
    payload = dict(event)
    payload.pop("event_hash", None)
    return payload


def append_event(path: Path, event: dict) -> None:
    payload = (json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written == 0:
                raise OSError("incomplete run-event write")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_events(workspace: Path) -> list[dict]:
    path = workspace / "run-events.jsonl"
    if not path.exists():
        raise ValueError(f"run event ledger not found: {path}")
    events = []
    previous_hash = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid run event at line {line_number}: {error}") from error
        expected_sequence = len(events) + 1
        if event.get("sequence") != expected_sequence:
            raise ValueError(
                f"run event sequence mismatch at line {line_number}: expected {expected_sequence}"
            )
        if event.get("previous_hash") != previous_hash:
            raise ValueError(f"run event hash linkage failed at line {line_number}")
        expected_hash = canonical_sha256(event_payload(event))
        if event.get("event_hash") != expected_hash:
            raise ValueError(f"run event hash mismatch at line {line_number}")
        events.append(event)
        previous_hash = expected_hash
    if not events or events[0].get("event_type") != "run_initialized":
        raise ValueError("run event ledger must begin with run_initialized")
    return events


def migrate_legacy_state(workspace: Path, state: dict) -> dict:
    """Create the first immutable ledger event for a pre-ledger schema-v2 run."""
    migrated = copy.deepcopy(state)
    migrated.setdefault("revision", 1)
    migrated.setdefault("source", {})
    migrated["source"].setdefault("membership_sha256", None)
    migrated.setdefault(
        "phases",
        {phase: {"status": "pending", "attempts": []} for phase in PHASES},
    )
    for phase in PHASES:
        migrated["phases"].setdefault(phase, {"status": "pending", "attempts": []})
    migrated["migration"] = {
        "from": "schema-v2-materialized-state-without-ledger",
        "recorded_at": now(),
    }
    event = {
        "schema_version": 1,
        "sequence": 1,
        "event_type": "run_initialized",
        "recorded_at": now(),
        "previous_hash": None,
        "details": {"legacy_state_migration": True},
        "state_after": state_snapshot(migrated),
    }
    event["event_hash"] = canonical_sha256(event_payload(event))
    payload = (json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    ledger_path = workspace / "run-events.jsonl"
    try:
        descriptor = os.open(
            ledger_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        return state
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written == 0:
                raise OSError("incomplete legacy migration event write")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    migrated["ledger_head"] = event["event_hash"]
    migrated["event_count"] = 1
    atomic_json(workspace / "run-state.json", migrated)
    return migrated


def state_snapshot(state: dict) -> dict:
    snapshot = copy.deepcopy(state)
    snapshot.pop("ledger_head", None)
    snapshot.pop("event_count", None)
    return snapshot


def write_event(workspace: Path, event_type: str, state: dict, details: dict) -> dict:
    events = read_events(workspace) if (workspace / "run-events.jsonl").exists() else []
    event = {
        "schema_version": 1,
        "sequence": len(events) + 1,
        "event_type": event_type,
        "recorded_at": now(),
        "previous_hash": events[-1]["event_hash"] if events else None,
        "details": details,
        "state_after": state_snapshot(state),
    }
    event["event_hash"] = canonical_sha256(event_payload(event))
    append_event(workspace / "run-events.jsonl", event)
    return event


def recover_state(workspace: Path) -> dict:
    with workspace_lock(workspace):
        state_path = workspace / "run-state.json"
        if not (workspace / "run-events.jsonl").exists() and state_path.is_file():
            legacy = json.loads(state_path.read_text(encoding="utf-8"))
            if legacy.get("schema_version") != 2:
                raise ValueError("run-state schema_version must be 2")
            migrate_legacy_state(workspace, legacy)
        events = read_events(workspace)
        state = copy.deepcopy(events[-1]["state_after"])
        state["ledger_head"] = events[-1]["event_hash"]
        state["event_count"] = len(events)
        atomic_json(workspace / "run-state.json", state)
        errors = verify_recorded_artifacts(workspace, state)
        result = copy.deepcopy(state)
        result["recovery_report"] = {
            "status": "PASS" if not errors else "BLOCKED",
            "errors": errors,
        }
        return result


def initialize(
    workspace: Path,
    version: str,
    target_count: int,
    source_identifier: str,
    expected_source_count: int | None,
    source_membership_sha256: str | None = None,
) -> dict:
    if source_membership_sha256 is not None:
        digest = source_membership_sha256.strip().lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("source membership SHA-256 must be 64 hexadecimal characters")
        source_membership_sha256 = digest
    secure_workspace(workspace)
    state = {
        "schema_version": 2,
        "revision": 1,
        "run_id": workspace.name,
        "version": version,
        "status": "initialized",
        "created_at": now(),
        "updated_at": now(),
        "target_count": target_count,
        "source": {
            "identifier": source_identifier,
            "expected_count": expected_source_count,
            "membership_sha256": source_membership_sha256,
        },
        "tool": {
            "name": "photo-fieldwork",
            "version": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "phases": {phase: {"status": "pending", "attempts": []} for phase in PHASES},
    }
    event = write_event(
        workspace,
        "run_initialized",
        state,
        {"version": version, "target_count": target_count},
    )
    state["ledger_head"] = event["event_hash"]
    state["event_count"] = 1
    atomic_json(workspace / "run-state.json", state)
    return state


def read_state(workspace: Path) -> dict:
    path = workspace / "run-state.json"
    if not path.exists():
        raise ValueError(f"run state not found: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 2:
        raise ValueError("run-state schema_version must be 2")
    if not (workspace / "run-events.jsonl").exists():
        state = migrate_legacy_state(workspace, state)
    events = read_events(workspace)
    if state.get("revision") != events[-1]["state_after"].get("revision"):
        raise ValueError("materialized run state revision does not match the event ledger")
    if state.get("ledger_head") != events[-1]["event_hash"]:
        raise ValueError("materialized run state does not match the event-ledger head")
    if state_snapshot(state) != events[-1]["state_after"]:
        raise ValueError("materialized run state differs from the event ledger")
    return state


def artifact(path: Path, workspace: Path) -> dict:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(workspace.resolve())
        recorded_path = str(relative)
    except ValueError:
        recorded_path = str(resolved)
    return {
        "path": recorded_path,
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def resolve_artifact(workspace: Path, record: dict) -> Path:
    path = Path(record["path"])
    return path if path.is_absolute() else workspace / path


def recorded_artifact_drift(workspace: Path, state: dict) -> list[tuple[str, str]]:
    drift = []
    for phase, phase_state in state.get("phases", {}).items():
        for attempt_index, attempt in enumerate(phase_state.get("attempts", []), start=1):
            if attempt.get("status") != "complete":
                continue
            for direction in ("inputs", "outputs"):
                for name, expected in attempt.get(direction, {}).items():
                    path = resolve_artifact(workspace, expected)
                    label = f"{phase} attempt {attempt_index} {direction}.{name}"
                    if not path.is_file():
                        drift.append((phase, f"missing recorded artifact {label}"))
                    elif path.stat().st_size != expected.get("bytes"):
                        drift.append((phase, f"size mismatch for recorded artifact {label}"))
                    elif sha256_file(path) != expected.get("sha256"):
                        drift.append((phase, f"hash mismatch for recorded artifact {label}"))
    return drift


def verify_recorded_artifacts(workspace: Path, state: dict) -> list[str]:
    return [error for _, error in recorded_artifact_drift(workspace, state)]


def validate_transition(state: dict, phase: str, status: str, facts: dict[str, Any]) -> None:
    phase_index = PHASES.index(phase)
    predecessor_errors = [
        predecessor
        for predecessor in PHASES[:phase_index]
        if state["phases"][predecessor]["status"] not in {"complete", "skipped"}
    ]
    if status in {"in-progress", "complete"} and predecessor_errors:
        raise ValueError(
            f"phase {phase} cannot {status} before predecessors complete: "
            + ", ".join(predecessor_errors)
        )
    if status == "skipped":
        if phase in REQUIRED_PHASES:
            raise ValueError(f"required phase {phase} cannot be skipped")
        if not str(facts.get("waiver_reason", "")).strip():
            raise ValueError("skipped phases require facts.waiver_reason")


def record_transition(
    workspace: Path,
    phase: str,
    status: str,
    inputs: dict[str, Path] | None = None,
    outputs: dict[str, Path] | None = None,
    facts: dict[str, Any] | None = None,
    expected_revision: int | None = None,
) -> dict:
    if phase not in PHASES:
        raise ValueError(f"unknown phase: {phase}")
    if status not in PHASE_STATUSES:
        raise ValueError(f"invalid phase status: {status}")
    facts = facts or {}
    with workspace_lock(workspace):
        state = read_state(workspace)
        if expected_revision is not None and state.get("revision") != expected_revision:
            raise ValueError(
                f"revision conflict: expected {expected_revision}, found {state.get('revision')}"
            )
        artifact_errors = verify_recorded_artifacts(workspace, state)
        if artifact_errors:
            raise ValueError("recorded artifact drift blocks transition: " + "; ".join(artifact_errors))
        validate_transition(state, phase, status, facts)
        if status == "complete" and phase in REQUIRED_PHASES and not outputs:
            raise ValueError(f"required phase {phase} cannot complete without output evidence")
        attempt = {
            "recorded_at": now(),
            "status": status,
            "inputs": {
                key: artifact(path, workspace) for key, path in sorted((inputs or {}).items())
            },
            "outputs": {
                key: artifact(path, workspace) for key, path in sorted((outputs or {}).items())
            },
            "facts": facts,
        }
        state["phases"][phase]["status"] = status
        state["phases"][phase]["attempts"].append(attempt)
        state["updated_at"] = now()
        state["status"] = "failed" if status == "failed" else f"{phase}:{status}"
        state["revision"] += 1
        event = write_event(
            workspace,
            "phase_transition",
            state,
            {"phase": phase, "status": status, "attempt": attempt},
        )
        state["ledger_head"] = event["event_hash"]
        state["event_count"] = event["sequence"]
        atomic_json(workspace / "run-state.json", state)
        return state


def record_invalidation(
    workspace: Path,
    phase: str,
    reason: str,
    expected_revision: int,
) -> dict:
    if phase not in PHASES:
        raise ValueError(f"unknown phase: {phase}")
    if not reason.strip():
        raise ValueError("invalidation requires a reason")
    with workspace_lock(workspace):
        state = read_state(workspace)
        if state.get("revision") != expected_revision:
            raise ValueError(
                f"revision conflict: expected {expected_revision}, found {state.get('revision')}"
            )
        artifact_drift = recorded_artifact_drift(workspace, state)
        if not artifact_drift:
            raise ValueError("invalidation requires recorded artifact drift")
        artifact_errors = [error for _, error in artifact_drift]
        drift_phases = {drift_phase for drift_phase, _ in artifact_drift}
        earliest_drift = min(drift_phases, key=PHASES.index)
        if phase != earliest_drift:
            raise ValueError(
                f"invalidation must begin at earliest drift phase {earliest_drift}"
            )
        invalidated_phases = []
        phase_index = PHASES.index(phase)
        for affected_phase in PHASES[phase_index:]:
            phase_state = state["phases"][affected_phase]
            invalidated_attempts = 0
            for attempt in phase_state.get("attempts", []):
                if attempt.get("status") == "complete":
                    attempt["status"] = "invalidated"
                    attempt["invalidated_reason"] = reason
                    invalidated_attempts += 1
            if invalidated_attempts or phase_state.get("status") not in {"pending", "skipped"}:
                invalidated_phases.append(affected_phase)
            phase_state["status"] = "pending"
        failure_attempt = {
            "recorded_at": now(),
            "status": "failed",
            "inputs": {},
            "outputs": {},
            "facts": {
                "reason": reason,
                "artifact_errors": artifact_errors,
                "invalidated_phases": invalidated_phases,
            },
        }
        state["phases"][phase]["status"] = "failed"
        state["phases"][phase]["attempts"].append(failure_attempt)
        state["updated_at"] = now()
        state["status"] = f"{phase}:invalidated"
        state["revision"] += 1
        event = write_event(
            workspace,
            "artifact_invalidation",
            state,
            {
                "phase": phase,
                "reason": reason,
                "artifact_errors": artifact_errors,
                "invalidated_phases": invalidated_phases,
            },
        )
        state["ledger_head"] = event["event_hash"]
        state["event_count"] = event["sequence"]
        atomic_json(workspace / "run-state.json", state)
        return state


def freeze_lock(
    workspace: Path,
    effective_config: Path,
    master: Path,
    holds: Path,
    additional: dict[str, Path] | None = None,
) -> dict:
    state = read_state(workspace)
    paths = {
        "effective_config": effective_config,
        "master": master,
        "holds": holds,
        **(additional or {}),
    }
    lock = {
        "schema_version": 1,
        "created_at": now(),
        "run_id": state["run_id"],
        "run_revision": state["revision"],
        "run_ledger_head": state["ledger_head"],
        "source": copy.deepcopy(state["source"]),
        "tool_version": __version__,
        "artifacts": {key: artifact(path, workspace) for key, path in sorted(paths.items())},
    }
    atomic_json(workspace / "run-lock.json", lock)
    return lock


def verify_lock(workspace: Path) -> tuple[list[str], dict]:
    path = workspace / "run-lock.json"
    if not path.exists():
        return [f"run lock not found: {path}"], {"status": "FAIL"}
    lock = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    state = read_state(workspace)
    if lock.get("run_id") != state.get("run_id"):
        errors.append("run lock belongs to another workspace")
    if lock.get("source") != state.get("source"):
        errors.append("run lock source identity differs from the frozen run source")
    checked = 0
    for name, expected in lock.get("artifacts", {}).items():
        artifact_path = Path(expected["path"])
        if not artifact_path.is_absolute():
            artifact_path = workspace / artifact_path
        if not artifact_path.exists():
            errors.append(f"missing locked artifact {name}: {artifact_path}")
            continue
        checked += 1
        actual = sha256_file(artifact_path)
        if actual != expected["sha256"]:
            errors.append(f"hash mismatch for locked artifact {name}")
    return errors, {
        "status": "PASS" if not errors else "FAIL",
        "checked_artifacts": checked,
        "locked_artifacts": len(lock.get("artifacts", {})),
        "errors": errors,
    }


def append_config_decision(
    workspace: Path,
    round_id: str,
    field: str,
    before: Any,
    after: Any,
    reason: str,
    reviewer: str,
) -> dict:
    read_state(workspace)
    path = workspace / "config-decisions.jsonl"
    records = []
    if path.exists():
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    previous_hash = records[-1]["record_hash"] if records else None
    record = {
        "sequence": len(records) + 1,
        "recorded_at": now(),
        "round_id": round_id,
        "field": field,
        "before": before,
        "after": after,
        "reason": reason,
        "reviewer": reviewer,
        "previous_hash": previous_hash,
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record["record_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    records.append(record)
    temporary = path.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return record
