from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Iterable


EVALUATION_SEAL_SCHEMA_VERSION = 1


def canonical_json_fingerprint(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def manifest_fingerprint(rows: Iterable[dict]) -> str:
    canonical = []
    seen = set()
    for row in rows:
        identifier = str(row.get("uuid", "")).split("/", 1)[0].strip()
        if not identifier:
            raise ValueError("manifest rows require UUIDs")
        if identifier in seen:
            raise ValueError(f"manifest contains duplicate UUID: {identifier}")
        seen.add(identifier)
        canonical.append(
            {
                "uuid": identifier,
                "primary_view": str(row.get("primary_view", "")).strip(),
                "safety_status": str(row.get("safety_status", "clear_automated")).strip().lower(),
            }
        )
    if not canonical:
        raise ValueError("manifest must not be empty")
    return canonical_json_fingerprint(sorted(canonical, key=lambda row: row["uuid"]))


def create_evaluation_seal(master: list[dict], config: dict, evaluation_report: dict) -> dict:
    if evaluation_report.get("passed") is not True:
        raise ValueError("cannot seal an evaluation that did not pass")
    seal = {
        "schema_version": EVALUATION_SEAL_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "master_count": len(master),
        "master_fingerprint": manifest_fingerprint(master),
        "config_fingerprint": canonical_json_fingerprint(config),
        "evaluation_report_fingerprint": canonical_json_fingerprint(evaluation_report),
        "evaluation_passed": True,
    }
    seal["seal_fingerprint"] = canonical_json_fingerprint(seal)
    return seal


def verify_evaluation_seal(
    seal: dict,
    master: list[dict],
    config: dict,
    evaluation_report: dict | None = None,
) -> list[str]:
    errors = []
    if int(seal.get("schema_version", -1)) != EVALUATION_SEAL_SCHEMA_VERSION:
        errors.append(f"unsupported evaluation seal schema: {seal.get('schema_version')}")
        return errors
    sealed_payload = {key: value for key, value in seal.items() if key != "seal_fingerprint"}
    actual_seal_fingerprint = canonical_json_fingerprint(sealed_payload)
    if actual_seal_fingerprint != seal.get("seal_fingerprint"):
        errors.append("evaluation seal fingerprint is invalid")
    if seal.get("evaluation_passed") is not True:
        errors.append("evaluation seal does not record a passing evaluation")
    if int(seal.get("master_count", -1)) != len(master):
        errors.append(f"master count changed after evaluation: {len(master)} != {seal.get('master_count')}")
    actual_master = manifest_fingerprint(master)
    if actual_master != seal.get("master_fingerprint"):
        errors.append("master membership, assignment, or safety state changed after evaluation")
    actual_config = canonical_json_fingerprint(config)
    if actual_config != seal.get("config_fingerprint"):
        errors.append("config changed after evaluation")
    if evaluation_report is not None:
        if evaluation_report.get("passed") is not True:
            errors.append("evaluation report no longer records a passing evaluation")
        actual_report = canonical_json_fingerprint(evaluation_report)
        if actual_report != seal.get("evaluation_report_fingerprint"):
            errors.append("evaluation report changed after sealing")
    return errors


def evaluate_freshness(
    current_identifiers: Iterable[object],
    prior_identifiers: Iterable[object],
    minimum_fresh_fraction: float,
    require_disjoint: bool = False,
) -> dict:
    if not 0 <= minimum_fresh_fraction <= 1:
        raise ValueError("minimum_fresh_fraction must be between 0 and 1")
    current_values = [str(value or "").split("/", 1)[0].strip() for value in current_identifiers]
    if any(not value for value in current_values):
        raise ValueError("freshness samples require UUIDs")
    if len(current_values) != len(set(current_values)):
        raise ValueError("freshness sample contains duplicate UUIDs")
    if not current_values:
        raise ValueError("freshness sample must not be empty")
    prior = {str(value or "").split("/", 1)[0].strip() for value in prior_identifiers}
    prior.discard("")
    reused = sorted(set(current_values) & prior)
    fresh_count = len(current_values) - len(reused)
    fraction = fresh_count / len(current_values)
    failures = []
    if fraction < minimum_fresh_fraction:
        failures.append("fresh evidence fraction below minimum")
    if require_disjoint and reused:
        failures.append("final holdout reuses tuning evidence")
    return {
        "sample_count": len(current_values),
        "fresh_count": fresh_count,
        "reused_count": len(reused),
        "fresh_fraction": round(fraction, 4),
        "minimum_fresh_fraction": minimum_fresh_fraction,
        "require_disjoint": require_disjoint,
        "reused_identifiers": reused,
        "gate_failures": failures,
        "passed": not failures,
    }
