import importlib.util
import json
import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory = load_script(
    "build_visible_library_inventory",
    "skills/curate-apple-photos/scripts/build_visible_library_inventory.py",
)
public_lint = load_script(
    "lint_public_report",
    "skills/curate-apple-photos/scripts/lint_public_report.py",
)
verifier = load_script(
    "verify_photos_commit",
    "skills/curate-apple-photos/scripts/verify_photos_commit.py",
)


class EvalContractTests(unittest.TestCase):
    def test_eval_bank_covers_release_critical_risks(self):
        path = ROOT / "skills" / "curate-apple-photos" / "evals" / "evals.json"
        bank = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(bank["skill_name"], "curate-apple-photos")
        self.assertGreaterEqual(len(bank["evals"]), 12)
        self.assertEqual(len({case["id"] for case in bank["evals"]}), len(bank["evals"]))
        tags = {tag for case in bank["evals"] for tag in case.get("tags", [])}
        required = {
            "source-integrity",
            "safety",
            "fresh-evidence",
            "preview-integrity",
            "evaluation-binding",
            "public-boundary",
            "independent-verification",
        }
        self.assertTrue(required <= tags)
        for case in bank["evals"]:
            self.assertGreaterEqual(len(case["expectations"]), 4)
            self.assertTrue(all(expectation.endswith(".") for expectation in case["expectations"]))

    def test_membership_fingerprint_detects_same_count_substitution(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE asset (uuid TEXT PRIMARY KEY)")
        connection.executemany("INSERT INTO asset(uuid) VALUES (?)", [("B",), ("A",)])
        first = inventory.membership_sha256(connection)
        self.assertEqual(first, verifier.membership_sha256({"A", "B"}))
        connection.execute("DELETE FROM asset WHERE uuid = 'B'")
        connection.execute("INSERT INTO asset(uuid) VALUES ('C')")
        second = inventory.membership_sha256(connection)
        self.assertNotEqual(first, second)
        self.assertEqual(connection.execute("SELECT count(*) FROM asset").fetchone()[0], 2)
        connection.close()

    def test_public_report_linter_blocks_operational_leakage(self):
        text = "\n".join(
            [
                "path: /Users/editor/private/run.json",
                "asset: 360ED78F-FB05-490A-8FFD-F3CB951D0D0A/L0/001",
                "raw_ocr: private correspondence",
                "latitude: 40.7",
                "api_key: do-not-publish",
            ]
        )
        findings = public_lint.lint(text)
        self.assertEqual(
            {finding["rule"] for finding in findings},
            {
                "absolute local path",
                "Photos local identifier",
                "raw OCR field",
                "exact coordinate field",
                "credential material",
            },
        )
        self.assertEqual(public_lint.lint("Editor-ready field; publication clearance remains pending."), [])


if __name__ == "__main__":
    unittest.main()
