#!/usr/bin/env python3
"""Verify that every exported preview is present and decodable."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def preview_path(directory: Path, identifier: str) -> Path:
    return directory / f"{identifier.replace('/', '_')}.jpg"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--previews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--allow-invalid", action="store_true")
    args = parser.parse_args()

    invalid = []
    checked = 0
    for line in args.inspection.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        identifier = row["asset_identifier"]
        if not row.get("preview_exported"):
            invalid.append((identifier.split("/", 1)[0], "preview not exported"))
            continue
        path = preview_path(args.previews, identifier)
        try:
            with Image.open(path) as image:
                image.verify()
            checked += 1
        except (FileNotFoundError, UnidentifiedImageError, OSError) as error:
            invalid.append((identifier.split("/", 1)[0], f"preview decode failure: {type(error).__name__}"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["uuid", "reason"])
        writer.writerows(invalid)
    print(f"decoded_previews={checked}")
    print(f"invalid_previews={len(invalid)}")
    print(f"output={args.output}")
    if args.report:
        report = {
            "schema_version": 1,
            "status": "PASS" if not invalid else "FAIL",
            "decoded_previews": checked,
            "invalid_previews": len(invalid),
            "failure_manifest": str(args.output),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if invalid and not args.allow_invalid:
        sys.exit(2)


if __name__ == "__main__":
    main()
