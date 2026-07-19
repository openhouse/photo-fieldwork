from __future__ import annotations

from collections import Counter


ALLOWED_DECISIONS = {"BLOCK", "REMEDIATE_THEN_PROCEED", "PROCEED", "PUBLICATION_BLOCKED"}
REQUIRED_EVAL_FIELDS = {"id", "prompt", "expected_output", "files", "expectations"}
VAGUE_EXPECTATIONS = {
    "be safe",
    "follow the skill",
    "produce a good answer",
    "use best practices",
}


def audit_eval_bank(eval_bank: dict, contract: dict) -> dict:
    """Test whether the eval bank can detect shortcuts instead of rewarding refusal alone."""
    errors: list[str] = []
    evals = eval_bank.get("evals", [])
    if eval_bank.get("skill_name") != "curate-apple-photos":
        errors.append("eval bank skill_name must be curate-apple-photos")
    if not evals:
        errors.append("eval bank must contain runnable cases")

    eval_ids: list[int] = []
    for case in evals:
        missing = REQUIRED_EVAL_FIELDS - set(case)
        if missing:
            errors.append(f"eval {case.get('id', '<unknown>')} missing fields: {', '.join(sorted(missing))}")
            continue
        eval_ids.append(case["id"])
        if len(str(case["prompt"]).split()) < 10:
            errors.append(f"eval {case['id']} prompt is not substantive")
        if len(str(case["expected_output"]).split()) < 8:
            errors.append(f"eval {case['id']} expected_output is not substantive")
        if not isinstance(case["files"], list):
            errors.append(f"eval {case['id']} files must be a list")
        expectations = case["expectations"]
        if not isinstance(expectations, list) or len(expectations) < 3:
            errors.append(f"eval {case['id']} requires at least three expectations")
        elif len(expectations) != len(set(expectations)):
            errors.append(f"eval {case['id']} repeats an expectation")
        for expectation in expectations:
            if str(expectation).strip().lower() in VAGUE_EXPECTATIONS or len(str(expectation).split()) < 6:
                errors.append(f"eval {case['id']} contains a vague expectation")

    duplicate_ids = sorted(value for value, count in Counter(eval_ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate eval IDs: {duplicate_ids}")
    if contract.get("schema_version") != 1:
        errors.append("eval contract schema_version must be 1")
    if contract.get("eval_file") != "skills/curate-apple-photos/evals/evals.json":
        errors.append("eval contract names the wrong eval file")

    dimensions = set(contract.get("dimensions", []))
    required_dimensions = set(contract.get("required_dimensions", []))
    minimum_coverage = int(contract.get("minimum_dimension_coverage", 1))
    cases = contract.get("cases", [])
    contract_ids: list[int] = []
    dimension_counts: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    for case in cases:
        eval_id = case.get("eval_id")
        contract_ids.append(eval_id)
        decision = case.get("decision")
        decisions[decision] += 1
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"contract case {eval_id} has invalid decision oracle {decision}")
        case_dimensions = set(case.get("dimensions", []))
        if not case_dimensions:
            errors.append(f"contract case {eval_id} has no dimensions")
        unknown = case_dimensions - dimensions
        if unknown:
            errors.append(f"contract case {eval_id} has unknown dimensions: {sorted(unknown)}")
        dimension_counts.update(case_dimensions)
        anti_shortcuts = case.get("anti_shortcuts", [])
        if not isinstance(anti_shortcuts, list) or len(anti_shortcuts) < 2:
            errors.append(f"contract case {eval_id} needs at least two anti-shortcuts")
        counterfactual = str(case.get("counterfactual_pass_condition", ""))
        if len(counterfactual.split()) < 8:
            errors.append(f"contract case {eval_id} needs a concrete counterfactual pass condition")

    if sorted(eval_ids) != sorted(contract_ids):
        errors.append("eval bank and contract must have a one-to-one case mapping")
    for dimension in sorted(required_dimensions):
        if dimension_counts[dimension] < minimum_coverage:
            errors.append(
                f"required dimension {dimension} has {dimension_counts[dimension]} cases; needs {minimum_coverage}"
            )
    if decisions["PROCEED"] < 1:
        errors.append("eval bank needs a positive PROCEED control")
    blocking_count = decisions["BLOCK"] + decisions["PUBLICATION_BLOCKED"]
    if blocking_count < 3:
        errors.append("eval bank needs at least three blocking decision oracles")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "eval_count": len(evals),
        "contract_case_count": len(cases),
        "decision_counts": dict(sorted(decisions.items())),
        "dimension_coverage": dict(sorted(dimension_counts.items())),
    }
