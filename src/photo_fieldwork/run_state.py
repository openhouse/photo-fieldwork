from __future__ import annotations

import hashlib
import json
import fcntl
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


PHASES = (
    "brief",
    "retrieval",
    "local_inspection",
    "recursive_evaluation",
    "validation",
    "write_test",
    "production_commit",
    "independent_verification",
)


def timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary_path.unlink(missing_ok=True)


@contextmanager
def run_lock(workspace: Path):
    with (workspace / ".run-state.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_run_event(workspace: Path, event: dict) -> None:
    payload = (json.dumps(event, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(workspace / "run-events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
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


def read_run_events(workspace: Path) -> list[dict]:
    path = workspace / "run-events.jsonl"
    if not path.exists():
        return []
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid run event at line {line_number}: {error}") from error
        expected = len(events) + 1
        if event.get("revision") != expected:
            raise ValueError(
                f"run event revision mismatch at line {line_number}: expected {expected}"
            )
        events.append(event)
    return events


def _commit_state(workspace: Path, state: dict, event_type: str) -> dict:
    event = {
        "revision": state["revision"],
        "event": event_type,
        "at": timestamp(),
        "run_id": state["run_id"],
        "state": state,
    }
    append_run_event(workspace, event)
    write_json(workspace / "run-state.json", state)
    return state


def initialize(
    workspace: Path,
    *,
    run_id: str,
    version: str,
    target_count: int,
    source_identifier: str,
    expected_source_count: int,
    config_hash: str | None = None,
    code_version: str | None = None,
) -> dict:
    workspace.mkdir(parents=True, exist_ok=False)
    for name in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets", "scripts"):
        (workspace / name).mkdir()
    state = {
        "schema_version": 2,
        "run_id": run_id,
        "version": version,
        "status": "initialized",
        "revision": 1,
        "created_at": timestamp(),
        "target_count": target_count,
        "source": {
            "identifier": source_identifier,
            "expected_count": expected_source_count,
        },
        "config_hash": config_hash,
        "code_version": code_version,
        "phases": {phase: {"status": "pending", "artifacts": []} for phase in PHASES},
        "history": [],
    }
    return _commit_state(workspace, state, "initialized")


def _latest(paths: list[Path]) -> Path | None:
    return max(paths, key=lambda item: item.stat().st_mtime_ns) if paths else None


def _json_pass(path: Path, *keys: str) -> bool:
    try:
        value = read_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    for key in keys:
        candidate = value.get(key)
        if candidate is True or str(candidate).upper() == "PASS":
            return True
    return False


def _artifact(path: Path, workspace: Path) -> dict:
    return {
        "path": str(path.relative_to(workspace)),
        "sha256": file_hash(path),
        "bytes": path.stat().st_size,
    }


def infer_phases(workspace: Path) -> dict[str, tuple[str, list[Path]]]:
    brief = [path for path in (workspace / "brief.md", workspace / "retrieval.json", workspace / "config.json") if path.exists()]
    candidates = sorted((workspace / "manifests").glob("candidate-pool*.csv"))
    inspection_receipts = sorted((workspace / "manifests").glob("*inspection-receipt.json"))
    evaluation_reports = sorted((workspace / "reports").glob("**/evaluation-report.json"))
    validation_reports = sorted((workspace / "reports").glob("**/validation-report.json"))
    test_receipts = sorted((workspace / "manifests").glob("*write-test-receipt.json"))
    production_receipts = sorted((workspace / "manifests").glob("*photo-archive-receipt.json"))
    verification_reports = sorted((workspace / "reports").glob("*verification.json"))

    inspection_complete = []
    for path in inspection_receipts:
        try:
            value = read_json(path)
            if value.get("completed_count") == value.get("requested_count") and not value.get("external_uploads_performed", False):
                inspection_complete.append(path)
        except (OSError, json.JSONDecodeError):
            continue
    evaluation_pass = [path for path in evaluation_reports if _json_pass(path, "passed", "status")]
    validation_pass = [path for path in validation_reports if _json_pass(path, "status", "passed")]
    verification_pass = [path for path in verification_reports if _json_pass(path, "status", "passed")]

    def verification_kind(path: Path) -> str:
        if path.suffix == ".json":
            try:
                plan_id = str(read_json(path).get("plan_id", "")).casefold()
                if "write-test" in plan_id:
                    return "write-test"
                if "production" in plan_id:
                    return "production"
            except (OSError, json.JSONDecodeError):
                pass
        name = path.name.casefold()
        return "write-test" if "write-test" in name else "production" if "production" in name else "unknown"

    test_verification = [path for path in verification_pass if verification_kind(path) == "write-test"]
    production_verification = [path for path in verification_pass if verification_kind(path) == "production"]

    def result(ok: bool, artifacts: list[Path]) -> tuple[str, list[Path]]:
        return ("complete" if ok else "pending", artifacts)

    return {
        "brief": result(len(brief) == 3, brief),
        "retrieval": result(bool(candidates), [_latest(candidates)] if candidates else []),
        "local_inspection": result(bool(inspection_complete), inspection_complete),
        "recursive_evaluation": result(bool(evaluation_pass), [_latest(evaluation_pass)] if evaluation_pass else []),
        "validation": result(bool(validation_pass), [_latest(validation_pass)] if validation_pass else []),
        "write_test": result(
            bool(test_receipts and test_verification),
            [path for path in (_latest(test_receipts), _latest(test_verification)) if path],
        ),
        "production_commit": result(bool(production_receipts), [_latest(production_receipts)] if production_receipts else []),
        "independent_verification": result(
            bool(production_verification),
            [_latest(production_verification)] if production_verification else [],
        ),
    }


def _artifact_drift(workspace: Path, state: dict) -> dict[str, list[str]]:
    drift: dict[str, list[str]] = {}
    for phase in PHASES:
        previous = state["phases"].get(phase, {})
        if previous.get("status") not in {"complete", "blocked"}:
            continue
        for artifact in previous.get("artifacts", []):
            path = workspace / artifact["path"]
            reasons = []
            if not path.is_file():
                reasons.append(f"missing {artifact['path']}")
            else:
                if path.stat().st_size != artifact.get("bytes"):
                    reasons.append(f"byte count changed for {artifact['path']}")
                if file_hash(path) != artifact.get("sha256"):
                    reasons.append(f"SHA-256 changed for {artifact['path']}")
            if reasons:
                drift.setdefault(phase, []).extend(reasons)
    return drift


def reconcile(
    workspace: Path,
    expected_revision: int | None = None,
    *,
    allow_phase_updates: tuple[str, ...] = (),
) -> dict:
    unknown_updates = set(allow_phase_updates) - set(PHASES)
    if unknown_updates:
        raise ValueError(f"unknown phase update: {sorted(unknown_updates)[0]}")
    if allow_phase_updates and expected_revision is None:
        raise ValueError("explicit phase updates require expected_revision")
    state_path = workspace / "run-state.json"
    with run_lock(workspace):
        state = read_json(state_path)
        events = read_run_events(workspace)
        if (
            not events
            or events[-1].get("revision") != state.get("revision")
            or events[-1].get("state") != state
        ):
            raise ValueError("run state and event ledger diverged; recover before reconciling")
        if expected_revision is not None and state.get("revision") != expected_revision:
            raise ValueError(
                f"revision conflict: expected {expected_revision}, found {state.get('revision')}"
            )
        inferred = infer_phases(workspace)
        drift = _artifact_drift(workspace, state)
        changes = []
        for phase in PHASES:
            previous_phase = state["phases"].get(phase, {"status": "pending", "artifacts": []})
            if phase in drift:
                current_phase = {
                    "status": "blocked",
                    "artifacts": previous_phase.get("artifacts", []),
                    "errors": drift[phase],
                }
            else:
                status, paths = inferred[phase]
                inferred_phase = {
                    "status": status,
                    "artifacts": [_artifact(path, workspace) for path in paths if path],
                }
                previous_complete = previous_phase.get("status") in {"complete", "blocked"}
                artifacts_changed = (
                    previous_complete
                    and previous_phase.get("artifacts", []) != inferred_phase["artifacts"]
                )
                if artifacts_changed and phase not in allow_phase_updates:
                    current_phase = {
                        "status": "blocked",
                        "artifacts": previous_phase.get("artifacts", []),
                        "errors": [
                            "completed phase artifacts changed; rerun reconcile with "
                            f"--allow-phase-update {phase} after review"
                        ],
                    }
                else:
                    current_phase = inferred_phase
            state["phases"][phase] = current_phase
            if previous_phase != current_phase:
                changes.append(
                    {
                        "phase": phase,
                        "previous": previous_phase.get("status", "pending"),
                        "new": current_phase["status"],
                    }
                )
        statuses = [state["phases"][phase]["status"] for phase in PHASES]
        state["status"] = (
            "blocked"
            if "blocked" in statuses
            else "ready-to-finalize"
            if all(status == "complete" for status in statuses)
            else "in-progress"
        )
        state["reconciled_at"] = timestamp()
        state["revision"] = int(state.get("revision", 0)) + 1
        if changes:
            state.setdefault("history", []).append(
                {"at": state["reconciled_at"], "revision": state["revision"], "changes": changes}
            )
        return _commit_state(workspace, state, "reconciled")


def finalize(workspace: Path, expected_revision: int | None = None) -> dict:
    state = reconcile(workspace, expected_revision=expected_revision)
    incomplete = [phase for phase in PHASES if state["phases"][phase]["status"] != "complete"]
    if incomplete:
        raise ValueError(f"cannot finalize; incomplete phases: {', '.join(incomplete)}")
    with run_lock(workspace):
        current = read_json(workspace / "run-state.json")
        if current.get("revision") != state.get("revision"):
            raise ValueError(
                f"revision conflict: expected {state.get('revision')}, found {current.get('revision')}"
            )
        state = current
        state["status"] = "complete"
        state["completed_at"] = timestamp()
        state["revision"] += 1
        return _commit_state(workspace, state, "finalized")


def recover(workspace: Path) -> dict:
    with run_lock(workspace):
        events = read_run_events(workspace)
        if not events or not isinstance(events[-1].get("state"), dict):
            raise ValueError("run event ledger has no recoverable state")
        state = events[-1]["state"]
        if state.get("revision") != events[-1].get("revision"):
            raise ValueError("latest run event contains an incoherent state revision")
        write_json(workspace / "run-state.json", state)
        return state
