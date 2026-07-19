import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = ROOT / "skills" / "curate-apple-photos" / "evals" / "evals.json"
SKILL_PATH = ROOT / "skills" / "curate-apple-photos" / "SKILL.md"


class SkillEvalBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = json.loads(EVAL_PATH.read_text(encoding="utf-8"))

    def test_eval_bank_has_stable_unique_contracts(self):
        self.assertEqual(self.bank["skill_name"], "curate-apple-photos")
        evals = self.bank["evals"]
        self.assertEqual([case["id"] for case in evals], list(range(1, 11)))
        self.assertEqual(len({case["prompt"] for case in evals}), len(evals))
        for case in evals:
            self.assertTrue(case["prompt"].strip())
            self.assertTrue(case["expected_output"].strip())
            for relative_path in case["files"]:
                self.assertTrue((ROOT / "skills" / "curate-apple-photos" / relative_path).is_file())
            self.assertGreaterEqual(len(case["expectations"]), 3)
            self.assertTrue(all(expectation.strip() for expectation in case["expectations"]))

    def test_eval_bank_covers_release_critical_failure_surfaces(self):
        corpus = json.dumps(self.bank).lower()
        required_concepts = (
            "source substitution",
            "fresh quality evidence",
            "unsupported project view",
            "automated clearance",
            "malformed shard",
            "assignment drift",
            "installed helper",
            "independent verification",
            "private run directory",
            "publication permission",
        )
        for concept in required_concepts:
            self.assertIn(concept, corpus)

    def test_skill_names_recursive_holdout_and_publication_boundaries(self):
        skill = SKILL_PATH.read_text(encoding="utf-8")
        for phrase in (
            "regression canaries",
            "final quality holdout",
            "audit_eval_split.py",
            "full-master audit",
            "cannot clear a protected safety state",
            "Editor-field membership is not publication permission",
            "allowlisted public handoff",
        ):
            self.assertIn(phrase, skill)


if __name__ == "__main__":
    unittest.main()
