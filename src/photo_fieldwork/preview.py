from __future__ import annotations

import hashlib
import io
from collections import Counter
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def preview_filename(identifier: object) -> str:
    value = str(identifier or "").strip()
    if not value:
        raise ValueError("preview records require UUIDs")
    return value.replace("/", "_") + ".jpg"


def verify_jpeg(data: bytes) -> tuple[int, int]:
    if len(data) < 12 or not data.startswith(b"\xff\xd8"):
        raise ValueError("not a JPEG stream")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG":
                raise ValueError(f"expected JPEG, found {image.format or 'unknown'}")
            image.load()
            width, height = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"JPEG decode failed: {error}") from error
    if width < 1 or height < 1:
        raise ValueError("JPEG dimensions must be positive")
    return width, height


def verify_preview_exports(records: list[dict], preview_directory: Path) -> dict:
    identifiers = [str(row.get("uuid", "")).strip() for row in records]
    if any(not identifier for identifier in identifiers):
        raise ValueError("preview records require UUIDs")
    duplicate_ids = sorted(value for value, count in Counter(identifiers).items() if count > 1)
    if duplicate_ids:
        raise ValueError(f"preview records contain duplicate UUIDs: {', '.join(duplicate_ids)}")
    filenames = [preview_filename(identifier) for identifier in identifiers]
    collisions = sorted(value for value, count in Counter(filenames).items() if count > 1)
    if collisions:
        raise ValueError(f"preview filename mapping is ambiguous: {', '.join(collisions)}")

    errors = []
    verified = []
    for row, filename in zip(records, filenames, strict=True):
        identifier = str(row["uuid"])
        if not truthy(row.get("preview_exported")):
            errors.append(f"{identifier}: inspection did not confirm preview export")
            continue
        path = preview_directory / filename
        if path.is_symlink():
            errors.append(f"{identifier}: preview must not be a symbolic link")
            continue
        if not path.is_file():
            errors.append(f"{identifier}: expected preview is missing")
            continue
        try:
            data = path.read_bytes()
            width, height = verify_jpeg(data)
        except (OSError, ValueError) as error:
            errors.append(f"{identifier}: preview integrity failed ({error})")
            continue
        verified.append(
            {
                "uuid": identifier,
                "filename": filename,
                "byte_count": len(data),
                "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
                "width": width,
                "height": height,
            }
        )
    return {
        "record_count": len(records),
        "valid_count": len(verified),
        "invalid_count": len(records) - len(verified),
        "passed": not errors and len(verified) == len(records),
        "errors": errors,
        "verified": verified,
    }
