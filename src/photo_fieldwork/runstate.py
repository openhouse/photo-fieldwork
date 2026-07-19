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

from .release import canonical_sha256


PHASES = [
    "briefed",
    "inventoried",
    "retrieved",
    "inspection-planned",
    "inspected",
    "selected",
    "evaluation-open",
    "evaluation-closed",
    "revised",
    "validated",
    "write-test-planned",
    "write-test-verified",
    "production-planned",
    "production-written",
    "independently-verified",
    "complete",
]
ATTEMPT_PHASES = {"write-test-verified", "production-written"}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def receipt_entry(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"receipt input is not a file: {path}")
    return {
        "path": str(path.resolve()),
        "sha256": file_hash(path),
        "bytes": path.stat().st_size,
    }


def ledger_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".events.jsonl")


def lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock")


@contextmanager
def locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path(path).open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
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


def _event_digest(event: dict) -> str:
    payload = dict(event)
    payload.pop("event_sha256", None)
    return canonical_sha256(payload)


def _append_event(path: Path, event: dict) -> None:
    payload = (json.dumps(event, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(ledger_path(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
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


def read_events(path: Path) -> list[dict]:
    ledger = ledger_path(path)
    if not ledger.is_file():
        return []
    events = []
    previous = ""
    for line_number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid event ledger line {line_number}: {exc}") from exc
        expected_revision = len(events) + 1
        if event.get("revision") != expected_revision:
            raise ValueError(f"event revision mismatch at line {line_number}: expected {expected_revision}")
        if event.get("previous_event_sha256", "") != previous:
            raise ValueError(f"event chain mismatch at line {line_number}")
        if event.get("event_sha256") != _event_digest(event):
            raise ValueError(f"event digest mismatch at line {line_number}")
        previous = event["event_sha256"]
        events.append(event)
    return events


def materialize(events: list[dict]) -> dict:
    if not events or events[0].get("event") != "run-initialized":
        raise ValueError("event ledger does not begin with run-initialized")
    first = events[0]
    state = {
        "schema_version": 2,
        "run_id": first["run_id"],
        "target_count": first["target_count"],
        "source_identifier": first["source_identifier"],
        "revision": 0,
        "phase": "briefed",
        "status": "active",
        "created_at": first["recorded_at"],
        "updated_at": first["recorded_at"],
        "event_head_sha256": "",
        "history": [],
    }
    seen_attempts: set[str] = set()
    for event in events:
        state["revision"] = event["revision"]
        state["event_head_sha256"] = event["event_sha256"]
        state["updated_at"] = event["recorded_at"]
        if event["event"] == "run-initialized":
            state["history"].append(
                {"phase": "briefed", "recorded_at": event["recorded_at"], "receipts": []}
            )
            continue
        if event.get("event") != "phase-advanced":
            raise ValueError(f"unknown run event: {event.get('event')}")
        expected = next_phase(state)
        if event.get("phase") != expected:
            raise ValueError(f"ledger phase transition is out of order: {state['phase']} -> {event.get('phase')}")
        attempt_id = str(event.get("attempt_id", ""))
        if attempt_id:
            if attempt_id in seen_attempts:
                raise ValueError(f"event ledger reuses attempt_id: {attempt_id}")
            seen_attempts.add(attempt_id)
        state["phase"] = event["phase"]
        state["status"] = "complete" if event["phase"] == "complete" else "active"
        history_entry = {
            "phase": event["phase"],
            "recorded_at": event["recorded_at"],
            "elapsed_since_previous_seconds": event["elapsed_since_previous_seconds"],
            "receipts": event["receipts"],
        }
        if event.get("note"):
            history_entry["note"] = event["note"]
        if attempt_id:
            history_entry["attempt_id"] = attempt_id
        state["history"].append(history_entry)
    return state


def _new_event(events: list[dict], payload: dict) -> dict:
    event = {
        "schema_version": 2,
        "revision": len(events) + 1,
        "previous_event_sha256": events[-1]["event_sha256"] if events else "",
        **payload,
    }
    event["event_sha256"] = _event_digest(event)
    return event


def initialize(path: Path, run_id: str, target_count: int, source_identifier: str) -> dict:
    with locked(path):
        if path.exists() or ledger_path(path).exists():
            raise ValueError(f"refusing to overwrite run state: {path}")
        recorded_at = timestamp()
        event = _new_event(
            [],
            {
                "event": "run-initialized",
                "run_id": run_id,
                "target_count": target_count,
                "source_identifier": source_identifier,
                "recorded_at": recorded_at,
            },
        )
        _append_event(path, event)
        state = materialize([event])
        save(path, state)
        return state


def load(path: Path) -> dict:
    events = read_events(path)
    materialized = materialize(events)
    try:
        observed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("materialized run state is missing or corrupt; run recovery from the event ledger") from exc
    if observed != materialized:
        raise ValueError("materialized run state does not match the append-only event ledger; run recovery")
    return observed


def recover(path: Path) -> dict:
    with locked(path):
        state = materialize(read_events(path))
        save(path, state)
        return state


def next_phase(state: dict) -> str | None:
    index = PHASES.index(state["phase"])
    return PHASES[index + 1] if index + 1 < len(PHASES) else None


def advance(
    path: Path,
    phase: str,
    receipts: list[Path],
    note: str = "",
    *,
    expected_revision: int | None = None,
    attempt_id: str = "",
) -> dict:
    with locked(path):
        events = read_events(path)
        state = materialize(events)
        if expected_revision is not None and state["revision"] != expected_revision:
            raise ValueError(f"revision conflict: expected {expected_revision}, found {state['revision']}")
        current_receipts = [receipt_entry(item) for item in receipts]
        if phase == state["phase"]:
            previous = state["history"][-1]
            if previous.get("receipts", []) == current_receipts and previous.get("attempt_id", "") == attempt_id:
                return state
            raise ValueError(f"phase {phase} already recorded with different evidence")
        expected = next_phase(state)
        if phase != expected:
            raise ValueError(f"illegal phase transition: {state['phase']} -> {phase}; expected {expected}")
        if phase in ATTEMPT_PHASES and not attempt_id:
            raise ValueError(f"phase {phase} requires a unique attempt_id")
        used_attempts = {
            str(entry.get("attempt_id")) for entry in state["history"] if entry.get("attempt_id")
        }
        if attempt_id and attempt_id in used_attempts:
            raise ValueError(f"attempt_id has already been used: {attempt_id}")
        recorded_at = timestamp()
        previous_at = datetime.fromisoformat(state["history"][-1]["recorded_at"])
        current_at = datetime.fromisoformat(recorded_at)
        event = _new_event(
            events,
            {
                "event": "phase-advanced",
                "run_id": state["run_id"],
                "phase": phase,
                "recorded_at": recorded_at,
                "elapsed_since_previous_seconds": round((current_at - previous_at).total_seconds(), 3),
                "receipts": current_receipts,
                "note": note,
                "attempt_id": attempt_id,
            },
        )
        _append_event(path, event)
        events.append(event)
        state = materialize(events)
        save(path, state)
        return state


def verify(state: dict, path: Path | None = None) -> list[str]:
    errors = []
    for entry in state.get("history", []):
        for receipt in entry.get("receipts", []):
            receipt_path = Path(receipt["path"])
            if not receipt_path.is_file():
                errors.append(f"missing receipt file: {receipt_path}")
            elif receipt_path.stat().st_size != receipt["bytes"]:
                errors.append(f"receipt size changed: {receipt_path}")
            elif file_hash(receipt_path) != receipt["sha256"]:
                errors.append(f"receipt hash changed: {receipt_path}")
    if path is not None:
        try:
            if materialize(read_events(path)) != state:
                errors.append("materialized state does not match the append-only event ledger")
        except ValueError as exc:
            errors.append(str(exc))
    return errors
