import unittest

from photo_fieldwork.eval_split import audit_eval_split


class EvaluationSplitTests(unittest.TestCase):
    def test_relationship_clusters_cannot_cross_into_holdout(self):
        report = audit_eval_split(
            [{"uuid": "TUNE-1", "perceptual_cluster_id": "P-1"}],
            [{"uuid": "HOLDOUT-1", "perceptual_cluster_id": "P-1"}],
            [{"uuid": "CANARY-1", "burst_group": "B-1"}],
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["leakage"]["tuning_cluster_overlap_count"], 1)
        self.assertNotIn("private_details", report)
        self.assertNotIn("HOLDOUT-1", str(report))

    def test_uuid_and_canary_cluster_leakage_are_reported_privately_on_request(self):
        report = audit_eval_split(
            [{"uuid": "SHARED"}],
            [{"uuid": "SHARED", "burst_group": "B-1"}],
            [{"uuid": "CANARY", "burst_group": "B-1"}],
            include_private_details=True,
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["leakage"]["tuning_uuid_overlap_count"], 1)
        self.assertEqual(report["leakage"]["canary_cluster_overlap_count"], 1)
        self.assertEqual(report["private_details"]["tuning_uuid_overlap"], ["SHARED"])

    def test_holdout_cannot_count_two_members_of_one_cluster_as_independent(self):
        report = audit_eval_split(
            [],
            [
                {"uuid": "HOLDOUT-1", "duplicate_group": "D-1"},
                {"uuid": "HOLDOUT-2", "duplicate_group": "D-1"},
            ],
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["leakage"]["holdout_duplicate_cluster_count"], 1)


if __name__ == "__main__":
    unittest.main()
