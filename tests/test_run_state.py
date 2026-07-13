import tempfile
import json
import unittest
from pathlib import Path

from photo_fieldwork.run_state import audit_state, mark_phase


class RunStateTests(unittest.TestCase):
    def test_completed_artifact_is_hashed_and_audited(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            artifact = workspace / "brief.md"
            artifact.write_text("brief\n", encoding="utf-8")
            mark_phase(workspace, "initialize", "complete", [artifact])
            report = audit_state(workspace)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["next_phase"], "retrieve")
            artifact.write_text("changed\n", encoding="utf-8")
            report = audit_state(workspace)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("changed artifact", report["errors"][0])

    def test_legacy_phase_strings_are_normalized(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "run-state.json").write_text(json.dumps({
                "schema_version": 1,
                "phases": {"brief": "complete", "retrieval": "in_progress"},
            }), encoding="utf-8")
            report = audit_state(workspace)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["complete"], ["initialize"])
            self.assertEqual(report["next_phase"], "retrieve")


if __name__ == "__main__":
    unittest.main()
