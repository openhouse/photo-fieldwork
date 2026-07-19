from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PHASES = [
    "initialize", "retrieve", "inspect", "select", "evaluate", "validate",
    "test-write", "production-write", "verify",
]
VALID_STATUSES = {"pending", "in-progress", "complete", "blocked"}
LEGACY_PHASES = {
    "brief": "initialize",
    "retrieval": "retrieve",
    "local_inspection": "inspect",
    "recursive_evaluation": "evaluate",
    "validation": "validate",
    "write_test": "test-write",
    "production_commit": "production-write",
    "independent_verification": "verify",
}


def state_path(workspace: Path) -> Path:
    return workspace / "run-state.json"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def new_state() -> dict:
    return {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "phases": {phase: {"status": "pending", "artifacts": []} for phase in PHASES},
    }


def load_state(workspace: Path) -> dict:
    path = state_path(workspace)
    if not path.exists():
        return new_state()
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise ValueError(f"unsupported run-state schema in {path}")
    incoming = state.setdefault("phases", {})
    normalized = {}
    for phase, value in incoming.items():
        phase = LEGACY_PHASES.get(phase, phase)
        if isinstance(value, str):
            status = "complete" if value == "completed" else value.replace("_", "-")
            normalized[phase] = {"status": status, "artifacts": []}
        elif isinstance(value, dict):
            normalized[phase] = value
    state["phases"] = normalized
    for phase in PHASES:
        state.setdefault("phases", {}).setdefault(phase, {"status": "pending", "artifacts": []})
    return state


def save_state(workspace: Path, state: dict) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = state_path(workspace)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def mark_phase(workspace: Path, phase: str, status: str, artifacts: list[Path]) -> dict:
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}; choose from {', '.join(PHASES)}")
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown status {status!r}; choose from {', '.join(sorted(VALID_STATUSES))}")
    records = []
    for artifact in artifacts:
        resolved = artifact.resolve()
        if not resolved.is_file():
            raise ValueError(f"artifact does not exist or is not a file: {artifact}")
        try:
            recorded_path = str(resolved.relative_to(workspace.resolve()))
        except ValueError:
            recorded_path = str(resolved)
        records.append({"path": recorded_path, "sha256": digest(resolved), "bytes": resolved.stat().st_size})
    state = load_state(workspace)
    state["phases"][phase] = {
        "status": status,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": records,
    }
    save_state(workspace, state)
    return state


def audit_state(workspace: Path) -> dict:
    state = load_state(workspace)
    errors = []
    for phase, phase_state in state["phases"].items():
        status = phase_state.get("status", "pending")
        if status not in VALID_STATUSES:
            errors.append(f"{phase}: invalid status {status!r}")
        if status != "complete":
            continue
        for artifact in phase_state.get("artifacts", []):
            path = Path(artifact["path"])
            if not path.is_absolute():
                path = workspace / path
            if not path.is_file():
                errors.append(f"{phase}: missing artifact {artifact['path']}")
            elif digest(path) != artifact.get("sha256"):
                errors.append(f"{phase}: changed artifact {artifact['path']}")
    next_phase = next(
        (phase for phase in PHASES if state["phases"][phase].get("status") != "complete"),
        None,
    )
    return {
        "status": "PASS" if not errors else "FAIL",
        "next_phase": next_phase,
        "complete": [phase for phase in PHASES if state["phases"][phase].get("status") == "complete"],
        "errors": errors,
    }
