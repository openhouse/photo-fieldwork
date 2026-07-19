import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.decision_ledger import append_events, audit_ledger, materialize, read_ledger


class DecisionLedgerTests(unittest.TestCase):
    def event(self, event_type: str, state: str, **overrides) -> dict:
        value = {
            "event_type": event_type,
            "asset_uuid": "ASSET-A",
            "state": state,
            "actor": "Jamie Example",
            "authority": "human",
            "reason": "visible evidence reviewed",
            "occurred_at": "2026-07-19T12:00:00+00:00",
        }
        value.update(overrides)
        return value

    def test_append_only_chain_records_supersession(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "decisions.jsonl"
            first = append_events(
                ledger,
                [self.event("assignment", "assigned", view_id="01", event_id="first")],
            )
            self.assertEqual(first["status"], "PASS")
            second = append_events(
                ledger,
                [self.event("assignment", "unclassified", view_id="01", event_id="second")],
            )
            self.assertEqual(second["event_count"], 2)
            events = read_ledger(ledger)
            self.assertEqual(events[1]["supersedes_event_id"], "first")
            self.assertEqual(events[1]["previous_event_sha256"], events[0]["event_sha256"])

    def test_tampering_breaks_the_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "decisions.jsonl"
            append_events(
                ledger,
                [self.event("assignment", "assigned", view_id="01", event_id="first")],
            )
            event = json.loads(ledger.read_text(encoding="utf-8"))
            event["reason"] = "rewritten history"
            ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report = audit_ledger(ledger)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("event hash mismatch", report["errors"][0])

    def test_materialization_applies_latest_assignment_and_related_hold(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "decisions.jsonl"
            append_events(
                ledger,
                [
                    self.event("assignment", "assigned", view_id="02", event_id="assignment"),
                    self.event("evaluation", "reject", view_id="03", event_id="rejection"),
                    self.event("safety", "hold", event_id="hold"),
                ],
            )
            inventory = [
                {"uuid": "ASSET-A", "filename": "a.jpg", "perceptual_cluster_id": "CLUSTER-1"},
                {"uuid": "ASSET-B", "filename": "b.jpg", "perceptual_cluster_id": "CLUSTER-1"},
            ]
            rows, report = materialize(inventory, read_ledger(ledger))
            by_id = {row["uuid"]: row for row in rows}
            self.assertEqual(by_id["ASSET-A"]["assigned_view"], "02")
            self.assertEqual(by_id["ASSET-A"]["excluded_views"], "03")
            self.assertEqual(by_id["ASSET-A"]["safety_status"], "hold")
            self.assertEqual(by_id["ASSET-B"]["safety_status"], "hold")
            self.assertEqual(report["held_or_related_rows"], 2)

    def test_automation_cannot_record_safety_clearance(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "decisions.jsonl"
            event = self.event("safety", "clear", authority="automation")
            with self.assertRaisesRegex(ValueError, "human authority"):
                append_events(ledger, [event])


if __name__ == "__main__":
    unittest.main()
