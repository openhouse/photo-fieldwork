#!/usr/bin/env python3
"""Freeze a read-only Photo Fieldwork inventory as a source snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--query-definition-version", type=int, default=1)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro&immutable=1", uri=True, timeout=60)
    conn.execute("PRAGMA query_only=ON")
    digest = hashlib.sha256()
    count = 0
    for (uuid,) in conn.execute("SELECT uuid FROM asset ORDER BY uuid"):
        digest.update(uuid.encode("utf-8"))
        digest.update(b"\n")
        count += 1
    conn.close()
    if args.expected_count is not None and count != args.expected_count:
        raise SystemExit(f"source count changed: {count} != {args.expected_count}")
    snapshot = {
        "schema_version": 1,
        "query_id": args.query_id,
        "query_definition_version": args.query_definition_version,
        "observed_count": count,
        "membership_sha256": digest.hexdigest(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"source_count={count}")
    print(f"membership_sha256={snapshot['membership_sha256']}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
