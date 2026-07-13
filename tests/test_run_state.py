import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.review import build_review_workbench
from photo_fieldwork.run_state import (
    append_config_decision,
    freeze_lock,
    initialize,
    record_transition,
    verify_lock,
)


class RunStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "v-test"
        initialize(self.workspace, "v-test", 2, "source://test", 10)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative: str, value: str) -> Path:
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def test_workspace_is_private_and_transition_hashes_artifacts(self):
        self.assertEqual(os.stat(self.workspace).st_mode & 0o777, 0o700)
        source = self.write("manifests/source.txt", "source")
        output = self.write("manifests/output.txt", "output")
        state = record_transition(
            self.workspace,
            "retrieval",
            "complete",
            {"source": source},
            {"candidate_pool": output},
            {"count": 2},
        )
        attempt = state["phases"]["retrieval"]["attempts"][0]
        self.assertEqual(len(attempt["inputs"]["source"]["sha256"]), 64)
        self.assertEqual(attempt["facts"]["count"], 2)

    def test_lock_detects_post_freeze_mutation(self):
        config = self.write("final/effective-final-config.json", "{}")
        master = self.write("final/proposed-master.csv", "uuid\nA\n")
        holds = self.write("final/hold-sensitive.csv", "uuid\nB\n")
        freeze_lock(self.workspace, config, master, holds)
        errors, report = verify_lock(self.workspace)
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        master.write_text("uuid\nC\n", encoding="utf-8")
        errors, report = verify_lock(self.workspace)
        self.assertTrue(errors)
        self.assertEqual(report["status"], "FAIL")

    def test_review_workbench_omits_people_and_has_no_external_requests(self):
        previews = self.workspace / "previews"
        output = self.workspace / "review" / "index.html"
        sample = [
            {
                "uuid": "A/L0/001",
                "primary_view": "01",
                "score_total": "10",
                "visible_context": "worktable",
                "persons": "Private Person",
                "place": "Exact home address",
            }
        ]
        build_review_workbench(sample, previews, output)
        document = output.read_text(encoding="utf-8")
        self.assertNotIn("Private Person", document)
        self.assertNotIn("Exact home address", document)
        self.assertNotIn("https://", document)
        self.assertIn("connect-src 'none'", document)

    def test_config_decisions_form_a_hash_chain(self):
        first = append_config_decision(
            self.workspace,
            "round-01",
            "views.07.status",
            "active",
            "unsupported",
            "No inspected image supported the project-specific claim.",
            "editor",
        )
        second = append_config_decision(
            self.workspace,
            "round-02",
            "views.07.quota",
            10,
            0,
            "Preserve the empty category without substitution.",
            "editor",
        )
        self.assertEqual(second["previous_hash"], first["record_hash"])
        self.assertNotEqual(second["record_hash"], first["record_hash"])


if __name__ == "__main__":
    unittest.main()
