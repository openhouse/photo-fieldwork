from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from .release import canonical_sha256, identifier_set_sha256


RELATION_FIELDS = ("uuid", "duplicate_group", "duplicate_group_id", "perceptual_cluster_id", "burst_group")


def _values(rows: Iterable[Mapping[str, object]], field: str) -> set[str]:
    return {str(row.get(field, "")).strip() for row in rows if str(row.get(field, "")).strip()}


def _duplicate_ids(rows: list[Mapping[str, object]], label: str) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("uuid", "")).strip()] += 1
    return sorted(value for value, count in counts.items() if value and count > 1)


def audit_evaluation_splits(
    tuning: list[Mapping[str, object]],
    final_holdout: list[Mapping[str, object]],
    canaries: list[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    canaries = canaries or []
    splits = {"tuning": tuning, "final_holdout": final_holdout, "canaries": canaries}
    errors: list[str] = []
    duplicate_rows = {label: _duplicate_ids(rows, label) for label, rows in splits.items()}
    for label, values in duplicate_rows.items():
        if values:
            errors.append(f"{label} contains duplicate UUID rows")
    if not final_holdout:
        errors.append("final_holdout is empty")

    leakage = []
    pairs = (("tuning", "final_holdout"), ("tuning", "canaries"), ("final_holdout", "canaries"))
    for left, right in pairs:
        for field in RELATION_FIELDS:
            overlap = sorted(_values(splits[left], field) & _values(splits[right], field))
            if overlap:
                leakage.append(
                    {
                        "left": left,
                        "right": right,
                        "relation": field,
                        "overlap_count": len(overlap),
                        "overlap_values": overlap,
                    }
                )
    if leakage:
        errors.append("evaluation splits overlap by UUID or a related-image group")
    identity_payload = {
        label: identifier_set_sha256(row.get("uuid", "") for row in rows)
        for label, rows in splits.items()
    }
    identity_payload["relations"] = {
        label: {
            field: canonical_sha256(sorted(_values(rows, field)))
            for field in RELATION_FIELDS[1:]
        }
        for label, rows in splits.items()
    }
    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "split_sha256": canonical_sha256(identity_payload),
        "counts": {label: len(rows) for label, rows in splits.items()},
        "membership_sha256": {
            label: identity_payload[label] for label in splits
        },
        "duplicate_uuid_rows": duplicate_rows,
        "leakage": leakage,
        "errors": errors,
    }
