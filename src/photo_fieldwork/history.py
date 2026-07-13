from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import read_csv


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _membership_hash(rows: list[dict[str, str]]) -> str:
    payload = "\n".join(sorted(row["uuid"].split("/", 1)[0] for row in rows)) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "versions": []}
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1 or not isinstance(registry.get("versions"), list):
        raise ValueError(f"unsupported version registry: {path}")
    return registry


def register_version(
    registry_path: Path,
    version: str,
    manifest_path: Path,
    source_identifier: str,
    source_count: int,
    album_identifier: str = "",
    verification_receipt: Path | None = None,
) -> dict:
    rows = read_csv(manifest_path)
    ids = [row["uuid"].split("/", 1)[0] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("version manifest contains duplicate UUIDs")
    entry = {
        "version": version,
        "registered_at": _timestamp(),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _file_hash(manifest_path),
        "membership_sha256": _membership_hash(rows),
        "member_count": len(ids),
        "source_identifier": source_identifier,
        "source_count": source_count,
        "album_identifier": album_identifier,
        "verification_receipt_path": str(verification_receipt.resolve()) if verification_receipt else "",
        "verification_receipt_sha256": _file_hash(verification_receipt) if verification_receipt else "",
    }
    registry = load_registry(registry_path)
    existing = next((item for item in registry["versions"] if item["version"] == version), None)
    if existing:
        stable_fields = [
            "manifest_sha256",
            "membership_sha256",
            "member_count",
            "source_identifier",
            "source_count",
            "album_identifier",
            "verification_receipt_sha256",
        ]
        if any(existing.get(field) != entry.get(field) for field in stable_fields):
            raise ValueError(f"version {version} is already registered with different evidence")
        return existing
    registry["versions"].append(entry)
    registry["versions"].sort(key=lambda item: item["version"])
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return entry


def verify_registry(registry_path: Path) -> tuple[list[str], dict]:
    registry = load_registry(registry_path)
    errors = []
    for entry in registry["versions"]:
        manifest = Path(entry["manifest_path"])
        if not manifest.is_file():
            errors.append(f"{entry['version']}: manifest missing: {manifest}")
            continue
        if _file_hash(manifest) != entry["manifest_sha256"]:
            errors.append(f"{entry['version']}: manifest bytes changed")
        rows = read_csv(manifest)
        if _membership_hash(rows) != entry["membership_sha256"]:
            errors.append(f"{entry['version']}: manifest membership changed")
        receipt_value = entry.get("verification_receipt_path", "")
        if receipt_value:
            receipt = Path(receipt_value)
            if not receipt.is_file():
                errors.append(f"{entry['version']}: verification receipt missing")
            elif _file_hash(receipt) != entry.get("verification_receipt_sha256"):
                errors.append(f"{entry['version']}: verification receipt changed")
    return errors, {
        "versions": len(registry["versions"]),
        "status": "PASS" if not errors else "FAIL",
    }


def compare_versions(before_path: Path, after_path: Path) -> dict:
    before = {row["uuid"].split("/", 1)[0] for row in read_csv(before_path)}
    after = {row["uuid"].split("/", 1)[0] for row in read_csv(after_path)}
    return {
        "before_count": len(before),
        "after_count": len(after),
        "retained": len(before & after),
        "added": len(after - before),
        "removed": len(before - after),
        "overlap_fraction_of_after": round(len(before & after) / len(after), 4) if after else 0.0,
    }
