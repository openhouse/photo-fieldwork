from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


SOURCE_MANIFEST_REQUIRED = {
    "schema_version",
    "source_adapter",
    "source_identifier",
    "source_title",
    "predicate_version",
    "observed_count",
    "membership_sha256",
    "source_fingerprint",
    "artifact_sensitivity",
}
RELEASE_CLASSES = {
    "editor-field-verified": 1,
    "master-human-reviewed": 2,
    "publication-ready": 3,
}
EVALUATION_SCOPES = {
    "learning-sample",
    "final-stratified-sample",
    "full-master",
    "publication-shortlist",
}


def parse_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return int(str(value))


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def base_identifier(value: str) -> str:
    return str(value).split("/", 1)[0]


def identifier_set_sha256(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for identifier in sorted({base_identifier(value) for value in values}):
        digest.update(identifier.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def rows_membership_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    return identifier_set_sha256(str(row["uuid"]) for row in rows)


def source_fingerprint_payload(manifest: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": parse_int(manifest["schema_version"]),
        "source_adapter": str(manifest["source_adapter"]),
        "source_identifier": str(manifest["source_identifier"]),
        "predicate_version": str(manifest["predicate_version"]),
        "observed_count": parse_int(manifest["observed_count"]),
        "membership_sha256": str(manifest["membership_sha256"]),
        "library_fingerprint": str(manifest.get("library_fingerprint", "")),
    }


def build_source_manifest(
    *,
    source_adapter: str,
    source_identifier: str,
    source_title: str,
    predicate_version: str,
    observed_count: int,
    membership_sha256: str,
    artifact_sensitivity: str = "private-operational",
    library_fingerprint: str = "",
    inventory_sha256: str = "",
    created_at: str | None = None,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_adapter": source_adapter,
        "source_identifier": source_identifier,
        "source_title": source_title,
        "predicate_version": predicate_version,
        "observed_count": int(observed_count),
        "membership_sha256": membership_sha256,
        "library_fingerprint": library_fingerprint,
        "inventory_sha256": inventory_sha256,
        "artifact_sensitivity": artifact_sensitivity,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    manifest["source_fingerprint"] = canonical_sha256(source_fingerprint_payload(manifest))
    return manifest


def validate_source_manifest(manifest: Mapping[str, object]) -> dict[str, object]:
    missing = SOURCE_MANIFEST_REQUIRED - set(manifest)
    if missing:
        raise ValueError(f"source manifest missing fields: {', '.join(sorted(missing))}")
    if parse_int(manifest["schema_version"]) != 1:
        raise ValueError("source manifest schema_version must be 1")
    if parse_int(manifest["observed_count"]) < 1:
        raise ValueError("source manifest observed_count must be positive")
    membership_hash = str(manifest["membership_sha256"])
    if len(membership_hash) != 64:
        raise ValueError("source manifest membership_sha256 must be a SHA-256 digest")
    expected = canonical_sha256(source_fingerprint_payload(manifest))
    if str(manifest["source_fingerprint"]) != expected:
        raise ValueError("source manifest fingerprint does not match its source contract")
    return dict(manifest)


def load_source_manifest(path: Path) -> dict[str, object]:
    return validate_source_manifest(json.loads(path.read_text(encoding="utf-8")))


def sample_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    payload = [
        {
            "uuid": base_identifier(str(row["uuid"])),
            "primary_view": str(row.get("primary_view", "")),
            "sample_kind": str(row.get("sample_kind", "fresh")),
            "proposal_id": str(row.get("proposal_id", "")),
            "master_sha256": str(row.get("master_sha256", "")),
        }
        for row in rows
    ]
    payload.sort(key=lambda row: (row["sample_kind"], row["primary_view"], row["uuid"]))
    return canonical_sha256(payload)


def plan_sha256(plan: Mapping[str, object]) -> str:
    payload = dict(plan)
    payload.pop("plan_sha256", None)
    return canonical_sha256(payload)


def finalize_plan(plan: Mapping[str, object]) -> dict[str, object]:
    result = dict(plan)
    result["plan_sha256"] = plan_sha256(result)
    return result


def validate_plan(plan: Mapping[str, object]) -> dict[str, object]:
    if parse_int(plan.get("schema_version", 0)) != 2:
        raise ValueError("plan schema_version must be 2")
    expected = plan_sha256(plan)
    if str(plan.get("plan_sha256", "")) != expected:
        raise ValueError("plan_sha256 does not match plan contents")
    source_value = plan.get("source", {})
    if not isinstance(source_value, Mapping):
        raise ValueError("plan source must be a source manifest object")
    source = validate_source_manifest(source_value)
    if str(plan.get("source_fingerprint", "")) != str(source["source_fingerprint"]):
        raise ValueError("plan source_fingerprint does not match source manifest")
    return dict(plan)


def release_satisfies(actual: str, required: str) -> bool:
    if actual not in RELEASE_CLASSES or required not in RELEASE_CLASSES:
        raise ValueError("unknown release class")
    return RELEASE_CLASSES[actual] >= RELEASE_CLASSES[required]
