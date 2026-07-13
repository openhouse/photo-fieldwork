import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.runstate import PHASES, derive_state, init_run, record_phase, render_report


class RunStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_version_reservation_and_phase_order(self):
        workspace = init_run(self.root, "v01-A", "example", 12, "SOURCE", 30, "abc123")
        with self.assertRaises(ValueError):
            init_run(self.root, "v01-A", "duplicate", 12, "SOURCE", 30)
        artifact = workspace / "reports" / "doctor.json"
        artifact.write_text('{"status":"PASS"}\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            record_phase(workspace, "retrieval", "pass", outputs=[artifact])
        receipt = record_phase(workspace, "preflight", "pass", outputs=[artifact])
        self.assertEqual(len(receipt["outputs"][0]["sha256"]), 64)
        self.assertEqual(derive_state(workspace)["next_phase"], "retrieval")

    def test_report_is_derived_from_receipts(self):
        workspace = init_run(self.root, "v02-A", "example", 4, "SOURCE", None)
        artifact = workspace / "reports" / "preflight.json"
        artifact.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        record_phase(workspace, "preflight", "pass", outputs=[artifact], metrics={"source": 30})
        report = render_report(workspace)
        self.assertIn("preflight`: pass", report)
        self.assertIn("publication permission", report)

    def test_complete_status_requires_every_phase(self):
        workspace = init_run(self.root, "v03-A", "complete", 4, "SOURCE", 10)
        artifact = workspace / "reports" / "evidence.json"
        artifact.write_text('{"status":"PASS"}\n', encoding="utf-8")
        for phase in PHASES:
            record_phase(workspace, phase, "pass", outputs=[artifact])
        state = derive_state(workspace)
        self.assertEqual(state["status"], "complete")
        self.assertIsNone(state["next_phase"])
