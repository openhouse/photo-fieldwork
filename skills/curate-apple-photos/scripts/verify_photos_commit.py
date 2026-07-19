#!/usr/bin/env python3
"""Independently verify a permissioned-app plan and receipt through read-only Photos SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from photo_fieldwork.contracts import identifier_set_sha256, validate_plan  # noqa: E402


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
        f"- Plan SHA-256: `{result.get('plan_sha256', 'not recorded')}`",
        f"- Source fingerprint: `{result.get('source_fingerprint', 'not recorded')}`",
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
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    photos_db = args.photos_db
    if args.profile:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        if int(profile.get("schema_version", 0)) != 1:
            raise ValueError("local profile schema_version must be 1")
        photos_db = Path(str(profile.get("photos_db") or photos_db)).expanduser()

    plan = validate_plan(json.loads(args.plan.read_text(encoding="utf-8")))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    expected = {
        item["key"]: {
            "title": item["title"],
            "members": {base(identifier) for identifier in item["asset_identifiers"]},
        }
        for item in plan["albums"]
    }
    for field in (
        "plan_id", "plan_sha256", "proposal_id", "master_sha256", "hold_sha256", "config_sha256",
        "source_fingerprint", "release_class",
    ):
        if receipt.get(field) != plan.get(field):
            raise RuntimeError(f"plan and receipt {field} differ")
    receipt_keys = {item["key"] for item in receipt["albums"]}
    if set(expected) != receipt_keys:
        raise RuntimeError("plan and receipt album keys differ")

    uri = f"file:{photos_db}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {len(source)} != {plan['expected_source_count']}")
    source_membership_sha256 = identifier_set_sha256(source)
    if source_membership_sha256 != plan["source"]["membership_sha256"]:
        raise RuntimeError("source membership changed without a new source manifest")

    verified = []
    for received in receipt["albums"]:
        key = received["key"]
        title = received["title"]
        if title != expected[key]["title"]:
            raise RuntimeError(f"title mismatch between plan and receipt for {key}")
        album_pk, actual_title = album_record(conn, received["identifier"])
        actual = members(conn, album_pk)
        if actual_title != title:
            raise RuntimeError(f"title mismatch for {title}")
        expected_members = expected[key]["members"]
        if actual != expected_members:
            raise RuntimeError(f"membership mismatch for {title}: expected {len(expected_members)}, got {len(actual)}")
        if not actual <= source:
            raise RuntimeError(f"{title} contains assets outside source")
        verified.append((key, title, len(actual), received["identifier"]))
    master_members = expected.get("master", {}).get("members", set())
    hold_members = expected.get("holds", {}).get("members", set())
    if master_members & hold_members:
        raise RuntimeError("verified plan overlaps master and safety holds")
    if identifier_set_sha256(hold_members) != plan["hold_sha256"]:
        raise RuntimeError("verified HOLD membership does not match hold_sha256")
    conn.close()

    result = {
        "schema_version": 2,
        "status": "PASS",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "proposal_id": plan.get("proposal_id"),
        "master_sha256": plan.get("master_sha256"),
        "hold_sha256": plan.get("hold_sha256"),
        "config_sha256": plan.get("config_sha256"),
        "source_fingerprint": plan.get("source_fingerprint"),
        "source_membership_sha256": source_membership_sha256,
        "release_class": plan.get("release_class"),
        "source_title": source_title,
        "source_count": len(source),
        "verified_album_count": len(verified),
        "unexpected_memberships": 0,
        "missing_memberships": 0,
        "members_outside_source": 0,
        "master_hold_overlap": 0,
        "albums": [
            {"key": key, "title": title, "count": count, "identifier": identifier}
            for key, title, count, identifier in verified
        ],
        "verification_connection": "read-only immutable query-only SQLite",
    }

    write_report(args.report, result)
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


if __name__ == "__main__":
    main()
