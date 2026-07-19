from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


RELATION_FIELDS = (
    "uuid",
    "perceptual_cluster",
    "duplicate_group",
    "burst_group",
)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def membership_sha256(identifiers: Iterable[str]) -> str:
    normalized = [str(identifier).strip() for identifier in identifiers]
    if any(not identifier for identifier in normalized):
        raise ValueError("membership identifiers cannot be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError("membership identifiers must be unique")
    payload = "\n".join(sorted(normalized)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def master_sha256(rows: Iterable[Mapping[str, Any]]) -> str:
    identity = [
        {
            "uuid": str(row.get("uuid", "")).strip(),
            "primary_view": str(row.get("primary_view", "")).strip(),
            "safety_status": str(row.get("safety_status", "clear")).strip().lower(),
        }
        for row in rows
    ]
    if any(not item["uuid"] or not item["primary_view"] for item in identity):
        raise ValueError("master identity requires non-empty UUIDs and primary views")
    if len({item["uuid"] for item in identity}) != len(identity):
        raise ValueError("master identity requires unique UUIDs")
    identity.sort(key=lambda item: (item["primary_view"], item["uuid"]))
    return canonical_sha256(identity)


def content_sha256(value: Any, digest_field: str | None = None) -> str:
    payload = dict(value) if isinstance(value, Mapping) else value
    if digest_field:
        if not isinstance(payload, dict):
            raise ValueError("digest_field requires a mapping")
        payload.pop(digest_field, None)
    return canonical_sha256(payload)


def evaluation_sample_sha256(rows: Iterable[Mapping[str, Any]]) -> str:
    identity_fields = (
        "uuid",
        "primary_view",
        "sample_role",
        "master_sha256",
        "proposal_id",
        "perceptual_cluster",
        "duplicate_group",
        "burst_group",
        "estimate_included",
        "sample_seed",
        "population_count",
        "full_master_count",
        "view_population_count",
    )
    identity = [
        {field: str(row.get(field, "")).strip() for field in identity_fields}
        for row in rows
    ]
    identity.sort(key=lambda item: (item["sample_role"], item["primary_view"], item["uuid"]))
    return canonical_sha256(identity)


def relation_leakage_report(
    sample: Iterable[Mapping[str, Any]],
    prior: Iterable[Mapping[str, Any]],
) -> dict:
    sample = list(sample)
    prior = list(prior)
    prior_values: dict[str, set[str]] = defaultdict(set)
    for row in prior:
        for field in RELATION_FIELDS:
            value = str(row.get(field, "")).strip()
            if value:
                prior_values[field].add(value)

    collisions = []
    for row in sample:
        uuid = str(row.get("uuid", "")).strip()
        for field in RELATION_FIELDS:
            value = str(row.get(field, "")).strip()
            if value and value in prior_values[field]:
                collisions.append(
                    {
                        "sample_uuid": uuid,
                        "relation": field,
                        "relation_value_sha256": hashlib.sha256(
                            value.encode("utf-8")
                        ).hexdigest(),
                    }
                )

    by_relation = {
        field: sum(item["relation"] == field for item in collisions)
        for field in RELATION_FIELDS
    }
    return {
        "status": "PASS" if not collisions else "FAIL",
        "sample_count": len(sample),
        "prior_count": len(prior),
        "collision_count": len(collisions),
        "collisions_by_relation": by_relation,
        "collisions": collisions,
        "claim_boundary": (
            "A clean relation audit establishes separation from recorded prior evidence; "
            "it does not establish statistical independence from unrecorded relationships."
        ),
    }
