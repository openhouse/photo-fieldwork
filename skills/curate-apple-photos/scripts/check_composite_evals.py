#!/usr/bin/env python3
"""Validate the composite behavioral bank and its mutation-resistant contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_ROOT = REPO_ROOT / "skills" / "curate-apple-photos" / "evals"
CONTRACT_PATH = EVAL_ROOT / "eval-contract.json"
sys.path.insert(0, str(REPO_ROOT / "src"))

from photo_fieldwork.evals import audit_eval_bank  # noqa: E402


def validate_composite_bank(contract_path: Path = CONTRACT_PATH) -> dict:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    eval_file = contract.get("eval_file", "")
    eval_path = EVAL_ROOT / eval_file
    if not eval_file or eval_path.parent != EVAL_ROOT or not eval_path.is_file():
        raise ValueError("composite eval contract does not bind a local eval file")
    bank = json.loads(eval_path.read_text(encoding="utf-8"))
    report = audit_eval_bank(bank, contract)
    if report["status"] != "PASS":
        raise ValueError("\n".join(report["errors"]))
    return report


def main() -> None:
    report = validate_composite_bank()
    print(
        "composite-eval-bank PASS "
        f"evals={report['eval_count']} dimensions={len(report['covered_dimensions'])} "
        f"decisions={json.dumps(report['decision_oracles'], sort_keys=True)}"
    )


if __name__ == "__main__":
    main()
