import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALS_PATH = ROOT / "skills" / "curate-apple-photos" / "evals" / "evals.json"


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


if __name__ == "__main__":
    unittest.main()
