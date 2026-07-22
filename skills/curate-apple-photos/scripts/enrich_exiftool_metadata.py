#!/usr/bin/env python3
"""Add full ExifTool resource metadata to private osxphotos PhotoInfo records."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


DEFAULT_PROFILE = Path(
    os.environ.get(
        "PHOTO_FIELDWORK_PROFILE",
        "~/.config/photo-fieldwork/apple-photos.json",
    )
).expanduser()
RESOURCE_FIELDS = (
    "path", "path_edited", "path_live_photo", "path_edited_live_photo", "path_raw",
)


def load_profile(path: Path) -> dict:
    path = path.expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("private machine profile must be a mode-0600 regular file")
    return json.loads(path.read_text(encoding="utf-8"))


def configured_exiftool(profile: dict) -> Path:
    value = profile.get("tools", {}).get("exiftool")
    path = Path(str(value or "")).expanduser()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("private machine profile requires an executable tools.exiftool")
    return path


def resource_paths(record: dict) -> list[Path]:
    values: list[str] = []
    for field in RESOURCE_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value:
            values.append(value)
    derivatives = record.get("path_derivatives", [])
    if isinstance(derivatives, list):
        values.extend(value for value in derivatives if isinstance(value, str) and value)
    for field in ("adjustments", "original_adjustments"):
        value = record.get(field)
        if isinstance(value, dict):
            for key, nested in value.items():
                if "path" in str(key).lower() and isinstance(nested, str) and nested:
                    values.append(nested)
    paths: list[Path] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        path = Path(value)
        if path.is_file():
            paths.append(path)
    return paths


def secure_write(path: Path, data: object) -> None:
    if path.is_symlink():
        raise ValueError("private ExifTool output must not be a symlink")
    parent_existed = path.parent.exists()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not parent_existed:
        path.parent.chmod(0o700)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def enrich(profile: dict, input_path: Path, output: Path, timeout_seconds: int) -> tuple[int, int]:
    records = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("private osxphotos input must be a non-empty JSON record list")
    if any(not isinstance(record, dict) or not record.get("uuid") for record in records):
        raise ValueError("private osxphotos input contains an invalid record")
    tool = configured_exiftool(profile)
    enriched = []
    unavailable = 0
    for record in records:
        paths = resource_paths(record)
        result_record = dict(record)
        if not paths:
            unavailable += 1
            result_record["photo_fieldwork_exiftool"] = {
                "available": False,
                "reason": "no locally available resource path",
                "resources": [],
            }
        else:
            command = [
                str(tool), "-json", "-G1", "-struct", "-api", "largefilesupport=1",
                *[str(path) for path in paths],
            ]
            completed = subprocess.run(
                command, text=True, capture_output=True, timeout=timeout_seconds, check=False,
            )
            if completed.returncode:
                raise ValueError("ExifTool metadata extraction failed")
            try:
                metadata = json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                raise ValueError("ExifTool returned invalid JSON") from error
            if not isinstance(metadata, list) or len(metadata) != len(paths):
                raise ValueError("ExifTool resource result count mismatch")
            result_record["photo_fieldwork_exiftool"] = {
                "available": True,
                "resource_count": len(paths),
                "resources": metadata,
            }
        enriched.append(result_record)
    secure_write(output, enriched)
    return len(enriched), unavailable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    try:
        count, unavailable = enrich(
            load_profile(args.profile), args.input, args.output, args.timeout_seconds,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"private_exiftool_records={count}")
    print(f"resources_unavailable={unavailable}")
    print("paths_emitted=false")


if __name__ == "__main__":
    main()
