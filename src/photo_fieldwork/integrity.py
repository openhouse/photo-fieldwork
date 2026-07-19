from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Iterable

from .artifacts import validate_source_snapshot
from .pipeline import validate


RELEASE_SEAL_SCHEMA_VERSION = 1


def canonical_json_fingerprint(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def row_artifact_fingerprint(rows: Iterable[dict], *, allow_empty: bool = False) -> str:
    canonical = []
    seen = set()
    for row in rows:
        identifier = str(row.get("uuid", "")).split("/", 1)[0].strip()
        if not identifier:
            raise ValueError("artifact rows require UUIDs")
        if identifier in seen:
            raise ValueError(f"artifact contains duplicate UUID: {identifier}")
        seen.add(identifier)
        normalized = {str(key): value for key, value in row.items()}
        normalized["uuid"] = identifier
        canonical.append(normalized)
    if not canonical and not allow_empty:
        raise ValueError("artifact must not be empty")
    return canonical_json_fingerprint(sorted(canonical, key=lambda row: row["uuid"]))


def _report_gate_errors(evaluation_report: dict, validation_report: dict) -> list[str]:
    errors = []
    if evaluation_report.get("passed") is not True:
        errors.append("evaluation report does not record a passing final evaluation")
    if str(validation_report.get("status", "")).upper() != "PASS":
        errors.append("validation report does not record PASS")
    if validation_report.get("errors"):
        errors.append("validation report still contains errors")
    return errors


def create_release_seal(
    master: list[dict],
    holds: list[dict],
    config: dict,
    source_snapshot: dict,
    evaluation_report: dict,
    validation_report: dict,
    *,
    created_at: str | None = None,
) -> dict:
    validate_source_snapshot(source_snapshot)
    gate_errors = _report_gate_errors(evaluation_report, validation_report)
    master_fingerprint = row_artifact_fingerprint(master)
    holds_fingerprint = row_artifact_fingerprint(holds, allow_empty=True)
    if evaluation_report.get("master_fingerprint") != master_fingerprint:
        gate_errors.append("evaluation report does not bind the current master")
    if validation_report.get("master_fingerprint") != master_fingerprint:
        gate_errors.append("validation report does not bind the current master")
    if validation_report.get("holds_fingerprint") != holds_fingerprint:
        gate_errors.append("validation report does not bind the current holds")
    actual_validation_errors, _ = validate(master, holds, config)
    if actual_validation_errors:
        gate_errors.append("current candidate fails deterministic validation: " + "; ".join(actual_validation_errors))
    if gate_errors:
        raise ValueError("; ".join(gate_errors))
    seal = {
        "schema_version": RELEASE_SEAL_SCHEMA_VERSION,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "master_count": len(master),
        "hold_count": len(holds),
        "source_fingerprint": canonical_json_fingerprint(source_snapshot),
        "master_fingerprint": master_fingerprint,
        "holds_fingerprint": holds_fingerprint,
        "config_fingerprint": canonical_json_fingerprint(config),
        "evaluation_fingerprint": canonical_json_fingerprint(evaluation_report),
        "validation_fingerprint": canonical_json_fingerprint(validation_report),
        "evaluation_passed": True,
        "validation_passed": True,
    }
    seal["seal_fingerprint"] = canonical_json_fingerprint(seal)
    return seal


def verify_release_seal(
    seal: dict,
    master: list[dict],
    holds: list[dict],
    config: dict,
    source_snapshot: dict,
    evaluation_report: dict,
    validation_report: dict,
) -> list[str]:
    errors = []
    if int(seal.get("schema_version", -1)) != RELEASE_SEAL_SCHEMA_VERSION:
        return [f"unsupported release seal schema: {seal.get('schema_version')}"]
    sealed_payload = {key: value for key, value in seal.items() if key != "seal_fingerprint"}
    if canonical_json_fingerprint(sealed_payload) != seal.get("seal_fingerprint"):
        errors.append("release seal fingerprint is invalid")
    comparisons = {
        "source": canonical_json_fingerprint(source_snapshot),
        "master": row_artifact_fingerprint(master),
        "holds": row_artifact_fingerprint(holds, allow_empty=True),
        "config": canonical_json_fingerprint(config),
        "evaluation": canonical_json_fingerprint(evaluation_report),
        "validation": canonical_json_fingerprint(validation_report),
    }
    for name, actual in comparisons.items():
        if actual != seal.get(f"{name}_fingerprint"):
            errors.append(f"{name} artifact changed after release sealing")
    if int(seal.get("master_count", -1)) != len(master):
        errors.append("master count changed after release sealing")
    if int(seal.get("hold_count", -1)) != len(holds):
        errors.append("holds count changed after release sealing")
    errors.extend(_report_gate_errors(evaluation_report, validation_report))
    if evaluation_report.get("master_fingerprint") != comparisons["master"]:
        errors.append("evaluation report does not bind the current master")
    if validation_report.get("master_fingerprint") != comparisons["master"]:
        errors.append("validation report does not bind the current master")
    if validation_report.get("holds_fingerprint") != comparisons["holds"]:
        errors.append("validation report does not bind the current holds")
    actual_validation_errors, _ = validate(master, holds, config)
    if actual_validation_errors:
        errors.append("current candidate fails deterministic validation: " + "; ".join(actual_validation_errors))
    return errors
