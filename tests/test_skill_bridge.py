import importlib.util
import argparse
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.pipeline import (
    build_catalog_plan,
    config_sha256,
    master_sha256,
    membership_sha256,
    validate,
    write_csv,
)


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SkillBridgeTests(unittest.TestCase):
    def test_init_run_uses_reconcilable_v2_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(
                workspace_root=root,
                version="v-test",
                slug="bridge",
                target=10,
                source_id="SOURCE",
                source_count=42,
                source_profile=None,
            )
            self.assertEqual(bridge.command_init(args), 0)
            run = next(root.iterdir())
            state = json.loads((run / "run-state.json").read_text())
            self.assertEqual(state["schema_version"], 2)
            self.assertEqual(state["revision"], 1)
            self.assertEqual(state["source"]["expected_count"], 42)
            self.assertEqual(state["phases"]["retrieval"]["status"], "pending")
            events = [json.loads(line) for line in (run / "run-events.jsonl").read_text().splitlines()]
            self.assertEqual([(event["revision"], event["event"]) for event in events], [(1, "initialized")])

    def test_source_profile_can_read_count_from_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "inventory.sqlite"
            conn = sqlite3.connect(inventory)
            conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.executemany(
                "INSERT INTO meta VALUES (?, ?)",
                [("source_identifier", "visible-library-stills://v1"), ("source_count", "123")],
            )
            conn.commit()
            conn.close()
            profile = root / "source.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "visible-library-stills://v1",
                        "inventory": str(inventory),
                    }
                )
            )
            args = argparse.Namespace(source_profile=profile, source_id="unused", source_count=0)
            self.assertEqual(bridge.resolve_source(args), ("visible-library-stills://v1", 123))

    def test_local_identifier_is_canonical(self):
        self.assertEqual(bridge.local_identifier("ABC"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/001"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/040"), "ABC/L0/001")

    def test_folder_contract_uses_protected_identifiers(self):
        folders = bridge.folder_specs("v03 example", include_version=True)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["existing_identifier"], bridge.ROOT_FOLDER_ID)
        self.assertEqual(by_key["private"]["existing_identifier"], bridge.PRIVATE_FOLDER_ID)
        self.assertEqual(by_key["audit"]["existing_identifier"], bridge.AUDIT_FOLDER_ID)
        self.assertEqual(by_key["version"]["title"], "v03 example")

    def test_snapshot_writer_requires_unchanged_candidate_bound_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "run"
            workspace.mkdir()
            config = {
                "seed": 7,
                "target_count": 1,
                "unclassified_view": "A",
                "quota_mode": "exact",
                "views": [{"id": "A", "label": "Archive", "quota": 1}],
            }
            master = [{
                "uuid": "M", "filename": "m.jpg", "primary_view": "A",
                "selection_reason": "visible archive context", "safety_status": "clear",
            }]
            holds = [{"uuid": "H", "filename": "h.jpg", "safety_status": "hold"}]
            source = [
                {"uuid": "M", "filename": "m.jpg"},
                {"uuid": "H", "filename": "h.jpg"},
            ]
            evaluation = {
                "passed": True,
                "release_class": "editor-field",
                "master_sha256": master_sha256(master),
                "config_sha256": config_sha256(config),
                "evaluation_sample_sha256": "a" * 64,
                "per_view_failures": [],
                "precision": 1.0,
                "coverage": 1.0,
            }
            errors, validation = validate(
                master,
                holds,
                config,
                evaluation_report=evaluation,
            )
            validation["errors"] = errors
            release = build_catalog_plan(
                master,
                holds,
                config,
                "release",
                "Synthetic source",
                "SOURCE",
                len(source),
                membership_sha256(source),
                evaluation,
                validation,
            )
            paths = {
                "master": root / "master.csv",
                "holds": root / "holds.csv",
                "source_membership": root / "source.csv",
                "config": root / "config.json",
                "evaluation_report": root / "evaluation.json",
                "validation_report": root / "validation.json",
                "release_plan": root / "release.json",
            }
            write_csv(paths["master"], master)
            write_csv(paths["holds"], holds)
            write_csv(paths["source_membership"], source)
            paths["config"].write_text(json.dumps(config))
            paths["evaluation_report"].write_text(json.dumps(evaluation))
            paths["validation_report"].write_text(json.dumps(validation))
            paths["release_plan"].write_text(json.dumps(release))
            args = argparse.Namespace(
                workspace=workspace,
                target=1,
                version="v01",
                folder_title="v01 synthetic",
                view_column="primary_view",
                batch_size=100,
                source_id="SOURCE",
                source_count=2,
                source_profile=None,
                **paths,
            )

            self.assertEqual(bridge.command_snapshot_plans(args), 0)
            production_path = workspace / "manifests" / "v01-production-plan.json"
            production = json.loads(production_path.read_text())
            bridge.verify_plan_sha256(production)
            self.assertEqual(
                production["authorization"]["release_plan_sha256"],
                release["plan_sha256"],
            )

            mutated_master = [dict(master[0], safety_status="hold")]
            write_csv(paths["master"], mutated_master)
            with self.assertRaisesRegex(ValueError, "master_sha256"):
                bridge.command_snapshot_plans(args)
            write_csv(paths["master"], master)

            mutated_source = [source[0], {"uuid": "X", "filename": "x.jpg"}]
            write_csv(paths["source_membership"], mutated_source)
            with self.assertRaisesRegex(ValueError, "membership SHA-256"):
                bridge.command_snapshot_plans(args)
            write_csv(paths["source_membership"], source)

            mutated_evaluation = dict(evaluation, passed=False)
            paths["evaluation_report"].write_text(json.dumps(mutated_evaluation))
            with self.assertRaisesRegex(ValueError, "evaluation_report_sha256"):
                bridge.command_snapshot_plans(args)
            paths["evaluation_report"].write_text(json.dumps(evaluation))

            production["albums"][0]["asset_identifiers"] = ["X/L0/001"]
            production["plan_sha256"] = bridge.canonical_json_sha256(
                {key: value for key, value in production.items() if key != "plan_sha256"}
            )
            production_path.write_text(json.dumps(production))
            run_args = argparse.Namespace(
                plan=production_path,
                source_id="SOURCE",
                source_count=2,
                source_profile=None,
                **paths,
            )
            with self.assertRaisesRegex(ValueError, "outside the authorized master/HOLD set"):
                bridge.command_run_plan(run_args)

            production["operation"] = "unknown-write-operation"
            production["plan_sha256"] = bridge.canonical_json_sha256(
                {key: value for key, value in production.items() if key != "plan_sha256"}
            )
            production_path.write_text(json.dumps(production))
            with self.assertRaisesRegex(ValueError, "unrecognized helper plan operation"):
                bridge.command_run_plan(argparse.Namespace(plan=production_path))


if __name__ == "__main__":
    unittest.main()
