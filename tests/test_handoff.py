import unittest

from photo_fieldwork.handoff import PUBLIC_FIELDS, build_public_handoff


def cleared_row(**changes) -> dict:
    row = {
        "uuid": "PRIVATE-UUID-1",
        "primary_view": "A",
        "page_slot": "home-lead",
        "publication_status": "cleared-for-specific-use",
        "rights_status": "owner-verified",
        "consent_status": "not-applicable",
        "claim_status": "visible-only",
        "alt_text": "A visible public scene",
        "caption": "A public-safe caption",
        "credit": "Jamie Burkart",
        "raw_ocr": "private source material",
        "local_path": "/private/archive/photo.jpg",
    }
    row.update(changes)
    return row


class PublicHandoffTests(unittest.TestCase):
    def test_public_projection_uses_only_allowlisted_fields_and_opaque_ids(self):
        output, errors = build_public_handoff([cleared_row()], "a-publication-salt-of-sufficient-length")
        self.assertEqual(errors, [])
        self.assertEqual(len(output), 1)
        self.assertEqual(tuple(output[0]), PUBLIC_FIELDS)
        self.assertNotEqual(output[0]["public_id"], "PRIVATE-UUID-1")
        self.assertNotIn("raw_ocr", output[0])
        self.assertNotIn("local_path", output[0])

    def test_rights_consent_and_claim_state_fail_closed(self):
        rows = [
            cleared_row(uuid="RIGHTS", rights_status="unknown"),
            cleared_row(uuid="CONSENT", consent_status="ask"),
            cleared_row(uuid="CLAIM", claim_status="caption-review"),
        ]
        output, errors = build_public_handoff(rows, "a-publication-salt-of-sufficient-length")
        self.assertEqual(output, [])
        self.assertEqual(len(errors), 3)

    def test_allowlisted_text_is_linted_for_private_content(self):
        row = cleared_row(caption="Open /Users/jamie/PRIVATE-UUID-1.jpg", alt_text="raw OCR account number")
        output, errors = build_public_handoff([row], "a-publication-salt-of-sufficient-length")
        self.assertEqual(output, [])
        self.assertTrue(any("private archive identifier" in error for error in errors))
        self.assertTrue(any("local filesystem path" in error for error in errors))
        self.assertTrue(any("account or credential" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
