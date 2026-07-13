#!/usr/bin/env python3
"""Verify a PhotoKit plan and receipt against a frozen read-only snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


VISIBLE_LIBRARY_STILLS = "visible-library-stills://v1"


def base(value: str) -> str:
    return value.split("/", 1)[0]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_metadata(conn: sqlite3.Connection) -> dict[str, str]:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    if not table:
        raise RuntimeError(
            "verification requires a compact frozen snapshot from "
            "build_verification_snapshot.py, not the live Photos database"
        )
    return dict(conn.execute("SELECT key, value FROM meta"))


def collection_record(conn: sqlite3.Connection, identifier: str) -> tuple[int, str, int | None]:
    rows = conn.execute(
        "SELECT Z_PK, ZTITLE, ZPARENTFOLDER FROM ZGENERICALBUM WHERE ZUUID = ?",
        (base(identifier),),
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"expected one collection for {identifier}; found {len(rows)}")
    return int(rows[0][0]), rows[0][1] or "", rows[0][2]


def members(conn: sqlite3.Connection, album_pk: int) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            """
            SELECT a.ZUUID
            FROM Z_30ASSETS membership
            JOIN ZASSET a ON a.Z_PK = membership.Z_3ASSETS
            WHERE membership.Z_30ALBUMS = ?
            """,
            (album_pk,),
        )
    }


def source_members(conn: sqlite3.Connection, identifier: str) -> tuple[set[str], str]:
    if identifier == VISIBLE_LIBRARY_STILLS:
        rows = conn.execute(
            """
            SELECT ZUUID FROM ZASSET
            WHERE ZKIND = 0 AND ZTRASHEDSTATE = 0 AND ZHIDDEN = 0
              AND ZVISIBILITYSTATE = 0 AND ZBUNDLESCOPE = 0
            """
        )
        return {row[0] for row in rows}, "Visible Apple Photos library — still photographs"
    source_pk, source_title, _ = collection_record(conn, identifier)
    return members(conn, source_pk), source_title


def verify(
    plan: dict,
    receipt: dict,
    database: Path,
    manifest_paths: dict[str, Path] | None = None,
) -> dict:
    errors = []
    if receipt.get("plan_id") != plan.get("plan_id"):
        errors.append("plan and receipt IDs differ")
    expected = {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }
    receipt_by_title = {item["title"]: item for item in receipt.get("albums", [])}
    if set(expected) != set(receipt_by_title):
        errors.append("plan and receipt album titles differ")

    conn = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    metadata = snapshot_metadata(conn)
    if metadata.get("plan_id") != plan.get("plan_id"):
        errors.append("verification snapshot was built for a different plan")
    if metadata.get("source_identifier") != plan.get("source_album_identifier"):
        errors.append("verification snapshot source differs from plan")
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        errors.append(f"source count changed: {len(source)} != {plan['expected_source_count']}")

    folder_pks = {}
    receipt_folders = {item["key"]: item for item in receipt.get("folders", [])}
    topology_errors = 0
    for spec in plan.get("folders", []):
        received = receipt_folders.get(spec["key"])
        if not received:
            errors.append(f"missing folder receipt: {spec['key']}")
            topology_errors += 1
            continue
        pk, title, parent_pk = collection_record(conn, received["identifier"])
        folder_pks[spec["key"]] = pk
        if title != spec["title"]:
            errors.append(f"folder title mismatch: {spec['key']}")
        expected_parent = folder_pks.get(spec.get("parent_key"))
        if spec.get("parent_key") and parent_pk != expected_parent:
            errors.append(f"folder parent mismatch: {spec['key']}")
            topology_errors += 1

    missing_count = 0
    unexpected_count = 0
    outside_count = 0
    verified = []
    private_members = set()
    master_members = set()
    specs_by_title = {item["title"]: item for item in plan["albums"]}
    for title, expected_members in expected.items():
        received = receipt_by_title.get(title)
        if not received:
            continue
        album_pk, actual_title, parent_pk = collection_record(conn, received["identifier"])
        actual = members(conn, album_pk)
        missing = expected_members - actual
        unexpected = actual - expected_members
        outside = actual - source
        missing_count += len(missing)
        unexpected_count += len(unexpected)
        outside_count += len(outside)
        if actual_title != title:
            errors.append(f"album title mismatch: {title}")
        if missing:
            errors.append(f"missing {len(missing)} memberships: {title}")
        if unexpected:
            errors.append(f"unexpected {len(unexpected)} memberships: {title}")
        if outside:
            errors.append(f"outside-source {len(outside)} memberships: {title}")
        spec = specs_by_title[title]
        if parent_pk != folder_pks.get(spec["parent_folder_key"]):
            errors.append(f"album parent mismatch: {title}")
            topology_errors += 1
        if spec["parent_folder_key"] == "private":
            private_members |= actual
        if title.startswith("00 MASTER"):
            master_members |= actual
        verified.append({"title": title, "count": len(actual), "identifier": received["identifier"]})
    conn.close()

    hold_overlap = len(master_members & private_members)
    if hold_overlap:
        errors.append(f"master overlaps private HOLD by {hold_overlap}")
    expected_hashes = plan.get("manifest_hashes", {})
    observed_hashes = {}
    for key, path in (manifest_paths or {}).items():
        observed_hashes[f"{key}_sha256"] = file_hash(path)
    for key in expected_hashes:
        if key not in observed_hashes:
            errors.append(f"manifest not supplied for hash verification: {key}")
    for key, observed in observed_hashes.items():
        if expected_hashes.get(key) != observed:
            errors.append(f"manifest hash mismatch: {key}")
    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "plan_id": plan.get("plan_id"),
        "source_title": source_title,
        "source_count": len(source),
        "albums_verified": len(verified),
        "missing_memberships": missing_count,
        "unexpected_memberships": unexpected_count,
        "outside_source": outside_count,
        "hold_overlap": hold_overlap,
        "folder_topology_errors": topology_errors,
        "manifest_hashes": expected_hashes,
        "verified_manifest_hashes": observed_hashes,
        "albums": verified,
        "errors": errors,
        "verification_access": "mode=ro&immutable=1; query_only",
    }


def markdown(report: dict) -> str:
    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"- Status: **{report['status']}**",
        f"- Plan: `{report['plan_id']}`",
        f"- Source: `{report['source_title']}`",
        f"- Source membership: {report['source_count']:,}",
        f"- Albums exactly verified: {report['albums_verified']}",
        f"- Unexpected memberships: {report['unexpected_memberships']}",
        f"- Missing memberships: {report['missing_memberships']}",
        f"- Members outside source corpus: {report['outside_source']}",
        f"- Master/HOLD overlap: {report['hold_overlap']}",
        f"- Folder topology errors: {report['folder_topology_errors']}",
        "",
        "## Albums",
        "",
        *[
            f"- `{item['title']}`: {item['count']:,} (`{item['identifier']}`)"
            for item in report["albums"]
        ],
    ]
    if report["errors"]:
        lines.extend(["", "## Errors", "", *[f"- {error}" for error in report["errors"]]])
    lines.extend(["", "Verification used a read-only, immutable, query-only SQLite connection.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--json-report", type=Path)
    parser.add_argument(
        "--photos-db",
        type=Path,
        required=True,
        help="compact frozen database produced by build_verification_snapshot.py",
    )
    parser.add_argument("--master", type=Path)
    parser.add_argument("--holds", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    manifest_paths = {
        key: path
        for key, path in {
            "master": args.master,
            "holds": args.holds,
            "config": args.config,
        }.items()
        if path is not None
    }
    report = verify(plan, receipt, args.photos_db, manifest_paths)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown(report), encoding="utf-8")
    json_path = args.json_report or args.report.with_suffix(".json")
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"status={report['status']}")
    print(f"verified_albums={report['albums_verified']}")
    print(f"source_count={report['source_count']}")
    if report["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
