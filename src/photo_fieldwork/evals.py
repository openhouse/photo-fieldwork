from __future__ import annotations

import json
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_eval_bank(evals: dict, contract: dict) -> tuple[list[str], dict]:
    errors = []
    cases = evals.get("evals", [])
    eval_ids = [int(item.get("id", -1)) for item in cases]
    runnable_ids = {
        int(item["id"])
        for item in cases
        if str(item.get("prompt", "")).strip()
        and str(item.get("expected_output", "")).strip()
        and len(item.get("expectations", [])) >= 4
    }
    if len(eval_ids) != len(set(eval_ids)):
        errors.append("eval IDs must be unique")
    incomplete_ids = sorted(set(eval_ids) - runnable_ids)
    if incomplete_ids:
        errors.append(f"evals are not runnable: {incomplete_ids}")

    contract_cases = contract.get("cases", [])
    contract_ids = [int(item.get("eval_id", -1)) for item in contract_cases]
    if set(contract_ids) != set(eval_ids):
        missing = sorted(set(eval_ids) - set(contract_ids))
        orphaned = sorted(set(contract_ids) - set(eval_ids))
        if missing:
            errors.append(f"evals missing decision contracts: {missing}")
        if orphaned:
            errors.append(f"decision contracts without runnable evals: {orphaned}")
    if len(contract_ids) != len(set(contract_ids)):
        errors.append("decision contracts must be unique")

    allowed = set(contract.get("allowed_decisions", []))
    for item in contract_cases:
        if item.get("decision_oracle") not in allowed:
            errors.append(f"eval {item.get('eval_id')} has an invalid decision oracle")
        if not str(item.get("unsafe_shortcut", "")).strip():
            errors.append(f"eval {item.get('eval_id')} lacks an unsafe shortcut")
    proceed_ids = {
        int(item["eval_id"])
        for item in contract_cases
        if item.get("decision_oracle") == "PROCEED"
    }
    if not proceed_ids & runnable_ids:
        errors.append("eval bank requires at least one runnable PROCEED control")

    covered = set()
    for dimension in contract.get("critical_dimensions", []):
        dimension_ids = {int(value) for value in dimension.get("eval_ids", [])}
        live = dimension_ids & runnable_ids
        if not live:
            errors.append(
                f"critical dimension {dimension.get('id')} has no runnable eval"
            )
        covered.update(live)
    unclassified = sorted(runnable_ids - covered)
    if unclassified:
        errors.append(f"runnable evals lack critical-dimension coverage: {unclassified}")

    return errors, {
        "status": "PASS" if not errors else "FAIL",
        "eval_count": len(cases),
        "runnable_eval_count": len(runnable_ids),
        "decision_contract_count": len(contract_cases),
        "critical_dimension_count": len(contract.get("critical_dimensions", [])),
        "proceed_control_count": len(proceed_ids & runnable_ids),
        "errors": errors,
    }


def audit_paths(evals_path: Path, contract_path: Path) -> tuple[list[str], dict]:
    return audit_eval_bank(read_json(evals_path), read_json(contract_path))
