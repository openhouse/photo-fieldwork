#!/usr/bin/env python3
"""Append-only, artifact-bound run lifecycle for Photo Fieldwork."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ZERO_HASH = "0" * 64


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _event_hash(event: dict) -> str:
    payload = {key: value for key, value in event.items() if key != "event_sha256"}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


@contextmanager
def _locked(workspace: Path):
    lock_path = workspace / ".run-state.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _append_event(path: Path, event: dict) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        os.chmod(path, 0o600)
        line = json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n"
        os.write(descriptor, line.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _artifact_receipt(workspace: Path, source: Path) -> dict:
    candidate = source if source.is_absolute() else workspace / source
    if candidate.is_symlink():
        raise ValueError(f"run artifact must be a regular file: {source}")
    path = candidate.resolve()
    try:
        relative = path.relative_to(workspace.resolve())
    except ValueError as error:
        raise ValueError(f"run artifact must remain inside workspace: {source}") from error
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"run artifact must be a regular file: {relative}")
    return {
        "path": relative.as_posix(),
        "size": path.stat().st_size,
        "sha256": _file_sha256(path),
    }


def _read_events(workspace: Path) -> list[dict]:
    ledger = workspace / "run-events.jsonl"
    if not ledger.is_file():
        raise ValueError(f"run event ledger is missing: {ledger}")
    events = []
    previous = ZERO_HASH
    for index, raw in enumerate(ledger.read_text(encoding="utf-8").splitlines()):
        if not raw.strip():
            continue
        event = json.loads(raw)
        if event.get("revision") != index:
            raise ValueError(f"run event revision mismatch at line {index + 1}")
        if event.get("previous_event_sha256") != previous:
            raise ValueError(f"run event hash chain mismatch at revision {index}")
        actual = _event_hash(event)
        if event.get("event_sha256") != actual:
            raise ValueError(f"run event content hash mismatch at revision {index}")
        previous = actual
        events.append(event)
    if not events or events[0].get("event_type") != "run_initialized":
        raise ValueError("run event ledger lacks its initialization event")
    return events


def _verify_artifacts(workspace: Path, events: Iterable[dict]) -> None:
    for event in events:
        for receipt in event.get("artifacts", []):
            candidate = workspace / receipt["path"]
            if candidate.is_symlink():
                raise ValueError(f"completed run artifact is not a regular file: {receipt['path']}")
            path = candidate.resolve()
            try:
                path.relative_to(workspace.resolve())
            except ValueError as error:
                raise ValueError("run event references an artifact outside the workspace") from error
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"completed run artifact is missing: {receipt['path']}")
            if path.stat().st_size != receipt["size"] or _file_sha256(path) != receipt["sha256"]:
                raise ValueError(f"completed run artifact drifted: {receipt['path']}")


def _materialize(events: list[dict]) -> dict:
    initial = events[0]
    phases = list(initial["phases"])
    completed: list[str] = []
    for event in events[1:]:
        if event.get("event_type") != "phase_completed":
            raise ValueError(f"unknown run event type: {event.get('event_type')}")
        expected = phases[len(completed)] if len(completed) < len(phases) else None
        if event.get("phase") != expected:
            raise ValueError(
                f"illegal phase order at revision {event['revision']}: "
                f"expected {expected}, found {event.get('phase')}"
            )
        completed.append(event["phase"])
    next_phase = phases[len(completed)] if len(completed) < len(phases) else None
    return {
        "schema_version": 2,
        "run_id": initial["run_id"],
        "status": "completed" if next_phase is None else "active",
        "revision": events[-1]["revision"],
        "ledger_head_sha256": events[-1]["event_sha256"],
        "created_at": initial["created_at"],
        "metadata": initial.get("metadata", {}),
        "next_phase": next_phase,
        "phases": {phase: "completed" if phase in completed else "pending" for phase in phases},
    }


def initialize_run(
    workspace: Path,
    *,
    run_id: str,
    phases: list[str],
    metadata: dict,
) -> dict:
    workspace.mkdir(parents=True, exist_ok=True)
    os.chmod(workspace, 0o700)
    if not phases or len(phases) != len(set(phases)):
        raise ValueError("run phases must be a non-empty unique sequence")
    with _locked(workspace):
        ledger = workspace / "run-events.jsonl"
        if ledger.exists():
            raise ValueError(f"run event ledger already exists: {ledger}")
        event = {
            "schema_version": 1,
            "revision": 0,
            "event_type": "run_initialized",
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "previous_event_sha256": ZERO_HASH,
            "phases": phases,
            "metadata": metadata,
            "artifacts": [],
        }
        event["event_sha256"] = _event_hash(event)
        _append_event(ledger, event)
        state = _materialize([event])
        _atomic_json(workspace / "run-state.json", state)
        return state


def _load_status_unlocked(workspace: Path, *, repair: bool, verify_artifacts: bool) -> dict:
    events = _read_events(workspace)
    if verify_artifacts:
        _verify_artifacts(workspace, events)
    state = _materialize(events)
    state_path = workspace / "run-state.json"
    current = None
    if state_path.is_file():
        try:
            current = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = None
    if current != state:
        if not repair:
            raise ValueError("materialized run state does not match the event ledger")
        _atomic_json(state_path, state)
    return state


def load_status(workspace: Path, *, repair: bool = True, verify_artifacts: bool = True) -> dict:
    workspace = workspace.resolve()
    with _locked(workspace):
        return _load_status_unlocked(
            workspace,
            repair=repair,
            verify_artifacts=verify_artifacts,
        )


def advance_phase(
    workspace: Path,
    *,
    phase: str,
    artifacts: list[Path],
    expected_revision: int,
) -> dict:
    workspace = workspace.resolve()
    if not artifacts:
        raise ValueError("phase completion requires at least one artifact")
    with _locked(workspace):
        state = _load_status_unlocked(workspace, repair=True, verify_artifacts=True)
        if state["revision"] != expected_revision:
            raise ValueError(
                f"run revision conflict: expected {expected_revision}, found {state['revision']}"
            )
        if phase != state["next_phase"]:
            raise ValueError(f"cannot complete {phase}; next legal phase is {state['next_phase']}")
        receipts = [_artifact_receipt(workspace, artifact) for artifact in artifacts]
        event = {
            "schema_version": 1,
            "revision": expected_revision + 1,
            "event_type": "phase_completed",
            "run_id": state["run_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "previous_event_sha256": state["ledger_head_sha256"],
            "phase": phase,
            "artifacts": receipts,
        }
        event["event_sha256"] = _event_hash(event)
        _append_event(workspace / "run-events.jsonl", event)
        return _load_status_unlocked(workspace, repair=True, verify_artifacts=True)
