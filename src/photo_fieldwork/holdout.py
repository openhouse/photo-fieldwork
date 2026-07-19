from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path


CLUSTER_FIELDS = (
    "perceptual_cluster_id",
    "duplicate_group",
    "duplicate_group_id",
    "burst_group",
)


def canonical_uuid(value: object) -> str:
    """Return the Photos asset portion of a possibly resource-qualified identifier."""
    return str(value or "").strip().split("/", 1)[0]


def read_manifest_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if "uuid" not in (reader.fieldnames or []):
                raise ValueError(f"manifest lacks uuid column: {path.name}")
            rows.extend(dict(row) for row in reader)
    return rows


def _identifiers(rows: list[dict[str, str]]) -> list[str]:
    values = [canonical_uuid(row.get("uuid")) for row in rows]
    if any(not value for value in values):
        raise ValueError("manifest contains a blank uuid")
    return values


def _clusters(rows: list[dict[str, str]]) -> set[str]:
    return {
        f"{field}:{str(row.get(field) or '').strip()}"
        for row in rows
        for field in CLUSTER_FIELDS
        if str(row.get(field) or "").strip()
    }


def _digest(values: list[str]) -> str:
    payload = "\n".join(sorted(set(values))) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_holdout_split(
    tuning: list[dict[str, str]],
    holdout: list[dict[str, str]],
    canaries: list[dict[str, str]],
    *,
    include_identifiers: bool = False,
) -> dict:
    """Detect direct and relation-level leakage into an independent holdout.

    The default report exposes counts and set digests only. Identifier-level
    details are available for a private remediation report when explicitly
    requested by the operator.
    """

    tuning_ids = _identifiers(tuning)
    holdout_ids = _identifiers(holdout)
    canary_ids = _identifiers(canaries)
    tuning_set = set(tuning_ids)
    holdout_set = set(holdout_ids)
    canary_set = set(canary_ids)

    details = {
        "holdout_duplicate_uuids": sorted(
            value for value, count in Counter(holdout_ids).items() if count > 1
        ),
        "tuning_duplicate_uuids": sorted(
            value for value, count in Counter(tuning_ids).items() if count > 1
        ),
        "canary_duplicate_uuids": sorted(
            value for value, count in Counter(canary_ids).items() if count > 1
        ),
        "tuning_uuid_overlap": sorted(holdout_set & tuning_set),
        "canary_uuid_overlap": sorted(holdout_set & canary_set),
        "tuning_cluster_overlap": sorted(_clusters(holdout) & _clusters(tuning)),
        "canary_cluster_overlap": sorted(_clusters(holdout) & _clusters(canaries)),
    }
    leakage = {f"{name[:-1] if name.endswith('s') else name}_count": len(values) for name, values in details.items()}
    problems = sorted(name for name, count in leakage.items() if count)
    report = {
        "schema_version": 1,
        "status": "PASS" if not problems else "FAIL",
        "counts": {
            "tuning_rows": len(tuning_ids),
            "holdout_rows": len(holdout_ids),
            "canary_rows": len(canary_ids),
        },
        "digests": {
            "tuning_uuid_sha256": _digest(tuning_ids),
            "holdout_uuid_sha256": _digest(holdout_ids),
            "canary_uuid_sha256": _digest(canary_ids),
        },
        "leakage": leakage,
        "problems": problems,
        "holdout_independent": not problems,
    }
    if include_identifiers:
        report["private_details"] = details
    return report
