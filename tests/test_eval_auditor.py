import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "evals" / "validate_evals.py"
SPEC = importlib.util.spec_from_file_location("validate_evals", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
PAYLOAD = json.loads((SCRIPT.parent / "evals.json").read_text(encoding="utf-8"))


class EvalAuditorTests(unittest.TestCase):
    def test_current_bank_passes_coverage_and_public_safety(self):
        self.assertEqual(validator.validate_bank(PAYLOAD), [])

    def test_missing_critical_dimension_and_refusal_only_bank_fail(self):
        mutated = copy.deepcopy(PAYLOAD)
        for case in mutated["evals"]:
            case["dimensions"] = [
                dimension for dimension in case["dimensions"] if dimension != "relational_safety"
            ]
            case["decision_oracle"] = "BLOCK"
        errors = validator.validate_bank(mutated)
        self.assertTrue(any("relational_safety" in error for error in errors))
        self.assertTrue(any("positive controls" in error for error in errors))

    def test_duplicate_identity_and_missing_anti_shortcuts_fail(self):
        mutated = copy.deepcopy(PAYLOAD)
        mutated["evals"][1]["id"] = mutated["evals"][0]["id"]
        mutated["evals"][1]["unsafe_shortcuts"] = []
        errors = validator.validate_bank(mutated)
        self.assertTrue(any("IDs must be unique" in error for error in errors))
        self.assertTrue(any("unsafe shortcuts" in error for error in errors))

    def test_private_fixture_path_fails(self):
        mutated = copy.deepcopy(PAYLOAD)
        mutated["evals"][0]["prompt"] += " Read /Users/example/private/photo.jpg."
        errors = validator.validate_bank(mutated)
        self.assertTrue(any("private or machine-specific" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
