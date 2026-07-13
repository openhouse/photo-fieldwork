from __future__ import annotations

import hashlib
import json
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
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    write_json(workspace / "run-state.json", state)
    return state


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
    verification_markdown = sorted((workspace / "reports").glob("*verification.md"))

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
    verification_pass.extend(
        path for path in verification_markdown
        if "Unexpected memberships: 0" in path.read_text(encoding="utf-8", errors="ignore")
        and "Missing memberships: 0" in path.read_text(encoding="utf-8", errors="ignore")
    )

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


def reconcile(workspace: Path) -> dict:
    state_path = workspace / "run-state.json"
    state = read_json(state_path)
    inferred = infer_phases(workspace)
    changes = []
    for phase in PHASES:
        status, paths = inferred[phase]
        artifacts = [_artifact(path, workspace) for path in paths if path]
        previous = state["phases"].get(phase, {}).get("status", "pending")
        state["phases"][phase] = {"status": status, "artifacts": artifacts}
        if previous != status:
            changes.append({"phase": phase, "previous": previous, "new": status})
    state["status"] = "ready-to-finalize" if all(
        state["phases"][phase]["status"] == "complete" for phase in PHASES
    ) else "in-progress"
    state["reconciled_at"] = timestamp()
    if changes:
        state.setdefault("history", []).append({"at": state["reconciled_at"], "changes": changes})
    write_json(state_path, state)
    return state


def finalize(workspace: Path) -> dict:
    state = reconcile(workspace)
    incomplete = [phase for phase in PHASES if state["phases"][phase]["status"] != "complete"]
    if incomplete:
        raise ValueError(f"cannot finalize; incomplete phases: {', '.join(incomplete)}")
    state["status"] = "complete"
    state["completed_at"] = timestamp()
    write_json(workspace / "run-state.json", state)
    return state
