#!/usr/bin/env python3
"""Independently verify a permissioned-app plan and receipt through read-only Photos SQLite."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


DEFAULT_DB = Path(
    "/Volumes/apple-photos-8tb-external-ssd/Photos Library.photoslibrary/database/Photos.sqlite"
)
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
            SELECT ZUUID FROM ZASSET
            WHERE ZKIND = 0 AND ZTRASHEDSTATE = 0 AND ZHIDDEN = 0
              AND ZVISIBILITYSTATE = 0 AND ZBUNDLESCOPE = 0
            """
        )
        return {row[0] for row in rows}, "Visible Apple Photos library - still photographs"
    source_pk, source_title = album_record(conn, identifier)
    return members(conn, source_pk), source_title


def membership_sha256(values: set[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--previous-receipt", type=Path)
    args = parser.parse_args()

    live_wal = args.photos_db.with_name(f"{args.photos_db.name}-wal")
    if args.photos_db == DEFAULT_DB and live_wal.exists() and live_wal.stat().st_size:
        raise RuntimeError(
            "live Photos WAL is non-empty; capture a query-only verification snapshot first"
        )

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    expected = {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }
    if len(expected) != len(plan["albums"]):
        raise RuntimeError("plan contains duplicate album titles")
    receipt_titles = {item["title"] for item in receipt["albums"]}
    if set(expected) != receipt_titles:
        raise RuntimeError("plan and receipt album titles differ")

    uri = f"file:{args.photos_db}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {len(source)} != {plan['expected_source_count']}")
    source_digest = membership_sha256(source)
    if source_digest != plan.get("source_membership_sha256"):
        raise RuntimeError(
            "source membership changed: "
            f"{source_digest} != {plan.get('source_membership_sha256', '<missing>')}"
        )

    verified = []
    folder_receipts = {item["key"]: item for item in receipt.get("folders", [])}
    planned_by_title = {item["title"]: item for item in plan["albums"]}
    duplicate_titles = 0
    for received in receipt["albums"]:
        title = received["title"]
        album_pk, actual_title = album_record(conn, received["identifier"])
        actual = members(conn, album_pk)
        if actual_title != title:
            raise RuntimeError(f"title mismatch for {title}")
        if actual != expected[title]:
            raise RuntimeError(f"membership mismatch for {title}: expected {len(expected[title])}, got {len(actual)}")
        if not actual <= source:
            raise RuntimeError(f"{title} contains assets outside source")
        parent_key = planned_by_title[title]["parent_folder_key"]
        if parent_key not in folder_receipts:
            raise RuntimeError(f"receipt lacks parent folder {parent_key} for {title}")
        parent_pk, _ = album_record(conn, folder_receipts[parent_key]["identifier"])
        same_title_count = conn.execute(
            """
            SELECT count(*) FROM ZGENERICALBUM
            WHERE ZTITLE = ? AND ZPARENTFOLDER = ? AND coalesce(ZTRASHEDSTATE, 0) = 0
            """,
            (title, parent_pk),
        ).fetchone()[0]
        if same_title_count != 1:
            duplicate_titles += max(0, same_title_count - 1)
            raise RuntimeError(f"expected one {title} inside parent folder; found {same_title_count}")
        verified.append((title, len(actual), received["identifier"]))
    conn.close()

    rerun_identical = None
    if args.previous_receipt:
        previous = json.loads(args.previous_receipt.read_text(encoding="utf-8"))
        previous_folders = {(item["key"], item["identifier"]) for item in previous.get("folders", [])}
        current_folders = {(item["key"], item["identifier"]) for item in receipt.get("folders", [])}
        previous_albums = {(item["title"], item["identifier"], item["count"]) for item in previous["albums"]}
        current_albums = {(item["title"], item["identifier"], item["count"]) for item in receipt["albums"]}
        rerun_identical = previous_folders == current_folders and previous_albums == current_albums
        if not rerun_identical:
            raise RuntimeError("production rerun changed folder or album identifiers/counts")

    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        f"- Plan: `{plan['plan_id']}`",
        f"- Source: `{source_title}`",
        f"- Source membership: {len(source):,}",
        f"- Source membership SHA-256: `{source_digest}`",
        f"- Albums exactly verified: {len(verified)}",
        "- Unexpected memberships: 0",
        "- Missing memberships: 0",
        "- Members outside source corpus: 0",
        f"- Duplicate album titles within intended parent folders: {duplicate_titles}",
        *([f"- Previous and current receipts identical: {rerun_identical}"] if rerun_identical is not None else []),
        "",
        "## Albums",
        "",
        *[f"- `{title}`: {count:,} (`{identifier}`)" for title, count, identifier in verified],
        "",
        "Verification used a read-only, immutable, query-only SQLite connection.",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


if __name__ == "__main__":
    main()
