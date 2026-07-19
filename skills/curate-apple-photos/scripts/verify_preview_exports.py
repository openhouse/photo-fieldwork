#!/usr/bin/env python3
"""Verify local preview coverage and full JPEG decoding before visual review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from photo_fieldwork.preview import verify_preview_exports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--preview-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records = []
    for line_number, line in enumerate(args.inspection.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid inspection JSONL line {line_number}: {error}") from error
        identifier = row.get("asset_identifier") or row.get("uuid")
        records.append({"uuid": identifier, "preview_exported": row.get("preview_exported")})

    report = verify_preview_exports(records, args.preview_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"preview_integrity={'PASS' if report['passed'] else 'FAIL'}")
    print(f"valid_previews={report['valid_count']}")
    print(f"invalid_previews={report['invalid_count']}")
    print(f"report={args.output}")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
