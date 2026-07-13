from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


RUN_STATE_SCHEMA_VERSION = 2
PHASE_STATUSES = {"pending", "started", "completed", "failed", "blocked", "superseded"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


@contextmanager
def run_lock(run: Path) -> Iterator[None]:
    run.mkdir(parents=True, exist_ok=True)
    lock_path = run / ".run-state.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
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


def append_event(path: Path, event: dict) -> None:
    payload = (json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written == 0:
                raise OSError("incomplete event-ledger write")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_events(run: Path) -> list[dict]:
    path = run / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid event ledger line {line_number}: {error}") from error
        expected = len(events) + 1
        if int(event.get("revision", -1)) != expected:
            raise ValueError(f"event revision mismatch at line {line_number}: expected {expected}")
        events.append(event)
    return events


def materialize_state(events: list[dict]) -> dict:
    if not events or events[0].get("event") != "run_initialized":
        raise ValueError("event ledger does not begin with run_initialized")
    first = events[0]
    state = {
        "schema_version": RUN_STATE_SCHEMA_VERSION,
        "run_id": first["run_id"],
        "revision": 0,
        "status": "initialized",
        "created_at": first["timestamp"],
        "metadata": dict(first.get("metadata", {})),
        "phases": {phase: "pending" for phase in first.get("phases", [])},
        "artifacts": {},
    }
    for event in events:
        state["revision"] = int(event["revision"])
        if event["event"] == "phase_transition":
            phase = event["phase"]
            state["phases"][phase] = event["status"]
            state["status"] = event["status"] if event["status"] in {"failed", "blocked"} else "active"
            if event.get("artifact"):
                state["artifacts"][phase] = {
                    "path": event["artifact"],
                    "sha256": event["artifact_sha256"],
                }
        state["updated_at"] = event["timestamp"]
    if state["phases"] and all(value in {"completed", "superseded"} for value in state["phases"].values()):
        state["status"] = "completed"
    return state


def initialize_run(run: Path, run_id: str, phases: list[str], metadata: dict | None = None) -> dict:
    if not phases or len(phases) != len(set(phases)):
        raise ValueError("run phases must be non-empty and unique")
    with run_lock(run):
        ledger = run / "events.jsonl"
        if ledger.exists() or (run / "run-state.json").exists():
            raise ValueError(f"run already initialized: {run}")
        event = {
            "schema_version": RUN_STATE_SCHEMA_VERSION,
            "revision": 1,
            "event": "run_initialized",
            "run_id": run_id,
            "timestamp": utc_now(),
            "phases": phases,
            "metadata": metadata or {},
        }
        append_event(ledger, event)
        state = materialize_state([event])
        atomic_write_json(run / "run-state.json", state)
        return state


def transition_phase(
    run: Path,
    phase: str,
    status: str,
    expected_revision: int | None = None,
    artifact: Path | None = None,
    note: str = "",
) -> dict:
    if status not in PHASE_STATUSES - {"pending"}:
        raise ValueError(f"invalid phase status: {status}")
    with run_lock(run):
        events = read_events(run)
        state = materialize_state(events)
        if phase not in state["phases"]:
            raise ValueError(f"unknown run phase: {phase}")
        if expected_revision is not None and state["revision"] != expected_revision:
            raise ValueError(f"revision conflict: expected {expected_revision}, found {state['revision']}")
        artifact_path = None
        artifact_sha256 = None
        if status == "completed":
            if artifact is None or not artifact.is_file():
                raise ValueError("completed transitions require an existing artifact")
            artifact_path = str(artifact.resolve())
            artifact_sha256 = sha256_file(artifact)
        event = {
            "schema_version": RUN_STATE_SCHEMA_VERSION,
            "revision": state["revision"] + 1,
            "event": "phase_transition",
            "run_id": state["run_id"],
            "timestamp": utc_now(),
            "phase": phase,
            "status": status,
            "note": note,
            "artifact": artifact_path,
            "artifact_sha256": artifact_sha256,
        }
        append_event(run / "events.jsonl", event)
        events.append(event)
        state = materialize_state(events)
        atomic_write_json(run / "run-state.json", state)
        return state


def recover_state(run: Path) -> dict:
    with run_lock(run):
        state = materialize_state(read_events(run))
        atomic_write_json(run / "run-state.json", state)
        return state
