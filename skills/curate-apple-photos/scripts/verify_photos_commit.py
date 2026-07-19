#!/usr/bin/env python3
"""Extract compact WAL-aware evidence, then verify a Photos membership plan immutably."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from photo_fieldwork.execution import validate_execution_attempt


VISIBLE_LIBRARY_STILLS = "visible-library-stills://v1"
VISIBLE_PREDICATE = """
ZKIND = 0 AND ZTRASHEDSTATE = 0 AND ZHIDDEN = 0
AND ZVISIBILITYSTATE = 0 AND ZBUNDLESCOPE = 0
"""


def base(value: str) -> str:
    return value.split("/", 1)[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def album_record(conn: sqlite3.Connection, identifier: str) -> tuple[int, str]:
    rows = conn.execute(
        "SELECT Z_PK, ZTITLE FROM ZGENERICALBUM WHERE ZUUID = ?",
        (base(identifier),),
    ).fetchall()
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


def source_count(conn: sqlite3.Connection, identifier: str) -> tuple[int, str, int | None]:
    if identifier == VISIBLE_LIBRARY_STILLS:
        count = conn.execute(f"SELECT count(*) FROM ZASSET WHERE {VISIBLE_PREDICATE}").fetchone()[0]
        return int(count), "Visible Apple Photos library - still photographs", None
    source_pk, title = album_record(conn, identifier)
    return len(members(conn, source_pk)), title, source_pk


def source_subset(
    conn: sqlite3.Connection,
    identifier: str,
    source_pk: int | None,
    identifiers: set[str],
) -> set[str]:
    found: set[str] = set()
    values = sorted(identifiers)
    for start in range(0, len(values), 700):
        batch = values[start : start + 700]
        placeholders = ",".join("?" for _ in batch)
        if identifier == VISIBLE_LIBRARY_STILLS:
            query = f"SELECT ZUUID FROM ZASSET WHERE {VISIBLE_PREDICATE} AND ZUUID IN ({placeholders})"
            params = batch
        else:
            query = f"""
                SELECT a.ZUUID
                FROM Z_30ASSETS membership
                JOIN ZASSET a ON a.Z_PK = membership.Z_3ASSETS
                WHERE membership.Z_30ALBUMS = ? AND a.ZUUID IN ({placeholders})
            """
            params = [source_pk, *batch]
        found.update(row[0] for row in conn.execute(query, params))
    return found


def extract_evidence(
    photos_db: Path,
    evidence_db: Path,
    plan: dict,
    receipt: dict,
    plan_hash: str,
    receipt_hash: str,
) -> None:
    if evidence_db.exists():
        raise RuntimeError(f"refusing to overwrite verification evidence: {evidence_db}")
    evidence_db.parent.mkdir(parents=True, exist_ok=True)
    live = sqlite3.connect(f"file:{photos_db}?mode=ro", uri=True, timeout=120)
    live.execute("PRAGMA query_only=ON")
    live.execute("BEGIN")
    evidence = sqlite3.connect(evidence_db)
    try:
        evidence.executescript(
            """
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE source_check(uuid TEXT PRIMARY KEY, in_source INTEGER NOT NULL);
            CREATE TABLE album(identifier TEXT PRIMARY KEY, title TEXT NOT NULL);
            CREATE TABLE album_member(album_identifier TEXT NOT NULL, uuid TEXT NOT NULL,
              PRIMARY KEY(album_identifier, uuid));
            """
        )
        count, title, source_pk = source_count(live, plan["source_album_identifier"])
        planned_ids = {
            base(identifier)
            for item in plan["albums"]
            for identifier in item["asset_identifiers"]
        }
        in_source = source_subset(
            live,
            plan["source_album_identifier"],
            source_pk,
            planned_ids,
        )
        evidence.executemany(
            "INSERT INTO source_check(uuid, in_source) VALUES (?, ?)",
            ((uuid, int(uuid in in_source)) for uuid in sorted(planned_ids)),
        )
        for item in receipt["albums"]:
            album_pk, actual_title = album_record(live, item["identifier"])
            identifier = base(item["identifier"])
            evidence.execute(
                "INSERT INTO album(identifier, title) VALUES (?, ?)",
                (identifier, actual_title),
            )
            evidence.executemany(
                "INSERT INTO album_member(album_identifier, uuid) VALUES (?, ?)",
                ((identifier, uuid) for uuid in sorted(members(live, album_pk))),
            )
        metadata = {
            "schema_version": "1",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_identifier": plan["source_album_identifier"],
            "source_title": title,
            "source_count": str(count),
            "plan_sha256": plan_hash,
            "receipt_sha256": receipt_hash,
            "photos_access": "read-only WAL-aware transaction",
            "direct_photos_writes": "false",
            "external_uploads": "false",
        }
        evidence.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", metadata.items())
        evidence.commit()
    finally:
        live.rollback()
        live.close()
        evidence.close()


def verify_evidence(evidence_db: Path, plan: dict, receipt: dict) -> tuple[list[tuple], int]:
    conn = sqlite3.connect(f"file:{evidence_db}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    meta = dict(conn.execute("SELECT key, value FROM meta"))
    count = int(meta["source_count"])
    if count != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {count} != {plan['expected_source_count']}")
    if receipt.get("plan_id") != plan["plan_id"]:
        raise RuntimeError("plan and receipt plan_id differ")
    if receipt.get("source_album_identifier") != plan["source_album_identifier"]:
        raise RuntimeError("plan and receipt source identifiers differ")
    if int(receipt.get("source_count", -1)) != count:
        raise RuntimeError("receipt source count does not match compact evidence")
    outside = conn.execute("SELECT count(*) FROM source_check WHERE in_source = 0").fetchone()[0]
    if outside:
        raise RuntimeError(f"planned memberships include {outside} assets outside source")
    expected = {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }
    if len(expected) != len(plan["albums"]):
        raise RuntimeError("plan contains duplicate album titles")
    receipt_titles = {item["title"] for item in receipt["albums"]}
    if set(expected) != receipt_titles:
        raise RuntimeError("plan and receipt album titles differ")
    verified = []
    for item in receipt["albums"]:
        identifier = base(item["identifier"])
        title = conn.execute("SELECT title FROM album WHERE identifier = ?", (identifier,)).fetchone()
        if not title or title[0] != item["title"]:
            raise RuntimeError(f"title mismatch for {item['title']}")
        actual = {
            row[0]
            for row in conn.execute(
                "SELECT uuid FROM album_member WHERE album_identifier = ?",
                (identifier,),
            )
        }
        if actual != expected[item["title"]]:
            raise RuntimeError(
                f"membership mismatch for {item['title']}: expected {len(expected[item['title']])}, got {len(actual)}"
            )
        if int(item.get("count", -1)) != len(actual):
            raise RuntimeError(f"receipt count mismatch for {item['title']}")
        verified.append((item["title"], len(actual), item["identifier"]))
    private_ids = {
        base(identifier)
        for item in plan["albums"]
        if item.get("parent_folder_key") == "private"
        for identifier in item["asset_identifiers"]
    }
    editor_ids = {
        base(identifier)
        for item in plan["albums"]
        if item.get("parent_folder_key") != "private"
        for identifier in item["asset_identifiers"]
    }
    overlap = private_ids & editor_ids
    if overlap:
        raise RuntimeError(f"private HOLD overlaps editor albums by {len(overlap)} assets")
    conn.close()
    return verified, count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--evidence-db", type=Path, required=True)
    parser.add_argument("--photos-db", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    plan_hash = sha256(args.plan)
    receipt_hash = sha256(args.receipt)
    validate_execution_attempt(plan, receipt)
    extract_evidence(args.photos_db, args.evidence_db, plan, receipt, plan_hash, receipt_hash)
    verified, count = verify_evidence(args.evidence_db, plan, receipt)
    evidence_hash = sha256(args.evidence_db)
    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        f"- Plan: `{plan['plan_id']}`",
        f"- Plan SHA-256: `{plan_hash}`",
        f"- Receipt SHA-256: `{receipt_hash}`",
        f"- Compact evidence SHA-256: `{evidence_hash}`",
        f"- Source membership: {count:,}",
        f"- Albums exactly verified: {len(verified)}",
        "- Unexpected memberships: 0",
        "- Missing memberships: 0",
        "- Members outside source corpus: 0",
        "- Private HOLD/editor overlap: 0",
        "",
        "## Albums",
        "",
        *[f"- `{title}`: {count:,} (`{identifier}`)" for title, count, identifier in verified],
        "",
        "Evidence was extracted through one WAL-aware, read-only transaction, then reopened through an immutable, query-only connection. No Photos SQLite write occurred.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    print(f"verified_albums={len(verified)}")
    print(f"source_count={count}")
    print(f"evidence_db={args.evidence_db}")


if __name__ == "__main__":
    main()
