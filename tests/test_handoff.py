import json
import unittest

from photo_fieldwork.handoff import PUBLIC_FIELDS, build_public_handoff


def cleared(public_id="public-1", derivative="public/photo-1.jpg"):
    return {
        "uuid": "PRIVATE-SOURCE-UUID",
        "persons": "Private Person Association",
        "raw_ocr": "Private address",
        "public_id": public_id,
        "derivative": derivative,
        "alt_text": "Two people working at a table.",
        "caption": "A public-safe caption.",
        "credit": "Jamie Burkart",
        "view_id": "work",
        "rights_status": "cleared",
        "consent_status": "cleared",
        "claim_status": "supported",
        "safety_status": "clear_for_public_derivative",
        "publication_status": "approved",
    }


class PublicHandoffTests(unittest.TestCase):
    def test_cleared_derivative_exports_only_allowlisted_fields(self):
        source = cleared()
        before = dict(source)
        manifest, report = build_public_handoff([source])
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(manifest["publication_clearance"])
        self.assertEqual(set(manifest["items"][0]), set(PUBLIC_FIELDS))
        rendered = json.dumps(manifest)
        self.assertNotIn("PRIVATE-SOURCE-UUID", rendered)
        self.assertNotIn("Private Person", rendered)
        self.assertEqual(source, before)

    def test_unresolved_rows_remain_closed_without_blocking_cleared_derivatives(self):
        unresolved = dict(cleared("public-2", "public/photo-2.jpg"), consent_status="unknown")
        manifest, report = build_public_handoff([cleared(), unresolved])
        self.assertEqual(len(manifest["items"]), 1)
        self.assertEqual(report["excluded_count"], 1)
        self.assertEqual(report["exclusions_by_reason"], {"consent_not_cleared": 1})

    def test_refusal_only_behavior_cannot_pass_positive_control(self):
        blocked = dict(cleared(), rights_status="unknown", publication_status="pending")
        manifest, report = build_public_handoff([blocked])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(manifest["publication_clearance"])
        self.assertEqual(manifest["items"], [])

    def test_public_derivative_paths_and_ids_are_safe_and_unique(self):
        with self.assertRaisesRegex(ValueError, "repository-relative"):
            build_public_handoff([cleared(derivative="/private/tmp/photo.jpg")])
        with self.assertRaisesRegex(ValueError, "duplicate public_id"):
            build_public_handoff([cleared(), cleared(derivative="public/photo-2.jpg")])
        with self.assertRaisesRegex(ValueError, "repository-relative"):
            build_public_handoff([cleared(derivative="https://example.com/photo.jpg")])
        with self.assertRaisesRegex(ValueError, "duplicate derivative"):
            build_public_handoff([cleared(), cleared("public-2")])


if __name__ == "__main__":
    unittest.main()
