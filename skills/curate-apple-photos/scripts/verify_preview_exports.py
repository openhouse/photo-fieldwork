#!/usr/bin/env python3
"""Verify that every exported preview is present and decodable."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def canonical_id(value: str) -> str:
    return value.strip().split("/", 1)[0]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def preview_paths(directories: list[Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    duplicates = set()
    for directory in directories:
        for path in sorted(candidate for candidate in directory.rglob("*") if candidate.suffix.lower() in {".jpg", ".jpeg"}):
            stem = path.stem
            uuid = stem[:-7] if stem.endswith("_L0_001") else stem.split("_L0_", 1)[0]
            if uuid in index and index[uuid].resolve() != path.resolve():
                duplicates.add(uuid)
            else:
                index[uuid] = path
    if duplicates:
        raise ValueError(f"duplicate previews across batches: {', '.join(sorted(duplicates)[:5])}")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--previews", type=Path, action="append", required=True, help="preview root; repeatable")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    invalid = []
    rows = []
    checked = 0
    index = preview_paths(args.previews)
    for line in args.inspection.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        identifier = row["asset_identifier"]
        uuid = canonical_id(identifier)
        result = {
            "uuid": uuid,
            "inspection_batch": args.inspection.stem,
            "preview_path": "",
            "byte_size": "",
            "sha256": "",
            "decode_status": "missing",
            "pixel_width": "",
            "pixel_height": "",
            "exported_at": "",
        }
        if not row.get("preview_exported"):
            invalid.append((uuid, "preview not exported"))
            rows.append(result)
            continue
        path = index.get(uuid)
        if path is None:
            invalid.append((uuid, "preview file missing"))
            rows.append(result)
            continue
        result["preview_path"] = str(path.resolve())
        result["byte_size"] = str(path.stat().st_size)
        result["exported_at"] = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        try:
            with Image.open(path) as image:
                result["pixel_width"] = str(image.width)
                result["pixel_height"] = str(image.height)
                image.verify()
            result["sha256"] = file_sha256(path)
            result["decode_status"] = "ok"
            checked += 1
        except (FileNotFoundError, UnidentifiedImageError, OSError) as error:
            result["decode_status"] = f"decode-failure:{type(error).__name__}"
            invalid.append((uuid, result["decode_status"]))
        rows.append(result)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        fields = ["uuid", "inspection_batch", "preview_path", "byte_size", "sha256", "decode_status", "pixel_width", "pixel_height", "exported_at"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    invalid_path = args.output.with_name(f"{args.output.stem}-invalid.csv")
    with invalid_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["uuid", "reason"])
        writer.writerows(invalid)
    print(f"decoded_previews={checked}")
    print(f"invalid_previews={len(invalid)}")
    print(f"output={args.output}")
    print(f"invalid_output={invalid_path}")
    if invalid:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
