#!/usr/bin/env python3
"""Export full osxphotos PhotoInfo JSON for selected assets into a private file."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
from pathlib import Path


DEFAULT_PROFILE = Path(
    os.environ.get(
        "PHOTO_FIELDWORK_PROFILE",
        "~/.config/photo-fieldwork/apple-photos.json",
    )
).expanduser()


def load_profile(path: Path) -> dict:
    path = path.expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError("private machine profile is missing or is a symlink")
    if path.stat().st_mode & 0o077:
        raise ValueError("private machine profile permissions exceed 0600")
    return json.loads(path.read_text(encoding="utf-8"))


def selected_uuids(path: Path, limit: int | None = None) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    values = [str(row.get("uuid") or "").strip().split("/", 1)[0] for row in rows]
    if not values or any(not value for value in values):
        raise ValueError("input CSV requires non-empty uuid rows")
    if len(values) != len(set(values)):
        raise ValueError("input CSV contains duplicate canonical UUIDs")
    return values[:limit] if limit else values


def tool_path(profile: dict) -> Path:
    value = profile.get("tools", {}).get("osxphotos")
    if not value:
        raise ValueError("private machine profile requires tools.osxphotos")
    path = Path(str(value)).expanduser()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("configured osxphotos executable is unavailable")
    return path


def photos_library(profile: dict) -> Path:
    database = Path(str(profile.get("photos_db", ""))).expanduser()
    if database.parent.name.lower() != "database" or not database.is_file():
        raise ValueError("configured photos_db is not a Photos library database")
    return database.parent.parent


def validate_records(records: object, identifiers: list[str]) -> list[dict]:
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("osxphotos did not return a JSON record list")
    returned = [str(row.get("uuid") or "").split("/", 1)[0] for row in records]
    if len(returned) != len(set(returned)):
        raise ValueError("osxphotos returned duplicate UUIDs")
    if set(returned) != set(identifiers):
        raise ValueError("osxphotos result does not match the requested UUID set")
    by_uuid = {str(row["uuid"]).split("/", 1)[0]: row for row in records}
    return [by_uuid[identifier] for identifier in identifiers]


def secure_output(path: Path, content: str) -> None:
    if path.is_symlink():
        raise ValueError("private metadata output must not be a symlink")
    parent_existed = path.parent.exists()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not parent_existed:
        path.parent.chmod(0o700)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    if path.stat().st_mode & 0o077:
        raise ValueError("private metadata output permissions exceed 0600")


def export(
    profile: dict,
    input_path: Path,
    output: Path,
    log: Path,
    limit: int | None,
    timeout_seconds: int,
) -> int:
    identifiers = selected_uuids(input_path, limit)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=output.parent, prefix=".osxphotos-uuids-",
        delete=False,
    ) as handle:
        identifier_file = Path(handle.name)
        identifier_file.chmod(0o600)
        handle.write("\n".join(identifiers) + "\n")
    command = [
        str(tool_path(profile)), "query", "--library", str(photos_library(profile)),
        "--uuid-from-file", str(identifier_file), "--json", "--mute",
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    finally:
        identifier_file.unlink(missing_ok=True)
    secure_output(log, result.stderr)
    if result.returncode:
        raise ValueError("osxphotos private metadata query failed; inspect the private log")
    try:
        records = validate_records(json.loads(result.stdout), identifiers)
    except json.JSONDecodeError as error:
        raise ValueError("osxphotos returned invalid JSON; inspect the private log") from error
    secure_output(output, json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    try:
        count = export(
            load_profile(args.profile), args.input, args.output, args.log,
            args.limit, args.timeout_seconds,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"private_osxphotos_records={count}")
    print("paths_emitted=false")


if __name__ == "__main__":
    main()
