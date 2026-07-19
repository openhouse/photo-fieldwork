#!/usr/bin/env python3
"""Audit tuning, canary, and holdout manifests for evaluation leakage."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


CLUSTER_FIELDS = (
    "perceptual_cluster_id",
    "duplicate_group",
    "duplicate_group_id",
    "burst_group",
)


def canonical_uuid(value: object) -> str:
    return str(value or "").strip().split("/", 1)[0]


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if "uuid" not in (reader.fieldnames or []):
                raise ValueError(f"manifest lacks uuid column: {path.name}")
            rows.extend(dict(row) for row in reader)
    return rows


def identifiers(rows: list[dict[str, str]]) -> list[str]:
    values = [canonical_uuid(row.get("uuid")) for row in rows]
    if any(not value for value in values):
        raise ValueError("manifest contains a blank uuid")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tuning", type=Path, action="append", required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--canary", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-identifiers", action="store_true")
    args = parser.parse_args()
    try:
        report = audit_split(
            read_rows(args.tuning),
            read_rows([args.holdout]),
            read_rows(args.canary),
            include_identifiers=args.include_identifiers,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
