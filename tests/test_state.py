import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.state import initialize_run, recover_state, transition_phase


class RunStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run = Path(self.temp.name) / "run"
        self.state = initialize_run(self.run, "test-run", ["retrieve", "verify"], {"target": 2})

    def tearDown(self):
        self.temp.cleanup()

    def test_completed_transition_requires_artifact_and_records_checksum(self):
        with self.assertRaisesRegex(ValueError, "existing artifact"):
            transition_phase(self.run, "retrieve", "completed", expected_revision=1)
        artifact = self.run / "candidate.csv"
        artifact.write_text("uuid\nA\n", encoding="utf-8")
        state = transition_phase(
            self.run,
            "retrieve",
            "completed",
            expected_revision=1,
            artifact=artifact,
        )
        self.assertEqual(state["revision"], 2)
        self.assertTrue(state["artifacts"]["retrieve"]["sha256"].startswith("sha256:"))

    def test_revision_conflict_fails_without_overwrite(self):
        transition_phase(self.run, "retrieve", "started", expected_revision=1)
        with self.assertRaisesRegex(ValueError, "revision conflict"):
            transition_phase(self.run, "verify", "started", expected_revision=1)
        self.assertEqual(recover_state(self.run)["revision"], 2)

    def test_status_recovers_corrupt_materialized_state_from_ledger(self):
        transition_phase(self.run, "retrieve", "started", expected_revision=1)
        (self.run / "run-state.json").write_text("", encoding="utf-8")
        recovered = recover_state(self.run)
        self.assertEqual(recovered["revision"], 2)
        self.assertEqual(recovered["phases"]["retrieve"], "started")
        on_disk = json.loads((self.run / "run-state.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, recovered)


if __name__ == "__main__":
    unittest.main()
