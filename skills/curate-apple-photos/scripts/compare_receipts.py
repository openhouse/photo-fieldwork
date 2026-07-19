#!/usr/bin/env python3
"""Compare first and second permissioned-app receipts for idempotence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from photos_sqlite import consistent_snapshot
from verify_photos_commit import verify


REQUIRED_FINGERPRINT_FIELDS = {
    "app_bundle_identifier",
    "app_binary_sha256",
    "plan_sha256",
}
SHA256 = re.compile(r"[a-f0-9]{64}")
LOCAL_IDENTIFIER = re.compile(r"[^/\s]{8,}/L0/[0-9]{3}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def require_distinct_executions(
    first_path: Path,
    second_path: Path,
    first_receipt: dict,
    second_receipt: dict,
) -> None:
    if first_path.resolve() == second_path.resolve():
        raise ValueError("idempotence requires two distinct receipt files")
    if first_receipt.get("completed_at") == second_receipt.get("completed_at"):
        raise ValueError("idempotence requires two distinct execution timestamps")
    if first_receipt.get("execution_nonce") == second_receipt.get("execution_nonce"):
        raise ValueError("idempotence requires two distinct bridge launch nonces")


def require_receipt(receipt: dict) -> None:
    for field in (
        "completed_at",
        "execution_nonce",
        "plan_id",
        "source_album_identifier",
        "source_identifier_sha256",
        "safety_mode",
    ):
        if not receipt.get(field):
            raise ValueError(f"receipt missing required field: {field}")
    try:
        datetime.fromisoformat(str(receipt["completed_at"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("receipt completed_at must be an ISO-8601 timestamp") from error
    if not re.fullmatch(r"[a-f0-9]{32}", str(receipt["execution_nonce"])):
        raise ValueError("receipt execution_nonce must be 32 lowercase hex characters")
    if not isinstance(receipt.get("source_count"), int) or receipt["source_count"] < 1:
        raise ValueError("receipt source_count must be a positive integer")
    if not SHA256.fullmatch(str(receipt["source_identifier_sha256"])):
        raise ValueError("receipt source_identifier_sha256 must be lowercase SHA-256")
    fingerprint = receipt.get("execution_fingerprint")
    if not isinstance(fingerprint, dict):
        raise ValueError("receipt missing execution_fingerprint")
    missing_fingerprint = REQUIRED_FINGERPRINT_FIELDS - set(fingerprint)
    if missing_fingerprint or any(not fingerprint.get(field) for field in REQUIRED_FINGERPRINT_FIELDS):
        raise ValueError(
            "receipt execution_fingerprint missing: "
            + ", ".join(sorted(missing_fingerprint or REQUIRED_FINGERPRINT_FIELDS))
        )
    for field in ("app_binary_sha256", "plan_sha256"):
        if not SHA256.fullmatch(str(fingerprint[field])):
            raise ValueError(f"receipt execution_fingerprint.{field} must be lowercase SHA-256")
    if not re.fullmatch(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)+", str(fingerprint["app_bundle_identifier"])):
        raise ValueError("receipt execution_fingerprint.app_bundle_identifier is malformed")
    folders = receipt.get("folders")
    albums = receipt.get("albums")
    if not isinstance(folders, list) or not folders:
        raise ValueError("receipt folders must be a non-empty list")
    if not isinstance(albums, list) or not albums:
        raise ValueError("receipt albums must be a non-empty list")
    for folder in folders:
        if any(not folder.get(field) for field in ("key", "title", "identifier")):
            raise ValueError("receipt folder lacks key, title, or identifier")
        if not LOCAL_IDENTIFIER.fullmatch(str(folder["identifier"])):
            raise ValueError("receipt folder identifier is not a PhotoKit local identifier")
    for album in albums:
        if any(not album.get(field) for field in ("title", "identifier")):
            raise ValueError("receipt album lacks title or identifier")
        if not isinstance(album.get("count"), int) or album["count"] < 1:
            raise ValueError("receipt album count must be a positive integer")
        if not LOCAL_IDENTIFIER.fullmatch(str(album["identifier"])):
            raise ValueError("receipt album identifier is not a PhotoKit local identifier")
    for label, values in (
        ("folder key", [item["key"] for item in folders]),
        ("folder identifier", [item["identifier"] for item in folders]),
        ("album title", [item["title"] for item in albums]),
        ("album identifier", [item["identifier"] for item in albums]),
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"receipt contains duplicate {label}s")


def require_plan_match(
    receipt: dict,
    plan: dict,
    plan_sha256: str,
    bundle_id: str,
    app_binary_sha256: str,
) -> None:
    if receipt["execution_fingerprint"]["plan_sha256"] != plan_sha256:
        raise ValueError("receipt plan_sha256 does not match the supplied plan")
    if receipt["execution_fingerprint"]["app_bundle_identifier"] != bundle_id:
        raise ValueError("receipt bundle identifier does not match the configured helper")
    if receipt["execution_fingerprint"]["app_binary_sha256"] != app_binary_sha256:
        raise ValueError("receipt app_binary_sha256 does not match the configured helper")
    expected_scalars = {
        "plan_id": plan.get("plan_id"),
        "source_album_identifier": plan.get("source_album_identifier"),
        "source_count": plan.get("expected_source_count"),
        "source_identifier_sha256": plan.get("source_identifier_sha256"),
        "safety_mode": plan.get("safety_mode"),
    }
    for field, expected in expected_scalars.items():
        if receipt.get(field) != expected:
            raise ValueError(f"receipt {field} does not match the supplied plan")
    planned_folders = sorted((item["key"], item["title"]) for item in plan.get("folders", []))
    receipt_folders = sorted((item["key"], item["title"]) for item in receipt["folders"])
    if receipt_folders != planned_folders:
        raise ValueError("receipt folders do not match the supplied plan")
    receipt_folder_ids = {item["key"]: item["identifier"] for item in receipt["folders"]}
    for item in plan.get("folders", []):
        parent_key = item.get("parent_key")
        expected_parent = receipt_folder_ids.get(parent_key) if parent_key else None
        received = next(folder for folder in receipt["folders"] if folder["key"] == item["key"])
        if received.get("parent_identifier") != expected_parent:
            raise ValueError("receipt folder hierarchy does not match the supplied plan")
    planned_albums = sorted(
        (item["title"], len(set(item.get("asset_identifiers", []))))
        for item in plan.get("albums", [])
    )
    receipt_albums = sorted((item["title"], item["count"]) for item in receipt["albums"])
    if receipt_albums != planned_albums:
        raise ValueError("receipt album counts do not match planned membership")
    for item in plan.get("albums", []):
        received = next(album for album in receipt["albums"] if album["title"] == item["title"])
        if received.get("parent_identifier") != receipt_folder_ids.get(item.get("parent_folder_key")):
            raise ValueError("receipt album hierarchy does not match the supplied plan")


def normalized(
    receipt: dict,
    plan: dict,
    plan_sha256: str,
    bundle_id: str,
    app_binary_sha256: str,
    verified_identifiers: set[str],
) -> dict:
    require_receipt(receipt)
    if not SHA256.fullmatch(plan_sha256) or not SHA256.fullmatch(app_binary_sha256):
        raise ValueError("expected plan and helper identities must be lowercase SHA-256")
    require_plan_match(receipt, plan, plan_sha256, bundle_id, app_binary_sha256)
    receipt_identifiers = {
        item["identifier"] for item in receipt["folders"] + receipt["albums"]
    }
    if receipt_identifiers != verified_identifiers:
        raise ValueError("receipt catalog identifiers lack independent verification")
    return {
        "plan_id": receipt.get("plan_id"),
        "source_album_identifier": receipt.get("source_album_identifier"),
        "source_count": receipt.get("source_count"),
        "source_identifier_sha256": receipt.get("source_identifier_sha256"),
        "safety_mode": receipt.get("safety_mode"),
        "folders": sorted(
            (
                item.get("key"),
                item.get("title"),
                item.get("identifier"),
            )
            for item in receipt.get("folders", [])
        ),
        "albums": sorted(
            (
                item.get("title"),
                item.get("identifier"),
                item.get("count"),
            )
            for item in receipt.get("albums", [])
        ),
        "execution_fingerprint": receipt.get("execution_fingerprint"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--app-binary", type=Path, required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--photos-db", type=Path, required=True)
    parser.add_argument("--snapshot-directory", type=Path)
    parser.add_argument("--keep-snapshot", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    plan_digest = file_sha256(args.plan)
    binary_digest = file_sha256(args.app_binary)
    first_receipt = json.loads(args.first.read_text(encoding="utf-8"))
    second_receipt = json.loads(args.second.read_text(encoding="utf-8"))
    require_distinct_executions(args.first, args.second, first_receipt, second_receipt)

    verification_root = args.report.parent / "receipt-verification"
    verification_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    verification_root.chmod(0o700)

    def verify_both(database: Path, metadata: dict) -> tuple[set[str], set[str]]:
        results = []
        for label, receipt_path in (("first", args.first), ("second", args.second)):
            results.append(
                verify(
                    argparse.Namespace(
                        plan=args.plan,
                        receipt=receipt_path,
                        report=verification_root / f"{label}.md",
                        include_identifiers=False,
                    ),
                    database,
                    metadata,
                )
            )
        return results[0], results[1]

    with consistent_snapshot(
        args.photos_db,
        snapshot_directory=args.snapshot_directory,
        keep=args.keep_snapshot,
    ) as (snapshot, metadata):
        verified_first, verified_second = verify_both(snapshot, metadata)

    first = normalized(
        first_receipt,
        plan,
        plan_digest,
        args.bundle_id,
        binary_digest,
        verified_first,
    )
    second = normalized(
        second_receipt,
        plan,
        plan_digest,
        args.bundle_id,
        binary_digest,
        verified_second,
    )
    passed = first == second
    lines = [
        "# Idempotence verification",
        "",
        f"- Receipt consistency: {'PASS' if passed else 'FAIL'}",
        f"- Folder identifiers compared: {len(first['folders'])}",
        f"- Album identifiers and counts compared: {len(first['albums'])}",
        f"- First planned memberships: {sum(int(item[2] or 0) for item in first['albums']):,}",
        f"- Second planned memberships: {sum(int(item[2] or 0) for item in second['albums']):,}",
        "",
        "The same plan, source, configured helper identity, folder identifiers, album identifiers, and counts must match.",
        "Independent read-only catalog verification passed for both receipts; editorial and publication gates remain separate.",
    ]
    if not passed:
        lines.extend(["", "The receipts differ. Do not declare the production write idempotent."])
    args.report.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.report.parent.chmod(0o700)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.report.chmod(0o600)
    machine_report = {
        "schema_version": 1,
        "status": "PASS" if passed else "FAIL",
        "verification_kind": "wal-aware-live-snapshot",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_digest,
        "first_receipt_sha256": file_sha256(args.first),
        "second_receipt_sha256": file_sha256(args.second),
        "source_album_identifier": plan["source_album_identifier"],
        "source_count": plan["expected_source_count"],
        "source_identifier_sha256": plan["source_identifier_sha256"],
    }
    machine_path = args.report.with_suffix(".json")
    machine_path.write_text(json.dumps(machine_report, indent=2) + "\n", encoding="utf-8")
    machine_path.chmod(0o600)
    print(f"receipt-consistency={'PASS' if passed else 'FAIL'}")
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
