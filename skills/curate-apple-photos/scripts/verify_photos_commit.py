#!/usr/bin/env python3
"""Independently verify a permissioned-app plan and receipt through read-only Photos SQLite."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from photos_sqlite import consistent_snapshot, open_query_only

VISIBLE_LIBRARY_STILLS = "visible-library-stills://v1"


def base(value: str) -> str:
    return value.split("/", 1)[0]


def collection_record(conn: sqlite3.Connection, identifier: str) -> tuple[int, str, int, int | None]:
    rows = conn.execute(
        "SELECT Z_PK, ZTITLE, ZKIND, ZPARENTFOLDER FROM ZGENERICALBUM WHERE ZUUID = ?",
        (base(identifier),),
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"expected one collection for {identifier}; found {len(rows)}")
    return int(rows[0][0]), rows[0][1] or "", int(rows[0][2]), rows[0][3]


def is_internal_library_root(conn: sqlite3.Connection, primary_key: int | None) -> bool:
    if primary_key is None:
        return False
    rows = conn.execute(
        "SELECT ZTITLE, ZKIND, ZPARENTFOLDER FROM ZGENERICALBUM WHERE Z_PK = ?",
        (primary_key,),
    ).fetchall()
    return bool(
        len(rows) == 1
        and not (rows[0][0] or "").strip()
        and int(rows[0][1]) == 3999
        and rows[0][2] is None
    )


def album_record(conn: sqlite3.Connection, identifier: str) -> tuple[int, str, int | None]:
    primary_key, title, kind, parent = collection_record(conn, identifier)
    if kind != 2:
        raise RuntimeError(f"expected album collection kind for {identifier}; found {kind}")
    return primary_key, title, parent


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
            SELECT ZUUID
            FROM ZASSET
            WHERE ZKIND = 0
              AND ZTRASHEDSTATE = 0
              AND ZHIDDEN = 0
              AND ZVISIBILITYSTATE = 0
              AND ZBUNDLESCOPE = 0
            """
        )
        return {row[0] for row in rows}, "Visible Apple Photos library — still photographs"
    source_pk, source_title, _ = album_record(conn, identifier)
    return members(conn, source_pk), source_title


