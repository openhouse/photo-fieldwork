from __future__ import annotations

import hashlib
from collections import Counter


CLUSTER_FIELDS = (
    "perceptual_cluster_id",
    "duplicate_group",
    "duplicate_group_id",
    "burst_group",
)


def canonical_identifier(value: object) -> str:
    return str(value or "").strip().split("/", 1)[0]


def identifiers(rows: list[dict]) -> list[str]:
    values = [canonical_identifier(row.get("uuid")) for row in rows]
    if any(not value for value in values):
        raise ValueError("evaluation manifests require UUIDs")
    return values


def cluster_keys(rows: list[dict]) -> set[str]:
    return {
        f"{field}:{str(row.get(field) or '').strip()}"
        for row in rows
        for field in CLUSTER_FIELDS
        if str(row.get(field) or "").strip()
    }


def duplicate_cluster_keys(rows: list[dict]) -> list[str]:
    counts = Counter(
        f"{field}:{str(row.get(field) or '').strip()}"
        for row in rows
        for field in CLUSTER_FIELDS
        if str(row.get(field) or "").strip()
    )
    return sorted(value for value, count in counts.items() if count > 1)


def identifiers_fingerprint(values: list[str]) -> str:
    payload = "\n".join(sorted(set(values))) + "\n"
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def audit_eval_split(
    tuning: list[dict],
    holdout: list[dict],
    canaries: list[dict] | None = None,
    include_private_details: bool = False,
) -> dict:
    canaries = canaries or []
    tuning_ids = identifiers(tuning)
    holdout_ids = identifiers(holdout)
    canary_ids = identifiers(canaries) if canaries else []
    holdout_set = set(holdout_ids)

    duplicate_holdout = sorted(value for value, count in Counter(holdout_ids).items() if count > 1)
    duplicate_holdout_clusters = duplicate_cluster_keys(holdout)
    tuning_overlap = sorted(holdout_set & set(tuning_ids))
    canary_overlap = sorted(holdout_set & set(canary_ids))
    tuning_cluster_overlap = sorted(cluster_keys(holdout) & cluster_keys(tuning))
    canary_cluster_overlap = sorted(cluster_keys(holdout) & cluster_keys(canaries))
    leakage = {
        "holdout_duplicate_uuid_count": len(duplicate_holdout),
        "holdout_duplicate_cluster_count": len(duplicate_holdout_clusters),
        "tuning_uuid_overlap_count": len(tuning_overlap),
        "canary_uuid_overlap_count": len(canary_overlap),
        "tuning_cluster_overlap_count": len(tuning_cluster_overlap),
        "canary_cluster_overlap_count": len(canary_cluster_overlap),
    }
    failures = [name for name, count in leakage.items() if count]
    report = {
        "schema_version": 1,
        "counts": {
            "tuning_rows": len(tuning_ids),
            "holdout_rows": len(holdout_ids),
            "canary_rows": len(canary_ids),
        },
        "digests": {
            "tuning_uuid_fingerprint": identifiers_fingerprint(tuning_ids),
            "holdout_uuid_fingerprint": identifiers_fingerprint(holdout_ids),
            "canary_uuid_fingerprint": identifiers_fingerprint(canary_ids),
        },
        "leakage": leakage,
        "gate_failures": failures,
        "holdout_independent": not failures,
        "passed": not failures,
    }
    if include_private_details:
        report["private_details"] = {
            "holdout_duplicate_uuids": duplicate_holdout,
            "holdout_duplicate_clusters": duplicate_holdout_clusters,
            "tuning_uuid_overlap": tuning_overlap,
            "canary_uuid_overlap": canary_overlap,
            "tuning_cluster_overlap": tuning_cluster_overlap,
            "canary_cluster_overlap": canary_cluster_overlap,
        }
    return report
