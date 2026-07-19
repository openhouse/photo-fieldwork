import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills/curate-apple-photos/scripts/audit_eval_split.py"
SPEC = importlib.util.spec_from_file_location("audit_eval_split", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
split_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(split_audit)


class EvalSplitTests(unittest.TestCase):
    def test_cluster_leakage_fails_even_without_uuid_overlap(self):
        tuning = [{"uuid": "A", "perceptual_cluster_id": "cluster-1"}]
        holdout = [{"uuid": "B", "perceptual_cluster_id": "cluster-1"}]
        report = split_audit.audit_split(tuning, holdout)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["counts"]["id_leakage"], 0)
        self.assertEqual(report["counts"]["cluster_leakage"], 1)

    def test_clean_split_passes_and_private_ids_are_omitted(self):
        tuning = [{"uuid": "A", "burst_group": "one"}]
        holdout = [{"uuid": "B", "burst_group": "two"}]
        report = split_audit.audit_split(tuning, holdout)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["holdout_independent"])
        self.assertNotIn("private_details", report)


if __name__ == "__main__":
    unittest.main()
