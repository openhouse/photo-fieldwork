#!/usr/bin/env python3
"""Fail closed unless every expected preview is present and decodable."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def preview_path(directory: Path, identifier: str) -> Path:
    return directory / f"{identifier.replace('/', '_')}.jpg"


def verify(inspection: Path, previews: Path) -> tuple[list[dict], dict]:
    invalid: list[dict] = []
    checked = 0
    identifiers: list[str] = []
    lines = [line for line in inspection.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            invalid.append({"uuid": "", "reason": f"invalid JSONL line {line_number}: {error.msg}"})
            continue
        identifier = str(row.get("asset_identifier", ""))
        identifiers.append(identifier)
        if not identifier:
            invalid.append({"uuid": "", "reason": f"missing asset_identifier on line {line_number}"})
            continue
        if not row.get("preview_exported"):
            invalid.append({"uuid": identifier.split("/", 1)[0], "reason": "preview not exported"})
            continue
        path = preview_path(previews, identifier)
        try:
            with Image.open(path) as image:
                image.verify()
            checked += 1
        except (FileNotFoundError, UnidentifiedImageError, OSError) as error:
            invalid.append(
                {
                    "uuid": identifier.split("/", 1)[0],
                    "reason": f"preview decode failure: {type(error).__name__}",
                }
            )
    digest = hashlib.sha256("\n".join(identifiers).encode()).hexdigest()
    report = {
        "status": "PASS" if not invalid else "FAIL",
        "inspection_rows": len(lines),
        "decoded_previews": checked,
        "invalid_previews": len(invalid),
        "ordered_identifier_sha256": digest,
    }
    return invalid, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--previews", type=Path, required=True)
    parser.add_argument("--invalid-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-invalid", action="store_true")
    args = parser.parse_args()

    invalid, report = verify(args.inspection, args.previews)
    args.invalid_output.parent.mkdir(parents=True, exist_ok=True)
    with args.invalid_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["uuid", "reason"])
        writer.writeheader()
        writer.writerows(invalid)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if invalid and not args.allow_invalid:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
