import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "check_evals.py"
SPEC = importlib.util.spec_from_file_location("check_evals", SCRIPT)
check_evals = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_evals)


class EvalBankTests(unittest.TestCase):
    def test_public_eval_bank_meets_coverage_contract(self):
        summary = check_evals.validate_eval_bank()
        self.assertGreaterEqual(summary["evals"], 30)
        self.assertGreaterEqual(summary["critical"], 27)
        self.assertGreaterEqual(summary["expectations"], 122)
        self.assertEqual(summary["fixture_canaries"], 11)

    def test_fixture_oracles_are_recomputable(self):
        errors = []
        self.assertEqual(check_evals.validate_fixture_oracles(errors), 11)
        self.assertEqual(errors, [])

    def test_critical_eval_without_refusal_condition_fails(self):
        source = json.loads(check_evals.EVAL_PATH.read_text(encoding="utf-8"))
        source["evals"][0]["expectations"] = [
            "Reports a result with a detailed artifact summary." for _ in range(4)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evals.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fail-closed expectation"):
                check_evals.validate_eval_bank(path)

    def test_eval_without_artifact_or_action_oracle_fails(self):
        source = json.loads(check_evals.EVAL_PATH.read_text(encoding="utf-8"))
        source["evals"][0].pop("oracle_contract")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evals.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lacks an oracle_contract"):
                check_evals.validate_eval_bank(path)

    def test_executable_checks_are_resolvable(self):
        checks = check_evals.executable_checks()
        self.assertIn("make demo", checks)
        self.assertGreaterEqual(len(checks), 43)
        for check in checks:
            if check == "make demo":
                continue
            suite = unittest.defaultTestLoader.loadTestsFromName(check)
            self.assertGreater(suite.countTestCases(), 0, check)
            self.assertFalse(
                any(isinstance(test, unittest.loader._FailedTest) for test in suite),
                check,
            )


if __name__ == "__main__":
    unittest.main()
