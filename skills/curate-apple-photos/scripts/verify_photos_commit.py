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


def content_sha256(value: dict, digest_field: str = "plan_sha256") -> str:
    payload = dict(value)
    payload.pop(digest_field, None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    album_identifier = identifier.removeprefix("album://")
    source_pk, source_title = album_record(conn, album_identifier)
    return members(conn, source_pk), source_title


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--photos-db", type=Path)
    parser.add_argument("--profile", type=Path, help="local source profile containing photos_db")
    args = parser.parse_args()

    profile = json.loads(args.profile.expanduser().read_text(encoding="utf-8")) if args.profile else {}
    photos_db = args.photos_db or Path(profile.get("photos_db", DEFAULT_DB)).expanduser()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    digest = content_sha256(plan)
    if plan.get("plan_sha256") != digest:
        raise RuntimeError("plan_sha256 is missing or does not match plan content")
    if receipt.get("plan_sha256") != digest:
        raise RuntimeError("receipt plan_sha256 does not match plan")
    expected = {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }
    receipt_titles = {item["title"] for item in receipt["albums"]}
    if set(expected) != receipt_titles:
        raise RuntimeError("plan and receipt album titles differ")
    master_ids = set().union(*(ids for title, ids in expected.items() if "MASTER" in title))
    hold_ids = set().union(*(ids for title, ids in expected.items() if "HOLD" in title))
    if master_ids & hold_ids:
        raise RuntimeError(f"master overlaps safety HOLD by {len(master_ids & hold_ids)} assets")

    uri = f"file:{photos_db}?mode=ro&immutable=1"
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

    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        f"- Plan: `{plan['plan_id']}`",
        f"- Plan SHA-256: `{digest}`",
        f"- Writer: `{receipt.get('writer_bundle_id', 'unknown')}` `{receipt.get('writer_build_version', 'unknown')}`",
        f"- Source: `{source_title}`",
        f"- Source membership: {len(source):,}",
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
    if args.report.suffix.lower() == ".json":
        report = {
            "status": "PASS",
            "plan_id": plan["plan_id"],
            "plan_sha256": digest,
            "writer_bundle_id": receipt.get("writer_bundle_id"),
            "writer_build_version": receipt.get("writer_build_version"),
            "source_title": source_title,
            "source_count": len(source),
            "verified_albums": [
                {"title": title, "count": count, "identifier": identifier}
                for title, count, identifier in verified
            ],
            "missing_memberships": 0,
            "unexpected_memberships": 0,
            "outside_source_memberships": 0,
            "hold_overlap": 0,
        }
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state_path = args.plan.resolve().parent.parent / "run-state.json"
    if state_path.is_file() and "production" in str(plan.get("plan_id", "")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "independently-verified"
        state["phases"]["independent_verification"] = "completed"
        state["verification_report"] = str(args.report.resolve())
        state["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        temporary = state_path.with_name(f".{state_path.name}.tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(state_path)
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


if __name__ == "__main__":
    main()
