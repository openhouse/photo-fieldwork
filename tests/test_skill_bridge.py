import csv
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from photo_fieldwork.integrity import master_sha256 as canonical_master_sha256


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)

WRITER_SCRIPT = SCRIPT.parent / "applescript_writer.py"
WRITER_SPEC = importlib.util.spec_from_file_location("applescript_writer", WRITER_SCRIPT)
writer = importlib.util.module_from_spec(WRITER_SPEC)
WRITER_SPEC.loader.exec_module(writer)

VERIFY_SCRIPT = SCRIPT.parent / "verify_photos_commit.py"
VERIFY_SPEC = importlib.util.spec_from_file_location("verify_photos_commit", VERIFY_SCRIPT)
verifier = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(verifier)


class SkillBridgeTests(unittest.TestCase):
    def test_local_identifier_is_canonical(self):
        self.assertEqual(bridge.local_identifier("ABC"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/001"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/040"), "ABC/L0/001")

    def test_bridge_master_identity_matches_core_contract(self):
        rows = [
            {"uuid": "B/L0/001", "primary_view": "02", "safety_status": "clear"},
            {"uuid": "A", "primary_view": "01", "safety_status": "CLEAR"},
        ]
        core_rows = [
            {"uuid": "B", "primary_view": "02", "safety_status": "clear"},
            {"uuid": "A", "primary_view": "01", "safety_status": "clear"},
        ]
        self.assertEqual(bridge.master_sha256(rows), canonical_master_sha256(core_rows))

    def test_database_source_fingerprint_detects_membership_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "Photos.sqlite"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE ZASSET (
                    Z_PK INTEGER PRIMARY KEY,
                    ZUUID TEXT,
                    ZKIND INTEGER,
                    ZTRASHEDSTATE INTEGER,
                    ZHIDDEN INTEGER,
                    ZVISIBILITYSTATE INTEGER,
                    ZBUNDLESCOPE INTEGER
                );
                CREATE TABLE ZGENERICALBUM (Z_PK INTEGER PRIMARY KEY, ZUUID TEXT);
                CREATE TABLE Z_30ASSETS (Z_3ASSETS INTEGER, Z_30ALBUMS INTEGER);
                INSERT INTO ZASSET VALUES (1, 'A', 0, 0, 0, 0, 0);
                INSERT INTO ZASSET VALUES (2, 'B', 0, 0, 0, 0, 0);
                """
            )
            connection.commit()
            connection.close()
            identifiers = bridge.source_membership_from_database(
                database, "visible-library-stills://v1"
            )
            self.assertEqual(identifiers, {"A", "B"})
            self.assertEqual(
                bridge.membership_sha256(identifiers),
                bridge.membership_sha256(["B/L0/001", "A/L0/001"]),
            )

    def test_folder_contract_uses_protected_identifiers(self):
        folders = bridge.folder_specs("v03 example", include_version=True)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["existing_identifier"], bridge.ROOT_FOLDER_ID)
        self.assertEqual(by_key["private"]["existing_identifier"], bridge.PRIVATE_FOLDER_ID)
        self.assertEqual(by_key["audit"]["existing_identifier"], bridge.AUDIT_FOLDER_ID)
        self.assertEqual(by_key["version"]["title"], "v03 example")

    def test_profile_can_replace_machine_specific_folder_contract(self):
        profile = bridge.default_profile()
        profile["protected_folders"] = {
            "root": {"title": "ROOT", "identifier": "ROOT-ID"},
            "private": {"title": "PRIVATE", "identifier": "PRIVATE-ID"},
            "audit": {"title": "AUDIT", "identifier": "AUDIT-ID"},
        }
        folders = bridge.folder_specs("v-test", include_version=True, profile=profile)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["title"], "ROOT")
        self.assertEqual(by_key["private"]["existing_identifier"], "PRIVATE-ID")

    def test_applescript_adapter_renders_fail_closed_membership_plan(self):
        plan = {
            "operation": "snapshot-membership",
            "schema_version": 1,
            "plan_id": "test",
            "execution_kind": "write-test",
            "catalog_plan_sha256": "a" * 64,
            "source_membership_sha256": "c" * 64,
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "source_album_identifier": "source",
            "expected_source_count": 2,
            "batch_size": 2,
            "receipt_path": "receipt.json",
            "folders": [
                {"key": "root", "title": "ROOT", "parent_key": None, "existing_identifier": "ROOT-ID"},
                {"key": "version", "title": "VERSION", "parent_key": "root", "existing_identifier": None},
            ],
            "albums": [
                {
                    "title": "MASTER",
                    "parent_folder_key": "version",
                    "existing_identifier": None,
                    "asset_identifiers": ["A/L0/001", "B/L0/001"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            id_directory = Path(temporary) / "ids"
            script = writer.render(plan, id_directory)
            self.assertIn("contains an unexpected member", script)
            self.assertIn("missing an expected UUID", script)
            self.assertIn("Final count mismatch", script)
            self.assertEqual((id_directory / "album-000.txt").read_text(), "A/L0/001\nB/L0/001")
            self.assertEqual(os.stat(id_directory).st_mode & 0o777, 0o700)

    def test_applescript_adapter_rejects_duplicate_ids(self):
        plan = {
            "operation": "snapshot-membership",
            "schema_version": 1,
            "plan_id": "test",
            "execution_kind": "write-test",
            "catalog_plan_sha256": "a" * 64,
            "source_membership_sha256": "c" * 64,
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "source_album_identifier": "source",
            "expected_source_count": 1,
            "batch_size": 1,
            "receipt_path": "receipt.json",
            "folders": [{"key": "root", "title": "ROOT", "parent_key": None, "existing_identifier": "ROOT-ID"}],
            "albums": [{"title": "MASTER", "parent_folder_key": "root", "existing_identifier": None, "asset_identifiers": ["A/L0/001", "A/L0/001"]}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                writer.render(plan, Path(temporary))

    def test_applescript_adapter_rejects_unbound_catalog_plan(self):
        plan = {
            "operation": "snapshot-membership",
            "schema_version": 1,
            "plan_id": "test",
            "execution_kind": "write-test",
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "source_album_identifier": "source",
            "expected_source_count": 1,
            "batch_size": 1,
            "receipt_path": "receipt.json",
            "folders": [],
            "albums": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "catalog_plan_sha256"):
                writer.render(plan, Path(temporary))

    def test_applescript_execution_receipt_binds_nonce_and_catalog_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt_path = root / "receipt.json"
            plan = {
                "operation": "snapshot-membership",
                "schema_version": 1,
                "plan_id": "test",
                "execution_kind": "write-test",
                "catalog_plan_sha256": "a" * 64,
                "adapter_plan_sha256": "d" * 64,
                "execution_nonce": "b" * 32,
                "source_membership_sha256": "c" * 64,
                "safety_mode": "create-folders-albums-and-add-membership-only",
                "source_album_identifier": "source",
                "expected_source_count": 1,
                "batch_size": 1,
                "receipt_path": str(receipt_path),
                "folders": [
                    {
                        "key": "root",
                        "title": "ROOT",
                        "parent_key": None,
                        "existing_identifier": "ROOT-ID",
                    }
                ],
                "albums": [
                    {
                        "title": "MASTER",
                        "parent_folder_key": "root",
                        "existing_identifier": None,
                        "asset_identifiers": ["A/L0/001"],
                    }
                ],
            }
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            runtime_plan_sha256 = bridge.file_sha256(plan_path)
            completed = SimpleNamespace(
                returncode=0,
                stderr="",
                stdout="FOLDER\troot\tROOT\tROOT-ID\nALBUM\tMASTER\tMASTER-ID\t1\n",
            )
            argv = [
                "applescript_writer.py",
                "--plan",
                str(plan_path),
                "--plan-sha256",
                runtime_plan_sha256,
                "--script",
                str(root / "writer.applescript"),
                "--id-directory",
                str(root / "ids"),
                "--execute",
            ]
            with patch.object(sys, "argv", argv), patch.object(
                writer.subprocess, "run", return_value=completed
            ) as run_mock:
                self.assertEqual(writer.main(), 0)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(receipt["execution_nonce"], "b" * 32)
            self.assertEqual(receipt["plan_sha256"], "a" * 64)
            self.assertEqual(receipt["adapter_plan_sha256"], "d" * 64)
            self.assertEqual(receipt["runtime_plan_sha256"], runtime_plan_sha256)
            self.assertEqual(receipt["source_membership_sha256"], "c" * 64)
            run_mock.assert_called_once()
            self.assertEqual(run_mock.call_args.args[0], ["/usr/bin/osascript", "-"])
            self.assertEqual(
                run_mock.call_args.kwargs["input"],
                (root / "writer.applescript").read_text(),
            )

    def test_applescript_execution_rejects_replaced_runtime_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            plan_path.write_text('{"authorized":true}', encoding="utf-8")
            authorized_digest = bridge.file_sha256(plan_path)
            plan_path.write_text('{"authorized":false}', encoding="utf-8")
            argv = [
                "applescript_writer.py",
                "--plan",
                str(plan_path),
                "--plan-sha256",
                authorized_digest,
                "--script",
                str(root / "writer.applescript"),
                "--id-directory",
                str(root / "ids"),
                "--execute",
            ]
            with patch.object(sys, "argv", argv), self.assertRaisesRegex(
                ValueError, "runtime plan bytes"
            ):
                writer.main()

    def test_independent_verifier_rejects_replaced_runtime_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "runtime-plan.json"
            receipt_path = root / "receipt.json"
            report_path = root / "verification.json"
            plan = {
                "execution_kind": "write-test",
                "execution_nonce": "b" * 32,
                "catalog_plan_sha256": "a" * 64,
                "adapter_plan_sha256": "d" * 64,
                "source_membership_sha256": "c" * 64,
                "albums": [],
            }
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            receipt_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "execution_kind": "write-test",
                        "execution_nonce": "b" * 32,
                        "plan_sha256": "a" * 64,
                        "adapter_plan_sha256": "d" * 64,
                        "runtime_plan_sha256": "e" * 64,
                        "source_membership_sha256": "c" * 64,
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "verify_photos_commit.py",
                "--plan",
                str(plan_path),
                "--receipt",
                str(receipt_path),
                "--report",
                str(report_path),
            ]
            with patch.object(sys, "argv", argv), self.assertRaisesRegex(
                RuntimeError, "runtime-plan digest"
            ):
                verifier.main()

    def test_photokit_snapshot_capability_requires_candidate_binding(self):
        plan = {
            "source_album_identifier": "source",
            "expected_source_count": 2,
        }
        receipt = {
            "status": "PASS",
            "source_album_identifier": "source",
            "source_count": 2,
            "capabilities": ["preflight-read-only", "snapshot-membership"],
        }
        with self.assertRaisesRegex(ValueError, "candidate-bound"):
            bridge.validate_snapshot_capability_receipt(receipt, plan)
        receipt["capabilities"].append("candidate-bound-snapshot-v2")
        bridge.validate_snapshot_capability_receipt(receipt, plan)

    def test_execution_authorization_binds_exact_adapter_bytes_and_kind(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "adapter.json"
            plan = {
                "execution_kind": "write-test",
                "catalog_plan_sha256": "a" * 64,
            }
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            plan_bytes = plan_path.read_bytes()
            registration_event = {
                "schema_version": 1,
                "sequence": 1,
                "recorded_at": "2026-07-19T00:00:00Z",
                "previous_hash": None,
                "event_type": "plan_registered",
                "plan_sha256": "a" * 64,
                "run_lock_sha256": "c" * 64,
            }
            registration_event["event_hash"] = bridge.content_sha256(
                registration_event, "event_hash"
            )
            event = {
                "schema_version": 1,
                "sequence": 2,
                "recorded_at": "2026-07-19T00:00:01Z",
                "previous_hash": registration_event["event_hash"],
                "event_type": "execution_started",
                "kind": "write-test",
                "execution_nonce": "b" * 32,
                "plan_sha256": "a" * 64,
                "adapter_plan": {
                    "path": "adapter.json",
                    "sha256": bridge.file_sha256(plan_path),
                    "bytes": len(plan_bytes),
                },
            }
            event["event_hash"] = bridge.content_sha256(event, "event_hash")
            (root / "execution-events.jsonl").write_text(
                json.dumps(registration_event) + "\n" + json.dumps(event) + "\n",
                encoding="utf-8",
            )
            run_event = {
                "schema_version": 1,
                "sequence": 1,
                "event_type": "run_initialized",
                "recorded_at": "2026-07-19T00:00:00Z",
                "previous_hash": None,
                "details": {},
                "state_after": {},
            }
            run_event["event_hash"] = bridge.content_sha256(run_event, "event_hash")
            later_run_event = {
                "schema_version": 1,
                "sequence": 2,
                "event_type": "phase_transition",
                "recorded_at": "2026-07-19T00:00:02Z",
                "previous_hash": run_event["event_hash"],
                "details": {"phase": "write_test"},
                "state_after": {},
            }
            later_run_event["event_hash"] = bridge.content_sha256(
                later_run_event, "event_hash"
            )
            (root / "run-events.jsonl").write_text(
                json.dumps(run_event) + "\n" + json.dumps(later_run_event) + "\n",
                encoding="utf-8",
            )
            (root / "registered-plan.json").write_text(
                json.dumps(
                    {
                        "plan_sha256": "a" * 64,
                        "run_event_count": 1,
                        "run_ledger_head": run_event["event_hash"],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                bridge.execution_authorization(root, "b" * 32, plan_bytes, plan),
                bridge.bytes_sha256(plan_bytes),
            )
            plan_path.write_text(json.dumps({**plan, "changed": True}), encoding="utf-8")
            self.assertEqual(
                bridge.execution_authorization(root, "b" * 32, plan_bytes, plan),
                bridge.bytes_sha256(plan_bytes),
            )
            changed_bytes = plan_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "authorize these adapter-plan bytes"):
                bridge.execution_authorization(root, "b" * 32, changed_bytes, plan)

    def test_execution_authorization_rejects_post_registration_invalidation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "adapter.json"
            plan = {"execution_kind": "production", "catalog_plan_sha256": "a" * 64}
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            plan_bytes = plan_path.read_bytes()
            events = []
            for value in (
                {"event_type": "plan_registered", "plan_sha256": "a" * 64},
                {
                    "event_type": "execution_started",
                    "kind": "production",
                    "execution_nonce": "b" * 32,
                    "plan_sha256": "a" * 64,
                    "adapter_plan": {
                        "path": "adapter.json",
                        "sha256": bridge.file_sha256(plan_path),
                        "bytes": len(plan_bytes),
                    },
                },
            ):
                event = {
                    "schema_version": 1,
                    "sequence": len(events) + 1,
                    "recorded_at": "2026-07-19T00:00:00Z",
                    "previous_hash": events[-1]["event_hash"] if events else None,
                    **value,
                }
                event["event_hash"] = bridge.content_sha256(event, "event_hash")
                events.append(event)
            (root / "execution-events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            (root / "registered-plan.json").write_text(
                json.dumps({"plan_sha256": "a" * 64, "run_event_count": 1}),
                encoding="utf-8",
            )
            run_events = []
            for event_type in ("run_initialized", "artifact_invalidation"):
                event = {
                    "schema_version": 1,
                    "sequence": len(run_events) + 1,
                    "event_type": event_type,
                    "recorded_at": "2026-07-19T00:00:00Z",
                    "previous_hash": run_events[-1]["event_hash"] if run_events else None,
                    "details": {},
                    "state_after": {},
                }
                event["event_hash"] = bridge.content_sha256(event, "event_hash")
                run_events.append(event)
            (root / "run-events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in run_events),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "revoked by candidate invalidation"):
                bridge.execution_authorization(root, "b" * 32, plan_bytes, plan)

    def test_snapshot_plans_preserve_registered_candidate_assignments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            (workspace / "manifests").mkdir(parents=True)
            (workspace / "logs").mkdir()
            profile_path = root / "profile.json"
            profile = bridge.default_profile()
            profile["workspace_root"] = str(workspace)
            profile["source"] = {
                "identifier": "source://test",
                "expected_count": 3,
                "title": "Test source",
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            master_path = root / "master.csv"
            fields = [
                "uuid",
                "primary_view",
                "safety_status",
                "selection_reason",
                "evidence_confidence",
                "persons",
            ]
            rows = [
                {
                    "uuid": "A",
                    "primary_view": "01",
                    "safety_status": "clear",
                    "selection_reason": "reason A",
                    "evidence_confidence": "high",
                    "persons": "",
                },
                {
                    "uuid": "B",
                    "primary_view": "02",
                    "safety_status": "clear",
                    "selection_reason": "reason B",
                    "evidence_confidence": "high",
                    "persons": "",
                },
            ]
            with master_path.open("w", newline="", encoding="utf-8") as handle:
                writer_handle = csv.DictWriter(handle, fieldnames=fields)
                writer_handle.writeheader()
                writer_handle.writerows(rows)
            holds_path = root / "holds.csv"
            holds_path.write_text("uuid\nH\n", encoding="utf-8")
            config = {
                "views": [
                    {"id": "01", "label": "One"},
                    {"id": "02", "label": "Two"},
                ]
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            master_digest = bridge.master_sha256(rows)
            catalog = {
                "schema_version": 2,
                "plan_id": "catalog",
                "proposal_id": f"pfp-{master_digest[:16]}",
                "master_sha256": master_digest,
                "config_sha256": bridge.content_sha256(config),
                "release_class": "editor-field",
                "expected_master_count": 2,
                "source": {
                    "identifier": "source://test",
                    "count": 3,
                    "membership_sha256": "d" * 64,
                },
                "albums": [
                    {"key": "master", "asset_ids": ["A", "B"]},
                    {"key": "view-01", "asset_ids": ["A"]},
                    {"key": "view-02", "asset_ids": ["B"]},
                ],
            }
            catalog["plan_sha256"] = bridge.content_sha256(catalog, "plan_sha256")
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            args = SimpleNamespace(
                profile=profile_path,
                master=master_path,
                holds=holds_path,
                target=2,
                version="v-test",
                folder_title="VERSION",
                view_column="primary_view",
                config=config_path,
                catalog_plan=catalog_path,
                workspace=workspace,
                source_id=None,
                source_count=None,
                batch_size=100,
            )
            self.assertEqual(bridge.command_snapshot_plans(args), 0)
            production = json.loads(
                (workspace / "manifests/v-test-production-plan.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(production["catalog_plan_sha256"], catalog["plan_sha256"])
            rows[1]["primary_view"] = "01"
            with master_path.open("w", newline="", encoding="utf-8") as handle:
                writer_handle = csv.DictWriter(handle, fieldnames=fields)
                writer_handle.writeheader()
                writer_handle.writerows(rows)
            with self.assertRaisesRegex(ValueError, "candidate identity"):
                bridge.command_snapshot_plans(args)

    def test_read_only_inspection_uses_photokit_without_release_nonce(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "Helper.app"
            app.mkdir()
            profile = bridge.default_profile()
            profile["app"]["path"] = str(app)
            profile_path = root / "profile.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            receipt_path = root / "inspection-receipt.json"
            receipt_path.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            plan_path = root / "inspection-plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "operation": "inspect-local-images",
                        "receipt_path": str(receipt_path),
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                profile=profile_path,
                plan=plan_path,
                backend="photokit",
                execution_nonce=None,
            )
            with patch.object(
                bridge.subprocess, "run", return_value=SimpleNamespace(returncode=0)
            ) as launched:
                self.assertEqual(bridge.command_run_plan(args), 0)
            self.assertIn(str(plan_path.resolve()), launched.call_args.args[0])
            args.backend = "applescript"
            with self.assertRaisesRegex(ValueError, "requires the photokit backend"):
                bridge.command_run_plan(args)

    def test_private_profile_initializer_uses_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "private" / "profile.json"
            args = SimpleNamespace(
                output=output,
                schema=None,
                workspace_root=root / "workspace",
                cli=root / "bin/photo-fieldwork",
                inventory=root / "inventory.sqlite",
                photos_db=root / "Photos.sqlite",
                app=root / "Helper.app",
                bundle_identifier="test.helper",
                executable="Helper",
                source_id="source://test",
                source_count=10,
                source_title="Source",
                root_title="ROOT",
                root_id="ROOT-ID",
                private_title="PRIVATE",
                private_id="PRIVATE-ID",
                audit_title="AUDIT",
                audit_id="AUDIT-ID",
            )
            self.assertEqual(bridge.command_init_profile(args), 0)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            profile = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(profile["source"]["expected_count"], 10)
            with self.assertRaises(ValueError):
                bridge.command_init_profile(args)


if __name__ == "__main__":
    unittest.main()
