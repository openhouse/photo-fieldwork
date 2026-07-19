import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.evals import audit_eval_bank


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "skills" / "curate-apple-photos" / "evals"
EVALS = EVAL_ROOT / "composite-evals.json"
CONTRACT = EVAL_ROOT / "eval-contract.json"
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "check_composite_evals.py"


class CompositeEvalBankTests(unittest.TestCase):
    def setUp(self):
        self.bank = json.loads(EVALS.read_text(encoding="utf-8"))
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def audit(self, bank=None, contract=None):
        return audit_eval_bank(bank or self.bank, contract or self.contract)

    def test_bank_passes_recursive_coverage_contract(self):
        report = self.audit()
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["eval_count"], 12)
        self.assertEqual(report["contract_case_count"], 12)
        self.assertEqual(report["decision_oracles"]["PROCEED"], 2)
        self.assertEqual(report["covered_dimensions"]["holdout-independence"], 1)

    def test_checker_resolves_the_contract_bound_bank(self):
        spec = importlib.util.spec_from_file_location("check_composite_evals", SCRIPT)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertEqual(checker.validate_composite_bank()["status"], "PASS")

    def test_orphaned_holdout_case_breaks_identity_and_coverage(self):
        mutated = copy.deepcopy(self.bank)
        mutated["evals"] = [case for case in mutated["evals"] if case["id"] != 2]
        report = self.audit(bank=mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("contract cases missing evals: 2" in error for error in report["errors"]))
        self.assertTrue(any("holdout-independence" in error for error in report["errors"]))

    def test_refusal_only_contract_fails_positive_control(self):
        mutated = copy.deepcopy(self.contract)
        for case in mutated["cases"]:
            case["decision"] = "BLOCK"
        report = self.audit(contract=mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("refusal-only" in error for error in report["errors"]))

    def test_permissive_only_contract_fails_blocking_control(self):
        mutated = copy.deepcopy(self.contract)
        for case in mutated["cases"]:
            case["decision"] = "PROCEED"
        report = self.audit(contract=mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("fail-closed" in error for error in report["errors"]))

    def test_vague_expectation_fails_meta_evaluation(self):
        mutated = copy.deepcopy(self.bank)
        mutated["evals"][0]["expectations"][0] = "Handle safely."
        report = self.audit(bank=mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("vague expectation" in error for error in report["errors"]))

    def test_missing_counterfactual_fails_meta_evaluation(self):
        mutated = copy.deepcopy(self.contract)
        mutated["cases"][0]["counterfactual_pass_condition"] = ""
        report = self.audit(contract=mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("counterfactual pass condition" in error for error in report["errors"]))

    def test_contract_cannot_escape_eval_directory(self):
        mutated = copy.deepcopy(self.contract)
        mutated["eval_file"] = "../../README.md"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contract.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            spec = importlib.util.spec_from_file_location("check_composite_evals_escape", SCRIPT)
            checker = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(checker)
            with self.assertRaisesRegex(ValueError, "local eval file"):
                checker.validate_composite_bank(path)


if __name__ == "__main__":
    unittest.main()
