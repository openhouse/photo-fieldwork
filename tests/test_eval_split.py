import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "audit_eval_split.py"
SPEC = importlib.util.spec_from_file_location("audit_eval_split", SCRIPT)
audit_eval_split = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_eval_split)


class EvalSplitTests(unittest.TestCase):
    def test_relation_overlap_fails_even_when_uuids_are_disjoint(self):
        report = audit_eval_split.audit_split(
            [{"uuid": "TUNE-1", "event_cluster": "EVENT-1"}],
            [{"uuid": "HOLD-1", "event_cluster": "EVENT-1"}],
            [{"uuid": "CANARY-1", "event_cluster": "EVENT-2"}],
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["leakage"]["tuning_holdout_uuid_overlap_count"], 0)
        self.assertEqual(report["leakage"]["tuning_holdout_relation_overlap_count"], 1)
        self.assertNotIn("EVENT-1", repr(report))

    def test_canonical_uuid_duplicates_and_canary_leakage_fail(self):
        report = audit_eval_split.audit_split(
            [{"uuid": "TUNE-1/L0/001"}, {"uuid": "TUNE-1/L0/002"}],
            [{"uuid": "HOLD-1", "inspection_sha256": "digest-a"}],
            [{"uuid": "CANARY-1", "inspection_sha256": "digest-a"}],
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["leakage"]["tuning_duplicate_uuid_count"], 1)
        self.assertEqual(report["leakage"]["canary_holdout_relation_overlap_count"], 1)

    def test_private_details_are_opt_in(self):
        public = audit_eval_split.audit_split(
            [{"uuid": "TUNE-1", "duplicate_group": "DUP-1"}],
            [{"uuid": "HOLD-1", "duplicate_group": "DUP-1"}],
            [],
        )
        private = audit_eval_split.audit_split(
            [{"uuid": "TUNE-1", "duplicate_group": "DUP-1"}],
            [{"uuid": "HOLD-1", "duplicate_group": "DUP-1"}],
            [],
            include_private_details=True,
        )
        self.assertNotIn("private_details", public)
        self.assertEqual(private["private_details"]["tuning_holdout_relations"], ["duplicate_group:DUP-1"])


if __name__ == "__main__":
    unittest.main()
