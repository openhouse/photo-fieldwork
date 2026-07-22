#!/usr/bin/env python3
"""Export every indexed property and relationship for selected assets privately."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from pathlib import Path


RELATIONS = {
    "people": ("asset_person", ("person",)),
    "albums": ("asset_album", ("album_uuid", "album_title")),
    "keywords": ("asset_keyword", ("keyword",)),
    "search_associations": (
        "asset_search",
        ("category", "category_name", "content_string", "normalized_string", "lookup_identifier"),
    ),
    "labels": ("asset_label", ("label", "label_normalized")),
    "places": ("asset_place", ("place_type", "place")),
}


def selected_uuids(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    identifiers = [str(row.get("uuid") or "").strip().split("/", 1)[0] for row in rows]
    if not identifiers or any(not value for value in identifiers):
        raise ValueError("input CSV requires non-empty uuid rows")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("input CSV contains duplicate canonical UUIDs")
    return identifiers


def export(database: Path, input_path: Path, output: Path) -> int:
    if output.is_symlink():
        raise ValueError("private metadata output must not be a symlink")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    connection = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    records = []
    for uuid in selected_uuids(input_path):
        rows = connection.execute("SELECT * FROM asset WHERE uuid = ?", (uuid,)).fetchall()
        if len(rows) != 1:
            connection.close()
            raise ValueError(f"expected one indexed asset for selected UUID; found {len(rows)}")
        record = {"uuid": uuid, "asset": dict(rows[0]), "relationships": {}}
        for name, (table, fields) in RELATIONS.items():
            columns = ", ".join(fields)
            related = connection.execute(
                f"SELECT {columns} FROM {table} WHERE uuid = ? ORDER BY {columns}",
                (uuid,),
            ).fetchall()
            record["relationships"][name] = [dict(row) for row in related]
        records.append(record)
    connection.close()
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    output.chmod(0o600)
    if output.stat().st_mode & 0o077:
        raise ValueError("private metadata output permissions exceed 0600")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = export(args.db, args.input, args.output)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.error(str(error))
    print(f"private_metadata_records={count}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
