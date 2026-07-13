import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.artifacts import build_source_snapshot, validate_source_snapshot, verify_source_snapshot
from photo_fieldwork.run_ledger import derive_state, initialize_run, next_phase, record_phase


class ArtifactTests(unittest.TestCase):
    def test_source_snapshot_is_order_independent_and_detects_same_count_drift(self):
        first = build_source_snapshot(["B", "A", "A"], "visible://v1", captured_at="2026-01-01T00:00:00Z")
        second = build_source_snapshot(["A", "B"], "visible://v1", captured_at="2026-01-01T00:00:00Z")
        self.assertEqual(first, second)
        self.assertEqual(verify_source_snapshot(["B", "A"], first), [])
        errors = verify_source_snapshot(["A", "C"], first)
        self.assertEqual(len(errors), 1)
        self.assertIn("digest changed", errors[0])
        legacy = {**first, "membership_sha256": None, "legacy_count_only": True}
        self.assertEqual(verify_source_snapshot(["A", "B"], legacy), [])
        with self.assertRaisesRegex(ValueError, "missing fields"):
            validate_source_snapshot({"schema_version": 1})

    def test_run_state_is_derived_from_append_only_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            snapshot = build_source_snapshot(["A"], "visible://v1")
            initialize_run(workspace, "run-1", 10, snapshot, "v01")
            self.assertEqual(next_phase(derive_state(workspace)), "brief")
            first = record_phase(workspace, "brief", "in_progress", {"file": "brief.md"})
            second = record_phase(workspace, "brief", "completed", {"sha256": "example"})
            state = derive_state(workspace)
            self.assertEqual(state["phases"]["brief"], "completed")
            self.assertEqual(next_phase(state), "retrieval")
            self.assertEqual(state["event_count"], 3)
            self.assertNotEqual(first["event_id"], second["event_id"])
            self.assertEqual(len((workspace / "events.jsonl").read_text().splitlines()), 3)
            self.assertTrue((workspace / "run-state.json").exists())


if __name__ == "__main__":
    unittest.main()
