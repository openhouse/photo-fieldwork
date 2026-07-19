import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from photo_fieldwork.cli import command_evaluate
from photo_fieldwork.feedback import sample_fingerprint
from photo_fieldwork.pipeline import write_csv


class CliArtifactTests(unittest.TestCase):
    def test_failed_evaluation_removes_a_stale_passing_seal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {
                "seed": 1,
                "target_count": 1,
                "unclassified_view": "A",
                "views": [{"id": "A", "label": "A", "quota": 1}],
                "minimum_eval_coverage": 1.0,
                "minimum_eval_precision": 1.0,
                "maximum_eval_uncertainty": 0.0,
                "minimum_decisive_per_view": 1,
                "minimum_view_precision": 1.0,
                "maximum_view_uncertainty": 0.0,
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            master = [
                {
                    "uuid": "SYN-1",
                    "filename": "one.jpg",
                    "primary_view": "A",
                    "score_total": "1",
                    "safety_status": "clear_automated",
                }
            ]
            master_path = root / "master.csv"
            write_csv(master_path, master)
            feedback = [
                {
                    **master[0],
                    "judgment": "reject",
                    "visible_reason": "Synthetic mismatch",
                    "error_category": "retrieval-mismatch",
                    "round_id": "synthetic-round",
                    "reviewer_lens": "contract-eval",
                }
            ]
            feedback[0]["sample_hash"] = sample_fingerprint(feedback)
            feedback_path = root / "feedback.csv"
            write_csv(feedback_path, feedback)
            output = root / "reports"
            output.mkdir()
            seal_path = output / "evaluation-seal.json"
            seal_path.write_text('{"stale": true}\n', encoding="utf-8")

            code = command_evaluate(
                Namespace(config=config_path, feedback=feedback_path, master=master_path, output=output)
            )

            self.assertEqual(code, 2)
            self.assertFalse(seal_path.exists())
            report = json.loads((output / "evaluation-report.json").read_text(encoding="utf-8"))
            self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
