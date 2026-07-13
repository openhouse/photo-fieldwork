#!/usr/bin/env python3
"""Independently verify a Photos plan through a bounded, WAL-aware snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from source_contract import VISIBLE_LIBRARY_STILLS, visible_stills_predicate


DEFAULT_DB = Path(
    os.environ.get(
        "PHOTO_FIELDWORK_PHOTOS_DB",
        "/Volumes/apple-photos-8tb-external-ssd/Photos Library.photoslibrary/database/Photos.sqlite",
    )
)


def base(value: str) -> str:
    return value.split("/", 1)[0]


def open_photos(path: Path, immutable: bool = False) -> sqlite3.Connection:
    immutable_flag = "&immutable=1" if immutable else ""
    conn = sqlite3.connect(f"file:{path}?mode=ro{immutable_flag}", uri=True, timeout=60)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    return conn


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


def source_members(conn: sqlite3.Connection, identifier: str) -> tuple[set[str], str]:
    if identifier == VISIBLE_LIBRARY_STILLS:
        rows = conn.execute(
            f"SELECT ZUUID FROM ZASSET a WHERE {visible_stills_predicate('a')}"
        )
        return {row[0] for row in rows}, "Visible Apple Photos library - still photographs"
    source_pk, source_title = album_record(conn, identifier)
    return members(conn, source_pk), source_title


def load_holds(path: Path | None) -> set[str]:
    if not path:
        return set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {base(row["uuid"]) for row in csv.DictReader(handle) if row.get("uuid")}


def expected_by_title(plan: dict) -> dict[str, set[str]]:
    return {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }


def source_fingerprint(plan: dict, source: set[str]) -> str:
    digest = hashlib.sha256(
        f"{plan['source_album_identifier']}\n{plan.get('source_predicate_version', '')}\n".encode()
    )
    for uuid in sorted(source):
        digest.update(uuid.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def estimate_snapshot_bytes(plan: dict) -> int:
    source_rows = int(plan["expected_source_count"])
    membership_rows = sum(len(item["asset_identifiers"]) for item in plan["albums"])
    return 16 * 1024 * 1024 + (source_rows + membership_rows) * 96


def build_compact_snapshot(
    photos: sqlite3.Connection,
    path: Path,
    plan: dict,
    receipt: dict,
) -> None:
    compact = sqlite3.connect(path)
    compact.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE source_member (uuid TEXT PRIMARY KEY);
        CREATE TABLE album (
          identifier TEXT PRIMARY KEY,
          title TEXT NOT NULL
        );
        CREATE TABLE album_member (
          identifier TEXT NOT NULL,
          uuid TEXT NOT NULL,
          PRIMARY KEY (identifier, uuid)
        );
        """
    )
    source, source_title = source_members(photos, plan["source_album_identifier"])
    compact.executemany("INSERT INTO source_member(uuid) VALUES (?)", ((uuid,) for uuid in source))
    compact.executemany(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        [
            ("source_title", source_title),
            ("source_identifier", plan["source_album_identifier"]),
            ("source_count", str(len(source))),
            ("captured_at", datetime.now().astimezone().isoformat(timespec="seconds")),
            ("photos_schema_version", str(photos.execute("PRAGMA schema_version").fetchone()[0])),
        ],
    )
    for received in receipt["albums"]:
        identifier = received["identifier"]
        album_pk, title = album_record(photos, identifier)
        actual = members(photos, album_pk)
        compact.execute(
            "INSERT INTO album(identifier, title) VALUES (?, ?)",
            (identifier, title),
        )
        compact.executemany(
            "INSERT INTO album_member(identifier, uuid) VALUES (?, ?)",
            ((identifier, uuid) for uuid in actual),
        )
    compact.commit()
    compact.close()


def compact_source(conn: sqlite3.Connection) -> tuple[set[str], str]:
    source = {row[0] for row in conn.execute("SELECT uuid FROM source_member")}
    title = conn.execute("SELECT value FROM meta WHERE key = 'source_title'").fetchone()[0]
    return source, title


def compact_album(conn: sqlite3.Connection, identifier: str) -> tuple[str, set[str]]:
    row = conn.execute("SELECT title FROM album WHERE identifier = ?", (identifier,)).fetchone()
    if not row:
        raise RuntimeError(f"compact snapshot is missing album {identifier}")
    actual = {
        item[0]
        for item in conn.execute(
            "SELECT uuid FROM album_member WHERE identifier = ?",
            (identifier,),
        )
    }
    return row[0], actual


def verify_sets(
    plan: dict,
    receipt: dict,
    source: set[str],
    source_title: str,
    album_reader,
    holds: set[str],
) -> tuple[list[dict], list[str]]:
    expected = expected_by_title(plan)
    errors: list[str] = []
    receipt_titles = {item["title"] for item in receipt["albums"]}
    if set(expected) != receipt_titles:
        errors.append("plan and receipt album titles differ")
    if len(source) != int(plan["expected_source_count"]):
        errors.append(
            f"source count changed: {len(source)} != {plan['expected_source_count']}"
        )
    expected_fingerprint = plan.get("source_fingerprint")
    if expected_fingerprint and source_fingerprint(plan, source) != expected_fingerprint:
        errors.append("source membership fingerprint changed")
    verified = []
    for received in receipt["albums"]:
        title = received["title"]
        actual_title, actual = album_reader(received["identifier"])
        expected_members = expected.get(title, set())
        missing = expected_members - actual
        unexpected = actual - expected_members
        outside = actual - source
        hold_overlap = actual & holds if title.startswith("00 MASTER") else set()
        if actual_title != title:
            errors.append(f"title mismatch for {title}")
        if missing:
            errors.append(f"{title}: {len(missing)} missing memberships")
        if unexpected:
            errors.append(f"{title}: {len(unexpected)} unexpected memberships")
        if outside:
            errors.append(f"{title}: {len(outside)} members outside source")
        if hold_overlap:
            errors.append(f"{title}: {len(hold_overlap)} HOLD overlaps")
        verified.append(
            {
                "title": title,
                "identifier": received["identifier"],
                "expected": len(expected_members),
                "actual": len(actual),
                "missing": len(missing),
                "unexpected": len(unexpected),
                "outside_source": len(outside),
                "hold_overlap": len(hold_overlap),
            }
        )
    return verified, errors


