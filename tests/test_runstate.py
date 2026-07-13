import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from photo_fieldwork.cli import command_apply_feedback
from photo_fieldwork.handoff import render_handoff
from photo_fieldwork.pipeline import read_csv, write_csv
from photo_fieldwork.runstate import PHASES, checkpoint, initialize_run, load_state, next_phase
from photo_fieldwork.review import render_review_workspace


class RunStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.brief = self.root / "brief-source.md"
        self.profile = self.root / "profile.json"
        self.brief.write_text("# Synthetic brief\n", encoding="utf-8")
        self.profile.write_text(
            json.dumps(
                {
                    "workspace_root": str(self.root / "runs"),
                    "photos_database": str(self.root / "Photos.sqlite"),
                    "permissioned_app": str(self.root / "Archive.app"),
                    "source": {"kind": "album", "identifier": "SOURCE", "expected_count": 3},
                    "folders": {
                        "root_identifier": "ROOT",
                        "private_identifier": "PRIVATE",
                        "audit_identifier": "AUDIT",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.workspace = self.root / "runs" / "v-test"

    def tearDown(self):
        self.temp.cleanup()

    def test_run_initializes_privately_and_resumes(self):
        state, created = initialize_run(self.workspace, self.brief, self.profile, "v-test", 10)
        self.assertTrue(created)
        self.assertEqual(next_phase(state), PHASES[0])
        resumed, created = initialize_run(self.workspace, self.brief, self.profile, "v-test", 10)
        self.assertFalse(created)
        self.assertEqual(resumed["run_id"], state["run_id"])

    def test_checkpoint_is_idempotent_and_detects_changed_artifact(self):
        initialize_run(self.workspace, self.brief, self.profile, "v-test", 10)
        receipt = self.workspace / "reports" / "doctor.json"
        receipt.write_text("{}\n", encoding="utf-8")
        state, changed = checkpoint(self.workspace, PHASES[0], [receipt])
        self.assertTrue(changed)
        self.assertEqual(next_phase(state), PHASES[1])
        _, changed = checkpoint(self.workspace, PHASES[0], [receipt])
        self.assertFalse(changed)
        receipt.write_text('{"changed": true}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "different artifact digests"):
            checkpoint(self.workspace, PHASES[0], [receipt])

    def test_checkpoint_requires_prior_phase_and_receipt(self):
        initialize_run(self.workspace, self.brief, self.profile, "v-test", 10)
        with self.assertRaisesRegex(ValueError, "requires at least one artifact"):
            checkpoint(self.workspace, PHASES[0], [])
        receipt = self.workspace / "reports" / "later.json"
        receipt.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "prior phases pending"):
            checkpoint(self.workspace, PHASES[1], [receipt])

    def test_state_rejects_profile_drift(self):
        initialize_run(self.workspace, self.brief, self.profile, "v-test", 10)
        profile = json.loads(self.profile.read_text(encoding="utf-8"))
        profile["source"]["expected_count"] = 4
        self.profile.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "different local profile"):
            initialize_run(self.workspace, self.brief, self.profile, "v-test", 10)
        self.assertEqual(load_state(self.workspace)["target_count"], 10)

    def test_state_rejects_resume_target_drift(self):
        initialize_run(self.workspace, self.brief, self.profile, "v-test", 10)
        with self.assertRaisesRegex(ValueError, "version or target"):
            initialize_run(self.workspace, self.brief, self.profile, "v-test", 11)


class HandoffTests(unittest.TestCase):
    def record(self) -> dict:
        return {
            "records": [
                {
                    "id": "material-practice",
                    "public_safe_observation": "Reviewed photographs show tools and working documents.",
                    "may_corroborate": ["A durable material practice."],
                    "does_not_establish": ["Authorship or project outcomes."],
                    "publication_boundary": "No image is approved for publication.",
                    "related_claim_ids": ["reviewable-artifacts-practice"],
                    "status": "draft",
                    "reviewed_at": "2026-07-13",
                }
            ]
        }

    def test_handoff_states_visual_evidence_boundary(self):
        rendered = render_handoff(self.record())
        self.assertIn("supporting evidence only", rendered)
        self.assertIn("Does not establish", rendered)
        self.assertNotIn("asset", rendered.lower())

    def test_handoff_rejects_private_operational_fields(self):
        data = self.record()
        data["records"][0]["uuid"] = "PRIVATE-ID"
        with self.assertRaisesRegex(ValueError, "prohibited fields"):
            render_handoff(data)

    def test_handoff_rejects_unsupported_fields(self):
        data = self.record()
        data["records"][0]["private_note"] = "not part of the public contract"
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            render_handoff(data)


class FeedbackTests(unittest.TestCase):
    def test_feedback_preserves_machine_and_human_safety_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = root / "inventory.csv"
            feedback = root / "feedback.csv"
            output = root / "updated.csv"
            write_csv(
                inventory,
                [
                    {"uuid": "MACHINE", "filename": "machine.jpg"},
                    {"uuid": "HUMAN", "filename": "human.jpg"},
                ],
            )
            write_csv(
                feedback,
                [
                    {
                        "uuid": "MACHINE",
                        "filename": "machine.jpg",
                        "judgment": "uncertain",
                        "safety_status": "machine-suspected",
                    },
                    {
                        "uuid": "HUMAN",
                        "filename": "human.jpg",
                        "judgment": "reject",
                        "safety_status": "human-confirmed-hold",
                    },
                ],
            )
            command_apply_feedback(Namespace(inventory=inventory, feedback=feedback, output=output))
            rows = {row["uuid"]: row for row in read_csv(output)}
            self.assertEqual(rows["MACHINE"]["safety_status"], "machine-suspected")
            self.assertEqual(rows["HUMAN"]["safety_status"], "human-confirmed-hold")


class ReviewWorkspaceTests(unittest.TestCase):
    def test_review_workspace_is_static_and_separates_decisions(self):
        html = render_review_workspace(
            [{"uuid": "DEMO-1", "filename": "demo.jpg", "primary_view": "01", "score_total": "1.0"}],
            Path("/private/example-previews"),
            "round-01",
            "editorial review",
        )
        self.assertIn("Export feedback CSV", html)
        self.assertIn("public_suitability", html)
        self.assertIn("provenance_status", html)
        self.assertIn('["uuid","filename","primary_view"', html)
        self.assertIn("No network service or upload", html)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
