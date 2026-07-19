#!/usr/bin/env python3
"""Build or reuse a transparent local preview cache without calling cached work fresh."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def safe_identifier(value: str) -> str:
    return value.replace("/", "_")


def decodable(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (FileNotFoundError, UnidentifiedImageError, OSError):
        return False


def fingerprint(row: dict) -> str:
    value = str(row.get("resource_fingerprint") or "").strip()
    if not value:
        value = "|".join(
            str(row.get(key) or "")
            for key in ("asset_identifier", "pixel_width", "pixel_height", "media_subtype")
        )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def place(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--fresh-previews", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--run-previews", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--fresh-only", action="store_true")
    args = parser.parse_args()

    records = []
    counts = {"newly_decoded": 0, "verified_cache_hit": 0, "missing_or_corrupt": 0}
    for line in args.inspection.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        identifier = row["asset_identifier"]
        name = safe_identifier(identifier) + ".jpg"
        fresh = args.fresh_previews / name
        cache_path = args.cache / safe_identifier(identifier) / f"{fingerprint(row)}.jpg"
        target = args.run_previews / name
        status = "missing_or_corrupt"
        if decodable(fresh):
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            if not decodable(cache_path):
                shutil.copy2(fresh, cache_path)
            place(fresh, target)
            status = "newly_decoded"
        elif not args.fresh_only and decodable(cache_path):
            place(cache_path, target)
            status = "verified_cache_hit"
        counts[status] += 1
        records.append(
            {
                "uuid": identifier.split("/", 1)[0],
                "resource_fingerprint": fingerprint(row),
                "status": status,
                "preview_decodable": status != "missing_or_corrupt",
            }
        )

    manifest = {
        "schema_version": 1,
        "operation": "assemble-local-preview-cache",
        "fresh_only": args.fresh_only,
        "counts": counts,
        "records": records,
        "external_uploads": False,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, indent=2))
    if counts["missing_or_corrupt"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
