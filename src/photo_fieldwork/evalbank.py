from __future__ import annotations

from collections import Counter


REQUIRED_DIMENSIONS = {
    "artifact-integrity",
    "assignment",
    "catalog-write",
    "evaluation",
    "holdout",
    "human-review",
    "privacy",
    "publication",
    "safety",
    "source-integrity",
    "verification",
}
DECISIONS = {"BLOCK", "PROCEED"}
SEVERITIES = {"critical", "high", "medium"}


def validate_eval_bank(bank: dict) -> dict:
    """Audit whether the prompt bank can distinguish safe action from fluent caution."""
    errors: list[str] = []
    if bank.get("schema_version") != 2:
        errors.append("eval bank schema_version must be 2")
    cases = bank.get("evals")
    if not isinstance(cases, list) or not cases:
        return {"status": "FAIL", "errors": [*errors, "eval bank must contain cases"]}

    ids = [str(case.get("id", "")).strip() for case in cases]
    if any(not identifier for identifier in ids):
        errors.append("every eval requires an id")
    if len(ids) != len(set(ids)):
        errors.append("eval ids must be unique")

    decisions = Counter()
    dimensions: set[str] = set()
    for case in cases:
        identifier = str(case.get("id", "<missing>"))
        severity = case.get("severity")
        decision = case.get("expected_decision")
        tags = case.get("tags")
        assertions = case.get("assertions")
        if severity not in SEVERITIES:
            errors.append(f"{identifier}: invalid severity")
        if decision not in DECISIONS:
            errors.append(f"{identifier}: expected_decision must be BLOCK or PROCEED")
        else:
            decisions[decision] += 1
        if not isinstance(tags, list) or not tags:
            errors.append(f"{identifier}: tags are required")
        else:
            dimensions.update(str(tag) for tag in tags)
        if (
            not isinstance(assertions, list)
            or len(assertions) < 4
            or any(not str(assertion).strip() for assertion in assertions)
        ):
            errors.append(f"{identifier}: at least four assertions are required")
        unsafe_shortcuts = case.get("unsafe_shortcuts")
        if (
            not isinstance(unsafe_shortcuts, list)
            or not unsafe_shortcuts
            or any(not str(shortcut).strip() for shortcut in unsafe_shortcuts)
        ):
            errors.append(f"{identifier}: unsafe_shortcuts are required")
        if not str(case.get("counterfactual", "")).strip():
            errors.append(f"{identifier}: a counterfactual pass condition is required")

    missing_dimensions = sorted(REQUIRED_DIMENSIONS - dimensions)
    if missing_dimensions:
        errors.append(f"missing critical dimensions: {', '.join(missing_dimensions)}")
    if not decisions["PROCEED"]:
        errors.append("eval bank requires a positive PROCEED control")
    if not decisions["BLOCK"]:
        errors.append("eval bank requires at least one BLOCK case")
    return {
        "status": "PASS" if not errors else "FAIL",
        "case_count": len(cases),
        "decision_counts": dict(sorted(decisions.items())),
        "covered_dimensions": sorted(dimensions),
        "errors": errors,
    }
