#!/usr/bin/env python3
"""Apply full-identifier editorial decisions to a frozen evaluation sample."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDS = (
    "judgment",
    "visible_reason",
    "safety_status",
    "error_category",
    "round_id",
    "reviewer_lens",
)
JUDGMENTS = {"fit", "reject", "uncertain"}


def read(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if not rows or "uuid" not in fields:
        raise ValueError(f"CSV requires uuid rows: {path}")
    return rows, fields


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sample, fields = read(args.sample)
    decisions, decision_fields = read(args.decisions)
    missing = set(FIELDS) - set(decision_fields)
    if missing:
        raise ValueError(f"decisions missing fields: {', '.join(sorted(missing))}")
    by_id = {row["uuid"]: row for row in decisions}
    if len(by_id) != len(decisions):
        raise ValueError("decisions contain duplicate UUIDs")
    sample_ids = {row["uuid"] for row in sample}
    if sample_ids != set(by_id):
        raise ValueError("sample and decision UUID sets differ")
    for field in (*FIELDS, "evaluation_note"):
        if field not in fields:
            fields.append(field)
    for row in sample:
        decision = by_id[row["uuid"]]
        judgment = decision["judgment"].strip().lower()
        if judgment not in JUDGMENTS:
            raise ValueError(f"invalid judgment for {row['uuid']}: {judgment}")
        for field in FIELDS:
            row[field] = decision[field].strip()
        row["judgment"] = judgment
        row["evaluation_note"] = row["visible_reason"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sample)
    print(f"applied={len(sample)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
