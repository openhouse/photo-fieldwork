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


def membership_digest(identifiers: set[str]) -> str:
    digest = hashlib.sha256()
    for identifier in sorted(identifiers):
        digest.update(identifier.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def object_digest(value: dict) -> str:
    clean = {key: item for key, item in value.items() if key != "plan_sha256"}
    encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parent_identifier(conn: sqlite3.Connection, identifier: str) -> str | None:
    row = conn.execute(
        """
        SELECT parent.ZUUID
        FROM ZGENERICALBUM child
        LEFT JOIN ZGENERICALBUM parent ON parent.Z_PK = child.ZPARENTFOLDER
        WHERE child.ZUUID = ?
        """,
        (base(identifier),),
    ).fetchone()
    if not row:
        raise RuntimeError(f"catalog object not found: {identifier}")
    return row[0]


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    receipt_group = parser.add_mutually_exclusive_group(required=True)
    receipt_group.add_argument("--receipt", type=Path)
    receipt_group.add_argument("--attempt-receipt", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--json-report", type=Path)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    attempt = None
    if args.attempt_receipt:
        attempt = json.loads(args.attempt_receipt.read_text(encoding="utf-8"))
        receipt = attempt.get("receipt") or {}
    else:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    if object_digest(plan) != plan.get("plan_sha256"):
        raise RuntimeError("plan_sha256 is missing or does not match the plan")
    if receipt.get("plan_sha256") not in {None, plan["plan_sha256"]}:
        raise RuntimeError("receipt plan_sha256 differs from the plan")
    if attempt and attempt.get("plan_sha256") != plan["plan_sha256"]:
        raise RuntimeError("attempt receipt plan_sha256 differs from the plan")
    if attempt and receipt.get("execution_nonce") != attempt.get("execution_nonce"):
        raise RuntimeError("helper receipt execution_nonce differs from the archived attempt")
    if receipt.get("plan_id") != plan.get("plan_id"):
        raise RuntimeError("receipt plan_id differs from the plan")
    plan_titles = [item["title"] for item in plan["albums"]]
    if len(plan_titles) != len(set(plan_titles)):
        raise RuntimeError("plan contains duplicate album titles")
    expected = {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }
    receipt_title_list = [item["title"] for item in receipt["albums"]]
    if len(receipt_title_list) != len(set(receipt_title_list)):
        raise RuntimeError("receipt contains duplicate album titles")
    receipt_titles = set(receipt_title_list)
    if set(expected) != receipt_titles:
        raise RuntimeError("plan and receipt album titles differ")

    uri = f"file:{args.photos_db}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {len(source)} != {plan['expected_source_count']}")
    source_sha256 = membership_digest(source)
    expected_source_sha256 = plan.get("expected_source_membership_sha256")
    if expected_source_sha256 and source_sha256 != expected_source_sha256:
        raise RuntimeError(
            f"source membership digest changed: {source_sha256} != {expected_source_sha256}"
        )

    folder_receipts = {item["key"]: item for item in receipt.get("folders", [])}
    if {item["key"] for item in plan["folders"]} != set(folder_receipts):
        raise RuntimeError("plan and receipt folder keys differ")
    for spec in plan["folders"]:
        received = folder_receipts[spec["key"]]
        if received["title"] != spec["title"]:
            raise RuntimeError(f"folder title mismatch for {spec['key']}")
        expected_parent = spec.get("parent_key")
        actual_parent = parent_identifier(conn, received["identifier"])
        if expected_parent:
            planned_parent = base(folder_receipts[expected_parent]["identifier"])
            if actual_parent != planned_parent:
                raise RuntimeError(f"folder parent mismatch for {spec['key']}")
        elif actual_parent is not None:
            raise RuntimeError(f"top-level folder has an unexpected parent: {spec['key']}")

    verified = []
    for received in receipt["albums"]:
        title = received["title"]
        spec = next(item for item in plan["albums"] if item["title"] == title)
        album_pk, actual_title = album_record(conn, received["identifier"])
        actual = members(conn, album_pk)
        if actual_title != title:
            raise RuntimeError(f"title mismatch for {title}")
        if actual != expected[title]:
            raise RuntimeError(f"membership mismatch for {title}: expected {len(expected[title])}, got {len(actual)}")
        if not actual <= source:
            raise RuntimeError(f"{title} contains assets outside source")
        expected_parent = base(folder_receipts[spec["parent_folder_key"]]["identifier"])
        if parent_identifier(conn, received["identifier"]) != expected_parent:
            raise RuntimeError(f"album parent mismatch for {title}")
        verified.append((title, len(actual), received["identifier"]))

    master = set()
    holds = set()
    for title, identifiers in expected.items():
        normalized = title.upper()
        if normalized.startswith("00 MASTER"):
            master.update(identifiers)
        if "SAFETY HOLD" in normalized:
            holds.update(identifiers)
    overlap = master & holds
    if overlap:
        raise RuntimeError(f"master overlaps safety HOLD by {len(overlap)} assets")
    conn.close()

    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        f"- Plan: `{plan['plan_id']}`",
        f"- Source: `{source_title}`",
        f"- Source membership: {len(source):,}",
        f"- Source membership SHA-256: `{source_sha256}`",
        f"- Plan SHA-256: `{plan['plan_sha256']}`",
        f"- Albums exactly verified: {len(verified)}",
        f"- Folder relationships verified: {len(folder_receipts)}",
        "- Unexpected memberships: 0",
        "- Missing memberships: 0",
        "- Members outside source corpus: 0",
        "- Master / safety-HOLD overlap: 0",
        "",
        "## Albums",
        "",
        *[f"- `{title}`: {count:,} (`{identifier}`)" for title, count, identifier in verified],
        "",
        "Verification used a read-only, immutable, query-only SQLite connection.",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.json_report:
        structured = {
            "schema_version": 1,
            "status": "PASS",
            "attempt_id": attempt.get("attempt_id") if attempt else None,
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "source_count": len(source),
            "source_membership_sha256": source_sha256,
            "verified_album_count": len(verified),
            "verified_folder_count": len(folder_receipts),
            "exact_membership": True,
            "exact_topology": True,
            "source_unchanged": True,
            "master_hold_overlap": 0,
        }
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(structured, indent=2) + "\n", encoding="utf-8")
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


if __name__ == "__main__":
    main()
