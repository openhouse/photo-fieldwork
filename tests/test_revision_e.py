import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.artifacts import diff_csv, merge_jsonl, replacement_audit, union_csv
from photo_fieldwork.decisions import append_decisions, apply_decisions, normalize_feedback
from photo_fieldwork.history import compare_versions, register_version, verify_registry
from photo_fieldwork.pipeline import evaluate, read_config, select, write_csv
from photo_fieldwork.publication import scaffold, validate_clearance
from photo_fieldwork.review import build_review_surface
from photo_fieldwork.runstate import advance, initialize, load, verify


ROOT = Path(__file__).resolve().parents[1]


def row(uuid, views="00", persons="", **values):
    return {
        "uuid": uuid,
        "filename": f"{uuid}.jpg",
        "candidate_views": views,
        "persons": persons,
        "evidence_confidence": "medium",
        "safety_status": "clear",
        **values,
    }


class RevisionETests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_rows(self, name, rows):
        path = self.root / name
        write_csv(path, rows)
        return path

    def test_assignment_satisfies_quotas_and_both_people_floors_jointly(self):
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "seed": 7,
                    "target_count": 4,
                    "unclassified_view": "A",
                    "minimum_named_people_fraction": 0.5,
                    "minimum_person_free_fraction": 0.5,
                    "views": [
                        {"id": "A", "label": "A", "quota": 2},
                        {"id": "B", "label": "B", "quota": 2},
                    ],
                }
            ),
            encoding="utf-8",
        )
        config = read_config(config_path)
        inventory = [
            row("n-flex", "A;B", "Named"),
            row("n-a", "A", "Named"),
            row("f-flex", "A;B"),
            row("f-b", "B"),
            row("extra", "A;B", "Named"),
        ]
        master, _, report = select(inventory, config)
        self.assertEqual(report["view_counts"], {"A": 2, "B": 2})
        self.assertEqual(report["named_people_count"], 2)
        self.assertEqual(report["person_free_count"], 2)
        self.assertEqual(len(master), 4)

    def test_assignment_reports_infeasible_view_scarcity(self):
        config = read_config(ROOT / "config" / "starter.json")
        with self.assertRaisesRegex(ValueError, "scarcity"):
            select([row(f"x-{index}") for index in range(12)], config)

    def test_rejected_unclassified_view_does_not_reenter(self):
        config = read_config(ROOT / "config" / "starter.json")
        inventory = [row(f"x-{index}", "", excluded_views="00") for index in range(30)]
        with self.assertRaisesRegex(ValueError, "unable to satisfy"):
            select(inventory, config)

    def test_per_view_failure_cannot_hide_behind_overall_precision(self):
        config = read_config(ROOT / "config" / "starter.json")
        config["minimum_view_eval_precision"] = 0.75
        feedback = []
        for view in ("00", "01", "02", "03", "04"):
            feedback.extend(
                [
                    {"uuid": f"{view}-a", "filename": "a", "primary_view": view, "judgment": "fit"},
                    {"uuid": f"{view}-b", "filename": "b", "primary_view": view, "judgment": "fit"},
                ]
            )
        feedback[3]["judgment"] = "reject"
        report, passed = evaluate(feedback, config)
        self.assertGreater(report["precision"], config["minimum_eval_precision"])
        self.assertFalse(passed)
        self.assertEqual(report["by_view"]["01"]["state"], "fail")

    def test_missing_view_evidence_is_not_a_pass(self):
        config = read_config(ROOT / "config" / "starter.json")
        feedback = [
            {"uuid": f"x-{view}", "filename": "x", "primary_view": view, "judgment": "fit"}
            for view in ("00", "01", "02", "03", "04")
        ]
        report, passed = evaluate(feedback, config)
        self.assertFalse(passed)
        self.assertTrue(all(item["state"] == "insufficient-evidence" for item in report["by_view"].values()))

    def test_decisions_prevent_reentry_and_propagate_safety_holds(self):
        inventory = [
            row("a", "01;02", duplicate_group="d1"),
            row("b", "01", duplicate_group="d1"),
        ]
        decisions = normalize_feedback(
            [
                {"uuid": "a", "filename": "a", "primary_view": "01", "judgment": "reject"},
                {
                    "uuid": "a",
                    "filename": "a",
                    "primary_view": "02",
                    "judgment": "uncertain",
                    "editorial_safety_status": "hold",
                },
            ],
            "round-1",
            "delegated-panel",
        )
        output, report = apply_decisions(inventory, decisions)
        by_id = {item["uuid"]: item for item in output}
        self.assertEqual(by_id["a"]["candidate_views"], "02")
        self.assertEqual(by_id["a"]["excluded_views"], "01")
        self.assertEqual(by_id["b"]["safety_status"], "hold")
        self.assertEqual(report["held_or_propagated_count"], 2)

    def test_later_decision_links_to_the_decision_it_supersedes(self):
        first = normalize_feedback(
            [{"uuid": "a", "filename": "a", "primary_view": "01", "judgment": "reject"}]
        )
        second = normalize_feedback(
            [{"uuid": "a", "filename": "a", "primary_view": "01", "judgment": "fit"}]
        )
        ledger = append_decisions(first, second)
        self.assertEqual(ledger[-1]["supersedes"], ledger[0]["decision_id"])

    def test_run_state_is_ordered_idempotent_and_tamper_evident(self):
        state_path = self.root / "run-state.json"
        receipt = self.root / "brief.md"
        receipt.write_text("brief", encoding="utf-8")
        initialize(state_path, "run-1", 100, "source")
        advance(state_path, "inventoried", [receipt])
        advance(state_path, "inventoried", [receipt])
        self.assertEqual(load(state_path)["phase"], "inventoried")
        self.assertEqual(verify(load(state_path)), [])
        receipt.write_text("changed", encoding="utf-8")
        self.assertRegex(verify(load(state_path))[0], "(size|hash) changed")

    def test_artifact_operations_preserve_uuid_integrity(self):
        first = self.write_rows("first.csv", [row("a"), row("b")])
        second = self.write_rows("second.csv", [row("b"), row("c")])
        rows, report = union_csv([first, second])
        self.assertEqual([item["uuid"] for item in rows], ["a", "b", "c"])
        self.assertEqual(report["unique"], 3)
        added, removed, diff = diff_csv(first, second)
        self.assertEqual([item["uuid"] for item in added], ["c"])
        self.assertEqual([item["uuid"] for item in removed], ["a"])
        self.assertEqual(diff["changed_shared_rows"], 0)
        jsonl_a = self.root / "a.jsonl"
        jsonl_b = self.root / "b.jsonl"
        jsonl_a.write_text('{"asset_identifier":"a/L0/001","ok":true}\n', encoding="utf-8")
        jsonl_b.write_text('{"asset_identifier":"b/L0/001","ok":true}\n', encoding="utf-8")
        merged, _ = merge_jsonl([jsonl_a, jsonl_b])
        self.assertEqual(len(merged), 2)
        entrants, audit = replacement_audit(second, [first])
        self.assertEqual([item["uuid"] for item in entrants], ["c"])
        self.assertEqual(audit["status"], "REVIEW_REQUIRED")

    def test_review_surface_is_offline_and_keeps_missing_previews_visible(self):
        output = self.root / "review"
        previews = self.root / "previews"
        previews.mkdir()
        (previews / "a_L0_001.jpg").write_bytes(b"local-preview-placeholder")
        report = build_review_surface([row("a"), row("b")], previews, output)
        document = (output / "index.html").read_text(encoding="utf-8")
        self.assertFalse(report["network_required"])
        self.assertEqual(report["previews_missing"], 1)
        self.assertEqual(report["previews_found"], 1)
        self.assertIn("Preview unavailable", document)
        self.assertIn("Download feedback CSV", document)
        self.assertIn('/[",\\n]/', document)
        self.assertIn(".join('\\n')+'\\n'", document)

    def test_publication_manifest_defaults_closed_and_requires_evidence(self):
        rows = scaffold([row("a")])
        self.assertEqual(rows[0]["publication_cleared"], "false")
        rows[0]["publication_cleared"] = "true"
        errors, report = validate_clearance(rows)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("caption", errors[0])

    def test_version_registry_is_idempotent_and_detects_manifest_change(self):
        before = self.write_rows("before.csv", [row("a"), row("b")])
        after = self.write_rows("after.csv", [row("b"), row("c")])
        registry = self.root / "versions.json"
        first = register_version(registry, "v1", before, "source", 2)
        second = register_version(registry, "v1", before, "source", 2)
        self.assertEqual(first["membership_sha256"], second["membership_sha256"])
        self.assertEqual(verify_registry(registry)[1]["status"], "PASS")
        self.assertEqual(compare_versions(before, after)["retained"], 1)
        with before.open("a", encoding="utf-8") as handle:
            handle.write("changed")
        self.assertEqual(verify_registry(registry)[1]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
