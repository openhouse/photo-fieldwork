from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


PHASES = (
    "preflight",
    "retrieval",
    "inspection",
    "review",
    "validation",
    "write_test",
    "production_commit",
    "independent_verification",
)
PASSING = {"pass", "complete"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:64] or "photo-field"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: Path) -> dict:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"receipt artifact must be an existing file: {resolved}")
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "size": stat.st_size,
        "sha256": file_sha256(resolved),
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def receipts(workspace: Path) -> list[dict]:
    directory = workspace / "receipts"
    if not directory.exists():
        return []
    return [_read_json(path) for path in sorted(directory.glob("*.json"))]


def verify_receipt_integrity(workspace: Path) -> dict:
    """Recheck the evidence that earlier phase receipts claim to preserve."""
    workspace = workspace.expanduser().resolve()
    records = receipts(workspace)
    run_id = _read_json(workspace / "run.json")["run_id"]
    issues = []
    checked_artifacts = 0
    for expected_sequence, record in enumerate(records, start=1):
        phase = record.get("phase", "unknown")
        if record.get("sequence") != expected_sequence:
            issues.append(
                {
                    "phase": phase,
                    "kind": "receipt-sequence",
                    "expected": expected_sequence,
                    "actual": record.get("sequence"),
                }
            )
        if record.get("run_id") != run_id:
            issues.append(
                {
                    "phase": phase,
                    "kind": "run-identity",
                    "expected": run_id,
                    "actual": record.get("run_id"),
                }
            )
        for direction in ("inputs", "outputs"):
            for artifact in record.get(direction, []):
                checked_artifacts += 1
                path = Path(artifact.get("path", "")).expanduser()
                if not path.is_file():
                    issues.append(
                        {
                            "phase": phase,
                            "kind": "artifact-missing",
                            "direction": direction,
                            "path": str(path),
                        }
                    )
                    continue
                actual_size = path.stat().st_size
                if actual_size != artifact.get("size"):
                    issues.append(
                        {
                            "phase": phase,
                            "kind": "artifact-size",
                            "direction": direction,
                            "path": str(path),
                            "expected": artifact.get("size"),
                            "actual": actual_size,
                        }
                    )
                    continue
                actual_digest = file_sha256(path)
                if actual_digest != artifact.get("sha256"):
                    issues.append(
                        {
                            "phase": phase,
                            "kind": "artifact-sha256",
                            "direction": direction,
                            "path": str(path),
                            "expected": artifact.get("sha256"),
                            "actual": actual_digest,
                        }
                    )
    return {
        "status": "PASS" if not issues else "FAIL",
        "receipt_count": len(records),
        "checked_artifact_count": checked_artifacts,
        "issues": issues,
    }


def derive_state(workspace: Path) -> dict:
    metadata = _read_json(workspace / "run.json")
    records = receipts(workspace)
    latest = {}
    for record in records:
        latest[record["phase"]] = record
    phases = {
        phase: latest.get(phase, {}).get("status", "pending")
        for phase in PHASES
    }
    integrity = verify_receipt_integrity(workspace)
    complete = integrity["status"] == "PASS" and all(phases[phase] in PASSING for phase in PHASES)
    next_phase = next((phase for phase in PHASES if phases[phase] not in PASSING), None)
    if integrity["status"] == "FAIL":
        next_phase = next(
            (issue.get("phase") for issue in integrity["issues"] if issue.get("phase") in PHASES),
            next_phase,
        )
    return {
        **metadata,
        "status": "complete" if complete else "blocked" if integrity["status"] == "FAIL" else "in_progress",
        "next_phase": next_phase,
        "phases": phases,
        "integrity": integrity,
        "receipt_count": len(records),
        "updated_at": records[-1]["recorded_at"] if records else metadata["created_at"],
    }


def write_state(workspace: Path) -> dict:
    state = derive_state(workspace)
    _write_json(workspace / "run-state.json", state)
    return state


