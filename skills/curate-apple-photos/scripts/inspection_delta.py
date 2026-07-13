#!/usr/bin/env python3
"""Select candidates not present in one or more prior inspection ledgers."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def base(value: str) -> str:
    return value.split("/", 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--inspection", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    inspected = set()
    for path in args.inspection:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                inspected.add(base(json.loads(line)["asset_identifier"]))
    with args.candidates.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [row for row in reader if base(row["uuid"]) not in inspected]
    if args.limit is not None:
        rows = rows[: args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"previously_inspected={len(inspected)}")
    print(f"fresh_candidates={len(rows)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