def identifier_digest(identifiers: set[str]) -> str:
    digest = hashlib.sha256()
    for identifier in sorted(identifiers):
        digest.update(identifier.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def verify(args: argparse.Namespace, database: Path, snapshot_meta: dict) -> set[str]:
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    album_specs = {item["title"]: item for item in plan["albums"]}
    if len(album_specs) != len(plan["albums"]):
        raise RuntimeError("plan contains duplicate album titles")
    expected = {
        title: {base(identifier) for identifier in item["asset_identifiers"]}
        for title, item in album_specs.items()
    }
    hold_ids = {base(identifier) for identifier in plan.get("hold_asset_identifiers", [])}
    receipt_titles = {item["title"] for item in receipt["albums"]}
    if len(receipt_titles) != len(receipt["albums"]):
        raise RuntimeError("receipt contains duplicate album titles")
    if set(expected) != receipt_titles:
        raise RuntimeError("plan and receipt album titles differ")
    if receipt.get("plan_id") != plan.get("plan_id"):
        raise RuntimeError("plan and receipt plan_id differ")
    if receipt.get("source_album_identifier") != plan.get("source_album_identifier"):
        raise RuntimeError("plan and receipt source identifier differ")
    plan_digest = hashlib.sha256(plan_bytes).hexdigest()
    if receipt.get("execution_fingerprint", {}).get("plan_sha256") != plan_digest:
        raise RuntimeError("receipt execution fingerprint does not match plan")

    conn = open_query_only(database, immutable=True)
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {len(source)} != {plan['expected_source_count']}")
    source_digest = identifier_digest(source)
    expected_source_digest = plan.get("source_identifier_sha256")
    if expected_source_digest and source_digest != expected_source_digest:
        raise RuntimeError("frozen source identifier digest changed")
    if receipt.get("source_count") != len(source):
        raise RuntimeError("receipt source count does not match verified source")
    if receipt.get("source_identifier_sha256") != source_digest:
        raise RuntimeError("receipt source digest does not match verified source")

    verified_identifiers = set()
    folder_specs = {item["key"]: item for item in plan.get("folders", [])}
    receipt_folders = {item["key"]: item for item in receipt.get("folders", [])}
    if set(folder_specs) != set(receipt_folders):
        raise RuntimeError("plan and receipt folder keys differ")
    folder_records = {}
    for key, folder in receipt_folders.items():
        expected_identifier = folder_specs[key].get("existing_identifier")
        if expected_identifier and folder.get("identifier") != expected_identifier:
            raise RuntimeError(f"folder identifier mismatch for {folder['title']}")
        primary_key, actual_title, kind, parent_pk = collection_record(conn, folder["identifier"])
        if kind != 4000:
            raise RuntimeError(f"expected folder collection kind for {folder['title']}; found {kind}")
        if actual_title != folder["title"]:
            raise RuntimeError(f"folder title mismatch for {folder['title']}")
        folder_records[key] = (primary_key, parent_pk)
        verified_identifiers.add(folder["identifier"])
    for key, spec in folder_specs.items():
        parent_key = spec.get("parent_key")
        actual_parent = folder_records[key][1]
        parent_policy = spec.get("parent_policy")
        if parent_policy not in {None, "external-anchor"}:
            raise RuntimeError(f"unknown folder parent policy for {spec['title']}")
        if parent_policy == "external-anchor":
            if key != "workspace_parent" or parent_key is not None or not spec.get("existing_identifier"):
                raise RuntimeError(f"invalid external-anchor policy for {spec['title']}")
            parent_matches = True
        else:
            if parent_key and parent_key not in folder_records:
                raise RuntimeError(f"unknown folder parent key for {spec['title']}")
            expected_parent = folder_records[parent_key][0] if parent_key else None
            parent_matches = (
                actual_parent == expected_parent
                if parent_key
                else actual_parent is None or is_internal_library_root(conn, actual_parent)
            )
        if not parent_matches:
            raise RuntimeError(f"folder parent mismatch for {spec['title']}")

    verified = []
    for received in receipt["albums"]:
        title = received["title"]
        album_pk, actual_title, parent_pk = album_record(conn, received["identifier"])
        actual = members(conn, album_pk)
        if actual_title != title:
            raise RuntimeError(f"title mismatch for {title}")
        if actual != expected[title]:
            raise RuntimeError(f"membership mismatch for {title}: expected {len(expected[title])}, got {len(actual)}")
        if int(received.get("count", -1)) != len(actual):
            raise RuntimeError(f"receipt count mismatch for {title}")
        if not actual <= source:
            raise RuntimeError(f"{title} contains assets outside source")
        if album_specs[title].get("safety_role", "editor") != "hold" and actual & hold_ids:
            raise RuntimeError(f"{title} overlaps safety HOLD by {len(actual & hold_ids)}")
        parent_key = album_specs[title].get("parent_folder_key")
        if parent_key not in folder_records or parent_pk != folder_records[parent_key][0]:
            raise RuntimeError(f"album parent mismatch for {title}")
        verified.append((title, len(actual), received["identifier"]))
        verified_identifiers.add(received["identifier"])
    conn.close()

    verification_kind = (
        "wal-aware-live-snapshot"
        if snapshot_meta.get("live_connection_mode") == "ro"
        and snapshot_meta.get("live_connection_query_only") is True
        else "supplied-test-snapshot"
    )
    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        f"- Plan: `{plan['plan_id']}`",
        f"- Source: `{source_title}`",
        f"- Source membership: {len(source):,}",
        f"- Source identifier digest: `{source_digest}`",
        f"- Albums exactly verified: {len(verified)}",
        "- Unexpected memberships: 0",
        "- Missing memberships: 0",
        "- Members outside source corpus: 0",
        "- HOLD overlap outside the protected HOLD album: 0",
        "",
        "## Albums",
        "",
        *[
            f"- `{title}`: {count:,}" + (f" (`{identifier}`)" if args.include_identifiers else "")
            for title, count, identifier in verified
        ],
        "",
        (
            "Verification used a WAL-aware read-only snapshot followed by an immutable, query-only connection."
            if verification_kind == "wal-aware-live-snapshot"
            else "Verification used a supplied read-only test snapshot; this is not production freshness evidence."
        ),
        f"Snapshot bytes: {snapshot_meta.get('snapshot_bytes', database.stat().st_size):,}.",
    ]
    args.report.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.report.parent.chmod(0o700)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.report.chmod(0o600)
    machine_report = {
        "schema_version": 1,
        "status": "PASS",
        "verification_kind": verification_kind,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_digest,
        "receipt_sha256": hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
        "source_album_identifier": plan["source_album_identifier"],
        "source_count": len(source),
        "source_identifier_sha256": source_digest,
        "verified_folder_count": len(folder_records),
        "verified_album_count": len(verified),
        "verified_identifiers_sha256": identifier_digest(verified_identifiers),
    }
    machine_path = args.report.with_suffix(".json")
    machine_path.write_text(json.dumps(machine_report, indent=2) + "\n", encoding="utf-8")
    machine_path.chmod(0o600)
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")
    return verified_identifiers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--photos-db", type=Path, required=True, help="live Photos database; copied read-only with WAL")
    parser.add_argument("--snapshot-directory", type=Path)
    parser.add_argument("--keep-snapshot", action="store_true")
    parser.add_argument("--include-identifiers", action="store_true")
    args = parser.parse_args()

    with consistent_snapshot(
        args.photos_db,
        snapshot_directory=args.snapshot_directory,
        keep=args.keep_snapshot,
    ) as (snapshot, metadata):
        verify(args, snapshot, metadata)


if __name__ == "__main__":
    main()
