#!/usr/bin/env python3
"""Apply explicit human safety decisions to a candidate inventory."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path


HUMAN_STATES = {
    "needs-human-review",
    "human-added-hold",
    "confirmed-sensitive",
    "cleared-false-positive",
}


def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if not rows or "uuid" not in fields:
        raise ValueError(f"CSV requires uuid rows: {path}")
    return rows, fields


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows, fields = read_rows(args.inventory)
    decisions, decision_fields = read_rows(args.decisions)
    required = {"uuid", "safety_status", "safety_reason", "safety_actor"}
    missing = required - set(decision_fields)
    if missing:
        raise ValueError(f"decisions missing fields: {', '.join(sorted(missing))}")
    by_id = {row["uuid"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("inventory contains duplicate UUIDs")
    decision_ids = [row["uuid"] for row in decisions]
    if len(set(decision_ids)) != len(decision_ids):
        raise ValueError("decisions contain duplicate UUIDs")

    additions = ["safety_status", "safety_reason", "safety_actor", "safety_reviewed_at"]
    for field in additions:
        if field not in fields:
            fields.append(field)
    reviewed_at = datetime.now(timezone.utc).isoformat()
    for decision in decisions:
        identifier = decision["uuid"]
        if identifier not in by_id:
            raise ValueError(f"decision UUID not found in inventory: {identifier}")
        state = decision["safety_status"].strip().lower()
        reason = decision["safety_reason"].strip()
        actor = decision["safety_actor"].strip()
        if state not in HUMAN_STATES:
            raise ValueError(f"human review cannot set safety state: {state}")
        if not reason or not actor:
            raise ValueError(f"human review requires generalized reason and actor: {identifier}")
        by_id[identifier].update(
            {
                "safety_status": state,
                "safety_reason": reason,
                "safety_actor": actor,
                "safety_reviewed_at": decision.get("safety_reviewed_at", "").strip() or reviewed_at,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"reviewed={len(decisions)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
