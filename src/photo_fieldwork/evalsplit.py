from __future__ import annotations

from collections import Counter

from .pipeline import membership_sha256


CLUSTER_FIELDS = (
    "perceptual_cluster_id",
    "duplicate_group",
    "duplicate_group_id",
    "burst_group",
)


def _identifiers(rows: list[dict[str, str]]) -> list[str]:
    values = [str(row.get("uuid", "")).strip().split("/", 1)[0] for row in rows]
    if any(not value for value in values):
        raise ValueError("evaluation split contains a blank UUID")
    return values


def _relations(rows: list[dict[str, str]]) -> set[str]:
    return {
        f"{field}:{str(row.get(field, '')).strip()}"
        for row in rows
        for field in CLUSTER_FIELDS
        if str(row.get(field, "")).strip()
    }


def audit_split(
    tuning: list[dict[str, str]],
    holdout: list[dict[str, str]],
    canaries: list[dict[str, str]],
    *,
    include_identifiers: bool = False,
) -> dict:
    tuning_ids = _identifiers(tuning)
    holdout_ids = _identifiers(holdout)
    canary_ids = _identifiers(canaries)
    duplicate_counts = {
        "tuning_duplicate_uuid_count": sum(count > 1 for count in Counter(tuning_ids).values()),
        "holdout_duplicate_uuid_count": sum(count > 1 for count in Counter(holdout_ids).values()),
        "canary_duplicate_uuid_count": sum(count > 1 for count in Counter(canary_ids).values()),
    }
    overlap_sets = {
        "tuning_uuid_overlap": set(tuning_ids) & set(holdout_ids),
        "canary_uuid_overlap": set(canary_ids) & set(holdout_ids),
        "tuning_cluster_overlap": _relations(tuning) & _relations(holdout),
        "canary_cluster_overlap": _relations(canaries) & _relations(holdout),
    }
    leakage = {
        **duplicate_counts,
        "holdout_empty_count": int(not holdout_ids),
        **{f"{name}_count": len(values) for name, values in overlap_sets.items()},
    }
    problems = sorted(name for name, count in leakage.items() if count)
    report = {
        "schema_version": 1,
        "status": "PASS" if not problems else "FAIL",
        "holdout_independent": not problems,
        "counts": {
            "tuning_rows": len(tuning_ids),
            "holdout_rows": len(holdout_ids),
            "canary_rows": len(canary_ids),
        },
        "digests": {
            "tuning_uuid_sha256": membership_sha256(tuning_ids),
            "holdout_uuid_sha256": membership_sha256(holdout_ids),
            "canary_uuid_sha256": membership_sha256(canary_ids),
        },
        "leakage": leakage,
        "problems": problems,
    }
    if include_identifiers:
        report["private_details"] = {
            name: sorted(values) for name, values in overlap_sets.items()
        }
    return report
