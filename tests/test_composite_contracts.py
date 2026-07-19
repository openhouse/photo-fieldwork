import unittest

from photo_fieldwork.artifacts import build_source_snapshot


class ReleaseSealTests(unittest.TestCase):
    def setUp(self):
        self.master = [
            {"uuid": "A", "filename": "a.jpg", "primary_view": "01", "safety_status": "clear", "selection_reason": "synthetic evidence"},
            {"uuid": "B", "filename": "b.jpg", "primary_view": "02", "safety_status": "clear", "selection_reason": "synthetic evidence"},
        ]
        self.holds = [{"uuid": "H", "filename": "h.jpg", "safety_status": "hold"}]
        self.config = {
            "seed": 7,
            "target_count": 2,
            "unclassified_view": "01",
            "minimum_view_precision": 0.75,
            "views": [
                {"id": "01", "label": "One", "quota": 1},
                {"id": "02", "label": "Two", "quota": 1},
            ],
        }
        self.source = build_source_snapshot(["A", "B", "H"], "synthetic://source", captured_at="2026-07-19T00:00:00+00:00")
        from photo_fieldwork.integrity import row_artifact_fingerprint

        master_fingerprint = row_artifact_fingerprint(self.master)
        holds_fingerprint = row_artifact_fingerprint(self.holds)
        self.evaluation = {
            "passed": True,
            "precision": 1.0,
            "view_failures": [],
            "master_fingerprint": master_fingerprint,
        }
        self.validation = {
            "status": "PASS",
            "errors": [],
            "master_count": 2,
            "master_fingerprint": master_fingerprint,
            "holds_fingerprint": holds_fingerprint,
        }

    def test_release_seal_binds_every_release_artifact(self):
        from photo_fieldwork.integrity import create_release_seal, verify_release_seal

        seal = create_release_seal(
            self.master,
            self.holds,
            self.config,
            self.source,
            self.evaluation,
            self.validation,
            created_at="2026-07-19T01:00:00+00:00",
        )
        self.assertEqual(
            verify_release_seal(
                seal,
                self.master,
                self.holds,
                self.config,
                self.source,
                self.evaluation,
                self.validation,
            ),
            [],
        )
        changed_master = [dict(row) for row in self.master]
        changed_master[0]["uuid"] = "C"
        changed_holds = [*self.holds, {"uuid": "H2", "filename": "h2.jpg", "safety_status": "hold"}]
        changed_config = {**self.config, "minimum_view_precision": 0.5}
        errors = verify_release_seal(
            seal,
            changed_master,
            changed_holds,
            changed_config,
            self.source,
            self.evaluation,
            self.validation,
        )
        self.assertTrue(any("master" in error for error in errors))
        self.assertTrue(any("holds" in error for error in errors))
        self.assertTrue(any("config" in error for error in errors))

    def test_release_seal_rejects_unpassed_reports(self):
        from photo_fieldwork.integrity import create_release_seal

        with self.assertRaisesRegex(ValueError, "evaluation"):
            create_release_seal(
                self.master,
                self.holds,
                self.config,
                self.source,
                {**self.evaluation, "passed": False},
                self.validation,
            )
        with self.assertRaisesRegex(ValueError, "validation"):
            create_release_seal(
                self.master,
                self.holds,
                self.config,
                self.source,
                self.evaluation,
                {**self.validation, "status": "FAIL", "errors": ["quota"]},
            )

    def test_release_seal_rejects_pass_report_for_another_master(self):
        from photo_fieldwork.integrity import create_release_seal

        with self.assertRaisesRegex(ValueError, "evaluation report does not bind"):
            create_release_seal(
                self.master,
                self.holds,
                self.config,
                self.source,
                {**self.evaluation, "master_fingerprint": "sha256:" + "0" * 64},
                self.validation,
            )

    def test_release_seal_recomputes_deterministic_validation(self):
        from photo_fieldwork.integrity import create_release_seal, row_artifact_fingerprint

        invalid = [dict(row) for row in self.master]
        invalid[0]["primary_view"] = "02"
        fingerprint = row_artifact_fingerprint(invalid)
        with self.assertRaisesRegex(ValueError, "fails deterministic validation"):
            create_release_seal(
                invalid,
                self.holds,
                self.config,
                self.source,
                {**self.evaluation, "master_fingerprint": fingerprint},
                {**self.validation, "master_fingerprint": fingerprint},
            )


