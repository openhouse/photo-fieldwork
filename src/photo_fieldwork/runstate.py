from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .integrity import file_sha256


PHASES = (
    "doctor",
    "source_snapshot",
    "retrieval_preflight",
    "local_inspection",
    "preview_integrity",
    "selection_evaluation",
    "feedback_expansion",
    "validation",
    "write_test",
    "production_commit",
    "idempotence_check",
    "independent_verification",
    "editor_evidence_handoff",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_path(workspace: Path) -> Path:
    return workspace / "run-state.json"


def load_state(workspace: Path) -> dict:
    path = state_path(workspace)
    if not path.is_file():
        raise ValueError(f"run state not found: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 2:
        raise ValueError(f"unsupported run-state schema: {state.get('schema_version')}")
    return state


def save_state(workspace: Path, state: dict) -> None:
    path = state_path(workspace)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def initialize_run(
    workspace: Path,
    brief: Path,
    profile: Path,
    version: str,
    target: int,
) -> tuple[dict, bool]:
    workspace = workspace.resolve()
    if state_path(workspace).exists():
        state = load_state(workspace)
        if state["version"] != version or state["target_count"] != target:
            raise ValueError("existing run version or target does not match the resume request")
        if state["brief_sha256"] != file_sha256(brief):
            raise ValueError("existing run was initialized with a different brief")
        if state["profile_sha256"] != file_sha256(profile):
            raise ValueError("existing run was initialized with a different local profile")
        return state, False

    profile_data = json.loads(profile.read_text(encoding="utf-8"))
    required_profile = {"workspace_root", "photos_database", "permissioned_app", "source", "folders"}
    missing = sorted(required_profile - set(profile_data))
    if missing:
        raise ValueError(f"local profile is missing: {', '.join(missing)}")
    if not isinstance(profile_data["source"], dict) or not {
        "kind", "identifier", "expected_count"
    } <= set(profile_data["source"]):
        raise ValueError("local profile source requires kind, identifier, and expected_count")
    if not isinstance(profile_data["folders"], dict) or not {
        "root_identifier", "private_identifier", "audit_identifier"
    } <= set(profile_data["folders"]):
        raise ValueError("local profile folders require root, private, and audit identifiers")
    if target < 1:
        raise ValueError("target must be positive")

    workspace.mkdir(parents=True, exist_ok=False)
    os.chmod(workspace, 0o700)
    for name in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets"):
        child = workspace / name
        child.mkdir()
        os.chmod(child, 0o700)
    brief_copy = workspace / "brief.md"
    brief_copy.write_text(brief.read_text(encoding="utf-8"), encoding="utf-8")

    state = {
        "schema_version": 2,
        "run_id": workspace.name,
        "version": version,
        "target_count": target,
        "status": "in_progress",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "brief_sha256": file_sha256(brief_copy),
        "profile_sha256": file_sha256(profile),
        "privacy": {
            "network_access_allowed": False,
            "external_uploads_allowed": False,
            "publication_approval_default": "not-approved",
        },
        "phases": {
            phase: {"status": "pending", "completed_at": None, "artifacts": []}
            for phase in PHASES
        },
    }
    save_state(workspace, state)
    return state, True


def next_phase(state: dict) -> str | None:
    return next((phase for phase in PHASES if state["phases"][phase]["status"] != "complete"), None)


def artifact_receipt(workspace: Path, artifact: Path) -> dict:
    workspace = workspace.resolve()
    path = artifact.resolve()
    if not path.is_file():
        raise ValueError(f"checkpoint artifact not found: {path}")
    try:
        relative = path.relative_to(workspace)
    except ValueError as error:
        raise ValueError("checkpoint artifacts must remain inside the private run workspace") from error
    return {
        "path": relative.as_posix(),
        "size": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def verify_completed_artifacts(workspace: Path, state: dict, phases: tuple[str, ...]) -> None:
    for phase in phases:
        phase_state = state["phases"][phase]
        if phase_state["status"] != "complete":
            continue
        for receipt in phase_state["artifacts"]:
            relative = receipt.get("path")
            if not relative:
                raise ValueError(f"completed phase {phase} has an unlocatable legacy artifact receipt")
            path = (workspace / relative).resolve()
            try:
                path.relative_to(workspace.resolve())
            except ValueError as error:
                raise ValueError(f"completed phase {phase} has an artifact outside the workspace") from error
            if (
                not path.is_file()
                or path.stat().st_size != receipt.get("size")
                or file_sha256(path) != receipt.get("sha256")
            ):
                raise ValueError(f"completed phase {phase} has different artifact digests")


def checkpoint(workspace: Path, phase: str, artifacts: list[Path]) -> tuple[dict, bool]:
    if phase not in PHASES:
        raise ValueError(f"unknown phase: {phase}")
    state = load_state(workspace)
    if not artifacts:
        raise ValueError("a phase checkpoint requires at least one artifact receipt")
    phase_index = PHASES.index(phase)
    incomplete_prior = [
        name for name in PHASES[:phase_index]
        if state["phases"][name]["status"] != "complete"
    ]
    if incomplete_prior:
        raise ValueError(f"cannot complete {phase}; prior phases pending: {', '.join(incomplete_prior)}")

    verify_completed_artifacts(workspace, state, PHASES[:phase_index])
    receipts = [artifact_receipt(workspace, artifact) for artifact in artifacts]
    receipts.sort(key=lambda item: item["path"])
    if len({item["path"] for item in receipts}) != len(receipts):
        raise ValueError("checkpoint contains duplicate artifact paths")

    current = state["phases"][phase]
    if current["status"] == "complete":
        verify_completed_artifacts(workspace, state, (phase,))
        if current["artifacts"] != receipts:
            raise ValueError(f"completed phase {phase} has different artifact digests")
        return state, False

    current.update({"status": "complete", "completed_at": utc_now(), "artifacts": receipts})
    state["updated_at"] = utc_now()
    if next_phase(state) is None:
        state["status"] = "complete"
        state["completed_at"] = utc_now()
    save_state(workspace, state)
    return state, True
