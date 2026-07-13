#!/usr/bin/env python3
"""Reject private operational fields in a proposed public-safe report."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


RULES = {
    "absolute user path": re.compile(r"/(?:Users|Volumes)/[^\s`\"']+"),
    "exact coordinate key": re.compile(r'(?i)["`]?\b(?:latitude|longitude|gps)\b["`]?\s*[:=]'),
    "raw OCR field": re.compile(r'(?i)["`]?\b(?:raw_ocr|recognized_text|ocr_text)\b["`]?\s*[:=]'),
    "credential material": re.compile(r"(?i)\b(?:password|api[_ -]?key|access[_ -]?token|secret)\b\s*[:=]"),
}


def lint(text: str) -> list[dict[str, object]]:
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in RULES.items():
            if pattern.search(line):
                findings.append({"line": line_number, "rule": rule})
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    findings = lint(args.report.read_text(encoding="utf-8"))
    result = {
        "schema_version": 1,
        "artifact_sensitivity": "public-safe-candidate",
        "status": "PASS" if not findings else "FAIL",
        "finding_count": len(findings),
        "findings": findings,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if not findings else 2)


if __name__ == "__main__":
    main()
