import json
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

import photo_fieldwork.pipeline as pipeline


ROOT = Path(__file__).resolve().parents[1]


def load_inventory_builder():
    path = ROOT / "skills" / "curate-apple-photos" / "scripts" / "build_visible_library_inventory.py"
    spec = importlib.util.spec_from_file_location("build_visible_library_inventory", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(uuid, views, score=0):
    return {
        "uuid": uuid,
        "filename": f"{uuid}.jpg",
        "candidate_views": views,
        "evidence_confidence": "high" if score else "medium",
        "favorite": "true" if score else "false",
        "safety_status": "clear",
    }


def config(views, target=None):
    return {
        "seed": 20260719,
        "target_count": target if target is not None else sum(view["quota"] for view in views),
        "unclassified_view": views[0]["id"],
        "minimum_named_people_fraction": 0,
        "minimum_person_free_fraction": 0,
        "minimum_eval_coverage": 1,
        "minimum_eval_decisive_precision": 0.75,
        "minimum_view_eval_decisive_precision": 0.65,
        "minimum_view_eval_decisive_count": 2,
        "maximum_eval_uncertainty": 0.25,
        "views": views,
    }


class RecursiveEvalContracts(unittest.TestCase):
    def test_prompt_bank_is_structured_and_discriminating(self):
        path = ROOT / "skills" / "curate-apple-photos" / "evals" / "evals.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        evals = payload["evals"]
        self.assertGreaterEqual(len(evals), 8)
        self.assertEqual(len({case["id"] for case in evals}), len(evals))
        self.assertEqual(len({case["name"] for case in evals}), len(evals))
        for case in evals:
            self.assertTrue(case["prompt"].strip())
            self.assertTrue(case["expected_output"].strip())
            self.assertGreaterEqual(len(case["assertions"]), 3)

    def test_overlap_assignment_meets_every_view_quota_exactly(self):
        cfg = config([
            {"id": "A", "label": "A", "quota": 1},
            {"id": "B", "label": "B", "quota": 1},
        ])
        master, _, summary = pipeline.select([row("one", "A;B", 1), row("two", "A")], cfg)
        self.assertEqual(summary["view_counts"], {"A": 1, "B": 1})
        self.assertEqual({item["uuid"]: item["primary_view"] for item in master}, {"one": "B", "two": "A"})

    def test_infeasible_quota_reports_deficit_without_rewriting_brief(self):
        cfg = config([
            {"id": "A", "label": "A", "quota": 1},
            {"id": "B", "label": "B", "quota": 1},
        ])
        with self.assertRaisesRegex(ValueError, "exact view quotas are infeasible.*B"):
            pipeline.select([row("one", "A"), row("two", "A")], cfg)

    def test_weak_material_view_blocks_strong_aggregate(self):
        cfg = config([
            {"id": "A", "label": "A", "quota": 10},
            {"id": "B", "label": "B", "quota": 2},
        ])
        feedback = []
        for index in range(10):
            feedback.append({
                "uuid": f"a-{index}", "filename": "a.jpg", "primary_view": "A",
                "proposal_id": "proposal", "master_sha256": "master", "judgment": "fit",
                "view_population": "10", "safety_status": "clear",
            })
        for index in range(2):
            feedback.append({
                "uuid": f"b-{index}", "filename": "b.jpg", "primary_view": "B",
                "proposal_id": "proposal", "master_sha256": "master", "judgment": "reject",
                "view_population": "2", "safety_status": "clear",
            })
        sample_hash = pipeline.evaluation_sample_sha256(feedback)
        for item in feedback:
            item["evaluation_sample_sha256"] = sample_hash
        report, passed = pipeline.evaluate(feedback, cfg)
        self.assertGreater(report["decisive_precision"], 0.8)
        self.assertFalse(passed)
        self.assertFalse(report["by_view"]["B"]["passed"])

    def test_duplicate_image_view_judgments_cannot_inflate_metrics(self):
        cfg = config([{"id": "A", "label": "A", "quota": 1}])
        feedback = [{
            "uuid": "same", "filename": "same.jpg", "primary_view": "A",
            "proposal_id": "proposal", "master_sha256": "master", "judgment": "fit",
            "view_population": "1", "safety_status": "clear",
        }] * 3
        sample_hash = pipeline.evaluation_sample_sha256(feedback[:1])
        feedback = [dict(item, evaluation_sample_sha256=sample_hash) for item in feedback]
        with self.assertRaisesRegex(ValueError, "duplicate evaluation edge"):
            pipeline.evaluate(feedback, cfg)

    def test_evaluation_detects_sample_membership_drift(self):
        cfg = config([
            {"id": "A", "label": "A", "quota": 2},
            {"id": "B", "label": "B", "quota": 2},
        ])
        master, _, _ = pipeline.select([
            row("a-1", "A"), row("a-2", "A"), row("b-1", "B"), row("b-2", "B")
        ], cfg)
        sample = pipeline.make_sample(master, 2, 1)
        for item in sample:
            item["judgment"] = "fit"
            item["safety_status"] = "clear"
        with self.assertRaisesRegex(ValueError, "sample membership"):
            pipeline.evaluate(sample[:-1], cfg)

    def test_recursive_sample_can_require_zero_prior_uuid_overlap(self):
        cfg = config([
            {"id": "A", "label": "A", "quota": 3},
            {"id": "B", "label": "B", "quota": 3},
        ])
        master, _, _ = pipeline.select([
            row("a-1", "A"), row("a-2", "A"), row("a-3", "A"),
            row("b-1", "B"), row("b-2", "B"), row("b-3", "B"),
        ], cfg)
        first = pipeline.make_sample(master, 1, 1)
        excluded = {item["uuid"] for item in first}
        second = pipeline.make_sample(master, 1, 2, excluded_ids=excluded, novel_only=True)
        self.assertFalse(excluded & {item["uuid"] for item in second})
        self.assertTrue(all(item["prior_review_overlap"] == "false" for item in second))

    def test_catalog_plan_requires_bound_editor_field_evaluation(self):
        cfg = config([{"id": "A", "label": "A", "quota": 1}])
        master, _, _ = pipeline.select([row("one", "A")], cfg)
        with self.assertRaisesRegex(ValueError, "passing bound evaluation"):
            pipeline.build_catalog_plan(master, cfg, "plan", "Source", "SOURCE")
        sample = pipeline.make_sample(master, 1, 1)
        sample[0]["judgment"] = "fit"
        sample[0]["safety_status"] = "clear"
        report, passed = pipeline.evaluate(sample, cfg)
        self.assertTrue(passed)
        plan = pipeline.build_catalog_plan(master, cfg, "plan", "Source", "SOURCE", report)
        self.assertEqual(report["release_class"], "editor-field")
        self.assertEqual(plan["release_class"], "editor-field")
        self.assertFalse(plan["publication_clearance"])

    def test_unknown_candidate_view_does_not_become_unclassified_silently(self):
        cfg = config([{"id": "A", "label": "Unclassified", "quota": 1}])
        with self.assertRaisesRegex(ValueError, "unknown candidate view"):
            pipeline.select([row("one", "TYPO")], cfg)

    def test_duplicate_inventory_uuid_is_rejected_before_assignment(self):
        cfg = config([{"id": "A", "label": "A", "quota": 1}])
        with self.assertRaisesRegex(ValueError, "duplicate inventory UUID"):
            pipeline.select([row("same", "A"), row("same", "A")], cfg)

    def test_omitted_safety_feedback_fails_closed(self):
        cfg = config([{"id": "A", "label": "A", "quota": 1}])
        master, _, _ = pipeline.select([row("one", "A")], cfg)
        sample = pipeline.make_sample(master, 1, 1)
        sample[0]["judgment"] = "fit"
        sample[0]["safety_status"] = ""
        report, passed = pipeline.evaluate(sample, cfg)
        self.assertFalse(passed)
        self.assertEqual(report["safety_regressions"], 1)

    def test_sparse_hypothesis_waiver_is_explicit_and_reported(self):
        invalid = config([{
            "id": "A", "label": "Project Evidence - Editor Hypothesis", "quota": 1,
            "evaluation_mode": "sparse-hypothesis",
        }])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evaluation_waiver_reason"):
                pipeline.read_config(path)

        valid = config([{
            "id": "A", "label": "Project Evidence - Editor Hypothesis", "quota": 1,
            "evaluation_mode": "sparse-hypothesis",
            "evaluation_waiver_reason": "No inspected candidate yet supports a stronger proof claim.",
        }])
        master, _, _ = pipeline.select([row("one", "A")], valid)
        sample = pipeline.make_sample(master, 1, 1)
        sample[0]["judgment"] = "fit"
        sample[0]["safety_status"] = "clear"
        report, passed = pipeline.evaluate(sample, valid)
        self.assertTrue(passed)
        self.assertEqual(report["by_view"]["A"]["gate_status"], "WAIVED")
        self.assertEqual(len(report["waivers"]), 1)
        plan = pipeline.build_catalog_plan(master, valid, "plan", "Source", "SOURCE", report)
        self.assertEqual(plan["evaluation_waivers"], report["waivers"])

    def test_production_shaped_assignment_meets_8000_item_contract(self):
        views = [{"id": str(index), "label": str(index), "quota": 1600} for index in range(5)]
        cfg = config(views, target=8000)
        inventory = [
            row(f"S-{index:05d}", f"{index % 5};{(index + 1) % 5}")
            for index in range(12000)
        ]
        master, holds, summary = pipeline.select(inventory, cfg)
        self.assertEqual(len(master), 8000)
        self.assertEqual(holds, [])
        self.assertEqual(summary["view_counts"], {str(index): 1600 for index in range(5)})
        self.assertEqual(summary["capacity"]["status"], "PASS")

    def test_source_membership_fingerprint_is_order_independent_and_exact(self):
        builder = load_inventory_builder()
        first = sqlite3.connect(":memory:")
        second = sqlite3.connect(":memory:")
        for connection, values in ((first, ["B", "A"]), (second, ["A", "B"])):
            connection.execute("CREATE TABLE asset (uuid TEXT PRIMARY KEY)")
            connection.executemany("INSERT INTO asset(uuid) VALUES (?)", [(value,) for value in values])
        self.assertEqual(builder.membership_sha256(first), builder.membership_sha256(second))
        second.execute("INSERT INTO asset(uuid) VALUES ('C')")
        self.assertNotEqual(builder.membership_sha256(first), builder.membership_sha256(second))


if __name__ == "__main__":
    unittest.main()
