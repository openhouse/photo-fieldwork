import json
import copy
import unittest
from pathlib import Path

from photo_fieldwork.evals import audit_eval_bank

ROOT = Path(__file__).resolve().parents[1]
EVALS_PATH = ROOT / "skills" / "curate-apple-photos" / "evals" / "evals.json"
CONTRACT_PATH = ROOT / "skills" / "curate-apple-photos" / "evals" / "eval-contract.json"


class SkillEvalTests(unittest.TestCase):
    def test_eval_bank_is_well_formed_and_covers_critical_failures(self):
        payload = json.loads(EVALS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["skill_name"], "curate-apple-photos")
        evals = payload["evals"]
        self.assertGreaterEqual(len(evals), 10)
        self.assertEqual(len({item["id"] for item in evals}), len(evals))
        for item in evals:
            self.assertIsInstance(item["id"], int)
            self.assertTrue(item["prompt"].strip())
            self.assertTrue(item["expected_output"].strip())
            self.assertEqual(item["files"], [])
            self.assertGreaterEqual(len(item["expectations"]), 4)
            self.assertTrue(all(expectation.strip() for expectation in item["expectations"]))

        corpus = json.dumps(payload).lower()
        for required in (
            "source-drift",
            "resumed",
            "final-holdout",
            "event_cluster_caps",
            "unsupported",
            "identified human",
            "cannot decode",
            "frozen master",
            "public handoff",
            "risk-stratified safety audit",
        ):
            self.assertIn(required, corpus)

    def test_eval_bank_contains_no_machine_specific_or_private_fixture_data(self):
        contents = EVALS_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "/Users/",
            "/Volumes/",
            "Photos.sqlite",
            "People/",
            "@ohai.us",
        ):
            self.assertNotIn(forbidden, contents)

    def test_skill_centralizes_release_dependencies_exposed_by_recursive_evals(self):
        skill = (
            ROOT / "skills" / "curate-apple-photos" / "SKILL.md"
        ).read_text(encoding="utf-8")
        for required in (
            "Catalog writing remains blocked until resumed inspection is complete",
            "Keep the release dependency strict",
            "Any selected UUID, assignment, quota, or HOLD change after final freeze",
            "verify the frozen master and `run-lock.json`",
            "inspect a fresh untouched final holdout",
        ):
            self.assertIn(required, skill)

    def test_eval_contract_requires_runnable_coverage_and_a_proceed_control(self):
        evals = json.loads(EVALS_PATH.read_text(encoding="utf-8"))
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        errors, report = audit_eval_bank(evals, contract)
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        self.assertGreaterEqual(report["proceed_control_count"], 1)

        missing_case = copy.deepcopy(evals)
        missing_case["evals"] = [
            item for item in missing_case["evals"] if item["id"] != 19
        ]
        errors, _ = audit_eval_bank(missing_case, contract)
        self.assertTrue(errors)

        orphaned_dimension = copy.deepcopy(contract)
        orphaned_dimension["critical_dimensions"].append(
            {"id": "orphaned-test-dimension", "eval_ids": [999]}
        )
        errors, _ = audit_eval_bank(evals, orphaned_dimension)
        self.assertTrue(any("no runnable eval" in error for error in errors))

        refusal_only = copy.deepcopy(contract)
        for item in refusal_only["cases"]:
            if item["decision_oracle"] == "PROCEED":
                item["decision_oracle"] = "BLOCK"
        errors, _ = audit_eval_bank(evals, refusal_only)
        self.assertTrue(any("PROCEED" in error for error in errors))

        incomplete = copy.deepcopy(evals)
        next(item for item in incomplete["evals"] if item["id"] == 15)[
            "expectations"
        ].pop()
        errors, report = audit_eval_bank(incomplete, contract)
        self.assertIn("evals are not runnable: [15]", errors)
        self.assertEqual(report["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
