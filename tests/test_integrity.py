import unittest
from copy import deepcopy

from photo_fieldwork.integrity import (
    create_evaluation_seal,
    evaluate_freshness,
    manifest_fingerprint,
    verify_evaluation_seal,
)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.master = [
            {"uuid": "SYN-1", "primary_view": "A", "safety_status": "clear_automated"},
            {"uuid": "SYN-2", "primary_view": "B", "safety_status": "cleared_editor_private"},
        ]
        self.config = {"seed": 1, "target_count": 2, "views": [{"id": "A"}, {"id": "B"}]}
        self.report = {"passed": True, "decisive_precision": 1.0, "uncertainty_rate": 0.0}

    def test_manifest_fingerprint_is_order_independent_and_assignment_sensitive(self):
        self.assertEqual(manifest_fingerprint(self.master), manifest_fingerprint(list(reversed(self.master))))
        changed = deepcopy(self.master)
        changed[0]["primary_view"] = "B"
        self.assertNotEqual(manifest_fingerprint(self.master), manifest_fingerprint(changed))

    def test_passing_evaluation_seal_rejects_candidate_and_config_drift(self):
        seal = create_evaluation_seal(self.master, self.config, self.report)
        self.assertEqual(verify_evaluation_seal(seal, self.master, self.config), [])

        changed_master = deepcopy(self.master)
        changed_master[1]["safety_status"] = "review_sensitive"
        self.assertTrue(any("master" in error for error in verify_evaluation_seal(seal, changed_master, self.config)))

        changed_config = deepcopy(self.config)
        changed_config["seed"] = 2
        self.assertTrue(any("config" in error for error in verify_evaluation_seal(seal, self.master, changed_config)))

    def test_seal_tampering_and_failed_evaluation_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "did not pass"):
            create_evaluation_seal(self.master, self.config, {"passed": False})
        seal = create_evaluation_seal(self.master, self.config, self.report)
        seal["master_count"] = 999
        errors = verify_evaluation_seal(seal, self.master, self.config)
        self.assertIn("evaluation seal fingerprint is invalid", errors)
        self.assertTrue(any("master count changed" in error for error in errors))

    def test_freshness_can_enforce_a_disjoint_final_holdout(self):
        report = evaluate_freshness(
            ["SYN-NEW", "SYN-REUSED"],
            ["SYN-REUSED"],
            minimum_fresh_fraction=1.0,
            require_disjoint=True,
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["reused_identifiers"], ["SYN-REUSED"])
        self.assertIn("final holdout reuses tuning evidence", report["gate_failures"])

    def test_freshness_rejects_duplicate_sample_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate UUIDs"):
            evaluate_freshness(["SYN-1", "SYN-1"], [], 0.5)


if __name__ == "__main__":
    unittest.main()
