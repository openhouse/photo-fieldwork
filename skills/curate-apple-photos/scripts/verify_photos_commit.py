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


def album_record(conn: sqlite3.Connection, identifier: str) -> tuple[int, str]:
    rows = conn.execute("SELECT Z_PK, ZTITLE FROM ZGENERICALBUM WHERE ZUUID = ?", (base(identifier),)).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"expected one album for {identifier}; found {len(rows)}")
    return int(rows[0][0]), rows[0][1] or ""


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
    source_pk, source_title = album_record(conn, identifier)
    return members(conn, source_pk), source_title


def identifier_digest(identifiers: set[str]) -> str:
    digest = hashlib.sha256()
    for identifier in sorted(identifiers):
        digest.update(identifier.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def verify(args: argparse.Namespace, database: Path, snapshot_meta: dict) -> None:
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

    verified = []
    for received in receipt["albums"]:
        title = received["title"]
        album_pk, actual_title = album_record(conn, received["identifier"])
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
        verified.append((title, len(actual), received["identifier"]))
    conn.close()

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
        "Verification used a WAL-aware read-only snapshot followed by an immutable, query-only connection.",
        f"Snapshot bytes: {snapshot_meta.get('snapshot_bytes', database.stat().st_size):,}.",
    ]
    args.report.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.report.parent.chmod(0o700)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.report.chmod(0o600)
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--photos-db", type=Path, help="live Photos database; copied read-only with WAL")
    source.add_argument("--snapshot", type=Path, help="existing frozen SQLite snapshot")
    parser.add_argument("--snapshot-directory", type=Path)
    parser.add_argument("--keep-snapshot", action="store_true")
    parser.add_argument("--include-identifiers", action="store_true")
    args = parser.parse_args()

    if args.snapshot:
        verify(
            args,
            args.snapshot,
            {
                "snapshot_bytes": args.snapshot.stat().st_size,
                "snapshot_connection_mode": "ro-immutable",
            },
        )
        return
    with consistent_snapshot(
        args.photos_db,
        snapshot_directory=args.snapshot_directory,
        keep=args.keep_snapshot,
    ) as (snapshot, metadata):
        verify(args, snapshot, metadata)


if __name__ == "__main__":
    main()
