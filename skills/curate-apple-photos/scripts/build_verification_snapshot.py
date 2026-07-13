#!/usr/bin/env python3
"""Build a compact, WAL-aware Photos snapshot for immutable verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


VISIBLE_LIBRARY_STILLS = "visible-library-stills://v1"

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE ZASSET(
  Z_PK INT PRIMARY KEY, ZUUID TEXT UNIQUE, ZKIND INT, ZTRASHEDSTATE INT,
  ZHIDDEN INT, ZVISIBILITYSTATE INT, ZBUNDLESCOPE INT
);
CREATE TABLE ZGENERICALBUM(
  Z_PK INT PRIMARY KEY, ZUUID TEXT UNIQUE, ZTITLE TEXT, ZPARENTFOLDER INT, ZKIND INT
);
CREATE TABLE Z_30ASSETS(Z_30ALBUMS INT, Z_3ASSETS INT, PRIMARY KEY(Z_30ALBUMS, Z_3ASSETS));
"""


def base(identifier: str) -> str:
    return identifier.split("/", 1)[0]


def one_album(conn: sqlite3.Connection, identifier: str) -> tuple:
    rows = conn.execute(
        "SELECT Z_PK, ZUUID, ZTITLE, ZPARENTFOLDER, ZKIND FROM ZGENERICALBUM WHERE ZUUID = ?",
        (base(identifier),),
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"expected one album or folder for {identifier}; found {len(rows)}")
    return rows[0]


def copy_assets(source: sqlite3.Connection, output: sqlite3.Connection, query: str, params: tuple = ()) -> int:
    rows = source.execute(query, params)
    before = output.total_changes
    output.executemany(
        "INSERT OR IGNORE INTO ZASSET VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return output.total_changes - before


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos-db", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite verification snapshot: {args.output}")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    if plan["plan_id"] != receipt["plan_id"]:
        raise SystemExit("plan and receipt IDs differ")

    live = sqlite3.connect(f"file:{args.photos_db}?mode=ro", uri=True, timeout=120)
    live.execute("PRAGMA query_only=ON")
    output = sqlite3.connect(args.output)
    try:
        output.executescript(SCHEMA)
        source_identifier = plan["source_album_identifier"]
        if source_identifier == VISIBLE_LIBRARY_STILLS:
            source_count = copy_assets(
                live,
                output,
                """
                SELECT Z_PK, ZUUID, ZKIND, ZTRASHEDSTATE, ZHIDDEN, ZVISIBILITYSTATE, ZBUNDLESCOPE
                FROM ZASSET
                WHERE ZKIND = 0 AND ZTRASHEDSTATE = 0 AND ZHIDDEN = 0
                  AND ZVISIBILITYSTATE = 0 AND ZBUNDLESCOPE = 0
                """,
            )
        else:
            source_album = one_album(live, source_identifier)
            output.execute("INSERT INTO ZGENERICALBUM VALUES (?, ?, ?, ?, ?)", source_album)
            output.executemany(
                "INSERT OR IGNORE INTO Z_30ASSETS VALUES (?, ?)",
                live.execute(
                    "SELECT Z_30ALBUMS, Z_3ASSETS FROM Z_30ASSETS WHERE Z_30ALBUMS = ?",
                    (source_album[0],),
                ),
            )
            source_count = copy_assets(
                live,
                output,
                """
                SELECT a.Z_PK, a.ZUUID, a.ZKIND, a.ZTRASHEDSTATE, a.ZHIDDEN,
                       a.ZVISIBILITYSTATE, a.ZBUNDLESCOPE
                FROM Z_30ASSETS m JOIN ZASSET a ON a.Z_PK=m.Z_3ASSETS
                WHERE m.Z_30ALBUMS = ?
                """,
                (source_album[0],),
            )

        collection_ids = {
            base(item["identifier"])
            for item in receipt.get("folders", []) + receipt.get("albums", [])
        }
        for identifier in sorted(collection_ids):
            record = one_album(live, identifier)
            output.execute("INSERT OR IGNORE INTO ZGENERICALBUM VALUES (?, ?, ?, ?, ?)", record)

        album_pks = []
        for item in receipt.get("albums", []):
            record = one_album(live, item["identifier"])
            album_pks.append(record[0])
            output.executemany(
                "INSERT OR IGNORE INTO Z_30ASSETS VALUES (?, ?)",
                live.execute(
                    "SELECT Z_30ALBUMS, Z_3ASSETS FROM Z_30ASSETS WHERE Z_30ALBUMS = ?",
                    (record[0],),
                ),
            )
            copy_assets(
                live,
                output,
                """
                SELECT a.Z_PK, a.ZUUID, a.ZKIND, a.ZTRASHEDSTATE, a.ZHIDDEN,
                       a.ZVISIBILITYSTATE, a.ZBUNDLESCOPE
                FROM Z_30ASSETS m JOIN ZASSET a ON a.Z_PK=m.Z_3ASSETS
                WHERE m.Z_30ALBUMS = ?
                """,
                (record[0],),
            )

        metadata = {
            "schema_version": "1",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "plan_id": plan["plan_id"],
            "source_identifier": source_identifier,
            "source_count": str(source_count),
            "photos_access": "mode=ro; WAL-aware; query_only",
            "direct_photos_writes": "false",
        }
        output.executemany("INSERT INTO meta VALUES (?, ?)", metadata.items())
        output.commit()
    finally:
        output.close()
        live.close()

    digest = hashlib.sha256()
    with args.output.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    frozen = sqlite3.connect(f"file:{args.output}?mode=ro&immutable=1", uri=True)
    frozen.execute("PRAGMA query_only=ON")
    album_count = frozen.execute("SELECT COUNT(*) FROM ZGENERICALBUM").fetchone()[0]
    membership_count = frozen.execute("SELECT COUNT(*) FROM Z_30ASSETS").fetchone()[0]
    frozen.close()
    print(f"source_count={source_count}")
    print(f"collections={album_count}")
    print(f"memberships={membership_count}")
    print(f"sha256={digest.hexdigest()}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
