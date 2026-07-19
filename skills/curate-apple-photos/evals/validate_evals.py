#!/usr/bin/env python3
"""Validate the checked-in skill eval bank and its synthetic fixtures."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def validate() -> list[str]:
    errors: list[str] = []
    path = ROOT / "evals.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("skill_name") != "curate-apple-photos":
        errors.append("skill_name must be curate-apple-photos")
    evals = data.get("evals") or []
    ids = [item.get("id") for item in evals]
    if ids != list(range(1, len(evals) + 1)):
        errors.append("eval IDs must be consecutive integers starting at 1")
    if len(evals) < 8:
        errors.append("eval bank must retain at least eight production-shaped scenarios")
    for item in evals:
        prefix = f"eval {item.get('id')}"
        if len(str(item.get("prompt") or "").split()) < 12:
            errors.append(f"{prefix} prompt is not production-shaped")
        if len(str(item.get("expected_output") or "").split()) < 10:
            errors.append(f"{prefix} expected_output is too vague")
        expectations = item.get("expectations") or []
        if not 3 <= len(expectations) <= 6:
            errors.append(f"{prefix} must have 3-6 verifiable expectations")
        if len(expectations) != len(set(expectations)):
            errors.append(f"{prefix} repeats an expectation")
        for relative in item.get("files") or []:
            fixture = ROOT.parent / relative
            if not fixture.is_file():
                errors.append(f"{prefix} fixture does not exist: {relative}")
    return errors


def main() -> None:
    errors = validate()
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(2)
    count = len(json.loads((ROOT / "evals.json").read_text(encoding="utf-8"))["evals"])
    print(f"PASS: {count} evals and all fixtures are valid")


if __name__ == "__main__":
    main()
