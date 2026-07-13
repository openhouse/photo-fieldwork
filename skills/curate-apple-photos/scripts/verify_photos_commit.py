#!/usr/bin/env python3
"""Independently verify a permissioned-app plan and receipt through read-only Photos SQLite."""

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


def membership_sha256(values: set[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(base(item) for item in values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def canonical_json_sha256(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "plan_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--photos-db", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 2:
        raise RuntimeError(f"unsupported plan schema: {plan.get('schema_version')}")
    if plan.get("plan_sha256") != canonical_json_sha256(plan):
        raise RuntimeError("plan digest mismatch")
    if receipt.get("plan_sha256") != plan["plan_sha256"]:
        raise RuntimeError("receipt does not bind to the exact plan digest")
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
    actual_source_digest = membership_sha256(source)
    if actual_source_digest != plan.get("source_membership_sha256"):
        raise RuntimeError("source membership digest changed")
    if receipt.get("source_membership_sha256") != actual_source_digest:
        raise RuntimeError("writer receipt source digest does not match independent verification")

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
        spec = next(item for item in plan["albums"] if item["title"] == title)
        if membership_sha256(actual) != spec.get("membership_sha256"):
            raise RuntimeError(f"membership digest mismatch for {title}")
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
        f"- Source membership SHA-256: `{actual_source_digest}`",
        f"- Plan SHA-256: `{plan['plan_sha256']}`",
        f"- Albums exactly verified: {len(verified)}",
        "- Unexpected memberships: 0",
        "- Missing memberships: 0",
        "- Members outside source corpus: 0",
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
