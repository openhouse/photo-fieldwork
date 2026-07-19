import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EvalCorpusTests(unittest.TestCase):
    def test_skill_eval_corpus_has_unique_actionable_assertions(self):
        data = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(data["skill_name"], "curate-apple-photos")
        identifiers = [item["id"] for item in data["evals"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertGreaterEqual(len(identifiers), 8)
        for item in data["evals"]:
            self.assertTrue(item["prompt"])
            self.assertTrue(item["expected_output"])
            self.assertGreaterEqual(len(item["assertions"]), 3)

    def test_system_eval_registry_is_recursive_and_complete(self):
        data = json.loads((ROOT / "evals" / "system-evals.json").read_text(encoding="utf-8"))
        identifiers = [item["id"] for item in data["cases"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertGreaterEqual(data["default_max_depth"], 3)
        self.assertGreaterEqual(len(identifiers), 10)
        self.assertTrue(all(item["mutations"] for item in data["cases"]))

    def test_system_eval_report_is_reproducible(self):
        spec = importlib.util.spec_from_file_location("test_run_evals", ROOT / "scripts" / "run_evals.py")
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        suite = json.loads((ROOT / "evals" / "system-evals.json").read_text(encoding="utf-8"))
        first = module.run_suite(suite, suite["default_max_depth"])
        second = module.run_suite(suite, suite["default_max_depth"])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
