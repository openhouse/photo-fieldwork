#!/usr/bin/env python3
"""Report the configured private Apple Photos insight surface without leaking it."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "references" / "capability-contract.json"
DEFAULT_PROFILE = Path(
    os.environ.get(
        "PHOTO_FIELDWORK_PROFILE",
        "~/.config/photo-fieldwork/apple-photos.json",
    )
).expanduser()

ASSET_FIELDS = {
    "uuid", "filename", "original_filename", "date_created", "date_added",
    "date_modified", "width", "height", "original_width", "original_height",
    "favorite", "edited", "external_edit", "hidden", "trashed", "missing",
    "cloud_asset", "local_availability", "remote_availability", "title",
    "description", "screenshot", "selfie", "portrait", "panorama", "burst",
    "burst_key", "overall_aesthetic_score", "curation_score", "promotion_score",
    "highlight_visibility_score", "failure_score", "duplicate_group_id",
    "camera_make", "camera_model", "original_file_size", "latitude", "longitude",
    "has_location", "face_count",
}
RELATION_TABLES = {
    "asset_person", "asset_album", "asset_keyword", "asset_search",
    "asset_label", "asset_place",
}


def load_private_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("private machine profile is missing or is a symlink")
    if path.stat().st_mode & 0o077:
        raise ValueError("private machine profile permissions exceed 0600")
    return json.loads(path.read_text(encoding="utf-8"))


def configured_tool(profile: dict, key: str, fallback: str) -> str | None:
    value = profile.get("tools", {}).get(key)
    if value:
        candidate = Path(str(value)).expanduser()
        return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None
    return shutil.which(fallback)


def inspect_inventory(path: Path) -> tuple[bool, bool]:
    if path.is_symlink() or not path.is_file():
        return False, False
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    connection.execute("PRAGMA query_only=ON")
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(asset)")
    } if "asset" in tables else set()
    connection.close()
    return ASSET_FIELDS <= columns, RELATION_TABLES <= tables


def valid_photokit_receipt(receipt: dict | None, profile: dict) -> bool:
    if not receipt:
        return False
    source = profile.get("default_source", {})
    return (
        receipt.get("source_album_identifier") == source.get("identifier")
        and receipt.get("source_count") == source.get("expected_count")
        and receipt.get("network_access_allowed") is False
        and receipt.get("external_uploads_performed") is False
        and receipt.get("completed_count") == receipt.get("requested_count")
    )


def valid_osxphotos_probe(probe: object | None) -> bool:
    return (
        isinstance(probe, list)
        and len(probe) == 1
        and isinstance(probe[0], dict)
        and bool(probe[0].get("uuid"))
    )


def build_report(
    profile: dict,
    contract: dict,
    photokit_receipt: dict | None = None,
    osxphotos_probe: object | None = None,
) -> dict:
    inventory = Path(str(profile.get("inventory_db", ""))).expanduser()
    asset_fields, relationships = inspect_inventory(inventory)
    osxphotos = configured_tool(profile, "osxphotos", "osxphotos")
    exiftool = configured_tool(profile, "exiftool", "exiftool")
    helper = Path(str(profile.get("app_executable", ""))).expanduser()
    helper_installed = helper.is_file() and os.access(helper, os.X_OK)

    provider_states = {
        "private inventory": "AVAILABLE" if asset_fields else "UNAVAILABLE",
        "private relationships": "AVAILABLE" if relationships else "UNAVAILABLE",
        "osxphotos": (
            "AVAILABLE" if osxphotos and valid_osxphotos_probe(osxphotos_probe)
            else "UNVERIFIED" if osxphotos else "UNAVAILABLE"
        ),
        "ExifTool": "AVAILABLE" if exiftool else "UNAVAILABLE",
        "PhotoKit helper": (
            "AVAILABLE" if helper_installed and valid_photokit_receipt(photokit_receipt, profile)
            else "UNVERIFIED" if helper_installed else "UNAVAILABLE"
        ),
        "independent catalog verifier": "AVAILABLE",
    }
    capabilities = []
    for item in contract["capabilities"]:
        states = []
        for provider in item["providers"]:
            if provider == "private inventory" and item["id"] in {
                "albums_and_structure", "people_and_faces", "places_and_location",
                "computational_context",
            }:
                states.append(provider_states["private relationships"])
            else:
                states.append(provider_states.get(provider, "UNAVAILABLE"))
        if states and all(state == "AVAILABLE" for state in states):
            state = "AVAILABLE"
        elif any(state in {"AVAILABLE", "UNVERIFIED"} for state in states):
            state = "UNVERIFIED" if "UNVERIFIED" in states else "PARTIAL"
        else:
            state = "UNAVAILABLE"
        capabilities.append({
            "id": item["id"],
            "label": item["label"],
            "state": state,
            "providers": item["providers"],
            "sensitivity": item["sensitivity"],
        })
    gaps = [item["id"] for item in capabilities if item["state"] != "AVAILABLE"]
    return {
        "schema_version": 1,
        "goal": contract["goal"],
        "overall_state": "READY" if not gaps else "NEEDS-LIVE-PROBES",
        "capabilities": capabilities,
        "gaps": gaps,
        "privacy": {
            "paths_emitted": False,
            "archive_values_emitted": False,
            "publication_clearance": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--photokit-receipt", type=Path)
    parser.add_argument("--osxphotos-probe", type=Path)
    parser.add_argument("--require-no-unavailable", action="store_true")
    args = parser.parse_args()
    try:
        profile = load_private_json(args.profile.expanduser())
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        photokit_receipt = (
            json.loads(args.photokit_receipt.read_text(encoding="utf-8"))
            if args.photokit_receipt else None
        )
        osxphotos_probe = (
            json.loads(args.osxphotos_probe.read_text(encoding="utf-8"))
            if args.osxphotos_probe else None
        )
        report = build_report(profile, contract, photokit_receipt, osxphotos_probe)
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    print(f"overall_state={report['overall_state']}")
    for item in report["capabilities"]:
        print(f"{item['state']:<10} {item['id']}: {item['label']}")
    if args.json_output:
        parent_existed = args.json_output.parent.exists()
        args.json_output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not parent_existed:
            args.json_output.parent.chmod(0o700)
        if args.json_output.is_symlink():
            parser.error("private capability report must not be a symlink")
        args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        args.json_output.chmod(0o600)
        print("private_json_report_written=true")
    unavailable = [item for item in report["capabilities"] if item["state"] == "UNAVAILABLE"]
    if args.require_no_unavailable and unavailable:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
