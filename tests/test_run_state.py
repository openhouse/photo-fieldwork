import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "run_state.py"
SPEC = importlib.util.spec_from_file_location("run_state", SCRIPT)
run_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_state)


class RunStateTests(unittest.TestCase):
    def initialize(self, workspace):
        return run_state.initialize_run(
            workspace,
            run_id="test-run",
            phases=["brief", "retrieval"],
            metadata={"target_count": 8_000},
        )

    def test_state_is_private_append_only_and_artifact_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            state = self.initialize(workspace)
            self.assertEqual(state["revision"], 0)
            self.assertEqual(os.stat(workspace).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(workspace / "run-events.jsonl").st_mode & 0o777, 0o600)
            artifact = workspace / "brief.md"
            artifact.write_text("brief\n", encoding="utf-8")
            state = run_state.advance_phase(
                workspace,
                phase="brief",
                artifacts=[artifact],
                expected_revision=0,
            )
            self.assertEqual(state["revision"], 1)
            self.assertEqual(state["next_phase"], "retrieval")
            self.assertEqual(len((workspace / "run-events.jsonl").read_text().splitlines()), 2)

    def test_truncated_materialized_state_recovers_from_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            self.initialize(workspace)
            artifact = workspace / "brief.md"
            artifact.write_text("brief\n", encoding="utf-8")
            run_state.advance_phase(workspace, phase="brief", artifacts=[artifact], expected_revision=0)
            (workspace / "run-state.json").write_text("{", encoding="utf-8")
            recovered = run_state.load_status(workspace)
            self.assertEqual(recovered["revision"], 1)
            self.assertEqual(json.loads((workspace / "run-state.json").read_text()), recovered)

    def test_artifact_drift_and_revision_conflict_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            self.initialize(workspace)
            artifact = workspace / "brief.md"
            artifact.write_text("brief\n", encoding="utf-8")
            run_state.advance_phase(workspace, phase="brief", artifacts=[artifact], expected_revision=0)
            with self.assertRaisesRegex(ValueError, "revision conflict"):
                run_state.advance_phase(
                    workspace,
                    phase="retrieval",
                    artifacts=[artifact],
                    expected_revision=0,
                )
            artifact.write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact drifted"):
                run_state.load_status(workspace)

    def test_phase_order_and_event_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            self.initialize(workspace)
            artifact = workspace / "retrieval.json"
            artifact.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "next legal phase is brief"):
                run_state.advance_phase(
                    workspace,
                    phase="retrieval",
                    artifacts=[artifact],
                    expected_revision=0,
                )
            ledger = workspace / "run-events.jsonl"
            ledger.write_text(ledger.read_text().replace("test-run", "altered", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content hash mismatch"):
                run_state.load_status(workspace)

    def test_symlink_cannot_authorize_phase_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run"
            self.initialize(workspace)
            artifact = workspace / "brief.md"
            artifact.write_text("brief\n", encoding="utf-8")
            link = workspace / "brief-link.md"
            link.symlink_to(artifact)
            with self.assertRaisesRegex(ValueError, "regular file"):
                run_state.advance_phase(
                    workspace,
                    phase="brief",
                    artifacts=[link],
                    expected_revision=0,
                )


if __name__ == "__main__":
    unittest.main()
