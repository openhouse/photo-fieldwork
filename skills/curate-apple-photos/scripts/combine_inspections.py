#!/usr/bin/env python3
"""Combine inspection JSONL files without reusing conflicting evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records: dict[str, dict] = {}
    for path in args.inspection:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            identifier = record["asset_identifier"]
            if identifier in records and records[identifier] != record:
                raise ValueError(f"conflicting inspection records: {identifier}")
            records[identifier] = record
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for identifier in sorted(records):
            handle.write(json.dumps(records[identifier], ensure_ascii=False, sort_keys=True) + "\n")
    print(f"unique_inspections={len(records)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
