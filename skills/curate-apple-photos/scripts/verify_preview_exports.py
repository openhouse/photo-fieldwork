#!/usr/bin/env python3
"""Verify exported previews and write a private evidence index."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

from PIL import ExifTags, Image, UnidentifiedImageError


INDEX_FIELDS = (
    "uuid",
    "local_identifier",
    "preview_path",
    "preview_sha256",
    "bytes",
    "width",
    "height",
    "decode_status",
    "reason",
)


def canonical_uuid(identifier: str) -> str:
    return identifier.strip().split("/", 1)[0]


def preview_path(directory: Path, identifier: str) -> Path:
    return directory / f"{identifier.replace('/', '_')}.jpg"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def has_source_bearing_exif(image: Image.Image) -> bool:
    """Allow only encoder-generated pixel dimensions and optional sRGB."""
    exif = image.getexif()
    if not exif:
        return False
    exif_offset = 34665
    if set(exif) - {exif_offset}:
        return True
    try:
        nested = exif.get_ifd(ExifTags.IFD.Exif)
    except (AttributeError, KeyError, TypeError, ValueError):
        return True
    allowed = {40961, 40962, 40963}
    if set(nested) - allowed:
        return True
    width = nested.get(40962)
    height = nested.get(40963)
    color_space = nested.get(40961)
    return (
        color_space not in {None, 1}
        or width != image.width
        or height != image.height
    )


def verify_preview_rows(inspection: Path, previews: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    seen_identifiers: set[str] = set()
    seen_uuids: set[str] = set()
    for line_number, line in enumerate(
        inspection.read_text(encoding="utf-8").splitlines(), start=1
    ):
        identifier = ""
        uuid = f"line-{line_number}"
        path: Path | None = None
        reason = ""
        width = 0
        height = 0
        size = 0
        digest = ""
        try:
            source = json.loads(line)
            identifier = str(source.get("asset_identifier") or "").strip()
            if not identifier:
                raise ValueError("inspection row lacks asset_identifier")
            uuid = canonical_uuid(identifier)
            if identifier in seen_identifiers:
                raise ValueError("duplicate local identifier")
            if uuid in seen_uuids:
                raise ValueError("duplicate canonical UUID")
            seen_identifiers.add(identifier)
            seen_uuids.add(uuid)
            if not source.get("preview_exported"):
                raise ValueError("preview not exported")
            path = preview_path(previews, identifier)
            if path.is_symlink():
                raise OSError("preview is a symlink")
            resolved = path.resolve(strict=True)
            if previews.resolve(strict=True) not in resolved.parents:
                raise OSError("preview resolves outside the preview root")
            if os.stat(resolved).st_mode & 0o077:
                raise OSError("preview permissions are broader than 0600")
            with Image.open(resolved) as image:
                image.verify()
            with Image.open(resolved) as image:
                width, height = image.size
                if width < 1 or height < 1:
                    raise OSError("preview has invalid dimensions")
                if has_source_bearing_exif(image):
                    raise OSError("preview retained source-bearing EXIF metadata")
            size = resolved.stat().st_size
            digest = file_sha256(resolved)
            path = resolved
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            reason = str(error) or "malformed inspection row"
        except (FileNotFoundError, UnidentifiedImageError, OSError) as error:
            reason = f"preview validation failure: {error}"
        rows.append(
            {
                "uuid": uuid,
                "local_identifier": identifier,
                "preview_path": str(path or ""),
                "preview_sha256": digest,
                "bytes": size,
                "width": width,
                "height": height,
                "decode_status": "invalid" if reason else "ok",
                "reason": reason,
            }
        )
    if not rows:
        raise ValueError("inspection JSONL contains no rows")
    return rows


def write_index(path: Path, rows: list[dict[str, str | int]]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--previews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        rows = verify_preview_rows(args.inspection, args.previews)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    write_index(args.output, rows)
    invalid = sum(row["decode_status"] != "ok" for row in rows)
    print(f"decoded_previews={len(rows) - invalid}")
    print(f"invalid_previews={invalid}")
    print(f"output={args.output}")
    if invalid:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
