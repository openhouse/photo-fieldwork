#!/usr/bin/env python3
"""Independently verify a permissioned-app plan and receipt through read-only Photos SQLite."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


DEFAULT_DB = Path.home() / "Pictures/Photos Library.photoslibrary/database/Photos.sqlite"
VISIBLE_LIBRARY_STILLS = "visible-library-stills://v1"


def base(value: str) -> str:
    return value.split("/", 1)[0]


def membership_sha256(identifiers: set[str]) -> str:
    payload = "\n".join(sorted(base(value) for value in identifiers)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def require_photos_schema(conn: sqlite3.Connection) -> None:
    required = {
        "ZASSET": {"ZUUID", "ZKIND", "ZTRASHEDSTATE", "ZHIDDEN", "ZVISIBILITYSTATE", "ZBUNDLESCOPE"},
        "ZGENERICALBUM": {"Z_PK", "ZUUID", "ZTITLE"},
        "Z_30ASSETS": {"Z_3ASSETS", "Z_30ALBUMS"},
    }
    for table, columns in required.items():
        actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        missing = columns - actual
        if missing:
            raise RuntimeError(
                f"unsupported Photos schema: {table} missing {', '.join(sorted(missing))}"
            )


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
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    plan_bytes = args.plan.read_bytes()
    receipt_bytes = args.receipt.read_bytes()
    runtime_plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    plan = json.loads(plan_bytes)
    receipt = json.loads(receipt_bytes)
    if receipt.get("status") != "completed":
        raise RuntimeError("writer receipt does not report completion")
    if receipt.get("execution_kind") != plan.get("execution_kind"):
        raise RuntimeError("writer receipt execution kind mismatch")
    if receipt.get("plan_sha256") != plan.get("catalog_plan_sha256"):
        raise RuntimeError("receipt catalog-plan digest mismatch")
    if receipt.get("adapter_plan_sha256") != plan.get("adapter_plan_sha256"):
        raise RuntimeError("receipt adapter-plan digest mismatch")
    if receipt.get("runtime_plan_sha256") != runtime_plan_sha256:
        raise RuntimeError("receipt runtime-plan digest mismatch")
    if receipt.get("source_membership_sha256") != plan.get("source_membership_sha256"):
        raise RuntimeError("receipt source-membership digest mismatch")
    if receipt.get("execution_nonce") != plan.get("execution_nonce"):
        raise RuntimeError("receipt execution nonce mismatch")
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
    require_photos_schema(conn)
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {len(source)} != {plan['expected_source_count']}")
    source_digest = membership_sha256(source)
    if source_digest != plan["source_membership_sha256"]:
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

    verification = {
        "schema_version": 1,
        "status": "PASS",
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "execution_kind": plan["execution_kind"],
        "execution_nonce": receipt["execution_nonce"],
        "plan_sha256": plan["catalog_plan_sha256"],
        "adapter_plan_sha256": plan["adapter_plan_sha256"],
        "runtime_plan_sha256": runtime_plan_sha256,
        "source_membership_sha256": source_digest,
        "receipt_sha256": receipt_sha256,
        "verified_album_count": len(verified),
        "missing_membership_count": 0,
        "unexpected_membership_count": 0,
        "outside_source_count": 0,
        "independent_read_only": True,
    }
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
        "",
        "## Albums",
        "",
        *[f"- `{title}`: {count:,} (`{identifier}`)" for title, count, identifier in verified],
        "",
        "Verification used a read-only, immutable, query-only SQLite connection.",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.report.suffix.lower() == ".json":
        args.report.write_text(
            json.dumps(verification, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    else:
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


if __name__ == "__main__":
    main()
