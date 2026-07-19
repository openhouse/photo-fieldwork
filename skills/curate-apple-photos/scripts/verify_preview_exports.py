#!/usr/bin/env python3
"""Verify that every exported preview is present and decodable."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def preview_path(directory: Path, identifier: str) -> Path:
    return directory / f"{identifier.replace('/', '_')}.jpg"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--previews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    invalid = []
    checked = 0
    seen = set()
    for line_number, line in enumerate(args.inspection.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            invalid.append((f"line-{line_number}", "malformed inspection JSONL"))
            continue
        identifier = row["asset_identifier"]
        base_identifier = identifier.split("/", 1)[0]
        if identifier in seen:
            invalid.append((base_identifier, "duplicate inspection row"))
            continue
        seen.add(identifier)
        if not row.get("preview_exported"):
            invalid.append((base_identifier, "preview not exported"))
            continue
        path = preview_path(args.previews, identifier)
        try:
            if path.is_symlink():
                raise OSError("preview is a symlink")
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.width < 1 or image.height < 1:
                    raise OSError("preview has invalid dimensions")
                if image.getexif():
                    raise OSError("preview retained EXIF metadata")
            if os.stat(path).st_mode & 0o077:
                raise OSError("preview permissions are broader than 0600")
            checked += 1
        except (FileNotFoundError, UnidentifiedImageError, OSError) as error:
            invalid.append((base_identifier, f"preview validation failure: {error}"))

    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.parent.chmod(0o700)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["uuid", "reason"])
        writer.writerows(invalid)
    args.output.chmod(0o600)
    print(f"decoded_previews={checked}")
    print(f"invalid_previews={len(invalid)}")
    print(f"output={args.output}")
    if invalid:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
