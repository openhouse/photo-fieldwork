#!/usr/bin/env python3
"""Fail when public source contains common private operational markers."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {
    ".git", ".venv", "__pycache__", "build", "dist", "runs", "previews", "originals", "private"
}
PATTERNS = {
    "macOS user path": re.compile("/" + "Users/"),
    "mounted-volume path": re.compile("/" + "Volumes/"),
    "catalog-style UUID": re.compile(r"\b[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}\b"),
    "email address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}


def main() -> None:
    findings = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or IGNORED_PARTS & set(path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{number}: {label}")
    if findings:
        raise SystemExit("private operational markers found:\n" + "\n".join(findings))
    print("public repository privacy scan: PASS")


if __name__ == "__main__":
    main()
