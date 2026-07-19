import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.integrity import membership_sha256, verify_plan_digest
from photo_fieldwork.pipeline import build_catalog_plan, evaluate, evaluation_sample_sha256, make_sample, read_config, read_csv, select, stable_noise, validate
from photo_fieldwork.practice import create_demo_inventory


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

    def test_selection_is_deterministic_and_excludes_holds(self):
        first, holds, _ = select(self.inventory, self.config)
        second, _, _ = select(self.inventory, self.config)
        self.assertEqual([row["uuid"] for row in first], [row["uuid"] for row in second])
        self.assertEqual(len(first), 12)
        self.assertTrue({"DEMO-009", "DEMO-024"}.issubset({row["uuid"] for row in holds}))
        self.assertFalse({row["uuid"] for row in first} & {row["uuid"] for row in holds})
        self.assertEqual(
            {view["id"]: view["quota"] for view in self.config["views"]},
            {view: sum(row["primary_view"] == view for row in first) for view in {item["primary_view"] for item in first}},
        )

    def test_explicit_safety_configuration_fails_closed(self):
        config = {
            "seed": 1,
            "target_count": 1,
            "unclassified_view": "00",
            "allow_unclassified_fallback": False,
            "require_explicit_safety_status": True,
            "views": [{"id": "00", "label": "Unclassified", "quota": 1}],
        }
        for status in ("needs-review", "editor-only", "unknown", ""):
            row = {"uuid": status or "missing", "filename": "item.jpg", "candidate_views": "00"}
            if status:
                row["safety_status"] = status
            with self.subTest(status=status or "missing"):
                with self.assertRaisesRegex(ValueError, "quota graph infeasible"):
                    select([row], config)

    def test_aesthetic_score_only_breaks_cluster_ties(self):
        master, _, _ = select(self.inventory, self.config)
        selected = {row["uuid"] for row in master}
        self.assertFalse({"DEMO-011", "DEMO-012"}.issubset(selected))

    def test_stable_noise_uses_canonical_asset_identity(self):
        self.assertEqual(stable_noise(7, "ASSET"), stable_noise(7, "ASSET/L0/040"))

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
        errors, metrics = validate(master, holds, self.config)
        self.assertEqual(errors, [])
        self.assertEqual(metrics["status"], "PASS")

    def test_catalog_plan_allows_only_membership_writes(self):
        master, _, _ = select(self.inventory, self.config)
        source = [row["uuid"] for row in self.inventory]
        plan = build_catalog_plan(master, self.config, "practice", "Source", "SOURCE-1", source)
        self.assertEqual(plan["safety_mode"], "create-folders-albums-and-add-membership-only")
        self.assertEqual(plan["expected_master_count"], 12)
        self.assertEqual(plan["write_test_count"], 10)
        self.assertEqual(len(plan["albums"][0]["asset_ids"]), 12)
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["source"]["membership_sha256"], membership_sha256(source))
        verify_plan_digest(plan)
        plan["plan_id"] = "tampered"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_plan_digest(plan)

    def test_equal_count_source_substitution_changes_digest(self):
        self.assertNotEqual(
            membership_sha256(["A", "B", "C"]),
            membership_sha256(["A", "B", "D"]),
        )

    def test_catalog_plan_rejects_master_outside_frozen_source(self):
        master, _, _ = select(self.inventory, self.config)
        with self.assertRaisesRegex(ValueError, "outside frozen source"):
            build_catalog_plan(
                master,
                self.config,
                "practice",
                "Source",
                "SOURCE-1",
                ["NOT-IN-MASTER"],
            )

    def test_capacity_flow_resolves_overlapping_quotas(self):
        config = {
            "seed": 1,
            "target_count": 3,
            "unclassified_view": "00",
            "allow_unclassified_fallback": False,
            "views": [
                {"id": "00", "label": "Unclassified", "quota": 0},
                {"id": "A", "label": "A", "quota": 2},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        inventory = [
            {"uuid": "AB-1", "filename": "1.jpg", "candidate_views": "A;B", "safety_status": "clear"},
            {"uuid": "A-1", "filename": "2.jpg", "candidate_views": "A", "safety_status": "clear"},
            {"uuid": "A-2", "filename": "3.jpg", "candidate_views": "A", "safety_status": "clear"},
        ]
        master, _, summary = select(inventory, config)
        self.assertEqual(summary["allocation"], "deterministic capacity flow")
        self.assertEqual(sum(row["primary_view"] == "B" for row in master), 1)
        self.assertEqual(sum(row["primary_view"] == "A" for row in master), 2)

        represented = [
            {**row, "uuid": row["uuid"] + "/L0/040" if index % 2 == 0 else row["uuid"]}
            for index, row in enumerate(inventory)
        ]
        represented_master, _, _ = select(represented, config)
        self.assertEqual(
            {(row["uuid"].split("/", 1)[0], row["primary_view"]) for row in master},
            {(row["uuid"].split("/", 1)[0], row["primary_view"]) for row in represented_master},
        )

    def test_capacity_flow_reports_infeasible_view(self):
        config = {
            "seed": 1,
            "target_count": 2,
            "unclassified_view": "00",
            "allow_unclassified_fallback": False,
            "views": [
                {"id": "00", "label": "Unclassified", "quota": 0},
                {"id": "A", "label": "A", "quota": 1},
                {"id": "B", "label": "B", "quota": 1},
            ],
        }
        inventory = [
            {"uuid": "A-1", "filename": "1.jpg", "candidate_views": "A", "safety_status": "clear"},
            {"uuid": "A-2", "filename": "2.jpg", "candidate_views": "A", "safety_status": "clear"},
        ]
        with self.assertRaisesRegex(ValueError, '"B": 1'):
            select(inventory, config)

    def test_evaluation_reports_denominators_and_uncertainty(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
            row["error_category"] = "visible-fit"
        report, passed = evaluate(sample, self.config)
        self.assertTrue(passed)
        self.assertEqual(report["decisive_count"], len(sample))
        self.assertEqual(len(report["precision_wilson_95"]), 2)
        self.assertTrue(all("decisive" in view for view in report["by_view"].values()))

    def test_evaluation_rejects_sample_drift_and_underpowered_view(self):
        master, _, _ = select(self.inventory, self.config)
        sample = make_sample(master, 3, 20260710)
        for row in sample:
            row["judgment"] = "fit"
        dropped_view = sample[0]["primary_view"]
        missing = [row for row in sample if row["primary_view"] != dropped_view]
        report, passed = evaluate(missing, self.config)
        self.assertFalse(passed)
        self.assertTrue(report["integrity_errors"])
        self.assertIn(dropped_view, report["missing_views"])

        underpowered = [dict(row) for row in sample]
        view = underpowered[0]["primary_view"]
        seen = False
        for row in underpowered:
            if row["primary_view"] == view and seen:
                row["judgment"] = "uncertain"
            elif row["primary_view"] == view:
                seen = True
        report, passed = evaluate(underpowered, self.config)
        self.assertFalse(passed)
        self.assertIn(view, report["insufficient_views"])

        relabeled = [dict(row) for row in sample]
        views = sorted({row["primary_view"] for row in relabeled})
        replacements = {views[0]: views[1], views[1]: views[0]}
        for row in relabeled:
            if row["primary_view"] in replacements:
                row["primary_view"] = replacements[row["primary_view"]]
        report, passed = evaluate(relabeled, self.config)
        self.assertFalse(passed)
        self.assertIn("membership does not match", "; ".join(report["integrity_errors"]))

    def test_evaluation_sample_digest_binds_canonical_identity_and_view(self):
        rows = [
            {"uuid": "A/L0/001", "primary_view": "01"},
            {"uuid": "B/L0/040", "primary_view": "02"},
        ]
        self.assertEqual(
            evaluation_sample_sha256(rows),
            evaluation_sample_sha256(list(reversed(rows))),
        )
        self.assertEqual(
            evaluation_sample_sha256(rows),
            evaluation_sample_sha256([
                {"uuid": "A", "primary_view": "01"},
                {"uuid": "B", "primary_view": "02"},
            ]),
        )
        relabeled = [dict(row) for row in rows]
        relabeled[0]["primary_view"] = "02"
        self.assertNotEqual(evaluation_sample_sha256(rows), evaluation_sample_sha256(relabeled))

    def test_validation_uses_canonical_identity(self):
        config = {
            "target_count": 1,
            "unclassified_view": "00",
            "views": [{"id": "00", "label": "Unclassified", "quota": 1}],
        }
        master = [{
            "uuid": "ASSET/L0/001",
            "filename": "asset.jpg",
            "primary_view": "00",
            "selection_reason": "visible fit",
        }]
        holds = [{"uuid": "ASSET", "filename": "hold.jpg"}]
        errors, _ = validate(master, holds, config)
        self.assertTrue(any("overlaps safety holds" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
