from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import validate_source_snapshot


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
PHASE_STATUSES = {"pending", "in_progress", "completed", "failed"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(workspace: Path, event: dict) -> dict:
    path = workspace / "events.jsonl"
    workspace.mkdir(parents=True, exist_ok=True)
    value = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "at": now(),
        **event,
    }
    line = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    materialize_state(workspace)
    return value


def initialize_run(
    workspace: Path,
    run_id: str,
    target_count: int,
    source_snapshot: dict,
    version: str | None = None,
) -> dict:
    events = workspace / "events.jsonl"
    if events.exists():
        raise ValueError(f"run ledger already exists: {events}")
    if target_count < 1:
        raise ValueError("target_count must be positive")
    validate_source_snapshot(source_snapshot)
    return append_event(
        workspace,
        {
            "event_type": "run.initialized",
            "run_id": run_id,
            "data": {
                "target_count": target_count,
                "version": version,
                "source_snapshot": source_snapshot,
            },
        },
    )


def record_phase(
    workspace: Path,
    phase: str,
    status: str,
    data: dict | None = None,
    attempt_id: str | None = None,
) -> dict:
    if phase not in PHASES:
        raise ValueError(f"unknown phase: {phase}")
    if status not in PHASE_STATUSES:
        raise ValueError(f"unknown phase status: {status}")
    state = derive_state(workspace)
    if data is not None and not isinstance(data, dict):
        raise ValueError("phase event data must be an object")
    phase_index = PHASES.index(phase)
    incomplete_earlier = [
        earlier
        for earlier in PHASES[:phase_index]
        if state["phases"][earlier] != "completed"
    ]
    if incomplete_earlier:
        raise ValueError(
            f"cannot record {phase} before earlier phase completion: {', '.join(incomplete_earlier)}"
        )
    if attempt_id:
        used_attempts = {
            event.get("attempt_id")
            for event in read_events(workspace)
            if event.get("attempt_id")
        }
        if attempt_id in used_attempts:
            raise ValueError(f"attempt_id already recorded: {attempt_id}")
    return append_event(
        workspace,
        {
            "event_type": "phase.updated",
            "run_id": state["run_id"],
            "phase": phase,
            "status": status,
            "attempt_id": attempt_id,
            "data": data or {},
        },
    )


def read_events(workspace: Path) -> list[dict]:
    path = workspace / "events.jsonl"
    if not path.exists():
        raise ValueError(f"run ledger not found: {path}")
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid run event on line {number}: {error}") from error
    if not events:
        raise ValueError(f"run ledger is empty: {path}")
    return events


def derive_state(workspace: Path) -> dict:
    events = read_events(workspace)
    initial = events[0]
    if initial.get("event_type") != "run.initialized":
        raise ValueError("first run event must be run.initialized")
    data = initial.get("data") or {}
    phases = {phase: "pending" for phase in PHASES}
    attempts = {phase: [] for phase in PHASES}
    for event in events[1:]:
        if event.get("run_id") != initial.get("run_id"):
            raise ValueError(f"run_id changed in event: {event.get('event_id', 'unknown')}")
        if event.get("event_type") != "phase.updated":
            continue
        phase = event.get("phase")
        status = event.get("status")
        if phase not in PHASES or status not in PHASE_STATUSES:
            raise ValueError(f"invalid phase event: {event.get('event_id', 'unknown')}")
        phases[phase] = status
        attempts[phase].append(event["event_id"])
    complete = all(status == "completed" for status in phases.values())
    failed = [phase for phase, status in phases.items() if status == "failed"]
    return {
        "schema_version": 1,
        "run_id": initial["run_id"],
        "status": "complete" if complete else "failed" if failed else "in_progress",
        "created_at": initial["at"],
        "updated_at": events[-1]["at"],
        "target_count": int(data["target_count"]),
        "version": data.get("version"),
        "source_snapshot": data["source_snapshot"],
        "phases": phases,
        "attempt_event_ids": attempts,
        "event_count": len(events),
    }


def next_phase(state: dict) -> str | None:
    for phase in PHASES:
        if state["phases"][phase] != "completed":
            return phase
    return None


def materialize_state(workspace: Path) -> dict:
    state = derive_state(workspace)
    path = workspace / "run-state.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return state
