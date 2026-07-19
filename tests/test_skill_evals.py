import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "skills" / "curate-apple-photos" / "evals"
SPEC = importlib.util.spec_from_file_location("validate_skill_evals", EVAL_ROOT / "validate_evals.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class SkillEvalBankTests(unittest.TestCase):
    def test_eval_bank_and_fixtures_validate(self):
        self.assertEqual(validator.validate(), [])

    def test_eval_bank_covers_the_release_chain(self):
        data = json.loads((EVAL_ROOT / "evals.json").read_text(encoding="utf-8"))
        prompts = " ".join(item["prompt"].lower() for item in data["evals"])
        for concept in ("source", "interrupted", "evaluation", "safety", "preview", "public", "master"):
            self.assertIn(concept, prompts)

    def test_fixtures_are_synthetic_and_contain_no_real_photo_identifiers(self):
        fixture_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((EVAL_ROOT / "files").iterdir())
            if path.is_file()
        )
        self.assertNotIn("/L0/001", fixture_text)
        self.assertNotIn("jamie@", fixture_text.lower())
        self.assertNotIn("jburkart", fixture_text.lower())


if __name__ == "__main__":
    unittest.main()
