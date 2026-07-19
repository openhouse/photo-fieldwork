import json
import copy
import unittest
from pathlib import Path

from photo_fieldwork.evals import audit_eval_bank


ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "evals" / "evals.json"
CONTRACT = ROOT / "evals" / "contract.json"
REQUIRED_RISKS = {
    "assignment-feasibility",
    "run-recovery",
    "evidence-freshness",
    "safety-consent",
    "claim-calibration",
    "source-integrity",
    "stratified-evaluation",
    "artifact-binding",
    "evidence-conflict",
    "catalog-verification",
    "relational-safety",
    "privacy-handoff",
    "epistemic-provenance",
    "holdout-independence",
    "idempotence-evidence",
    "positive-control",
    "publication-clearance",
    "release-seal",
}


class EvalBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = json.loads(BANK.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.evals = cls.bank["evals"]

    def test_bank_has_versioned_complete_risk_coverage(self):
        self.assertEqual(self.bank["schema_version"], 2)
        self.assertEqual(self.bank["skill_name"], "curate-apple-photos")
        self.assertEqual({case["risk"] for case in self.evals}, REQUIRED_RISKS)

    def test_cases_have_unique_stable_identity(self):
        identifiers = [case["id"] for case in self.evals]
        names = [case["name"] for case in self.evals]
        self.assertEqual(identifiers, list(range(1, len(self.evals) + 1)))
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(name == name.lower() and " " not in name for name in names))

    def test_every_case_is_evidence_gradeable_and_adversarial(self):
        for case in self.evals:
            with self.subTest(case=case["name"]):
                self.assertGreaterEqual(len(case["expectations"]), 4)
                self.assertGreaterEqual(len(case["evidence_required"]), 2)
                self.assertGreaterEqual(len(case["anti_patterns"]), 2)
                self.assertTrue(all(len(item) >= 24 for item in case["expectations"]))
                self.assertTrue(all(len(item) >= 24 for item in case["evidence_required"]))
                self.assertTrue(all(len(item) >= 24 for item in case["anti_patterns"]))
                self.assertNotIn("correctly", case["expected_output"].lower())
                self.assertEqual(case["files"], [])

    def test_synthetic_bank_never_requests_a_real_catalog_write(self):
        prompts = "\n".join(case["prompt"].lower() for case in self.evals)
        self.assertNotIn("/applications/jamie photo archive.app", prompts)
        self.assertNotIn("/volumes/apple-photos", prompts)
        self.assertNotIn("write these to my apple photos", prompts)

    def test_bank_passes_recursive_coverage_contract(self):
        report = audit_eval_bank(self.bank, self.contract)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["eval_count"], 18)
        self.assertEqual(report["contract_case_count"], 18)
        self.assertEqual(report["decision_oracles"]["PROCEED"], 1)

    def test_refusal_only_oracles_fail_positive_control(self):
        mutated = copy.deepcopy(self.contract)
        for case in mutated["cases"]:
            case["decision"] = "BLOCK"
        report = audit_eval_bank(self.bank, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("refusal-only" in error for error in report["errors"]))

    def test_removing_holdout_case_breaks_contract_closure(self):
        mutated = copy.deepcopy(self.bank)
        mutated["evals"] = [case for case in mutated["evals"] if case["id"] != 16]
        report = audit_eval_bank(mutated, self.contract)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("contract cases missing evals: 16" in error for error in report["errors"]))
        self.assertTrue(any("holdout-independence" in error for error in report["errors"]))

    def test_vague_counterfactual_fails_meta_evaluation(self):
        mutated = copy.deepcopy(self.contract)
        mutated["cases"][0]["counterfactual_pass_condition"] = "Be safe."
        report = audit_eval_bank(self.bank, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("counterfactual pass condition" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
