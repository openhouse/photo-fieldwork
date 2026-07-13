#!/usr/bin/env python3
"""Independently verify a permissioned-app plan and receipt through read-only Photos SQLite."""

from __future__ import annotations

import argparse
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


def report_markdown(result: dict) -> str:
    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {result['generated_at']}",
        "",
        f"- Plan: `{result['plan_id']}`",
        f"- Source: `{result['source_title']}`",
        f"- Source membership: {result['source_count']:,}",
        f"- Albums exactly verified: {result['verified_album_count']}",
        f"- Unexpected memberships: {result['unexpected_memberships']}",
        f"- Missing memberships: {result['missing_memberships']}",
        f"- Members outside source corpus: {result['members_outside_source']}",
        "",
        "## Albums",
        "",
        *[
            f"- `{album['title']}`: {album['count']:,} (`{album['identifier']}`)"
            for album in result["albums"]
        ],
        "",
        "Verification used a read-only, immutable, query-only SQLite connection.",
    ]
    return "\n".join(lines) + "\n"


def write_report(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif path.suffix.lower() in {".md", ".markdown"}:
        path.write_text(report_markdown(result), encoding="utf-8")
    else:
        raise ValueError("report extension must be .json, .md, or .markdown")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    expected = {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }
    receipt_titles = {item["title"] for item in receipt["albums"]}
    if set(expected) != receipt_titles:
        raise RuntimeError("plan and receipt album titles differ")

    uri = f"file:{args.photos_db}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {len(source)} != {plan['expected_source_count']}")

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

    result = {
        "schema_version": 1,
        "status": "PASS",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "plan_id": plan["plan_id"],
        "proposal_id": plan.get("proposal_id"),
        "master_sha256": plan.get("master_sha256"),
        "source_title": source_title,
        "source_count": len(source),
        "verified_album_count": len(verified),
        "unexpected_memberships": 0,
        "missing_memberships": 0,
        "members_outside_source": 0,
        "albums": [
            {"title": title, "count": count, "identifier": identifier}
            for title, count, identifier in verified
        ],
        "verification_connection": "read-only immutable query-only SQLite",
    }

    write_report(args.report, result)
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


if __name__ == "__main__":
    main()
