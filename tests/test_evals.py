import copy
import json
import unittest
from pathlib import Path

from photo_fieldwork.evals import audit_eval_bank


ROOT = Path(__file__).resolve().parents[1]


class EvalBankTests(unittest.TestCase):
    def setUp(self):
        self.bank = json.loads(
            (ROOT / "skills/curate-apple-photos/evals/evals.json").read_text(encoding="utf-8")
        )
        self.contract = json.loads(
            (ROOT / "skills/curate-apple-photos/evals/eval-contract.json").read_text(encoding="utf-8")
        )

    def test_composite_eval_contract_passes_its_own_audit(self):
        report = audit_eval_bank(self.bank, self.contract)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["eval_count"], 16)
        self.assertEqual(report["decision_counts"]["PROCEED"], 1)

    def test_missing_required_dimension_is_detected(self):
        contract = copy.deepcopy(self.contract)
        for case in contract["cases"]:
            case["dimensions"] = [value for value in case["dimensions"] if value != "sample-identity"]
        report = audit_eval_bank(self.bank, contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("sample-identity" in error for error in report["errors"]))

    def test_refusal_only_contract_fails_positive_control(self):
        contract = copy.deepcopy(self.contract)
        for case in contract["cases"]:
            if case["decision"] == "PROCEED":
                case["decision"] = "BLOCK"
        report = audit_eval_bank(self.bank, contract)
        self.assertTrue(any("positive PROCEED" in error for error in report["errors"]))

    def test_orphan_contract_case_and_vague_expectation_fail(self):
        contract = copy.deepcopy(self.contract)
        contract["cases"].append(copy.deepcopy(contract["cases"][0]))
        contract["cases"][-1]["eval_id"] = 99
        bank = copy.deepcopy(self.bank)
        bank["evals"][0]["expectations"][0] = "Be safe"
        report = audit_eval_bank(bank, contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("one-to-one" in error for error in report["errors"]))
        self.assertTrue(any("vague expectation" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
