#!/usr/bin/env python3
"""Validate the public synthetic eval bank and its release-risk coverage."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_DIMENSIONS = {
    "source_identity",
    "exact_assignment",
    "diversity",
    "fresh_evidence",
    "evaluation_binding",
    "preview_integrity",
    "safety_authority",
    "relational_safety",
    "per_view_quality",
    "canary_integrity",
    "holdout_integrity",
    "run_recovery",
    "catalog_verification",
    "publication_boundary",
    "positive_control",
}
ALLOWED_ORACLES = {"BLOCK", "HUMAN_REVIEW", "PROCEED", "PROCEED_IF_GATES_PASS", "RECOVER_ONLY"}
PRIVATE_PATTERNS = (
    re.compile(r"/(?:Users|Volumes|private|var/folders)/"),
    re.compile(r"[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}", re.I),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
)


def validate_bank(payload: dict) -> list[str]:
    errors = []
    if payload.get("skill_name") != "curate-apple-photos":
        errors.append("skill_name must be curate-apple-photos")
    cases = payload.get("evals")
    if not isinstance(cases, list) or len(cases) < 12:
        return [*errors, "eval bank must contain at least 12 cases"]
    ids = [case.get("id") for case in cases]
    names = [case.get("name") for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("eval IDs must be unique")
    if len(names) != len(set(names)):
        errors.append("eval names must be unique")
    covered = set()
    proceed_count = 0
    for case in cases:
        label = case.get("name") or f"id={case.get('id')}"
        dimensions = case.get("dimensions")
        if not isinstance(dimensions, list) or not dimensions:
            errors.append(f"{label}: dimensions must be a non-empty list")
            dimensions = []
        covered.update(dimensions)
        oracle = case.get("decision_oracle")
        if oracle not in ALLOWED_ORACLES:
            errors.append(f"{label}: unknown decision_oracle {oracle}")
        if str(oracle).startswith("PROCEED"):
            proceed_count += 1
        assertions = case.get("assertions")
        if not isinstance(assertions, list) or len(assertions) < 3:
            errors.append(f"{label}: requires at least three assertions")
        elif any(len(str(assertion).strip()) < 24 for assertion in assertions):
            errors.append(f"{label}: assertions must name observable behavior")
        shortcuts = case.get("unsafe_shortcuts")
        if not isinstance(shortcuts, list) or len(shortcuts) < 2:
            errors.append(f"{label}: requires at least two unsafe shortcuts")
        for field in ("prompt", "expected_output"):
            if not str(case.get(field, "")).strip():
                errors.append(f"{label}: {field} is required")
        rendered = json.dumps(case, sort_keys=True)
        if any(pattern.search(rendered) for pattern in PRIVATE_PATTERNS):
            errors.append(f"{label}: contains private or machine-specific fixture data")
    missing = sorted(REQUIRED_DIMENSIONS - covered)
    if missing:
        errors.append("missing critical dimensions: " + ", ".join(missing))
    if proceed_count < 2:
        errors.append("eval bank requires at least two positive controls")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path(__file__).with_name("evals.json"),
    )
    args = parser.parse_args()
    payload = json.loads(args.path.read_text(encoding="utf-8"))
    errors = validate_bank(payload)
    if errors:
        print("eval bank FAIL")
        for error in errors:
            print(f"- {error}")
        return 2
    print(f"eval bank PASS: {len(payload['evals'])} cases, {len(REQUIRED_DIMENSIONS)} dimensions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
