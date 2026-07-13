from __future__ import annotations

import subprocess
from pathlib import Path


BLOCKED_PARTS = {"runs", "previews", "originals", "private"}
BLOCKED_SUFFIXES = {".photoslibrary", ".jsonl", ".mbox"}
BLOCKED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".gif", ".webp"}
BLOCKED_NAMES = {
    "proposed-master.csv",
    "hold-sensitive.csv",
    "catalog-plan.json",
    "inspection.jsonl",
}


def repository_paths(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [root / line for line in completed.stdout.splitlines() if line]


def audit_paths(root: Path, paths: list[Path]) -> list[str]:
    failures = []
    for path in paths:
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            failures.append(f"outside repository: {path}")
            continue
        lowered_parts = {part.casefold() for part in relative.parts}
        name = relative.name.casefold()
        suffix = relative.suffix.casefold()
        if lowered_parts & BLOCKED_PARTS:
            failures.append(f"private artifact directory: {relative}")
        elif name in BLOCKED_NAMES or name.endswith("-receipt.json"):
            failures.append(f"private run artifact: {relative}")
        elif suffix in BLOCKED_SUFFIXES:
            failures.append(f"private archive format: {relative}")
        elif suffix in BLOCKED_IMAGE_SUFFIXES and "synthetic" not in lowered_parts:
            failures.append(f"non-synthetic image asset: {relative}")
    return failures
