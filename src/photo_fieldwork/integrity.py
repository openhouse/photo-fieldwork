from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


def base_identifier(value: str) -> str:
    return value.strip().split("/", 1)[0]


def membership_sha256(values: Iterable[str]) -> str:
    identifiers = sorted({base_identifier(value) for value in values if value.strip()})
    digest = hashlib.sha256()
    for identifier in identifiers:
        digest.update(identifier.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def assignment_sha256(rows: Iterable[dict]) -> str:
    assignments = []
    seen = set()
    for row in rows:
        identifier = base_identifier(str(row.get("uuid") or ""))
        if not identifier:
            raise ValueError("assignment manifest contains a blank UUID")
        if identifier in seen:
            raise ValueError(f"assignment manifest contains duplicate canonical UUID: {identifier}")
        seen.add(identifier)
        assignments.append({
            "uuid": identifier,
            "primary_view": str(row.get("primary_view") or "").strip(),
            "safety_status": str(row.get("safety_status") or "").strip().lower(),
        })
    return canonical_json_sha256(sorted(assignments, key=lambda row: row["uuid"]))


def canonical_json_sha256(value: object, excluded_keys: set[str] | None = None) -> str:
    if isinstance(value, dict) and excluded_keys:
        value = {key: item for key, item in value.items() if key not in excluded_keys}
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def attach_plan_digest(plan: dict) -> dict:
    plan = dict(plan)
    plan["plan_sha256"] = canonical_json_sha256(plan, {"plan_sha256"})
    return plan


def verify_plan_digest(plan: dict) -> None:
    expected = str(plan.get("plan_sha256") or "")
    if not expected:
        raise ValueError("plan is missing plan_sha256")
    actual = canonical_json_sha256(plan, {"plan_sha256"})
    if actual != expected:
        raise ValueError(f"plan digest mismatch: expected {expected}, computed {actual}")