def write_report(
    path: Path,
    plan: dict,
    source_title: str,
    source_count: int,
    mode: str,
    verified: list[dict],
    errors: list[str],
) -> None:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    result = {
        "schema_version": 2,
        "artifact_sensitivity": "review-sensitive",
        "status": "PASS" if not errors else "FAIL",
        "generated_at": generated_at,
        "plan_id": plan["plan_id"],
        "proposal_id": plan.get("proposal_id"),
        "master_sha256": plan.get("master_sha256"),
        "audited_uuid_sha256": plan.get("audited_uuid_sha256"),
        "source_title": source_title,
        "source_count": source_count,
        "source_fingerprint": plan.get("source_fingerprint"),
        "verification_mode": mode,
        "verified_album_count": len(verified),
        "missing_memberships": sum(item["missing"] for item in verified),
        "unexpected_memberships": sum(item["unexpected"] for item in verified),
        "members_outside_source": sum(item["outside_source"] for item in verified),
        "master_hold_overlap": sum(item["hold_overlap"] for item in verified),
        "albums": verified,
        "errors": errors,
        "direct_photos_writes": False,
    }
    if path.suffix.lower() == ".json":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("report extension must be .json, .md, or .markdown")
    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {generated_at}",
        "",
        f"- Status: {result['status']}",
        f"- Plan: `{plan['plan_id']}`",
        f"- Source: `{source_title}`",
        f"- Source membership: {source_count:,}",
        f"- Verification mode: `{mode}`",
        f"- Albums inspected: {len(verified)}",
        f"- Total missing memberships: {sum(item['missing'] for item in verified)}",
        f"- Total unexpected memberships: {sum(item['unexpected'] for item in verified)}",
        f"- Total members outside source: {sum(item['outside_source'] for item in verified)}",
        f"- Master/HOLD overlap: {sum(item['hold_overlap'] for item in verified)}",
        "",
        "## Albums",
        "",
        *[
            f"- `{item['title']}`: {item['actual']:,} actual / {item['expected']:,} expected; "
            f"missing {item['missing']}; unexpected {item['unexpected']}; "
            f"outside source {item['outside_source']}; HOLD overlap {item['hold_overlap']}"
            for item in verified
        ],
    ]
    if errors:
        lines.extend(["", "## Errors", "", *[f"- {error}" for error in errors]])
    lines.extend(
        [
            "",
            "The verifier opened Photos read-only and never issued a Photos database write.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--holds", type=Path)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--mode",
        choices=["compact", "live-ro", "immutable"],
        default="compact",
    )
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--max-snapshot-mb", type=int, default=512)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    holds = load_holds(args.holds)

    if args.mode == "compact":
        estimate = estimate_snapshot_bytes(plan)
        maximum = args.max_snapshot_mb * 1024 * 1024
        if estimate > maximum:
            raise SystemExit(
                f"estimated compact snapshot {estimate / 1024 / 1024:.1f} MB exceeds "
                f"configured limit {args.max_snapshot_mb} MB"
            )
        temp_parent = args.temp_dir or Path(tempfile.gettempdir())
        free = shutil.disk_usage(temp_parent).free
        if free < estimate * 2:
            raise SystemExit(
                f"insufficient free space for bounded snapshot: need {estimate * 2}, have {free}"
            )
        with tempfile.TemporaryDirectory(prefix="photo-fieldwork-verify-", dir=temp_parent) as temp:
            snapshot = Path(temp) / "verification.sqlite"
            photos = open_photos(args.photos_db, immutable=False)
            try:
                build_compact_snapshot(photos, snapshot, plan, receipt)
            finally:
                photos.close()
            compact = sqlite3.connect(f"file:{snapshot}?mode=ro&immutable=1", uri=True)
            compact.execute("PRAGMA query_only=ON")
            source, source_title = compact_source(compact)
            verified, errors = verify_sets(
                plan,
                receipt,
                source,
                source_title,
                lambda identifier: compact_album(compact, identifier),
                holds,
            )
            compact.close()
    else:
        photos = open_photos(args.photos_db, immutable=args.mode == "immutable")
        try:
            source, source_title = source_members(photos, plan["source_album_identifier"])

            def read_album(identifier: str) -> tuple[str, set[str]]:
                pk, title = album_record(photos, identifier)
                return title, members(photos, pk)

            verified, errors = verify_sets(
                plan,
                receipt,
                source,
                source_title,
                read_album,
                holds,
            )
        finally:
            photos.close()

    write_report(
        args.report,
        plan,
        source_title,
        len(source),
        args.mode,
        verified,
        errors,
    )
    print(f"status={'PASS' if not errors else 'FAIL'}")
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
