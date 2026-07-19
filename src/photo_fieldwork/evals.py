from __future__ import annotations

from collections import Counter
from typing import Any


ALLOWED_DECISIONS = {"BLOCK", "REMEDIATE_THEN_PROCEED", "PROCEED", "PUBLICATION_BLOCKED"}
REQUIRED_EVAL_FIELDS = {
    "id",
    "name",
    "risk",
    "prompt",
    "expected_output",
    "files",
    "evidence_required",
    "expectations",
    "anti_patterns",
}
VAGUE_EXPECTATIONS = {
    "be accurate",
    "be careful",
    "do the right thing",
    "follow best practices",
    "handle safely",
}


def _substantive(value: object, minimum_words: int) -> bool:
    return isinstance(value, str) and len(value.split()) >= minimum_words


def audit_eval_bank(eval_bank: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Audit whether the behavioral bank discriminates governed failure modes."""
    errors: list[str] = []
    evals = eval_bank.get("evals")
    if eval_bank.get("skill_name") != "curate-apple-photos":
        errors.append("eval bank skill_name must be curate-apple-photos")
    if not isinstance(evals, list) or not evals:
        errors.append("eval bank must contain a non-empty evals list")
        evals = []

    ids: list[int] = []
    for position, case in enumerate(evals, 1):
        if not isinstance(case, dict):
            errors.append(f"eval at position {position} must be an object")
            continue
        missing = REQUIRED_EVAL_FIELDS - case.keys()
        if missing:
            errors.append(f"eval {case.get('id', position)} missing fields: {', '.join(sorted(missing))}")
        eval_id = case.get("id")
        if not isinstance(eval_id, int):
            errors.append(f"eval at position {position} must have an integer id")
            continue
        ids.append(eval_id)
        if not _substantive(case.get("prompt"), 20):
            errors.append(f"eval {eval_id} prompt is not a substantive field scenario")
        if not _substantive(case.get("expected_output"), 12):
            errors.append(f"eval {eval_id} expected_output is too vague")
        files = case.get("files")
        if not isinstance(files, list) or any(not isinstance(path, str) for path in files):
            errors.append(f"eval {eval_id} files must be a list of paths")
        for field, minimum in (("expectations", 4), ("evidence_required", 2), ("anti_patterns", 2)):
            values = case.get(field)
            if not isinstance(values, list) or len(values) < minimum:
                errors.append(f"eval {eval_id} needs at least {minimum} {field.replace('_', ' ')}")
                continue
            normalized = [str(item).strip().casefold().rstrip(".") for item in values]
            if len(normalized) != len(set(normalized)):
                errors.append(f"eval {eval_id} contains duplicate {field.replace('_', ' ')}")
            for value in values:
                normalized_value = str(value).strip().casefold().rstrip(".")
                if not _substantive(value, 4) or normalized_value in VAGUE_EXPECTATIONS:
                    errors.append(f"eval {eval_id} contains vague {field.replace('_', ' ')}: {value}")

    if len(ids) != len(set(ids)):
        errors.append("eval IDs must be unique")
    if ids != list(range(1, len(ids) + 1)):
        errors.append("eval IDs must be contiguous and ordered from 1")

    if int(contract.get("schema_version", 0)) != 1:
        errors.append("eval contract schema_version must be 1")
    if contract.get("eval_file") != "evals.json":
        errors.append("eval contract must bind evals.json")
    required_dimensions = set(contract.get("required_dimensions") or [])
    if not required_dimensions:
        errors.append("eval contract must declare required dimensions")
    cases = contract.get("cases")
    if not isinstance(cases, list):
        errors.append("eval contract cases must be a list")
        cases = []

    contract_ids: list[int] = []
    eval_id_set = set(ids)
    dimension_counts: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    for position, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            errors.append(f"contract case at position {position} must be an object")
            continue
        eval_id = case.get("eval_id")
        if not isinstance(eval_id, int):
            errors.append(f"contract case at position {position} must have an integer eval_id")
            continue
        contract_ids.append(eval_id)
        decision = str(case.get("decision") or "")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"eval {eval_id} has unsupported decision oracle: {decision}")
        elif eval_id in eval_id_set:
            decisions[decision] += 1
        dimensions = case.get("dimensions")
        if not isinstance(dimensions, list) or not dimensions:
            errors.append(f"eval {eval_id} must cover at least one dimension")
            dimensions = []
        unknown = set(dimensions) - required_dimensions
        if unknown:
            errors.append(f"eval {eval_id} uses undeclared dimensions: {', '.join(sorted(unknown))}")
        if eval_id in eval_id_set:
            dimension_counts.update(str(value) for value in dimensions)
        shortcuts = case.get("anti_shortcuts")
        if not isinstance(shortcuts, list) or len(shortcuts) < 2:
            errors.append(f"eval {eval_id} needs at least two anti-shortcuts")
        elif any(not _substantive(value, 6) for value in shortcuts):
            errors.append(f"eval {eval_id} contains a vague anti-shortcut")
        if not _substantive(case.get("counterfactual_pass_condition"), 10):
            errors.append(f"eval {eval_id} needs a concrete counterfactual pass condition")

    if len(contract_ids) != len(set(contract_ids)):
        errors.append("contract eval IDs must be unique")
    if set(ids) != set(contract_ids):
        missing_contract = set(ids) - set(contract_ids)
        missing_eval = set(contract_ids) - set(ids)
        if missing_contract:
            errors.append(f"evals missing contract cases: {', '.join(map(str, sorted(missing_contract)))}")
        if missing_eval:
            errors.append(f"contract cases missing evals: {', '.join(map(str, sorted(missing_eval)))}")
    for dimension in sorted(required_dimensions):
        if dimension_counts[dimension] == 0:
            errors.append(f"required dimension has no eval coverage: {dimension}")
    for dimension, minimum in sorted((contract.get("minimum_cases_by_dimension") or {}).items()):
        if dimension not in required_dimensions:
            errors.append(f"minimum references undeclared dimension: {dimension}")
        elif dimension_counts[dimension] < int(minimum):
            errors.append(f"dimension {dimension} has {dimension_counts[dimension]} cases; requires {int(minimum)}")
    if decisions["PROCEED"] < 1:
        errors.append("eval bank needs a positive-control PROCEED case to detect refusal-only behavior")
    if decisions["BLOCK"] + decisions["PUBLICATION_BLOCKED"] < 5:
        errors.append("eval bank needs at least five blocking cases to test fail-closed behavior")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "eval_count": len(evals),
        "contract_case_count": len(cases),
        "covered_dimensions": dict(sorted(dimension_counts.items())),
        "decision_oracles": dict(sorted(decisions.items())),
    }
