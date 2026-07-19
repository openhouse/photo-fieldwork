from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Iterable


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def object_digest(value: object, omit_keys: Iterable[str] = ()) -> str:
    if isinstance(value, dict):
        omitted = set(omit_keys)
        value = {key: item for key, item in value.items() if key not in omitted}
    return hashlib.sha256(canonical_json(value)).hexdigest()


def membership_digest(identifiers: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for identifier in sorted(set(identifiers)):
        digest.update(identifier.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_source_snapshot(
    identifiers: Iterable[str],
    query_id: str,
    query_definition_version: int = 1,
    captured_at: str | None = None,
) -> dict:
    unique = set(identifiers)
    if not query_id.strip():
        raise ValueError("source query_id cannot be empty")
    if query_definition_version < 1:
        raise ValueError("query_definition_version must be positive")
    return {
        "schema_version": 1,
        "query_id": query_id,
        "query_definition_version": query_definition_version,
        "observed_count": len(unique),
        "membership_sha256": membership_digest(unique),
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
    }


def validate_source_snapshot(snapshot: dict) -> None:
    required = {
        "schema_version",
        "query_id",
        "query_definition_version",
        "observed_count",
        "membership_sha256",
        "captured_at",
    }
    missing = required - set(snapshot)
    if missing:
        raise ValueError(f"source snapshot missing fields: {', '.join(sorted(missing))}")
    if int(snapshot["schema_version"]) != 1:
        raise ValueError("unsupported source snapshot schema_version")
    if not str(snapshot["query_id"]).strip():
        raise ValueError("source snapshot query_id cannot be empty")
    if int(snapshot["query_definition_version"]) < 1:
        raise ValueError("source snapshot query_definition_version must be positive")
    if int(snapshot["observed_count"]) < 0:
        raise ValueError("source snapshot observed_count cannot be negative")
    digest = snapshot["membership_sha256"]
    if digest is None:
        if not snapshot.get("legacy_count_only"):
            raise ValueError("source snapshot without a digest must be marked legacy_count_only")
    elif not re.fullmatch(r"[a-f0-9]{64}", str(digest)):
        raise ValueError("source snapshot membership_sha256 must be a lowercase SHA-256 digest")


def verify_source_snapshot(identifiers: Iterable[str], snapshot: dict) -> list[str]:
    validate_source_snapshot(snapshot)
    unique = set(identifiers)
    errors = []
    expected_count = int(snapshot["observed_count"])
    if len(unique) != expected_count:
        errors.append(f"source count changed: {len(unique)} != {expected_count}")
    expected_digest = snapshot["membership_sha256"]
    if expected_digest:
        actual_digest = membership_digest(unique)
        if actual_digest != expected_digest:
            errors.append(f"source membership digest changed: {actual_digest} != {expected_digest}")
    return errors
