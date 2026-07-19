#!/usr/bin/env python3
"""Validate the skill eval bank and optionally grade typed decision responses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DECISIONS = {"block", "resume", "revise", "proceed", "complete"}
RELEASE_CLASSES = {None, "editor-field-verified", "master-human-reviewed", "publication-ready"}
CONTROL_KEYS = {
    "photos_mutation_authorized",
    "publication_authorized",
    "source_revalidation_required",
    "human_safety_review_required",
    "fresh_visual_review_required",
    "helper_compatibility_required",
    "independent_verification_required",
}
RESPONSE_KEYS = {
    "decision",
    "release_class",
    "controls",
    "observed_facts",
    "unknowns",
    "blocking_conditions",
    "next_actions",
    "prohibited_actions",
    "claim_boundary",
}
LIST_FIELDS = {
    "observed_facts",
    "unknowns",
    "blocking_conditions",
    "next_actions",
    "prohibited_actions",
    "claim_boundary",
}


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def validate_bank(bank: dict[str, object]) -> list[dict[str, object]]:
    if bank.get("skill_name") != "curate-apple-photos":
        raise ValueError("skill_name must be curate-apple-photos")
    evals = bank.get("evals")
    if not isinstance(evals, list) or not evals:
        raise ValueError("evals must be a non-empty array")
    ids: set[int] = set()
    names: set[str] = set()
    for item in evals:
        if not isinstance(item, dict):
            raise ValueError("each eval must be an object")
        eval_id = item.get("id")
        name = item.get("name")
        if not isinstance(eval_id, int) or eval_id <= 0 or eval_id in ids:
            raise ValueError(f"invalid or duplicate eval id: {eval_id}")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError(f"invalid or duplicate eval name: {name}")
        ids.add(eval_id)
        names.add(name)
        for field in ("prompt", "expected_output"):
            if not isinstance(item.get(field), str) or not str(item[field]).strip():
                raise ValueError(f"eval {eval_id} requires {field}")
        expectations = item.get("expectations")
        if not isinstance(expectations, list) or len(expectations) < 2:
            raise ValueError(f"eval {eval_id} requires at least two expectations")
        checks = item.get("machine_checks")
        if not isinstance(checks, dict):
            raise ValueError(f"eval {eval_id} requires machine_checks")
        decisions = checks.get("decision_in")
        if not isinstance(decisions, list) or not decisions or not set(decisions) <= DECISIONS:
            raise ValueError(f"eval {eval_id} has invalid decision_in")
        if checks.get("release_class") not in RELEASE_CLASSES:
            raise ValueError(f"eval {eval_id} has invalid release_class")
        controls = checks.get("controls")
        if not isinstance(controls, dict) or not set(controls) <= CONTROL_KEYS:
            raise ValueError(f"eval {eval_id} has invalid control checks")
        if not all(isinstance(value, bool) for value in controls.values()):
            raise ValueError(f"eval {eval_id} control checks must be boolean")
    return evals


def find_response(root: Path, eval_id: int, name: str) -> Path:
    matches = sorted(root.glob(f"eval-{eval_id:02d}-{name}/response.json"))
    if len(matches) != 1:
        raise ValueError(f"expected one response for eval {eval_id}, found {len(matches)}")
    return matches[0]


def validate_response(response: dict[str, object]) -> None:
    if set(response) != RESPONSE_KEYS:
        raise ValueError(f"response fields must be exactly {sorted(RESPONSE_KEYS)}")
    if response.get("decision") not in DECISIONS:
        raise ValueError("response decision is invalid")
    if response.get("release_class") not in RELEASE_CLASSES:
        raise ValueError("response release_class is invalid")
    controls = response.get("controls")
    if not isinstance(controls, dict) or set(controls) != CONTROL_KEYS:
        raise ValueError(f"response controls must be exactly {sorted(CONTROL_KEYS)}")
    if not all(isinstance(value, bool) for value in controls.values()):
        raise ValueError("response controls must be boolean")
    for field in LIST_FIELDS:
        values = response.get(field)
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError(f"response {field} must be an array of strings")
    if not response["next_actions"] or not response["claim_boundary"]:
        raise ValueError("response next_actions and claim_boundary cannot be empty")


def grade(evals: list[dict[str, object]], root: Path) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for item in evals:
        eval_id = int(item["id"])
        name = str(item["name"])
        response = load_json(find_response(root, eval_id, name))
        validate_response(response)
        checks = item["machine_checks"]
        assert isinstance(checks, dict)
        failures: list[str] = []
        if response.get("decision") not in checks["decision_in"]:
            failures.append(
                f"decision {response.get('decision')!r} not in {checks['decision_in']!r}"
            )
        if response.get("release_class") != checks.get("release_class"):
            failures.append(
                f"release_class {response.get('release_class')!r} != {checks.get('release_class')!r}"
            )
        response_controls = response.get("controls")
        if not isinstance(response_controls, dict):
            failures.append("controls is not an object")
        else:
            expected_controls = checks["controls"]
            assert isinstance(expected_controls, dict)
            for key, expected in expected_controls.items():
                if response_controls.get(key) is not expected:
                    failures.append(
                        f"control {key}={response_controls.get(key)!r}, expected {expected!r}"
                    )
        results.append(
            {
                "id": eval_id,
                "name": name,
                "passed": not failures,
                "failures": failures,
            }
        )
    passed = sum(bool(item["passed"]) for item in results)
    return {
        "summary": {
            "passed": passed,
            "failed": len(results) - passed,
            "total": len(results),
            "pass_rate": passed / len(results),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evals", type=Path, required=True)
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ids", type=int, nargs="*")
    args = parser.parse_args()

    evals = validate_bank(load_json(args.evals))
    if args.ids:
        requested = set(args.ids)
        evals = [item for item in evals if int(item["id"]) in requested]
        found = {int(item["id"]) for item in evals}
        if found != requested:
            raise ValueError(f"unknown eval ids: {sorted(requested - found)}")
    if args.responses is None:
        result: dict[str, object] = {"valid": True, "eval_count": len(evals)}
    else:
        result = grade(evals, args.responses)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    summary = result.get("summary")
    return 1 if isinstance(summary, dict) and int(summary["failed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
