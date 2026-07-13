from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


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


def initialize(path: Path, run_id: str, target_count: int, source_identifier: str) -> dict:
    if path.exists():
        raise ValueError(f"refusing to overwrite run state: {path}")
    state = {
        "schema_version": 1,
        "run_id": run_id,
        "target_count": target_count,
        "source_identifier": source_identifier,
        "phase": "briefed",
        "status": "active",
        "created_at": timestamp(),
        "updated_at": timestamp(),
        "history": [
            {
                "phase": "briefed",
                "recorded_at": timestamp(),
                "receipts": [],
            }
        ],
    }
    save(path, state)
    return state


def load(path: Path) -> dict:
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("phase") not in PHASES:
        raise ValueError(f"invalid run phase: {state.get('phase')}")
    return state


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def next_phase(state: dict) -> str | None:
    index = PHASES.index(state["phase"])
    return PHASES[index + 1] if index + 1 < len(PHASES) else None


def advance(path: Path, phase: str, receipts: list[Path], note: str = "") -> dict:
    state = load(path)
    expected = next_phase(state)
    if phase == state["phase"]:
        previous = state["history"][-1]
        current_receipts = [receipt_entry(item) for item in receipts]
        if previous.get("receipts", []) == current_receipts:
            return state
        raise ValueError(f"phase {phase} already recorded with different receipts")
    if phase != expected:
        raise ValueError(f"illegal phase transition: {state['phase']} -> {phase}; expected {expected}")
    recorded_at = timestamp()
    previous_at = datetime.fromisoformat(state["history"][-1]["recorded_at"])
    current_at = datetime.fromisoformat(recorded_at)
    entry = {
        "phase": phase,
        "recorded_at": recorded_at,
        "elapsed_since_previous_seconds": round((current_at - previous_at).total_seconds(), 3),
        "receipts": [receipt_entry(item) for item in receipts],
    }
    if note:
        entry["note"] = note
    state["phase"] = phase
    state["status"] = "complete" if phase == "complete" else "active"
    state["updated_at"] = timestamp()
    state["history"].append(entry)
    save(path, state)
    return state


def verify(state: dict) -> list[str]:
    errors = []
    for entry in state.get("history", []):
        for receipt in entry.get("receipts", []):
            path = Path(receipt["path"])
            if not path.is_file():
                errors.append(f"missing receipt file: {path}")
            elif file_hash(path) != receipt["sha256"]:
                errors.append(f"receipt hash changed: {path}")
    return errors
