import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SkillBridgeTests(unittest.TestCase):
    def test_local_identifier_is_canonical(self):
        self.assertEqual(bridge.local_identifier("ABC"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/001"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/040"), "ABC/L0/001")

    def test_inventory_metadata_supports_json_and_plain_values(self):
        self.assertEqual(bridge.decode_meta_value('"album-id"'), "album-id")
        self.assertEqual(bridge.decode_meta_value("visible-library-stills://v1"), "visible-library-stills://v1")

    def test_folder_contract_uses_protected_identifiers(self):
        folders = bridge.folder_specs("v03 example", include_version=True)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["existing_identifier"], bridge.ROOT_FOLDER_ID)
        self.assertEqual(by_key["private"]["existing_identifier"], bridge.PRIVATE_FOLDER_ID)
        self.assertEqual(by_key["audit"]["existing_identifier"], bridge.AUDIT_FOLDER_ID)
        self.assertEqual(by_key["version"]["title"], "v03 example")

    def test_snapshot_plan_is_v2_and_content_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                source_id="visible-library-stills://v1",
                source_count=42,
                source_membership_sha256="a" * 64,
                batch_size=10,
                workspace=Path(directory),
            )
            plan = bridge.snapshot_plan(
                args,
                "test-plan",
                bridge.folder_specs("v99", include_version=True),
                [bridge.album("00 MASTER", "version", ["ABC"])],
                "receipt.json",
            )
            self.assertEqual(plan["schema_version"], 2)
            self.assertEqual(plan["adapter"]["name"], "apple-photos-photokit")
            self.assertEqual(plan["source_membership_sha256"], "a" * 64)
            self.assertEqual(plan["plan_sha256"], bridge.content_sha256(plan))
            plan["batch_size"] = 11
            self.assertNotEqual(plan["plan_sha256"], bridge.content_sha256(plan))

    def test_release_seal_hashes_inputs_and_updates_run_state_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest = workspace / "master.csv"
            manifest.write_text("uuid\nABC\n", encoding="utf-8")
            phases = {phase: "completed" for phase in bridge.PHASE_ORDER}
            state = {
                "run_id": "qa-run",
                "status": "validation",
                "source_album_identifier": "visible-library-stills://v1",
                "expected_source_count": 42,
                "source_membership_sha256": "a" * 64,
                "target_count": 1,
                "phases": phases,
            }
            (workspace / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
            original_app = bridge.APP_EXECUTABLE
            original_plist = bridge.APP_PLIST
            try:
                bridge.APP_EXECUTABLE = workspace / "missing-app"
                bridge.APP_PLIST = workspace / "missing-plist"
                with redirect_stdout(io.StringIO()):
                    code = bridge.command_seal(
                        SimpleNamespace(workspace=workspace, input=[manifest], output=None)
                    )
            finally:
                bridge.APP_EXECUTABLE = original_app
                bridge.APP_PLIST = original_plist
            self.assertEqual(code, 0)
            seal = json.loads((workspace / "manifests" / "release-seal.json").read_text())
            updated = json.loads((workspace / "run-state.json").read_text())
            self.assertEqual(seal["seal_sha256"], bridge.content_sha256(seal, "seal_sha256"))
            self.assertEqual(updated["status"], "sealed")

    def test_snapshot_plans_require_matching_passing_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifests = workspace / "manifests"
            manifests.mkdir()
            row = {
                "uuid": "ABC",
                "primary_view": "A",
                "assigned_view": "A",
                "selection_reason": "visible evidence",
            }
            digest = bridge.master_membership_sha256([row])
            proposal_id = f"pfp-{digest[:16]}"
            config_path = workspace / "config.json"
            config = {"views": [{"id": "A", "label": "A", "quota": 1}]}
            config_path.write_text(json.dumps(config), encoding="utf-8")
            config_digest = bridge.content_sha256(config)
            row["master_sha256"] = digest
            row["config_sha256"] = config_digest
            row["proposal_id"] = proposal_id
            master = manifests / "master.csv"
            master.write_text(
                "uuid,primary_view,assigned_view,selection_reason,master_sha256,config_sha256,proposal_id\n"
                f"ABC,A,A,visible evidence,{digest},{config_digest},{proposal_id}\n",
                encoding="utf-8",
            )
            holds = manifests / "holds.csv"
            holds.write_text("uuid\n", encoding="utf-8")
            evaluation_path = workspace / "evaluation.json"
            evaluation = {
                "passed": True,
                "master_sha256": digest,
                "config_sha256": config_digest,
                "evaluation_sample_sha256": "d" * 64,
                "evaluation_scope": "final-holdout",
                "split_audit_sha256": "e" * 64,
                "proposal_id": proposal_id,
            }
            evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
            args = SimpleNamespace(
                workspace=workspace,
                master=master,
                holds=holds,
                target=1,
                version="v99",
                folder_title="v99 test",
                view_column="primary_view",
                config=config_path,
                evaluation_report=evaluation_path,
                source_id="visible-library-stills://v1",
                source_count=42,
                source_membership_sha256="b" * 64,
                batch_size=10,
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(bridge.command_snapshot_plans(args), 0)
            plan = json.loads((manifests / "v99-production-plan.json").read_text())
            self.assertEqual(plan["master_sha256"], digest)
            self.assertEqual(plan["proposal_id"], proposal_id)
            self.assertTrue(plan["evaluation"]["passed"])
            evaluation["master_sha256"] = "c" * 64
            evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                bridge.command_snapshot_plans(args)


if __name__ == "__main__":
    unittest.main()
