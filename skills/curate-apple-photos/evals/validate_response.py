#!/usr/bin/env python3
"""Validate the skill eval suite and deterministically grade one response."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def suite_index(evals_path: Path) -> dict[int, dict[str, Any]]:
    payload = read_json(evals_path)
    if payload.get("skill_name") != "curate-apple-photos":
        raise ValueError("evals.json skill_name must be curate-apple-photos")
    evals = payload.get("evals", [])
    indexed = {int(item["id"]): item for item in evals}
    if len(indexed) != len(evals):
        raise ValueError("eval IDs must be unique")
    return indexed


def check_suite(evals_path: Path, rubric_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        evals = suite_index(evals_path)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    rubric = read_json(rubric_path).get("evals", {})
    try:
        read_json(ROOT / "response.schema.json")
        history = read_json(ROOT / "history.json")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"supporting eval JSON is invalid: {exc}")
        history = {}

    iterations = history.get("iterations", [])
    versions = {item.get("version") for item in iterations}
    current_best = history.get("current_best")
    if current_best not in versions:
        errors.append(f"history current_best is not an iteration: {current_best!r}")
    if sum(bool(item.get("is_current_best")) for item in iterations) != 1:
        errors.append("history must have exactly one current-best iteration")
    for item in iterations:
        rate = item.get("expectation_pass_rate")
        if not isinstance(rate, (int, float)) or not 0 <= rate <= 1:
            errors.append(f"history has invalid pass rate for {item.get('version')!r}: {rate!r}")

    rubric_ids = {int(value) for value in rubric}
    if rubric_ids != set(evals):
        errors.append(f"rubric IDs {sorted(rubric_ids)} do not match eval IDs {sorted(evals)}")

    for eval_id, item in evals.items():
        for field in ("name", "prompt", "expected_output", "files", "expectations"):
            if not item.get(field):
                errors.append(f"eval {eval_id} is missing {field}")
        if len(item.get("files", [])) != 1:
            errors.append(f"eval {eval_id} must name exactly one fixture")
            continue
        fixture_path = ROOT.parent / item["files"][0]
        if not fixture_path.is_file():
            errors.append(f"eval {eval_id} fixture does not exist: {fixture_path}")
            continue
        fixture = read_json(fixture_path)
        evidence = fixture.get("evidence", [])
        evidence_ids = [entry.get("id") for entry in evidence]
        if not evidence or any(not value for value in evidence_ids):
            errors.append(f"eval {eval_id} fixture needs non-empty evidence with IDs")
        if len(evidence_ids) != len(set(evidence_ids)):
            errors.append(f"eval {eval_id} fixture evidence IDs must be unique")
        expected_refs = set(rubric.get(str(eval_id), {}).get("required_evidence", []))
        missing = expected_refs - set(evidence_ids)
        if missing:
            errors.append(f"eval {eval_id} rubric references missing evidence: {sorted(missing)}")
        required_codes = set(rubric.get(str(eval_id), {}).get("required_codes", []))
        alias_codes = set(rubric.get(str(eval_id), {}).get("code_aliases", {}))
        if not alias_codes <= required_codes:
            errors.append(f"eval {eval_id} defines aliases for non-required codes: {sorted(alias_codes - required_codes)}")
        required_literals = rubric.get(str(eval_id), {}).get("required_literals", [])
        for group in required_literals:
            values = [group] if isinstance(group, str) else group
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
                errors.append(f"eval {eval_id} required_literals must be strings or non-empty string lists")

    return errors


def expectation(text: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {"text": text, "passed": passed, "evidence": evidence}


def grade_response(
    eval_id: int,
    response: dict[str, Any],
    fixture: dict[str, Any],
    rubric: dict[str, Any],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    def normalized(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")

    def code_matches(required: str, observed: Any) -> bool:
        if not isinstance(observed, str):
            return False
        accepted = [required, *code_aliases.get(required, [])]
        return any(observed == value or observed.startswith(f"{value}_") for value in accepted)

    def exact(field: str) -> None:
        wanted = rubric[field]
        observed = response.get(field)
        accepted = [wanted, *rubric.get(f"{field}_aliases", [])]
        matched = normalized(observed) in {normalized(value) for value in accepted}
        terms = rubric.get(f"{field}_terms", [])
        if terms:
            matched = matched or all(normalized(term) in normalized(observed) for term in terms)
        results.append(
            expectation(
                f"{field} is {wanted}",
                matched,
                f"observed {field}={observed!r}; accepted={accepted!r}",
            )
        )

    results.append(
        expectation(
            f"eval_id is {eval_id}",
            response.get("eval_id") == eval_id,
            f"observed eval_id={response.get('eval_id')!r}",
        )
    )
    for field in ("disposition", "gate", "editor_field_status", "publication_status"):
        exact(field)

    response_text = json.dumps(response, sort_keys=True).lower()
    required_literals = rubric.get("required_literals", [])
    if required_literals:
        missing_literals = []
        for group in required_literals:
            values = [group] if isinstance(group, str) else group
            if not any(value.lower() in response_text for value in values):
                missing_literals.append(values)
        results.append(
            expectation(
                "fixture-specific facts appear in the response",
                not missing_literals,
                "all required facts are present" if not missing_literals else f"missing={missing_literals}",
            )
        )

    findings = response.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    codes = {item.get("code") for item in findings if isinstance(item, dict)}
    required_codes = set(rubric.get("required_codes", []))
    code_aliases = rubric.get("code_aliases", {})
    matched_codes = {
        required
        for required in required_codes
        if any(code_matches(required, observed) for observed in codes)
    }
    results.append(
        expectation(
            "all required finding concepts are present",
            required_codes <= matched_codes,
            f"required={sorted(required_codes)} matched={sorted(matched_codes)} observed={sorted(value for value in codes if value)}",
        )
    )

    evidence_ids = {item["id"] for item in fixture.get("evidence", [])}
    cited: set[str] = set()
    invalid_refs: set[str] = set()
    malformed_findings: list[str] = []
    for item in findings:
        if not isinstance(item, dict):
            malformed_findings.append("non-object finding")
            continue
        refs = item.get("evidence_refs", [])
        if not refs or not item.get("required_action") or item.get("severity") not in {"blocker", "warning", "note"}:
            malformed_findings.append(str(item.get("code", "unknown")))
        for ref in refs:
            cited.add(ref)
            if ref not in evidence_ids:
                invalid_refs.add(ref)

    results.append(
        expectation(
            "all finding citations resolve to attached evidence IDs",
            not invalid_refs,
            "all references resolve" if not invalid_refs else f"unknown references={sorted(invalid_refs)}",
        )
    )
    results.append(
        expectation(
            "findings include severity, evidence, and a required action",
            not malformed_findings and bool(findings),
            "findings are substantive" if not malformed_findings and findings else f"malformed={malformed_findings}",
        )
    )

    actions = response.get("next_actions", [])
    mutating = [item for item in actions if isinstance(item, dict) and item.get("mutates_photos") is True]
    mutation_allowed = bool(rubric.get("photos_mutation_allowed", False))
    results.append(
        expectation(
            "Photos mutation respects the rubric",
            mutation_allowed or not mutating,
            "no Photos mutation proposed" if not mutating else f"mutating actions={mutating}",
        )
    )

    claims = response.get("claims", [])
    malformed_claims: list[str] = []
    for item in claims:
        if not isinstance(item, dict):
            malformed_claims.append("non-object claim")
            continue
        refs = item.get("evidence_refs", [])
        if item.get("status") in {"supported", "inference"} and not refs:
            malformed_claims.append(str(item.get("claim", "unnamed")))
        cited.update(refs)
        invalid_refs.update(ref for ref in refs if ref not in evidence_ids)
    required_evidence = set(rubric.get("required_evidence", []))
    results.append(
        expectation(
            "all required synthetic evidence is cited",
            required_evidence <= cited,
            f"required={sorted(required_evidence)} cited={sorted(cited)}",
        )
    )
    results.append(
        expectation(
            "supported claims cite only attached evidence",
            not malformed_claims and not invalid_refs,
            "claims are evidence-bound" if not malformed_claims and not invalid_refs else f"malformed={malformed_claims} unknown={sorted(invalid_refs)}",
        )
    )

    required_speakers = set(rubric.get("required_speakers", []))
    if required_speakers:
        roleplay = response.get("roleplay", [])
        observed_speakers = {item.get("speaker") for item in roleplay if isinstance(item, dict)}
        required_basis = rubric.get("required_roleplay_basis")
        missing_speakers = set()
        matching = []
        for required_speaker in required_speakers:
            aliases = {required_speaker, required_speaker.split()[0]}
            speaker_matches = [item for item in roleplay if isinstance(item, dict) and item.get("speaker") in aliases]
            if not speaker_matches:
                missing_speakers.add(required_speaker)
            matching.extend(speaker_matches)
        roleplay_pass = not missing_speakers and all(
            item.get("basis") == required_basis and item.get("thought") for item in matching
        )
        results.append(
            expectation(
                "requested role-play speakers are labeled as delegated inference",
                roleplay_pass,
                f"speakers={sorted(value for value in observed_speakers if value)} basis={required_basis}",
            )
        )

    if rubric["disposition"] == "BLOCKED":
        blocker_codes = {
            item.get("code") for item in findings if isinstance(item, dict) and item.get("severity") == "blocker"
        }
        matched_blockers = {
            required
            for required in required_codes
            if any(code_matches(required, observed) for observed in blocker_codes)
        }
        results.append(
            expectation(
                "a blocked disposition has a required blocker",
                bool(matched_blockers),
                f"blocker_codes={sorted(value for value in blocker_codes if value)}",
            )
        )

    passed = sum(item["passed"] for item in results)
    total = len(results)
    return {
        "expectations": results,
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": passed / total if total else 0.0,
        },
        "claims": [],
        "user_notes_summary": {"uncertainties": [], "needs_review": [], "workarounds": []},
        "eval_feedback": {
            "suggestions": [],
            "overall": "Structural checks require scoped disposition, semantic gate matching, evidence closure, and mutation boundaries.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evals", type=Path, default=ROOT / "evals.json")
    parser.add_argument("--rubric", type=Path, default=ROOT / "rubric.json")
    parser.add_argument("--check-suite", action="store_true")
    parser.add_argument("--eval-id", type=int)
    parser.add_argument("--response", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.check_suite:
        errors = check_suite(args.evals, args.rubric)
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        print("PASS: skill eval suite is internally consistent")
        return 0

    if args.eval_id is None or args.response is None:
        parser.error("--eval-id and --response are required when grading")

    evals = suite_index(args.evals)
    item = evals[args.eval_id]
    fixture = read_json(ROOT.parent / item["files"][0])
    rubric = read_json(args.rubric)["evals"][str(args.eval_id)]
    result = grade_response(args.eval_id, read_json(args.response), fixture, rubric)
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if result["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
