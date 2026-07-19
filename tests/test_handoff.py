import unittest

from photo_fieldwork.handoff import PUBLIC_FIELDS, build_public_handoff


class PublicHandoffTests(unittest.TestCase):
    def test_handoff_is_allowlisted_and_destination_scoped(self):
        rows = [
            {
                "uuid": "PRIVATE-ASSET-1",
                "primary_view": "01",
                "publication_status": "cleared-for-specific-use",
                "publication_destination": "portfolio-case-study",
                "rights_status": "owner-verified",
                "consent_status": "not-applicable",
                "claim_status": "provenance-backed",
                "caption": "Synthetic caption",
                "private_path": "/private/example.jpg",
                "raw_ocr": "synthetic private text",
            }
        ]
        output, errors = build_public_handoff(
            rows, "synthetic-salt-value", "portfolio-case-study"
        )
        self.assertEqual(errors, [])
        self.assertEqual(tuple(output[0]), PUBLIC_FIELDS)
        self.assertNotIn("uuid", output[0])
        self.assertNotIn("private_path", output[0])
        self.assertNotIn("raw_ocr", output[0])

    def test_handoff_fails_closed_on_incomplete_or_wrong_scope_clearance(self):
        base = {
            "uuid": "PRIVATE-ASSET-2",
            "publication_status": "cleared-for-specific-use",
            "publication_destination": "press-kit",
            "rights_status": "owner-verified",
            "consent_status": "cleared-for-use",
            "claim_status": "visible-only",
        }
        wrong_scope, scope_errors = build_public_handoff(
            [base], "synthetic-salt-value", "portfolio-case-study"
        )
        missing_rights = dict(base, publication_destination="portfolio-case-study", rights_status="unknown")
        rights_output, rights_errors = build_public_handoff(
            [missing_rights], "synthetic-salt-value", "portfolio-case-study"
        )
        self.assertEqual(wrong_scope, [])
        self.assertTrue(scope_errors)
        self.assertEqual(rights_output, [])
        self.assertTrue(rights_errors)

    def test_editor_field_membership_alone_is_not_publishable(self):
        output, errors = build_public_handoff(
            [{"uuid": "PRIVATE-ASSET-3", "publication_status": "not-reviewed"}],
            "synthetic-salt-value",
            "portfolio-case-study",
        )
        self.assertEqual(output, [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
