import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from copy import deepcopy
from pathlib import Path

from photo_fieldwork.contracts import canonical_sha256, validate_plan
from photo_fieldwork.cli import command_select
from photo_fieldwork.pipeline import SelectionInfeasible, select, validate, write_csv


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
BRIDGE_SPEC = importlib.util.spec_from_file_location("composite_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(BRIDGE_SPEC)
BRIDGE_SPEC.loader.exec_module(bridge)

SPLIT_PATH = ROOT / "skills" / "curate-apple-photos" / "scripts" / "audit_eval_split.py"
SPLIT_SPEC = importlib.util.spec_from_file_location("audit_eval_split", SPLIT_PATH)
split_audit = importlib.util.module_from_spec(SPLIT_SPEC)
SPLIT_SPEC.loader.exec_module(split_audit)


def config(quotas):
    return {
        "schema_version": 2,
        "seed": 7,
        "target_count": sum(quotas.values()),
        "unclassified_view": next(iter(quotas)),
        "minimum_named_people_fraction": 0,
        "minimum_person_free_fraction": 0,
        "views": [
            {"id": view, "label": view, "quota": quota, "evaluation_mode": "material"}
            for view, quota in quotas.items()
        ],
    }


def row(identifier, view, **extra):
    return {
        "uuid": identifier,
        "filename": f"{identifier}.jpg",
        "assigned_view": view,
        "assignment_status": "assigned",
        "assignment_reason": "synthetic visible evidence",
        "assignment_version": "eval-v1",
        "evidence_confidence": "high",
        "safety_status": "clear",
        **extra,
    }


class CompositeContractTests(unittest.TestCase):
    def test_exact_view_scarcity_fails_with_structured_deficit(self):
        inventory = [row("A", "one"), row("B", "one"), row("C", "one")]
        with self.assertRaises(SelectionInfeasible) as raised:
            select(inventory, config({"one": 1, "two": 1}))
        self.assertEqual(
            raised.exception.deficits["two"],
            {"required": 1, "available": 0, "deficit": 1},
        )

    def test_selection_command_preserves_a_structured_failure_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory_path = root / "inventory.csv"
            config_path = root / "config.json"
            output = root / "run"
            write_csv(inventory_path, [row("A", "one"), row("B", "one")])
            config_path.write_text(json.dumps(config({"one": 1, "two": 1})), encoding="utf-8")
            status = command_select(
                Namespace(config=config_path, inventory=inventory_path, output=output)
            )
            report = json.loads(
                (output / "reports/selection-failure.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status, 2)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["deficits"]["two"]["deficit"], 1)

    def test_hold_propagates_through_transitive_duplicate_and_burst_relations(self):
        inventory = [
            row("HOLD", "one", safety_status="hold-human", duplicate_group="dup"),
            row("BRIDGE", "one", duplicate_group="dup", burst_group="burst"),
            row("RELATED", "one", burst_group="burst"),
            row("SAFE", "one"),
        ]
        master, holds, _ = select(inventory, config({"one": 1}))
        self.assertEqual([item["uuid"] for item in master], ["SAFE"])
        self.assertEqual({item["uuid"] for item in holds}, {"HOLD", "BRIDGE", "RELATED"})
        propagated = {item["uuid"]: item for item in holds}
        self.assertEqual(propagated["RELATED"]["safety_status"], "hold-related")

    def test_validation_rejects_count_preserving_quota_drift(self):
        cfg = config({"one": 1, "two": 1})
        master, holds, _ = select([row("A", "one"), row("B", "two")], cfg)
        changed = deepcopy(master)
        changed[1]["assigned_view"] = "one"
        changed[1]["primary_view"] = "one"
        errors, report = validate(changed, holds, cfg)
        self.assertTrue(any("exact quotas" in error for error in errors))
        self.assertEqual(report["quota_drift"]["two"]["actual"], 0)

    def test_holdout_audit_catches_uuid_and_relation_leakage(self):
        report = split_audit.audit_split(
            [{"uuid": "A", "perceptual_cluster_id": "scene"}],
            [
                {"uuid": "A/L0/001", "perceptual_cluster_id": "other"},
                {"uuid": "B", "perceptual_cluster_id": "scene"},
            ],
            [],
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["leakage"]["tuning_uuid_overlap_count"], 1)
        self.assertEqual(report["leakage"]["tuning_cluster_overlap_count"], 1)
        self.assertNotIn("private_details", report)

    def test_run_state_rejects_stale_revision_and_chains_events(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            state = {
                "schema_version": 2,
                "run_id": "synthetic-run",
                "status": "initialized",
                "phases": {phase: "pending" for phase in bridge.RUN_PHASES},
                "phase_records": {},
                "revision": 0,
                "last_event_sha256": None,
            }
            (workspace / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
            bridge.update_run_state(
                workspace, "brief", "completed", expected_revision=0, actor="test"
            )
            updated = json.loads((workspace / "run-state.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["revision"], 1)
            event = json.loads((workspace / "run-events.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(event["event_sha256"], updated["last_event_sha256"])
            with self.assertRaisesRegex(ValueError, "stale run-state revision"):
                bridge.update_run_state(
                    workspace, "retrieval", "completed", expected_revision=0, actor="test"
                )

    def test_run_state_rejects_a_tampered_event_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            state = {
                "schema_version": 2,
                "run_id": "synthetic-run",
                "status": "initialized",
                "phases": {phase: "pending" for phase in bridge.RUN_PHASES},
                "phase_records": {},
                "revision": 0,
                "last_event_sha256": None,
            }
            (workspace / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
            bridge.update_run_state(workspace, "brief", "completed", expected_revision=0)
            event_path = workspace / "run-events.jsonl"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["actor"] = "substituted"
            event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid event hash"):
                bridge.update_run_state(
                    workspace, "retrieval", "completed", expected_revision=1
                )

    def test_plan_validation_rejects_rehashed_artifact_substitution(self):
        source = {
            "schema_version": 1,
            "source_adapter": "synthetic",
            "source_identifier": "synthetic://source",
            "source_title": "Synthetic",
            "predicate_version": "all-v1",
            "observed_count": 1,
            "membership_sha256": "a" * 64,
            "library_fingerprint": "",
            "inventory_sha256": "",
            "artifact_sensitivity": "public-safe",
            "created_at": "2026-07-19T00:00:00Z",
        }
        source["source_fingerprint"] = canonical_sha256(
            {
                "schema_version": 1,
                "source_adapter": "synthetic",
                "source_identifier": "synthetic://source",
                "predicate_version": "all-v1",
                "observed_count": 1,
                "membership_sha256": "a" * 64,
                "library_fingerprint": "",
            }
        )
        evaluation = {
            "passed": True,
            "proposal_id": "pfp-" + "b" * 16,
            "master_sha256": "b" * 64,
            "config_sha256": "c" * 64,
        }
        validation = {
            "status": "PASS",
            "proposal_id": evaluation["proposal_id"],
            "master_sha256": evaluation["master_sha256"],
            "config_sha256": evaluation["config_sha256"],
        }
        plan = {
            "schema_version": 2,
            "operation": "snapshot-membership",
            "source": source,
            "source_fingerprint": source["source_fingerprint"],
            "proposal_id": evaluation["proposal_id"],
            "master_sha256": evaluation["master_sha256"],
            "config_sha256": evaluation["config_sha256"],
            "evaluation": evaluation,
            "evaluation_report_sha256": canonical_sha256(evaluation),
            "validation": validation,
            "validation_report_sha256": canonical_sha256(validation),
        }
        from photo_fieldwork.contracts import finalize_plan

        plan = finalize_plan(plan)
        validate_plan(plan)
        tampered = deepcopy(plan)
        tampered["evaluation"]["passed"] = False
        tampered["plan_sha256"] = canonical_sha256(
            {key: value for key, value in tampered.items() if key != "plan_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "evaluation_report_sha256"):
            validate_plan(tampered)


if __name__ == "__main__":
    unittest.main()
