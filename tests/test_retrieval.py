import importlib.util
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "retrieve_candidates.py"
SPEC = importlib.util.spec_from_file_location("retrieve_candidates", SCRIPT)
retrieve_candidates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(retrieve_candidates)


class RetrievalTests(unittest.TestCase):
    def bounded_scores(self):
        scores = defaultdict(float)
        reasons = defaultdict(set)
        for index in range(500):
            retrieve_candidates.add_score(
                scores,
                reasons,
                f"PHOTO-{index:04d}",
                float(index % 11),
                "broad-term",
                25,
                47,
                "work",
            )
            self.assertLessEqual(len(scores), 50)
        retrieve_candidates.prune_view(scores, reasons, 25, 47, "work")
        return dict(scores), {key: set(value) for key, value in reasons.items()}

    def test_broad_candidate_stream_remains_bounded_and_deterministic(self):
        first_scores, first_reasons = self.bounded_scores()
        second_scores, second_reasons = self.bounded_scores()
        self.assertEqual(len(first_scores), 25)
        self.assertEqual(first_scores, second_scores)
        self.assertEqual(first_reasons, second_reasons)

    def test_event_cluster_generalizes_bursts_and_nearby_capture_context(self):
        burst_a = retrieve_candidates.event_cluster({"burst_key": "BURST-123"})
        burst_b = retrieve_candidates.event_cluster({"burst_key": "BURST-123"})
        self.assertEqual(burst_a, burst_b)
        first = retrieve_candidates.event_cluster(
            {"date_created": "2026-07-19T14:04:00", "camera_make": "Apple", "camera_model": "Phone"}
        )
        second = retrieve_candidates.event_cluster(
            {"date_created": "2026-07-19 14:55:00", "camera_make": "Apple", "camera_model": "Phone"}
        )
        different = retrieve_candidates.event_cluster(
            {"date_created": "2026-07-19 15:01:00", "camera_make": "Apple", "camera_model": "Phone"}
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)


if __name__ == "__main__":
    unittest.main()
