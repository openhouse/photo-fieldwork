from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__


PHASES = (
    "brief",
    "source",
    "retrieval",
    "inspection",
    "evaluation",
    "final_freeze",
    "validation",
    "write_test",
    "production_commit",
    "independent_verification",
)
PHASE_STATUSES = {"pending", "in-progress", "complete", "failed", "skipped"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def initialize(
    workspace: Path,
    version: str,
    target_count: int,
    source_identifier: str,
    expected_source_count: int | None,
) -> dict:
    secure_workspace(workspace)
    state = {
        "schema_version": 2,
        "run_id": workspace.name,
        "version": version,
        "status": "initialized",
        "created_at": now(),
        "updated_at": now(),
        "target_count": target_count,
        "source": {
            "identifier": source_identifier,
            "expected_count": expected_source_count,
        },
        "tool": {
            "name": "photo-fieldwork",
            "version": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "phases": {phase: {"status": "pending", "attempts": []} for phase in PHASES},
    }
    atomic_json(workspace / "run-state.json", state)
    return state


def read_state(workspace: Path) -> dict:
    path = workspace / "run-state.json"
    if not path.exists():
        raise ValueError(f"run state not found: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 2:
        raise ValueError("run-state schema_version must be 2")
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


def record_transition(
    workspace: Path,
    phase: str,
    status: str,
    inputs: dict[str, Path] | None = None,
    outputs: dict[str, Path] | None = None,
    facts: dict[str, Any] | None = None,
) -> dict:
    if phase not in PHASES:
        raise ValueError(f"unknown phase: {phase}")
    if status not in PHASE_STATUSES:
        raise ValueError(f"invalid phase status: {status}")
    state = read_state(workspace)
    attempt = {
        "recorded_at": now(),
        "status": status,
        "inputs": {
            key: artifact(path, workspace) for key, path in sorted((inputs or {}).items())
        },
        "outputs": {
            key: artifact(path, workspace) for key, path in sorted((outputs or {}).items())
        },
        "facts": facts or {},
    }
    state["phases"][phase]["status"] = status
    state["phases"][phase]["attempts"].append(attempt)
    state["updated_at"] = now()
    state["status"] = "failed" if status == "failed" else f"{phase}:{status}"
    atomic_json(workspace / "run-state.json", state)
    return state


def freeze_lock(
    workspace: Path,
    effective_config: Path,
    master: Path,
    holds: Path,
    additional: dict[str, Path] | None = None,
) -> dict:
    paths = {
        "effective_config": effective_config,
        "master": master,
        "holds": holds,
        **(additional or {}),
    }
    lock = {
        "schema_version": 1,
        "created_at": now(),
        "run_id": read_state(workspace)["run_id"],
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
