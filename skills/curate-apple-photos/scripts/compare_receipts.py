#!/usr/bin/env python3
"""Compare first and second permissioned-app receipts for idempotence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def normalized(receipt: dict) -> dict:
    return {
        "plan_id": receipt.get("plan_id"),
        "source_album_identifier": receipt.get("source_album_identifier"),
        "source_count": receipt.get("source_count"),
        "source_identifier_sha256": receipt.get("source_identifier_sha256"),
        "safety_mode": receipt.get("safety_mode"),
        "folders": sorted(
            (
                item.get("key"),
                item.get("title"),
                item.get("identifier"),
            )
            for item in receipt.get("folders", [])
        ),
        "albums": sorted(
            (
                item.get("title"),
                item.get("identifier"),
                item.get("count"),
            )
            for item in receipt.get("albums", [])
        ),
        "execution_fingerprint": receipt.get("execution_fingerprint"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    first = normalized(json.loads(args.first.read_text(encoding="utf-8")))
    second = normalized(json.loads(args.second.read_text(encoding="utf-8")))
    passed = first == second
    lines = [
        "# Idempotence verification",
        "",
        f"- Status: {'PASS' if passed else 'FAIL'}",
        f"- Folder identifiers compared: {len(first['folders'])}",
        f"- Album identifiers and counts compared: {len(first['albums'])}",
        f"- First planned memberships: {sum(int(item[2] or 0) for item in first['albums']):,}",
        f"- Second planned memberships: {sum(int(item[2] or 0) for item in second['albums']):,}",
        "",
        "The same plan, source, helper fingerprint, folder identifiers, album identifiers, and counts must match.",
    ]
    if not passed:
        lines.extend(["", "The receipts differ. Do not declare the production write idempotent."])
    args.report.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.report.parent.chmod(0o700)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.report.chmod(0o600)
    print(f"idempotence={'PASS' if passed else 'FAIL'}")
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
