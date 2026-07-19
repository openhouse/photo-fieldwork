#!/usr/bin/env python3
"""Fail closed when final holdout rows overlap tuning evidence or related clusters."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


CLUSTER_FIELDS = ("perceptual_cluster_id", "duplicate_group", "duplicate_group_id", "burst_group")


def canonical_id(value: str) -> str:
    return value.strip().split("/", 1)[0]


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def digest(values: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()


def identifiers(rows: list[dict[str, str]]) -> set[str]:
    return {canonical_id(row.get("uuid", "")) for row in rows if row.get("uuid", "").strip()}


def clusters(rows: list[dict[str, str]]) -> set[str]:
    return {
        f"{field}:{row[field].strip()}"
        for row in rows
        for field in CLUSTER_FIELDS
        if row.get(field, "").strip()
    }


def audit_split(
    tuning: list[dict[str, str]],
    holdout: list[dict[str, str]],
    canaries: list[dict[str, str]] | None = None,
    include_identifiers: bool = False,
) -> dict:
    canaries = canaries or []
    tuning_ids, holdout_ids, canary_ids = identifiers(tuning), identifiers(holdout), identifiers(canaries)
    tuning_clusters, holdout_clusters, canary_clusters = clusters(tuning), clusters(holdout), clusters(canaries)
    duplicate_holdout_ids = len(holdout_ids) != len(holdout)
    id_leakage = holdout_ids & (tuning_ids | canary_ids)
    cluster_leakage = holdout_clusters & (tuning_clusters | canary_clusters)
    problems = []
    if duplicate_holdout_ids:
        problems.append("holdout contains duplicate or empty UUID rows")
    if id_leakage:
        problems.append("holdout UUIDs overlap tuning or canary evidence")
    if cluster_leakage:
        problems.append("holdout perceptual, duplicate, or burst clusters overlap tuning or canary evidence")
    report = {
        "status": "PASS" if not problems else "FAIL",
        "holdout_independent": not problems,
        "counts": {
            "tuning_ids": len(tuning_ids),
            "holdout_ids": len(holdout_ids),
            "canary_ids": len(canary_ids),
            "id_leakage": len(id_leakage),
            "cluster_leakage": len(cluster_leakage),
        },
        "digests": {
            "tuning_ids_sha256": digest(tuning_ids),
            "holdout_ids_sha256": digest(holdout_ids),
            "canary_ids_sha256": digest(canary_ids),
        },
        "problems": problems,
    }
    if include_identifiers:
        report["private_details"] = {
            "id_leakage": sorted(id_leakage),
            "cluster_leakage": sorted(cluster_leakage),
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tuning", type=Path, action="append", default=[])
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--canary", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-identifiers", action="store_true")
    args = parser.parse_args()
    report = audit_split(
        read_rows(args.tuning),
        read_rows([args.holdout]),
        read_rows(args.canary),
        args.include_identifiers,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
