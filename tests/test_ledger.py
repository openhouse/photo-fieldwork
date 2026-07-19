import unittest

from photo_fieldwork.ledger import build_events


class LedgerTests(unittest.TestCase):
    def test_ledger_separates_retrieval_visible_and_verified_context(self):
        master = [{
            "uuid": "A",
            "proposal_id": "P",
            "master_sha256": "H",
            "primary_view": "01",
            "candidate_views": "01;02",
            "visible_context": "meeting table",
            "verified_contexts": "",
            "selection_reason": "retrieval hypothesis",
            "safety_state": "clear_for_editor_field",
        }]
        events = build_events(master, [], [])
        details = events[0]["details"]
        self.assertEqual(details["retrieval_hypotheses"], "01;02")
        self.assertEqual(details["visible_description"], "meeting table")
        self.assertEqual(details["verified_contexts"], "")
        self.assertEqual(len(events[0]["event_id"]), 64)

    def test_ledger_is_deterministic(self):
        row = {"uuid": "A", "proposal_id": "P", "master_sha256": "H"}
        self.assertEqual(build_events([row], [], []), build_events([row], [], []))
