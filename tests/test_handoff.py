import unittest

from photo_fieldwork.handoff import PUBLIC_FIELDS, build_public_handoff


class HandoffTests(unittest.TestCase):
    def test_public_projection_requires_every_independent_gate(self):
        base = {
            "uuid": "PRIVATE-UUID/L0/001",
            "primary_view": "01",
            "publication_status": "cleared-for-specific-use",
            "rights_status": "owner-verified",
            "consent_status": "cleared-for-use",
            "claim_status": "provenance-backed",
            "public_safety_status": "clear",
            "caption": "Public-safe caption",
            "private_note": "must never cross",
        }
        rows, report = build_public_handoff([base], "private-test-salt")
        self.assertEqual(report["public_count"], 1)
        self.assertEqual(set(rows[0]), set(PUBLIC_FIELDS))
        self.assertNotIn("uuid", rows[0])
        self.assertNotIn("private_note", rows[0])
        self.assertEqual(len(rows[0]["public_id"]), 20)

        for field in ("publication_status", "rights_status", "consent_status", "claim_status", "public_safety_status"):
            blocked = dict(base)
            blocked[field] = "unreviewed"
            projected, blocked_report = build_public_handoff([blocked], "private-test-salt")
            self.assertEqual(projected, [], field)
            self.assertEqual(blocked_report["withheld_count"], 1)

    def test_public_ids_are_stable_per_salt_and_change_across_salts(self):
        row = {
            "uuid": "A",
            "publication_status": "published",
            "rights_status": "owner-verified",
            "consent_status": "not-applicable",
            "claim_status": "visible-only",
            "public_safety_status": "clear",
        }
        first, _ = build_public_handoff([row], "one")
        repeat, _ = build_public_handoff([row], "one")
        second, _ = build_public_handoff([row], "two")
        self.assertEqual(first[0]["public_id"], repeat[0]["public_id"])
        self.assertNotEqual(first[0]["public_id"], second[0]["public_id"])


if __name__ == "__main__":
    unittest.main()
