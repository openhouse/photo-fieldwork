import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.feedback import apply_feedback, sample_fingerprint, validate_feedback


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.sample = [
            {"uuid": "A", "filename": "a.jpg", "primary_view": "01", "score_total": "2.0"},
            {"uuid": "B", "filename": "b.jpg", "primary_view": "02", "score_total": "1.0"},
        ]
        sample_hash = sample_fingerprint(self.sample)
        self.decisions = [
            {
                "uuid": "A",
                "filename": "a.jpg",
                "sample_hash": sample_hash,
                "judgment": "fit",
                "visible_reason": "Visible work context",
                "safety_status": "clear_automated",
                "error_category": "visible-fit",
                "round_id": "round-01",
                "reviewer_lens": "editor",
            },
            {
                "uuid": "B",
                "filename": "b.jpg",
                "sample_hash": sample_hash,
                "judgment": "reject",
                "visible_reason": "Metadata-only mismatch",
                "safety_status": "review_sensitive",
                "error_category": "retrieval-mismatch",
                "round_id": "round-01",
                "reviewer_lens": "editor",
            },
        ]

    def test_feedback_is_uuid_keyed_not_position_keyed(self):
        by_uuid = validate_feedback(self.sample, list(reversed(self.decisions)))
        self.assertEqual(by_uuid["A"]["judgment"], "fit")
        self.assertEqual(by_uuid["B"]["judgment"], "reject")

    def test_duplicate_and_unknown_uuids_fail(self):
        with self.assertRaisesRegex(ValueError, "duplicate UUIDs"):
            validate_feedback(self.sample, [self.decisions[0], self.decisions[0]])
        unknown = dict(self.decisions[1], uuid="C")
        with self.assertRaisesRegex(ValueError, "unknown UUIDs"):
            validate_feedback(self.sample, [self.decisions[0], unknown])

    def test_sample_hash_mismatch_fails(self):
        decisions = [dict(row, sample_hash="sha256:wrong") for row in self.decisions]
        with self.assertRaisesRegex(ValueError, "sample_hash"):
            validate_feedback(self.sample, decisions)

    def test_apply_feedback_preserves_raw_decision_and_routes_removals(self):
        master = [
            {"uuid": "A", "filename": "a.jpg", "safety_status": "clear_automated"},
            {"uuid": "B", "filename": "b.jpg", "safety_status": "clear_automated"},
        ]
        reviewed, removed, report = apply_feedback(master, self.sample, self.decisions)
        self.assertEqual([row["uuid"] for row in reviewed], ["A"])
        self.assertEqual([row["uuid"] for row in removed], ["B"])
        self.assertEqual(removed[0]["last_visible_reason"], "Metadata-only mismatch")
        self.assertTrue(report["requires_reselection"])

    def test_clearance_requires_a_human_editor_actor(self):
        sample = [dict(self.sample[0], safety_status="review_sensitive")]
        sample_hash = sample_fingerprint(sample)
        decision = dict(
            self.decisions[0],
            sample_hash=sample_hash,
            safety_status="cleared_editor_private",
        )
        master = [{"uuid": "A", "filename": "a.jpg", "safety_status": "review_sensitive"}]
        with self.assertRaisesRegex(ValueError, "requires actor=human-editor"):
            apply_feedback(master, sample, [decision])
        decision["reviewer_actor"] = "human-editor"
        reviewed, removed, _ = apply_feedback(master, sample, [decision])
        self.assertEqual(len(reviewed), 1)
        self.assertEqual(removed, [])
        self.assertEqual(reviewed[0]["safety_status"], "cleared_editor_private")


if __name__ == "__main__":
    unittest.main()
