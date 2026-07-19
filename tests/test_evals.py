import copy
import json
import unittest
from pathlib import Path

from photo_fieldwork.evals import audit_eval_bank


ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "skills" / "curate-apple-photos" / "evals" / "evals.json"
CONTRACT = ROOT / "skills" / "curate-apple-photos" / "evals" / "eval-contract.json"


class EvalBankTests(unittest.TestCase):
    def setUp(self):
        self.eval_bank = json.loads(EVALS.read_text(encoding="utf-8"))
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_eval_bank_passes_its_recursive_coverage_contract(self):
        report = audit_eval_bank(self.eval_bank, self.contract)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["eval_count"], 12)
        self.assertEqual(report["contract_case_count"], 12)
        self.assertEqual(report["decision_oracles"]["PROCEED"], 1)

    def test_removing_source_drift_case_breaks_critical_coverage(self):
        mutated = copy.deepcopy(self.eval_bank)
        mutated["evals"] = [case for case in mutated["evals"] if case["id"] != 1]
        report = audit_eval_bank(mutated, self.contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("contract cases missing evals: 1" in error for error in report["errors"]))
        self.assertTrue(any("source-membership-identity" in error for error in report["errors"]))

    def test_refusal_only_oracles_fail_the_positive_control(self):
        mutated = copy.deepcopy(self.contract)
        for case in mutated["cases"]:
            case["decision"] = "BLOCK"
        report = audit_eval_bank(self.eval_bank, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("refusal-only" in error for error in report["errors"]))

    def test_removing_local_privacy_case_breaks_required_coverage(self):
        mutated = copy.deepcopy(self.eval_bank)
        mutated["evals"] = [case for case in mutated["evals"] if case["id"] != 11]
        report = audit_eval_bank(mutated, self.contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("local-only-data-boundary" in error for error in report["errors"]))
        self.assertTrue(any("identity-inference-boundary" in error for error in report["errors"]))

    def test_vague_expectation_fails_meta_evaluation(self):
        mutated = copy.deepcopy(self.eval_bank)
        mutated["evals"][0]["expectations"][0] = "Handle safely."
        report = audit_eval_bank(mutated, self.contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("vague expectation" in error for error in report["errors"]))

    def test_missing_counterfactual_fails_meta_evaluation(self):
        mutated = copy.deepcopy(self.contract)
        mutated["cases"][0]["counterfactual_pass_condition"] = ""
        report = audit_eval_bank(self.eval_bank, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("counterfactual pass condition" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
