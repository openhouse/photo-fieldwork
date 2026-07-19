import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "curate-apple-photos"
EVALS = SKILL / "evals" / "evals.json"


class SkillEvalBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = json.loads(EVALS.read_text(encoding="utf-8"))

    def test_eval_bank_has_stable_unique_cases(self):
        self.assertEqual(self.bank["skill_name"], "curate-apple-photos")
        evals = self.bank["evals"]
        self.assertGreaterEqual(len(evals), 8)
        self.assertLessEqual(len(evals), 12)
        self.assertEqual(len({case["id"] for case in evals}), len(evals))
        self.assertEqual(len({case["name"] for case in evals}), len(evals))
        for case in evals:
            self.assertIsInstance(case["id"], int)
            self.assertTrue(case["prompt"].strip())
            self.assertTrue(case["expected_output"].strip())
            self.assertGreaterEqual(len(case["expectations"]), 4)
            self.assertEqual(len(case["tags"]), len(set(case["tags"])))

    def test_eval_files_are_repo_local_and_present(self):
        for case in self.bank["evals"]:
            for relative in case["files"]:
                path = Path(relative)
                self.assertFalse(path.is_absolute())
                self.assertNotIn("..", path.parts)
                fixture = SKILL / path
                self.assertTrue(fixture.is_file(), f"missing eval fixture: {relative}")
                self.assertIn(fixture.suffix, {".csv", ".json", ".py"})
                if fixture.suffix == ".json":
                    json.loads(fixture.read_text(encoding="utf-8"))

    def test_eval_bank_covers_release_boundaries(self):
        tags = {tag for case in self.bank["evals"] for tag in case["tags"]}
        required = {
            "source-integrity",
            "safety",
            "evaluation",
            "verification",
            "resumability",
            "publication",
            "privacy",
            "human-gate",
        }
        self.assertEqual(required - tags, set())
        self.assertIn("positive-path", tags)

    def test_fixtures_are_synthetic_and_public_safe(self):
        fixtures = (SKILL / "evals" / "files").glob("*")
        forbidden = ("/Users/", "/Volumes/", "Library/Photos", "@gmail.com")
        for path in fixtures:
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden:
                self.assertNotIn(fragment, text, f"private locator in {path.name}")

    def test_positive_path_fake_adapter_proves_order_and_idempotence(self):
        scenario = SKILL / "evals" / "files" / "safe-happy-path.json"
        adapter = SKILL / "evals" / "files" / "fake_catalog_adapter.py"
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for operation in (
                "ten-item-test",
                "production",
                "production-idempotence-rerun",
                "verify",
            ):
                subprocess.run(
                    [
                        sys.executable,
                        str(adapter),
                        "--scenario",
                        str(scenario),
                        "--workspace",
                        str(workspace),
                        "--operation",
                        operation,
                    ],
                    check=True,
                )
            trace = json.loads((workspace / "invocation-trace.json").read_text())
            self.assertEqual([item["operation"] for item in trace], [
                "ten-item-test",
                "production",
                "production-idempotence-rerun",
                "verify",
            ])
            self.assertFalse(trace[2]["changed"])
            verification = json.loads((workspace / "verification.json").read_text())
            self.assertEqual(verification["status"], "PASS")

    def test_hash_fixtures_are_computable_and_discriminating(self):
        files = SKILL / "evals" / "files"
        happy = json.loads((files / "safe-happy-path.json").read_text())
        membership = "".join(f"{uuid}\n" for uuid in happy["source"]["observed_members"])
        self.assertEqual(
            hashlib.sha256(membership.encode()).hexdigest(),
            happy["source"]["frozen_membership_sha256"],
        )

        verification = json.loads((files / "verification-scenario.json").read_text())
        approved = verification["approved_plan"]
        for file_key, hash_key in (
            ("master_file", "master_sha256"),
            ("holds_file", "holds_sha256"),
            ("config_file", "config_sha256"),
        ):
            payload = (files / approved[file_key]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), approved[hash_key])
        current = (files / verification["current_master_file"]).read_bytes()
        self.assertNotEqual(hashlib.sha256(current).hexdigest(), approved["master_sha256"])

        resume = json.loads((files / "resume-scenario.json").read_text())
        for phase in ("brief", "retrieval"):
            artifact = resume["phases"][phase]
            payload = (files / artifact["artifact"]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), artifact["recorded_sha256"])
        inspected = {
            uuid
            for attempt in resume["phases"]["local_inspection"]["attempts"]
            for uuid in attempt["completed_ids"]
        }
        self.assertEqual(inspected, set("ABCDEFGH"))

        holdout = json.loads((files / "holdout-scenario.json").read_text())
        current_sample = "".join(f"{uuid}\n" for uuid in holdout["final_sample_ids"])
        self.assertEqual(holdout["sample_hash_serialization"], "utf8-lines-final-lf")
        self.assertNotEqual(
            hashlib.sha256(current_sample.encode()).hexdigest(),
            holdout["recorded_sample_sha256"],
        )

        source_rows = (files / verification["snapshot_receipt"]["source_membership_file"]).read_text().splitlines()[1:]
        source_payload = (files / verification["snapshot_receipt"]["source_membership_file"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(source_payload).hexdigest(),
            verification["snapshot_receipt"]["source_membership_sha256"],
        )
        prior_payload = (files / verification["protected_digests"]["prior_versions_file"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(prior_payload).hexdigest(),
            verification["protected_digests"]["prior_versions_before"],
        )
        current_rows = (files / verification["current_master_file"]).read_text().splitlines()[1:]
        approved_rows = (files / approved["master_file"]).read_text().splitlines()[1:]
        self.assertEqual(set(approved_rows) - set(current_rows), {"D"})
        self.assertEqual(set(current_rows) - set(approved_rows), {"X"})
        self.assertEqual(set(current_rows) - set(source_rows), {"X"})


if __name__ == "__main__":
    unittest.main()
