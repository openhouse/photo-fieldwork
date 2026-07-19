import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.review import build_review_workbench
from photo_fieldwork.run_state import (
    append_config_decision,
    freeze_lock,
    initialize,
    read_events,
    read_state,
    record_invalidation,
    record_transition,
    recover_state,
    verify_lock,
)


class RunStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "v-test"
        initialize(self.workspace, "v-test", 2, "source://test", 10)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative: str, value: str) -> Path:
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def test_workspace_is_private_and_transition_hashes_artifacts(self):
        self.assertEqual(os.stat(self.workspace).st_mode & 0o777, 0o700)
        brief = self.write("manifests/brief.txt", "brief")
        record_transition(self.workspace, "brief", "complete", outputs={"brief": brief})
        source = self.write("manifests/source.txt", "source")
        record_transition(self.workspace, "source", "complete", outputs={"source": source})
        output = self.write("manifests/output.txt", "output")
        state = record_transition(
            self.workspace,
            "retrieval",
            "complete",
            {"source": source},
            {"candidate_pool": output},
            {"count": 2},
        )
        attempt = state["phases"]["retrieval"]["attempts"][0]
        self.assertEqual(len(attempt["inputs"]["source"]["sha256"]), 64)
        self.assertEqual(attempt["facts"]["count"], 2)
        events = (self.workspace / "run-events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(events), 4)

    def test_transition_requires_order_and_expected_revision(self):
        with self.assertRaisesRegex(ValueError, "predecessors complete"):
            record_transition(self.workspace, "evaluation", "complete")
        current = read_state(self.workspace)["revision"]
        brief = self.write("manifests/brief.txt", "brief")
        with self.assertRaisesRegex(ValueError, "revision conflict"):
            record_transition(
                self.workspace,
                "brief",
                "complete",
                outputs={"brief": brief},
                expected_revision=current + 1,
            )
        state = record_transition(
            self.workspace,
            "brief",
            "complete",
            outputs={"brief": brief},
            expected_revision=current,
        )
        self.assertEqual(state["revision"], current + 1)
        with self.assertRaisesRegex(ValueError, "without output evidence"):
            record_transition(self.workspace, "source", "complete")

    def test_recovery_rebuilds_state_and_reports_artifact_drift(self):
        brief = self.write("manifests/brief.txt", "brief")
        record_transition(self.workspace, "brief", "complete", outputs={"brief": brief})
        (self.workspace / "run-state.json").write_text("{", encoding="utf-8")
        recovered = recover_state(self.workspace)
        self.assertEqual(recovered["recovery_report"]["status"], "PASS")
        self.assertEqual(read_state(self.workspace)["phases"]["brief"]["status"], "complete")
        brief.write_text("altered", encoding="utf-8")
        (self.workspace / "run-state.json").write_text("{", encoding="utf-8")
        blocked = recover_state(self.workspace)
        self.assertEqual(blocked["recovery_report"]["status"], "BLOCKED")
        with self.assertRaisesRegex(ValueError, "artifact drift"):
            source = self.write("manifests/source.txt", "source")
            record_transition(self.workspace, "source", "complete", outputs={"source": source})

    def test_legacy_schema_v2_state_is_migrated_before_recovery(self):
        legacy_workspace = Path(self.temp.name) / "legacy"
        legacy_workspace.mkdir(mode=0o700)
        legacy_state = {
            "schema_version": 2,
            "run_id": "legacy",
            "version": "v-old",
            "status": "initialized",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "target_count": 1,
            "source": {"identifier": "source://legacy", "expected_count": 2},
            "tool": {},
            "phases": {
                phase: {"status": "pending", "attempts": []}
                for phase in (
                    "brief", "source", "retrieval", "inspection", "evaluation",
                    "final_freeze", "validation", "write_test", "production_commit",
                    "independent_verification",
                )
            },
        }
        (legacy_workspace / "run-state.json").write_text(
            json.dumps(legacy_state), encoding="utf-8"
        )
        migrated = read_state(legacy_workspace)
        self.assertEqual(migrated["event_count"], 1)
        self.assertEqual(migrated["source"]["membership_sha256"], None)
        self.assertEqual(
            read_events(legacy_workspace)[0]["details"],
            {"legacy_state_migration": True},
        )

    def test_artifact_drift_invalidation_appends_and_allows_repair(self):
        brief = self.write("manifests/brief.txt", "brief")
        state = record_transition(
            self.workspace,
            "brief",
            "complete",
            outputs={"brief": brief},
            expected_revision=1,
        )
        source = self.write("manifests/source.txt", "source")
        state = record_transition(
            self.workspace,
            "source",
            "complete",
            outputs={"source": source},
            expected_revision=state["revision"],
        )
        source.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact drift"):
            record_transition(
                self.workspace,
                "retrieval",
                "in-progress",
                expected_revision=state["revision"],
            )
        with self.assertRaisesRegex(ValueError, "earliest drift phase source"):
            record_invalidation(
                self.workspace,
                "brief",
                "wrong restart point",
                expected_revision=state["revision"],
            )
        invalidated = record_invalidation(
            self.workspace,
            "source",
            "source artifact changed",
            expected_revision=state["revision"],
        )
        self.assertEqual(invalidated["revision"], state["revision"] + 1)
        self.assertEqual(
            invalidated["phases"]["source"]["attempts"][0]["status"],
            "invalidated",
        )
        repaired = self.write("manifests/source-repaired.txt", "repaired")
        resumed = record_transition(
            self.workspace,
            "source",
            "complete",
            outputs={"source": repaired},
            expected_revision=invalidated["revision"],
        )
        self.assertEqual(resumed["phases"]["source"]["status"], "complete")
        events = read_events(self.workspace)
        self.assertEqual(events[-2]["event_type"], "artifact_invalidation")

    def test_lock_detects_post_freeze_mutation(self):
        config = self.write("final/effective-final-config.json", "{}")
        master = self.write("final/proposed-master.csv", "uuid\nA\n")
        holds = self.write("final/hold-sensitive.csv", "uuid\nB\n")
        freeze_lock(self.workspace, config, master, holds)
        errors, report = verify_lock(self.workspace)
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "PASS")
        master.write_text("uuid\nC\n", encoding="utf-8")
        errors, report = verify_lock(self.workspace)
        self.assertTrue(errors)
        self.assertEqual(report["status"], "FAIL")

    def test_review_workbench_omits_people_and_has_no_external_requests(self):
        previews = self.workspace / "previews"
        previews.mkdir(exist_ok=True)
        (previews / "A_L0_001.jpg").write_bytes(b"private-preview-bytes")
        output = self.workspace / "review" / "index.html"
        sample = [
            {
                "uuid": "A/L0/001",
                "primary_view": "01",
                "score_total": "10",
                "visible_context": "worktable",
                "persons": "Private Person",
                "place": "Exact home address",
            }
        ]
        build_review_workbench(sample, previews, output)
        document = output.read_text(encoding="utf-8")
        self.assertNotIn("Private Person", document)
        self.assertNotIn("Exact home address", document)
        self.assertNotIn("https://", document)
        self.assertIn("connect-src 'none'", document)
        self.assertNotIn("../previews", document)
        self.assertIn("review-assets/A_L0_001.jpg", document)
        copied = output.parent / "review-assets" / "A_L0_001.jpg"
        self.assertTrue(copied.exists())
        self.assertEqual(os.stat(copied).st_mode & 0o777, 0o600)

    def test_review_export_preserves_final_holdout_design_fields(self):
        previews = self.workspace / "previews"
        previews.mkdir(exist_ok=True)
        (previews / "B_L0_001.jpg").write_bytes(b"private-preview-bytes")
        output = self.workspace / "review" / "index.html"
        sample = [
            {
                "uuid": "B/L0/001",
                "primary_view": "02",
                "sample_role": "final-holdout-estimate",
                "estimate_included": "true",
                "sample_seed": "44",
                "population_count": "3800",
                "full_master_count": "4000",
                "view_population_count": "800",
                "perceptual_cluster": "pc-opaque",
                "duplicate_group": "dg-opaque",
                "burst_group": "bg-opaque",
            }
        ]
        build_review_workbench(sample, previews, output)
        document = output.read_text(encoding="utf-8")
        for expected in (
            "final-holdout-estimate",
            '"master_sha256": ""',
            '"proposal_id": ""',
            '"perceptual_cluster": "pc-opaque"',
            '"duplicate_group": "dg-opaque"',
            '"burst_group": "bg-opaque"',
            '"estimate_included": "true"',
            '"population_count": "3800"',
            '"full_master_count": "4000"',
            '"view_population_count": "800"',
            '"sample_role","master_sha256","proposal_id","perceptual_cluster","duplicate_group","burst_group","estimate_included","sample_seed","population_count","full_master_count","view_population_count"',
        ):
            self.assertIn(expected, document)

    def test_config_decisions_form_a_hash_chain(self):
        first = append_config_decision(
            self.workspace,
            "round-01",
            "views.07.status",
            "active",
            "unsupported",
            "No inspected image supported the project-specific claim.",
            "editor",
        )
        second = append_config_decision(
            self.workspace,
            "round-02",
            "views.07.quota",
            10,
            0,
            "Preserve the empty category without substitution.",
            "editor",
        )
        self.assertEqual(second["previous_hash"], first["record_hash"])
        self.assertNotEqual(second["record_hash"], first["record_hash"])


if __name__ == "__main__":
    unittest.main()