class PublicationClearanceTests(unittest.TestCase):
    def test_publication_clearance_defaults_closed_and_validates_complete_rows(self):
        from photo_fieldwork.publication import CLEARANCE_FIELDS, scaffold, validate_clearance

        master = [{"uuid": "A", "filename": "a.jpg"}, {"uuid": "B", "filename": "b.jpg"}]
        rows = scaffold(master)
        self.assertEqual([row["publication_cleared"] for row in rows], ["false", "false"])
        rows[0]["publication_cleared"] = "true"
        errors, report = validate_clearance(rows, master_ids={"A", "B"})
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A is cleared but missing" in error for error in errors))
        for field in CLEARANCE_FIELDS[3:]:
            rows[0][field] = "approved" if field in {
                "participant_consent",
                "collaborator_approval",
                "artwork_review",
                "crop_approved",
                "sensitive_context_review",
            } else "reviewed"
        errors, report = validate_clearance(rows, master_ids={"A", "B"})
        self.assertEqual(errors, [])
        self.assertEqual(report["publication_cleared"], 1)

        rows[0]["participant_consent"] = "false"
        errors, _ = validate_clearance(rows, master_ids={"A", "B"})
        self.assertTrue(any("participant_consent" in error for error in errors))

    def test_publication_clearance_requires_exact_master_coverage(self):
        from photo_fieldwork.publication import scaffold, validate_clearance

        rows = scaffold([{"uuid": "A", "filename": "a.jpg"}])
        errors, _ = validate_clearance(rows, master_ids={"A", "B"})
        self.assertTrue(any("missing master UUIDs" in error for error in errors))


class HoldoutIndependenceTests(unittest.TestCase):
    def test_holdout_audit_detects_related_frames_without_disclosing_them(self):
        from photo_fieldwork.splits import audit_split

        tuning = [
            {"uuid": "T1", "perceptual_cluster_id": "P1"},
            {"uuid": "T2", "duplicate_group": "D1"},
        ]
        holdout = [
            {"uuid": "H1", "perceptual_cluster_id": "P1"},
            {"uuid": "H2", "duplicate_group": "D1"},
            {"uuid": "H3", "burst_group": "B1"},
        ]
        canaries = [{"uuid": "C1", "burst_group": "B1"}]
        report = audit_split(tuning, holdout, canaries)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["leakage"]["tuning_cluster_overlap_count"], 2)
        self.assertEqual(report["leakage"]["canary_cluster_overlap_count"], 1)
        self.assertNotIn("private_details", report)
        private = audit_split(tuning, holdout, canaries, include_identifiers=True)
        self.assertIn("perceptual_cluster_id:P1", private["private_details"]["tuning_cluster_overlap"])


class IdempotenceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.attempts = [
            {
                "attempt_id": "attempt-1",
                "execution_nonce": "1" * 32,
                "plan_sha256": "a" * 64,
                "execution_fingerprint": {"app_bundle_identifier": "art.example.helper", "app_binary_sha256": "b" * 64, "plan_sha256": "a" * 64},
                "receipt": {"execution_nonce": "1" * 32, "folders": [{"key": "root", "identifier": "F"}], "albums": [{"title": "Master", "identifier": "A"}]},
            },
            {
                "attempt_id": "attempt-2",
                "execution_nonce": "2" * 32,
                "plan_sha256": "a" * 64,
                "execution_fingerprint": {"app_bundle_identifier": "art.example.helper", "app_binary_sha256": "b" * 64, "plan_sha256": "a" * 64},
                "receipt": {"execution_nonce": "2" * 32, "folders": [{"key": "root", "identifier": "F"}], "albums": [{"title": "Master", "identifier": "A"}]},
            },
        ]
        self.verifications = [
            {"attempt_id": "attempt-1", "plan_sha256": "a" * 64, "status": "PASS", "exact_membership": True, "exact_topology": True},
            {"attempt_id": "attempt-2", "plan_sha256": "a" * 64, "status": "PASS", "exact_membership": True, "exact_topology": True},
        ]

    def test_two_distinct_verified_executions_establish_idempotence(self):
        from photo_fieldwork.receipts import audit_idempotence_evidence

        report = audit_idempotence_evidence(self.attempts, self.verifications, "a" * 64)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertTrue(report["same_catalog_bindings"])

    def test_copied_nonce_or_missing_verification_fails(self):
        from photo_fieldwork.receipts import audit_idempotence_evidence

        copied = [dict(item) for item in self.attempts]
        copied[1]["execution_nonce"] = "1" * 32
        report = audit_idempotence_evidence(copied, self.verifications[:1], "a" * 64)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("execution nonces" in error for error in report["errors"]))
        self.assertTrue(any("verification" in error for error in report["errors"]))

    def test_different_helper_build_does_not_establish_idempotence(self):
        from photo_fieldwork.receipts import audit_idempotence_evidence

        changed = [dict(item) for item in self.attempts]
        changed[1]["execution_fingerprint"] = {
            **changed[1]["execution_fingerprint"],
            "app_binary_sha256": "c" * 64,
        }
        report = audit_idempotence_evidence(changed, self.verifications, "a" * 64)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("app binary" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
