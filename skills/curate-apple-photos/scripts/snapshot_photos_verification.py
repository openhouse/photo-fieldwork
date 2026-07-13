#!/usr/bin/env python3
"""Capture a transaction-consistent Photos subset for immutable verification.

The live Photos database is opened mode=ro with query_only enabled so committed
WAL rows remain visible. Only the source and planned album memberships are copied
to a separate SQLite database. The live database is never checkpointed or written.
"""

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
SCHEMA = """
CREATE TABLE ZASSET (
  Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZKIND INTEGER, ZTRASHEDSTATE INTEGER,
  ZHIDDEN INTEGER, ZVISIBILITYSTATE INTEGER, ZBUNDLESCOPE INTEGER
);
CREATE TABLE ZGENERICALBUM (
  Z_PK INTEGER PRIMARY KEY, ZUUID TEXT, ZTITLE TEXT, ZPARENTFOLDER INTEGER,
  ZTRASHEDSTATE INTEGER
);
CREATE TABLE Z_30ASSETS (Z_30ALBUMS INTEGER, Z_3ASSETS INTEGER);
CREATE TABLE snapshot_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX idx_asset_uuid ON ZASSET(ZUUID);
CREATE INDEX idx_album_uuid ON ZGENERICALBUM(ZUUID);
CREATE INDEX idx_membership_album ON Z_30ASSETS(Z_30ALBUMS);
"""


def base(value: str) -> str:
    return value.split("/", 1)[0]


def readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=120)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    return conn


def batches(values: list[int], size: int = 700):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def build_snapshot(plan_path: Path, receipt_path: Path, photos_db: Path, output_path: Path) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if output_path.exists():
        raise ValueError(f"refusing to overwrite verification snapshot: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(f".{output_path.name}.partial")
    if partial.exists():
        raise ValueError(f"remove or inspect incomplete snapshot first: {partial}")

    live = readonly(photos_db)
    album_ids = {base(item["identifier"]) for item in receipt["albums"]}
    album_ids.update(base(item["identifier"]) for item in receipt.get("folders", []))
    source_identifier = plan["source_album_identifier"]
    if source_identifier != VISIBLE_LIBRARY_STILLS:
        album_ids.add(base(source_identifier))
    placeholders = ",".join("?" for _ in album_ids)
    album_rows = live.execute(
        f"SELECT Z_PK, ZUUID, ZTITLE, ZPARENTFOLDER, ZTRASHEDSTATE FROM ZGENERICALBUM WHERE ZUUID IN ({placeholders})",
        sorted(album_ids),
    ).fetchall()
    found_ids = {row[1] for row in album_rows}
    if found_ids != album_ids:
        raise ValueError(f"could not resolve albums: {', '.join(sorted(album_ids - found_ids))}")
    album_pks = [int(row[0]) for row in album_rows]

    membership_rows = []
    if album_pks:
        placeholders = ",".join("?" for _ in album_pks)
        membership_rows = live.execute(
            f"SELECT Z_30ALBUMS, Z_3ASSETS FROM Z_30ASSETS WHERE Z_30ALBUMS IN ({placeholders})",
            album_pks,
        ).fetchall()

    asset_rows: dict[int, tuple] = {}
    if source_identifier == VISIBLE_LIBRARY_STILLS:
        rows = live.execute(
            """
            SELECT Z_PK, ZUUID, ZKIND, ZTRASHEDSTATE, ZHIDDEN, ZVISIBILITYSTATE, ZBUNDLESCOPE
            FROM ZASSET
            WHERE ZKIND = 0 AND ZTRASHEDSTATE = 0 AND ZHIDDEN = 0
              AND ZVISIBILITYSTATE = 0 AND ZBUNDLESCOPE = 0
            """
        )
        asset_rows.update((int(row[0]), row) for row in rows)
    relevant_pks = sorted({int(row[1]) for row in membership_rows} - set(asset_rows))
    for batch in batches(relevant_pks):
        placeholders = ",".join("?" for _ in batch)
        for row in live.execute(
            f"""
            SELECT Z_PK, ZUUID, ZKIND, ZTRASHEDSTATE, ZHIDDEN, ZVISIBILITYSTATE, ZBUNDLESCOPE
            FROM ZASSET WHERE Z_PK IN ({placeholders})
            """,
            batch,
        ):
            asset_rows[int(row[0])] = row

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    user_version = live.execute("PRAGMA user_version").fetchone()[0]
    snapshot = sqlite3.connect(partial)
    snapshot.executescript(SCHEMA)
    snapshot.executemany("INSERT INTO ZASSET VALUES (?, ?, ?, ?, ?, ?, ?)", asset_rows.values())
    snapshot.executemany("INSERT INTO ZGENERICALBUM VALUES (?, ?, ?, ?, ?)", album_rows)
    snapshot.executemany("INSERT INTO Z_30ASSETS VALUES (?, ?)", membership_rows)
    metadata = {
        "generated_at": generated_at,
        "source_database": str(photos_db),
        "plan_id": str(plan["plan_id"]),
        "photos_schema_user_version": str(user_version),
        "asset_rows": str(len(asset_rows)),
        "album_rows": str(len(album_rows)),
        "membership_rows": str(len(membership_rows)),
        "live_database_mode": "read-only query-only transaction",
        "live_checkpoint_requested": "false",
    }
    snapshot.executemany("INSERT INTO snapshot_meta(key, value) VALUES (?, ?)", metadata.items())
    snapshot.commit()
    snapshot.close()
    live.rollback()
    live.close()
    partial.replace(output_path)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = build_snapshot(args.plan, args.receipt, args.photos_db, args.output)
    print(json.dumps(metadata, indent=2))
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
