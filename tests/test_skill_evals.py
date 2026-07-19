import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skills" / "curate-apple-photos" / "evals" / "validate_response.py"
SPEC = importlib.util.spec_from_file_location("validate_response", MODULE_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(VALIDATOR)


class SkillEvalTests(unittest.TestCase):
    def test_suite_is_internally_consistent(self):
        evals_root = MODULE_PATH.parent
        self.assertEqual(
            VALIDATOR.check_suite(evals_root / "evals.json", evals_root / "rubric.json"),
            [],
        )

    def test_grader_rejects_uncited_and_mutating_blocker(self):
        fixture = {"evidence": [{"id": "source-manifest"}, {"id": "doctor-live-count"}]}
        rubric = {
            "disposition": "BLOCKED",
            "gate": "source_freshness",
            "editor_field_status": "blocked",
            "publication_status": "not-assessed",
            "required_codes": ["SOURCE_COUNT_MISMATCH", "FRESH_INVENTORY_REQUIRED"],
            "required_evidence": ["source-manifest", "doctor-live-count"],
            "photos_mutation_allowed": False,
        }
        response = {
            "eval_id": 1,
            "disposition": "BLOCKED",
            "gate": "source_freshness",
            "editor_field_status": "blocked",
            "publication_status": "not-assessed",
            "findings": [{
                "code": "SOURCE_COUNT_MISMATCH",
                "severity": "blocker",
                "evidence_refs": ["source-manifest"],
                "required_action": "continue anyway",
            }],
            "next_actions": [{"action": "write albums", "mutates_photos": True}],
            "claims": [],
            "roleplay": [],
        }
        result = VALIDATOR.grade_response(1, response, fixture, rubric)
        self.assertGreater(result["summary"]["failed"], 0)

    def test_grader_accepts_evidence_closed_blocker(self):
        evals_root = MODULE_PATH.parent
        fixture = json.loads((evals_root / "fixtures" / "01-source-drift.json").read_text())
        rubric = json.loads((evals_root / "rubric.json").read_text())["evals"]["1"]
        response = {
            "eval_id": 1,
            "disposition": "BLOCKED",
            "gate": "source_freshness",
            "editor_field_status": "blocked",
            "publication_status": "not-assessed",
            "findings": [
                {
                    "code": "SOURCE_COUNT_MISMATCH",
                    "severity": "blocker",
                    "evidence_refs": ["source-manifest", "doctor-live-count"],
                    "required_action": "Freeze a new source inventory.",
                },
                {
                    "code": "FRESH_INVENTORY_REQUIRED",
                    "severity": "blocker",
                    "evidence_refs": ["source-manifest", "doctor-live-count"],
                    "required_action": "Rerun doctor against the new manifest.",
                },
            ],
            "next_actions": [{"action": "Build a new immutable inventory", "mutates_photos": False}],
            "claims": [{
                "claim": "The frozen count 100000 differs from the live count 100077.",
                "status": "supported",
                "evidence_refs": ["source-manifest", "doctor-live-count"],
            }],
            "roleplay": [],
        }
        result = VALIDATOR.grade_response(1, response, fixture, rubric)
        self.assertEqual(result["summary"]["failed"], 0)

    def test_grader_counts_evidence_cited_in_supported_claims(self):
        evals_root = MODULE_PATH.parent
        fixture = json.loads((evals_root / "fixtures" / "01-source-drift.json").read_text())
        rubric = json.loads((evals_root / "rubric.json").read_text())["evals"]["1"]
        response = {
            "eval_id": 1,
            "disposition": "BLOCKED",
            "gate": "source_freshness",
            "editor_field_status": "blocked",
            "publication_status": "not-assessed",
            "findings": [
                {
                    "code": "SOURCE_COUNT_MISMATCH",
                    "severity": "blocker",
                    "evidence_refs": ["doctor-live-count"],
                    "required_action": "Stop the transition.",
                },
                {
                    "code": "FRESH_INVENTORY_REQUIRED_V04",
                    "severity": "blocker",
                    "evidence_refs": ["doctor-live-count"],
                    "required_action": "Freeze a fresh inventory.",
                },
            ],
            "next_actions": [{"action": "Create immutable inventory", "mutates_photos": False}],
            "claims": [{
                "claim": "The frozen count 100000 differs from the live count 100077.",
                "status": "supported",
                "evidence_refs": ["source-manifest"],
            }],
            "roleplay": [],
        }
        result = VALIDATOR.grade_response(1, response, fixture, rubric)
        self.assertEqual(result["summary"]["failed"], 0)

    def test_grader_rejects_wrong_counts_with_valid_evidence_references(self):
        evals_root = MODULE_PATH.parent
        fixture = json.loads((evals_root / "fixtures" / "01-source-drift.json").read_text())
        rubric = json.loads((evals_root / "rubric.json").read_text())["evals"]["1"]
        response = {
            "eval_id": 1,
            "disposition": "BLOCKED",
            "gate": "source_freshness",
            "editor_field_status": "in-progress",
            "publication_status": "not-assessed",
            "findings": [
                {
                    "code": "SOURCE_COUNT_MISMATCH",
                    "severity": "blocker",
                    "evidence_refs": ["source-manifest", "doctor-live-count"],
                    "required_action": "The wrong count 200000 differs from 200077.",
                },
                {
                    "code": "FRESH_INVENTORY_REQUIRED",
                    "severity": "blocker",
                    "evidence_refs": ["source-manifest", "doctor-live-count"],
                    "required_action": "Freeze a new inventory.",
                },
            ],
            "next_actions": [{"action": "Create immutable inventory", "mutates_photos": False}],
            "claims": [],
            "roleplay": [],
        }
        result = VALIDATOR.grade_response(1, response, fixture, rubric)
        failed = [item["text"] for item in result["expectations"] if not item["passed"]]
        self.assertIn("fixture-specific facts appear in the response", failed)


if __name__ == "__main__":
    unittest.main()