def init_run(
    root: Path,
    version: str,
    slug: str,
    target_count: int,
    source_identifier: str,
    expected_source_count: int | None,
    code_commit: str | None = None,
    parent_run: str | None = None,
) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    reservation_dir = root / ".photo-fieldwork" / "versions"
    reservation_dir.mkdir(parents=True, exist_ok=True)
    reservation = reservation_dir / f"{safe_slug(version)}.json"
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    workspace = root / f"{safe_slug(version)}-{safe_slug(slug)}-{stamp}"
    payload = {
        "schema_version": 1,
        "version": version,
        "workspace": str(workspace),
        "reserved_at": now(),
    }
    try:
        descriptor = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        existing = _read_json(reservation)
        raise ValueError(
            f"semantic version {version} is already reserved by {existing.get('workspace')}"
        ) from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        for name in (
            "inventory",
            "manifests",
            "reports",
            "logs",
            "previews",
            "contact-sheets",
            "evaluations",
            "plans",
            "receipts",
        ):
            (workspace / name).mkdir(parents=True, exist_ok=False)
        metadata = {
            "schema_version": 1,
            "run_id": workspace.name,
            "version": version,
            "slug": slug,
            "created_at": now(),
            "target_count": target_count,
            "source_identifier": source_identifier,
            "expected_source_count": expected_source_count,
            "code_commit": code_commit,
            "parent_run": parent_run,
            "publication_edit_complete": False,
            "external_uploads_permitted": False,
        }
        _write_json(workspace / "run.json", metadata)
        write_state(workspace)
    except Exception:
        reservation.unlink(missing_ok=True)
        raise
    return workspace


def record_phase(
    workspace: Path,
    phase: str,
    status: str,
    inputs: list[Path] | None = None,
    outputs: list[Path] | None = None,
    metrics: dict | None = None,
    note: str | None = None,
) -> dict:
    workspace = workspace.expanduser().resolve()
    if phase not in PHASES:
        raise ValueError(f"unknown run phase: {phase}")
    status = status.casefold()
    if status not in {"pass", "fail", "complete"}:
        raise ValueError("phase status must be pass, fail, or complete")
    existing = receipts(workspace)
    integrity = verify_receipt_integrity(workspace)
    if existing and status in PASSING and integrity["status"] != "PASS":
        raise ValueError(
            "run integrity failed; preserve this workspace and begin an explicit recovery run"
        )
    latest = {}
    for item in existing:
        latest[item["phase"]] = item
    phase_index = PHASES.index(phase)
    missing = [
        prior for prior in PHASES[:phase_index]
        if latest.get(prior, {}).get("status") not in PASSING
    ]
    if missing and status in PASSING:
        raise ValueError(f"cannot pass {phase}; prerequisite phases incomplete: {', '.join(missing)}")
    sequence = len(existing) + 1
    record = {
        "schema_version": 1,
        "sequence": sequence,
        "run_id": _read_json(workspace / "run.json")["run_id"],
        "phase": phase,
        "status": status,
        "recorded_at": now(),
        "inputs": [artifact_record(path) for path in inputs or []],
        "outputs": [artifact_record(path) for path in outputs or []],
        "metrics": metrics or {},
        "note": note,
    }
    receipt_path = workspace / "receipts" / f"{sequence:04d}-{phase}-{status}.json"
    _write_json(receipt_path, record)
    write_state(workspace)
    return record


def render_report(workspace: Path) -> str:
    state = derive_state(workspace)
    records = receipts(workspace)
    lines = [
        f"# {state['version']}: Photo Fieldwork run report",
        "",
        f"- Status: **{state['status'].upper()}**",
        f"- Run: `{state['run_id']}`",
        f"- Target: {state['target_count']:,}",
        f"- Source: `{state['source_identifier']}`",
        f"- Expected source count: {state['expected_source_count']}",
        f"- Code commit: `{state.get('code_commit') or 'not recorded'}`",
        f"- External uploads permitted: {str(state['external_uploads_permitted']).lower()}",
        f"- Final publication edit performed: {str(state['publication_edit_complete']).lower()}",
        f"- Receipt integrity: **{state['integrity']['status']}**",
        "",
        "## Phases",
        "",
    ]
    for phase in PHASES:
        lines.append(f"- `{phase}`: {state['phases'][phase]}")
    lines.extend(["", "## Receipts", ""])
    for record in records:
        metric_text = ", ".join(f"{key}={value}" for key, value in record["metrics"].items())
        suffix = f"; {metric_text}" if metric_text else ""
        lines.append(
            f"- {record['sequence']:04d} `{record['phase']}`: {record['status']}{suffix}"
        )
    lines.extend(
        [
            "",
            "This report is derived from append-only phase receipts. It describes an editor-ready field only when every phase passes. It never establishes publication permission.",
            "",
        ]
    )
    return "\n".join(lines)


def cleanup_report(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    categories = {}
    total = 0
    for name in ("previews", "contact-sheets", "logs"):
        directory = workspace / name
        files = [path for path in directory.rglob("*") if path.is_file()] if directory.exists() else []
        size = sum(path.stat().st_size for path in files)
        categories[name] = {"files": len(files), "bytes": size}
        total += size
    protected = ["run.json", "run-state.json", "receipts", "manifests", "reports", "evaluations", "plans"]
    return {
        "workspace": str(workspace),
        "report_only": True,
        "potentially_disposable": categories,
        "potentially_disposable_bytes": total,
        "always_preserve": protected,
        "photos_versions_affected": False,
    }
