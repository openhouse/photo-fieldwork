import tempfile
import tomllib
import unittest
from copy import deepcopy
from pathlib import Path

from photo_fieldwork import __version__
from photo_fieldwork.pipeline import (
    build_catalog_plan,
    content_sha256,
    evaluate,
    make_sample,
    membership_sha256,
    read_config,
    read_csv,
    select,
    validate,
)
from photo_fieldwork.practice import STARTER_CONFIG, create_demo_inventory


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.inventory_path = Path(self.temp.name) / "inventory.csv"
        create_demo_inventory(self.inventory_path)
        self.inventory = read_csv(self.inventory_path)
        self.config = read_config(ROOT / "config" / "starter.json")

    def tearDown(self):
        self.temp.cleanup()

    def mark_final(self, rows):
        for row in rows:
            row.update(
                {
                    "judgment": "fit",
                    "evaluation_note": "Synthetic visible fit.",
                    "reviewer_actor": "Synthetic Human",
                    "reviewer_kind": "human",
                    "round_id": "final-01",
                }
            )

    def test_selection_is_deterministic_and_excludes_holds(self):
        first, holds, _ = select(self.inventory, self.config)
        second, _, _ = select(self.inventory, self.config)
        self.assertEqual([row["uuid"] for row in first], [row["uuid"] for row in second])
        self.assertEqual(len(first), 12)
        self.assertTrue({"DEMO-009", "DEMO-024"}.issubset({row["uuid"] for row in holds}))
        self.assertFalse({row["uuid"] for row in first} & {row["uuid"] for row in holds})

    def test_aesthetic_score_only_breaks_cluster_ties(self):
        master, _, _ = select(self.inventory, self.config)
        selected = {row["uuid"] for row in master}
        self.assertFalse({"DEMO-011", "DEMO-012"}.issubset(selected))

    def test_sample_covers_every_selected_view(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        self.assertEqual(
            {row["primary_view"] for row in master},
            {row["primary_view"] for row in sample},
        )

    def test_evaluation_can_fail_and_pass(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "reject"
        _, passed = evaluate(sample, self.config)
        self.assertFalse(passed)
        for row in sample:
            row["judgment"] = "fit"
        _, passed = evaluate(sample, self.config)
        self.assertTrue(passed)

    def test_validation_enforces_invariants(self):
        master, holds, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        self.mark_final(sample)
        report, passed = evaluate(sample, self.config, final_field=True)
        self.assertTrue(passed)
        errors, metrics = validate(master, holds, self.config, report, sample)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")

    def test_known_reject_cannot_reenter(self):
        self.inventory[0]["known_reject"] = "true"
        master, _, summary = select(self.inventory, self.config)
        self.assertNotIn(self.inventory[0]["uuid"], {row["uuid"] for row in master})
        self.assertEqual(summary["known_reject_count"], 1)

    def test_material_view_failure_blocks_evaluation(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        self.mark_final(sample)
        weak_view = sample[0]["primary_view"]
        for row in sample:
            row["judgment"] = "reject" if row["primary_view"] == weak_view else "fit"
        report, passed = evaluate(sample, self.config, final_field=True)
        self.assertFalse(passed)
        self.assertFalse(report["by_view"][weak_view]["passed"])

    def test_event_cluster_limit_fails_instead_of_padding(self):
        config = deepcopy(self.config)
        config["event_cluster_limit"] = 1
        for row in self.inventory:
            row["event_cluster"] = "one-event"
        with self.assertRaises(ValueError):
            select(self.inventory, config)

    def test_final_audit_requires_every_replacement(self):
        master, holds, _ = select(self.inventory, self.config)
        master[0]["replacement"] = "true"
        sample = make_sample(master, 3, 20260710)
        self.mark_final(sample)
        report, _ = evaluate(sample, self.config, final_field=True)
        final_feedback = [row for row in sample if row["uuid"] != master[0]["uuid"]]
        errors, _ = validate(master, holds, self.config, report, final_feedback)
        self.assertTrue(any("replacement" in error for error in errors))

    def test_catalog_plan_allows_only_membership_writes(self):
        master, holds, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        self.mark_final(sample)
        evaluation, passed = evaluate(sample, self.config, final_field=True)
        self.assertTrue(passed)
        errors, validation = validate(master, holds, self.config, evaluation, sample)
        self.assertEqual(errors, [])
        source_ids = [row["uuid"] for row in self.inventory]
        plan = build_catalog_plan(
            master,
            self.config,
            "practice",
            "Source",
            "SOURCE-1",
            evaluation_report=evaluation,
            validation_report=validation,
            source_count=len(source_ids),
            source_membership_sha256=membership_sha256(source_ids),
        )
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["evaluation"]["master_sha256"], plan["master_sha256"])
        self.assertEqual(
            plan["evaluation"]["report_sha256"],
            content_sha256(evaluation, digest_field="report_sha256"),
        )
        self.assertEqual(plan["validation"]["master_sha256"], plan["master_sha256"])
        self.assertEqual(
            plan["validation"]["report_sha256"],
            content_sha256(validation, digest_field="report_sha256"),
        )
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)

    def test_packaged_starter_matches_repository_config(self):
        repository_config = dict(self.config)
        repository_config.pop("$schema", None)
        self.assertEqual(repository_config, STARTER_CONFIG)

    def test_package_versions_match(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], __version__)


if __name__ == "__main__":
    unittest.main()
