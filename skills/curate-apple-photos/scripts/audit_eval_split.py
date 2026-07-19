#!/usr/bin/env python3
"""Audit tuning, canary, and holdout manifests for relation leakage."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


RELATION_FIELDS = (
    "perceptual_cluster_id",
    "duplicate_group",
    "duplicate_group_id",
    "burst_group",
    "event_cluster",
    "inspection_sha256",
)


def canonical_uuid(value: object) -> str:
    return str(value or "").strip().split("/", 1)[0]


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
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


def relations(rows: list[dict[str, str]]) -> set[str]:
    return {
        f"{field}:{str(row.get(field) or '').strip()}"
        for row in rows
        for field in RELATION_FIELDS
        if str(row.get(field) or "").strip()
    }


def digest(values: list[str]) -> str:
    payload = "\n".join(sorted(set(values))) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def duplicate_count(values: list[str]) -> int:
    return sum(count - 1 for count in Counter(values).values() if count > 1)


def audit_split(
    tuning: list[dict[str, str]],
    holdout: list[dict[str, str]],
    canaries: list[dict[str, str]],
    *,
    include_private_details: bool = False,
) -> dict:
    groups = {
        "tuning": (identifiers(tuning), relations(tuning)),
        "holdout": (identifiers(holdout), relations(holdout)),
        "canary": (identifiers(canaries), relations(canaries)),
    }
    ids = {name: set(values) for name, (values, _) in groups.items()}
    relation_sets = {name: values for name, (_, values) in groups.items()}
    leakage = {
        "tuning_duplicate_uuid_count": duplicate_count(groups["tuning"][0]),
        "holdout_duplicate_uuid_count": duplicate_count(groups["holdout"][0]),
        "canary_duplicate_uuid_count": duplicate_count(groups["canary"][0]),
        "tuning_holdout_uuid_overlap_count": len(ids["tuning"] & ids["holdout"]),
        "canary_holdout_uuid_overlap_count": len(ids["canary"] & ids["holdout"]),
        "tuning_holdout_relation_overlap_count": len(
            relation_sets["tuning"] & relation_sets["holdout"]
        ),
        "canary_holdout_relation_overlap_count": len(
            relation_sets["canary"] & relation_sets["holdout"]
        ),
    }
    problems = sorted(name for name, count in leakage.items() if count)
    report = {
        "schema_version": 2,
        "status": "PASS" if not problems else "FAIL",
        "counts": {name: len(values) for name, (values, _) in groups.items()},
        "digests": {
            f"{name}_uuid_sha256": digest(values)
            for name, (values, _) in groups.items()
        },
        "relation_fields": list(RELATION_FIELDS),
        "leakage": leakage,
        "problems": problems,
        "holdout_independent": not problems,
    }
    if include_private_details:
        report["private_details"] = {
            "tuning_holdout_uuids": sorted(ids["tuning"] & ids["holdout"]),
            "canary_holdout_uuids": sorted(ids["canary"] & ids["holdout"]),
            "tuning_holdout_relations": sorted(
                relation_sets["tuning"] & relation_sets["holdout"]
            ),
            "canary_holdout_relations": sorted(
                relation_sets["canary"] & relation_sets["holdout"]
            ),
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tuning", type=Path, action="append", required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--canary", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-private-details", action="store_true")
    args = parser.parse_args()
    if args.include_private_details and not args.output:
        parser.error("--include-private-details requires a private --output file")
    try:
        report = audit_split(
            read_rows(args.tuning),
            read_rows([args.holdout]),
            read_rows(args.canary),
            include_private_details=args.include_private_details,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        if args.output.is_symlink() or args.output.parent.is_symlink():
            parser.error("private output and its parent must not be symlinks")
        args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        args.output.parent.chmod(0o700)
        args.output.write_text(rendered, encoding="utf-8")
        args.output.chmod(0o600)
    public_report = dict(report)
    public_report.pop("private_details", None)
    print(json.dumps(public_report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
