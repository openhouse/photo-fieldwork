from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SOURCE_PROFILE_SCHEMA_VERSION = 1


def canonical_identifier(value: object) -> str:
    return str(value or "").split("/", 1)[0].strip()


def fingerprint_identifiers(values: Iterable[object]) -> str:
    identifiers = set()
    for value in values:
        identifier = canonical_identifier(value)
        if identifier:
            identifiers.add(identifier)
    digest = hashlib.sha256()
    for identifier in sorted(identifiers):
        digest.update(identifier.encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def build_source_profile(
    rows: Iterable[dict],
    profile_id: str,
    kind: str,
    scope: str,
    inventory: str,
) -> dict:
    canonical = set()
    for row in rows:
        identifier = canonical_identifier(row.get("uuid"))
        if identifier:
            canonical.add(identifier)
    if not canonical:
        raise ValueError("source profile requires at least one UUID")
    return {
        "schema_version": SOURCE_PROFILE_SCHEMA_VERSION,
        "id": profile_id,
        "kind": kind,
        "scope": scope,
        "inventory": inventory,
        "actual_count": len(canonical),
        "fingerprint": fingerprint_identifiers(canonical),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def read_source_profile(path: Path) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "id", "kind", "scope", "actual_count", "fingerprint"}
    missing = required - set(profile)
    if missing:
        raise ValueError(f"source profile missing fields: {', '.join(sorted(missing))}")
    if int(profile["schema_version"]) != SOURCE_PROFILE_SCHEMA_VERSION:
        raise ValueError(f"unsupported source profile schema: {profile['schema_version']}")
    if int(profile["actual_count"]) < 1:
        raise ValueError("source profile actual_count must be positive")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(profile["fingerprint"])):
        raise ValueError("source profile fingerprint must use sha256")
    return profile


def verify_source_profile(profile: dict, identifiers: Iterable[object]) -> list[str]:
    canonical = {canonical_identifier(value) for value in identifiers if canonical_identifier(value)}
    errors = []
    if len(canonical) != int(profile["actual_count"]):
        errors.append(f"source count changed: {len(canonical)} != {profile['actual_count']}")
    actual_fingerprint = fingerprint_identifiers(canonical)
    if actual_fingerprint != profile["fingerprint"]:
        errors.append(f"source fingerprint changed: {actual_fingerprint} != {profile['fingerprint']}")
    return errors
