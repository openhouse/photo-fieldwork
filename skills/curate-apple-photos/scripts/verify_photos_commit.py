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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def membership_sha256(values: set[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def snapshot_database(source_path: Path, snapshot_path: Path) -> dict:
    if snapshot_path.exists():
        raise RuntimeError(f"refusing to overwrite verification snapshot: {snapshot_path}")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True, timeout=30)
    source.execute("PRAGMA query_only=ON")
    destination = sqlite3.connect(snapshot_path)
    try:
        source.backup(destination)
        quick_check = destination.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise RuntimeError(f"verification snapshot failed quick_check: {quick_check}")
    finally:
        destination.close()
        source.close()
    return {
        "path": str(snapshot_path.resolve()),
        "sha256": file_sha256(snapshot_path),
        "bytes": snapshot_path.stat().st_size,
        "wal_visible_backup": True,
    }


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
        return {row[0] for row in rows}, "Visible Apple Photos library - still photographs"
    source_pk, source_title = album_record(conn, identifier)
    return members(conn, source_pk), source_title


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    for field in ("plan_id", "plan_sha256", "candidate_id", "source_membership_sha256"):
        if receipt.get(field) != plan.get(field):
            raise RuntimeError(f"plan and receipt {field} differ")
    if receipt.get("helper_contract_version") != 2 or not receipt.get("execution_nonce"):
        raise RuntimeError("receipt lacks helper contract 2 execution identity")
    expected = {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }
    receipt_titles = {item["title"] for item in receipt["albums"]}
    if set(expected) != receipt_titles:
        raise RuntimeError("plan and receipt album titles differ")

    snapshot_path = args.snapshot or args.report.with_suffix(".photos-snapshot.sqlite")
    snapshot_receipt = snapshot_database(args.photos_db, snapshot_path)
    uri = f"file:{snapshot_path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {len(source)} != {plan['expected_source_count']}")
    observed_source_sha256 = membership_sha256(source)
    if observed_source_sha256 != plan["source_membership_sha256"]:
        raise RuntimeError("source membership digest changed")

    verified = []
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
        verified.append((title, len(actual), received["identifier"]))
    conn.close()

    machine_report = {
        "schema_version": 1,
        "status": "PASS",
        "candidate_id": plan["candidate_id"],
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "receipt_sha256": file_sha256(args.receipt),
        "source_identifier": plan["source_album_identifier"],
        "source_count": len(source),
        "source_membership_sha256": observed_source_sha256,
        "snapshot": snapshot_receipt,
        "album_count": len(verified),
        "missing_count": 0,
        "unexpected_count": 0,
        "outside_source_count": 0,
        "albums": [
            {"title": title, "count": count, "identifier": identifier}
            for title, count, identifier in verified
        ],
        "database_access": "read-only-backup-then-immutable-query-only",
    }
    report_json = args.report_json or args.report.with_suffix(".json")
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(machine_report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        f"- Plan: `{plan['plan_id']}`",
        f"- Source: `{source_title}`",
        f"- Source membership: {len(source):,}",
        f"- Albums exactly verified: {len(verified)}",
        f"- Frozen snapshot SHA-256: `{snapshot_receipt['sha256']}`",
        "- Unexpected memberships: 0",
        "- Missing memberships: 0",
        "- Members outside source corpus: 0",
        "",
        "## Albums",
        "",
        *[f"- `{title}`: {count:,} (`{identifier}`)" for title, count, identifier in verified],
        "",
        "Verification used a read-only SQLite backup that includes committed WAL-visible state, then an immutable query-only connection to the frozen snapshot.",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


if __name__ == "__main__":
    main()
