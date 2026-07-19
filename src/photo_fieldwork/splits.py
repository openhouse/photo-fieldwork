from __future__ import annotations

import hashlib
from collections import Counter


CLUSTER_FIELDS = (
    "perceptual_cluster_id",
    "duplicate_group",
    "duplicate_group_id",
    "burst_group",
    "burst_group_id",
)


def canonical_uuid(value: object) -> str:
    return str(value or "").strip().split("/", 1)[0]


def identifiers(rows: list[dict[str, str]]) -> list[str]:
    values = [canonical_uuid(row.get("uuid")) for row in rows]
    if any(not value for value in values):
        raise ValueError("manifest contains a blank UUID")
    return values


def clusters(rows: list[dict[str, str]]) -> set[str]:
    return {
        f"{field}:{str(row.get(field) or '').strip()}"
        for row in rows
        for field in CLUSTER_FIELDS
        if str(row.get(field) or "").strip()
    }


def digest(values: list[str]) -> str:
    payload = "\n".join(sorted(set(values))) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_split(
    tuning: list[dict[str, str]],
    holdout: list[dict[str, str]],
    canaries: list[dict[str, str]],
    include_identifiers: bool = False,
) -> dict:
    tuning_ids = identifiers(tuning)
    holdout_ids = identifiers(holdout)
    canary_ids = identifiers(canaries)
    tuning_set = set(tuning_ids)
    holdout_set = set(holdout_ids)
    canary_set = set(canary_ids)
    holdout_duplicates = sorted(value for value, count in Counter(holdout_ids).items() if count > 1)
    tuning_duplicates = sorted(value for value, count in Counter(tuning_ids).items() if count > 1)
    canary_duplicates = sorted(value for value, count in Counter(canary_ids).items() if count > 1)
    tuning_uuid_overlap = sorted(holdout_set & tuning_set)
    canary_uuid_overlap = sorted(holdout_set & canary_set)
    tuning_cluster_overlap = sorted(clusters(holdout) & clusters(tuning))
    canary_cluster_overlap = sorted(clusters(holdout) & clusters(canaries))
    leakage = {
        "holdout_duplicate_uuid_count": len(holdout_duplicates),
        "tuning_duplicate_uuid_count": len(tuning_duplicates),
        "canary_duplicate_uuid_count": len(canary_duplicates),
        "tuning_uuid_overlap_count": len(tuning_uuid_overlap),
        "canary_uuid_overlap_count": len(canary_uuid_overlap),
        "tuning_cluster_overlap_count": len(tuning_cluster_overlap),
        "canary_cluster_overlap_count": len(canary_cluster_overlap),
    }
    problems = [name for name, count in leakage.items() if count]
    report = {
        "schema_version": 1,
        "status": "PASS" if not problems else "FAIL",
        "counts": {
            "tuning_rows": len(tuning_ids),
            "holdout_rows": len(holdout_ids),
            "canary_rows": len(canary_ids),
        },
        "digests": {
            "tuning_uuid_sha256": digest(tuning_ids),
            "holdout_uuid_sha256": digest(holdout_ids),
            "canary_uuid_sha256": digest(canary_ids),
        },
        "leakage": leakage,
        "problems": problems,
        "holdout_independent": not problems,
    }
    if include_identifiers:
        report["private_details"] = {
            "holdout_duplicate_uuids": holdout_duplicates,
            "tuning_duplicate_uuids": tuning_duplicates,
            "canary_duplicate_uuids": canary_duplicates,
            "tuning_uuid_overlap": tuning_uuid_overlap,
            "canary_uuid_overlap": canary_uuid_overlap,
            "tuning_cluster_overlap": tuning_cluster_overlap,
            "canary_cluster_overlap": canary_cluster_overlap,
        }
    return report
