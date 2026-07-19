import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "evals" / "evals.json"
REQUIRED_RISKS = {
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
}


class EvalBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = json.loads(BANK.read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
