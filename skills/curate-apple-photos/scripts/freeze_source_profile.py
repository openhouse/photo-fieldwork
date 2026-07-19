#!/usr/bin/env python3
"""Freeze an album or visible-library source count and identifier digest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from photos_sqlite import consistent_snapshot, open_query_only
from verify_photos_commit import VISIBLE_LIBRARY_STILLS, identifier_digest, source_members


def freeze(args: argparse.Namespace, database: Path) -> None:
    connection = open_query_only(database, immutable=True)
    identifiers, title = source_members(connection, args.source_identifier)
    connection.close()
    if args.expected_count is not None and len(identifiers) != args.expected_count:
        raise RuntimeError(f"source count changed: {len(identifiers)} != {args.expected_count}")
    profile = {
        "schema_version": 1,
        "kind": "visible-library-stills" if args.source_identifier == VISIBLE_LIBRARY_STILLS else "album",
        "identifier": args.source_identifier,
        "expected_title": title,
        "expected_count": len(identifiers),
        "identifier_sha256": identifier_digest(identifiers),
    }
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.parent.chmod(0o700)
    args.output.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    args.output.chmod(0o600)
    print(f"source_count={len(identifiers)}")
    print(f"source_identifier_sha256={profile['identifier_sha256']}")
    print(f"output={args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--photos-db", type=Path)
    source.add_argument("--snapshot", type=Path)
    parser.add_argument("--snapshot-directory", type=Path)
    parser.add_argument("--keep-snapshot", action="store_true")
    parser.add_argument("--source-identifier", required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.snapshot:
        freeze(args, args.snapshot)
        return
    with consistent_snapshot(
        args.photos_db,
        snapshot_directory=args.snapshot_directory,
        keep=args.keep_snapshot,
    ) as (snapshot, _):
        freeze(args, snapshot)


if __name__ == "__main__":
    main()
