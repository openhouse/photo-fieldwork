import importlib.util
import tempfile
import unittest
import argparse
import contextlib
import csv
import io
import json
import sqlite3
import sys
from pathlib import Path
from unittest import mock

from photo_fieldwork.governance import audit_evaluation_split, build_release_seal, seal_decision_event
from photo_fieldwork.integrity import attach_plan_digest
from photo_fieldwork.pipeline import build_catalog_plan, make_sample


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
VERIFY_SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "verify_photos_commit.py"
VERIFY_SPEC = importlib.util.spec_from_file_location("verify_photos_commit", VERIFY_SCRIPT)
verifier = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(verifier)


class SkillBridgeTests(unittest.TestCase):
    def test_local_identifier_is_canonical(self):
        self.assertEqual(bridge.local_identifier("ABC"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/001"), "ABC/L0/001")
        self.assertEqual(bridge.local_identifier("ABC/L0/040"), "ABC/L0/001")

    def test_folder_contract_uses_profile_identifiers(self):
        profile = {
            "folders": {
                "root_identifier": "ROOT",
                "private_identifier": "PRIVATE",
                "audit_identifier": "AUDIT",
            }
        }
        folders = bridge.folder_specs("v03 example", include_version=True, profile=profile)
        by_key = {folder["key"]: folder for folder in folders}
        self.assertEqual(by_key["root"]["existing_identifier"], "ROOT")
        self.assertEqual(by_key["private"]["existing_identifier"], "PRIVATE")
        self.assertEqual(by_key["audit"]["existing_identifier"], "AUDIT")
        self.assertEqual(by_key["version"]["title"], "v03 example")

    def test_plan_digest_rejects_tampering(self):
        plan = bridge.attach_plan_digest({"schema_version": 2, "plan_id": "test"})
        bridge.verify_plan_digest(plan)
        plan["plan_id"] = "changed"
        with self.assertRaisesRegex(ValueError, "digest"):
            bridge.verify_plan_digest(plan)

    def test_writer_receipt_requires_release_identity_and_exact_counts(self):
        plan = {
            "plan_id": "plan",
            "plan_sha256": "1" * 64,
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "source_album_identifier": "SOURCE",
            "expected_source_count": 2,
            "source_membership_sha256": "2" * 64,
            "release_candidate_sha256": "3" * 64,
            "release_seal_sha256": "4" * 64,
            "catalog_plan_sha256": "5" * 64,
            "master_assignment_sha256": "6" * 64,
            "folders": [{"key": "version", "title": "Version"}],
            "albums": [{"title": "Master", "asset_identifiers": ["A", "B"]}],
        }
        receipt = {
            "completed_at": "2026-07-19T00:00:00+00:00",
            "plan_id": "plan",
            "plan_sha256": "1" * 64,
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "source_album_identifier": "SOURCE",
            "source_count": 2,
            "source_membership_sha256": "2" * 64,
            "release_candidate_sha256": "3" * 64,
            "release_seal_sha256": "4" * 64,
            "catalog_plan_sha256": "5" * 64,
            "master_assignment_sha256": "6" * 64,
            "folders": [{"key": "version", "title": "Version", "identifier": "FOLDER"}],
            "albums": [{"title": "Master", "identifier": "ALBUM", "count": 2}],
        }
        bridge.verify_writer_receipt(plan, receipt)
        incomplete = dict(receipt)
        incomplete.pop("completed_at")
        with self.assertRaisesRegex(ValueError, "completed_at"):
            bridge.verify_writer_receipt(plan, incomplete)
        incomplete = json.loads(json.dumps(receipt))
        incomplete["albums"][0].pop("identifier")
        with self.assertRaisesRegex(ValueError, "album"):
            bridge.verify_writer_receipt(plan, incomplete)
        incomplete = json.loads(json.dumps(receipt))
        incomplete["folders"][0]["title"] = "Another folder"
        with self.assertRaisesRegex(ValueError, "folders"):
            bridge.verify_writer_receipt(plan, incomplete)
        receipt.pop("release_seal_sha256")
        with self.assertRaisesRegex(ValueError, "release_seal_sha256"):
            bridge.verify_writer_receipt(plan, receipt)

    def test_inspection_plan_sharding_is_complete_and_digest_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = bridge.attach_plan_digest(
                {
                    "operation": "inspect-local-images",
                    "schema_version": 1,
                    "plan_id": "inspection",
                    "asset_identifiers": [f"DEMO-{index}/L0/001" for index in range(7)],
                    "output_jsonl_path": str(root / "inspection.jsonl"),
                    "receipt_path": str(root / "receipt.json"),
                    "log_path": str(root / "inspection.log"),
                    "preview_directory": str(root / "previews"),
                }
            )
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            output = root / "shards"
            with contextlib.redirect_stdout(io.StringIO()):
                code = bridge.command_shard_plan(
                    argparse.Namespace(plan=plan_path, output_dir=output, shards=3)
                )
            self.assertEqual(code, 0)
            shard_paths = sorted(output.glob("*-plan.json"))
            self.assertEqual(len(shard_paths), 3)
            shards = [json.loads(path.read_text(encoding="utf-8")) for path in shard_paths]
            self.assertEqual(sum(len(item["asset_identifiers"]) for item in shards), 7)
            self.assertEqual({item["parent_plan_sha256"] for item in shards}, {plan["plan_sha256"]})
            for shard in shards:
                bridge.verify_plan_digest(shard)

    def test_combine_inspection_rejects_substituted_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_digest = bridge.membership_sha256(["A", "B", "C"])
            plan = bridge.attach_plan_digest({
                "operation": "inspect-local-images",
                "schema_version": 1,
                "plan_id": "shard-01",
                "source_album_identifier": "SOURCE",
                "expected_source_count": 3,
                "source_membership_sha256": source_digest,
                "asset_identifiers": ["A/L0/001", "B/L0/001"],
                "output_jsonl_path": str(root / "inspection.jsonl"),
                "receipt_path": str(root / "receipt.json"),
            })
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            Path(plan["output_jsonl_path"]).write_text(
                json.dumps({"asset_identifier": "A/L0/001"}) + "\n" +
                json.dumps({"asset_identifier": "OUTSIDE/L0/001"}) + "\n",
                encoding="utf-8",
            )
            Path(plan["receipt_path"]).write_text(json.dumps({
                "plan_id": plan["plan_id"],
                "plan_sha256": plan["plan_sha256"],
                "source_count": 3,
                "source_membership_sha256": source_digest,
                "requested_count": 2,
                "completed_count": 2,
                "network_access_allowed": False,
                "external_uploads_performed": False,
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "membership mismatch"):
                bridge.command_combine_inspection(argparse.Namespace(
                    plan=[plan_path],
                    output=root / "combined.jsonl",
                    receipt=root / "combined-receipt.json",
                    expected=2,
                ))
            Path(plan["output_jsonl_path"]).write_text(
                json.dumps({"asset_identifier": "A/L0/001"}) + "\n" +
                json.dumps({"asset_identifier": "B/L0/001"}) + "\n",
                encoding="utf-8",
            )
            receipt = json.loads(Path(plan["receipt_path"]).read_text(encoding="utf-8"))
            receipt["source_count"] = 99
            Path(plan["receipt_path"]).write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source count"):
                bridge.command_combine_inspection(argparse.Namespace(
                    plan=[plan_path],
                    output=root / "combined.jsonl",
                    receipt=root / "combined-receipt.json",
                    expected=2,
                ))

    def test_snapshot_plan_binds_profile_inventory_and_album_digests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "inventory.sqlite"
            conn = sqlite3.connect(inventory)
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                [
                    ("source_identifier", "SOURCE"),
                    ("source_count", "2"),
                    ("source_membership_sha256", bridge.membership_sha256(["A", "B"])),
                ],
            )
            conn.commit()
            conn.close()
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "workspace_root": str(root),
                        "photos_database": str(root / "Photos.sqlite"),
                        "permissioned_app": str(root / "Archive.app"),
                        "inventory_database": str(inventory),
                        "source": {"kind": "album", "identifier": "SOURCE", "expected_count": 2},
                        "folders": {
                            "root_identifier": "ROOT",
                            "private_identifier": "PRIVATE",
                            "audit_identifier": "AUDIT",
                        },
                    }
                ),
                encoding="utf-8",
            )
            config_value = {
                "seed": 17,
                "target_count": 2,
                "unclassified_view": "00",
                "allow_unclassified_fallback": False,
                "require_explicit_safety_status": True,
                "require_evaluation_binding": True,
                "require_per_view_sufficiency": True,
                "minimum_eval_coverage": 1.0,
                "minimum_eval_precision": 0.75,
                "minimum_view_precision": 0.65,
                "minimum_decisive_per_view": 1,
                "views": [{"id": "00", "label": "Editor Field", "quota": 2}],
            }
            config = root / "config.json"
            config.write_text(json.dumps(config_value), encoding="utf-8")
            master_rows = [
                {
                    "uuid": "A",
                    "filename": "a.jpg",
                    "selection_reason": "reason",
                    "primary_view": "00",
                    "safety_status": "clear",
                    "publication_status": "not-approved",
                },
                {
                    "uuid": "B",
                    "filename": "b.jpg",
                    "selection_reason": "reason",
                    "primary_view": "00",
                    "safety_status": "clear",
                    "publication_status": "not-approved",
                },
            ]
            master = root / "master.csv"
            with master.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(master_rows[0]))
                writer.writeheader()
                writer.writerows(master_rows)
            holds = root / "holds.csv"
            with holds.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["uuid"])
                writer.writeheader()
                writer.writerow({"uuid": "HOLD"})
            catalog_plan_value = build_catalog_plan(
                master_rows,
                config_value,
                "v-test",
                "Source",
                "SOURCE",
                ["A", "B"],
            )
            catalog_plan_value["created_at"] = "2026-07-19T00:00:00+00:00"
            catalog_plan_value = attach_plan_digest(catalog_plan_value)
            catalog_plan = root / "catalog-plan.json"
            catalog_plan.write_text(json.dumps(catalog_plan_value), encoding="utf-8")
            feedback = make_sample(master_rows, 2, 17)
            for row in feedback:
                row["judgment"] = "fit"
                row["visible_reason"] = "Synthetic visible fit."
            decision = seal_decision_event({
                "schema_version": 1,
                "event_id": "decision-01",
                "occurred_at": "2026-07-19T00:00:00+00:00",
                "run_id": "v-test",
                "event_type": "editorial-assignment",
                "actor_id": "editor-01",
                "actor_kind": "human",
                "authority_scope": "editorial",
                "reason": "Synthetic fixture accepted for the editor field.",
            }, "")
            release_seal_value = build_release_seal(
                config=config_value,
                master=master_rows,
                holds=[{"uuid": "HOLD"}],
                feedback=feedback,
                holdout=[{"uuid": "HOLDOUT"}],
                canaries=[],
                safety_baseline=master_rows,
                catalog_plan=catalog_plan_value,
                decision_events=[decision],
                holdout_report=audit_evaluation_split(feedback, [{"uuid": "HOLDOUT"}], []),
            )
            release_seal = root / "release-seal.json"
            release_seal.write_text(json.dumps(release_seal_value), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = bridge.command_snapshot_plans(
                    argparse.Namespace(
                        workspace=root,
                        master=master,
                        holds=holds,
                        target=2,
                        version="v-test",
                        folder_title="v-test field",
                        view_column="primary_view",
                        config=config,
                        catalog_plan=catalog_plan,
                        release_seal=release_seal,
                        profile=profile,
                        batch_size=100,
                    )
                )
            self.assertEqual(code, 0)
            plan = json.loads((root / "manifests" / "v-test-production-plan.json").read_text(encoding="utf-8"))
            bridge.verify_plan_digest(plan)
            self.assertEqual(plan["schema_version"], 3)
            self.assertEqual(plan["source_membership_sha256"], bridge.membership_sha256(["A", "B"]))
            self.assertEqual(plan["release_candidate_sha256"], release_seal_value["candidate_sha256"])
            self.assertEqual(plan["release_seal_sha256"], release_seal_value["release_seal_sha256"])
            self.assertEqual(plan["catalog_plan_sha256"], catalog_plan_value["plan_sha256"])
            self.assertTrue(all(item["membership_sha256"] for item in plan["albums"]))

            with self.assertRaisesRegex(ValueError, "primary_view"):
                bridge.command_snapshot_plans(
                    argparse.Namespace(
                        workspace=root,
                        master=master,
                        holds=holds,
                        target=2,
                        version="v-test",
                        folder_title="v-test field",
                        view_column="candidate_views",
                        config=config,
                        catalog_plan=catalog_plan,
                        release_seal=release_seal,
                        profile=profile,
                        batch_size=100,
                    )
                )

            master_rows[0]["publication_status"] = "approved"
            with master.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(master_rows[0]))
                writer.writeheader()
                writer.writerows(master_rows)
            with self.assertRaisesRegex(ValueError, "master_sha256"):
                bridge.command_snapshot_plans(
                    argparse.Namespace(
                        workspace=root,
                        master=master,
                        holds=holds,
                        target=2,
                        version="v-test",
                        folder_title="v-test field",
                        view_column="primary_view",
                        config=config,
                        catalog_plan=catalog_plan,
                        release_seal=release_seal,
                        profile=profile,
                        batch_size=100,
                    )
                )
            master_rows[0]["publication_status"] = "not-approved"
            with master.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(master_rows[0]))
                writer.writeheader()
                writer.writerows(master_rows)

            changed = json.loads(release_seal.read_text(encoding="utf-8"))
            changed["bindings"]["master_assignment_sha256"] = "0" * 64
            release_seal.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "candidate digest|seal digest|binding mismatch"):
                bridge.command_snapshot_plans(
                    argparse.Namespace(
                        workspace=root,
                        master=master,
                        holds=holds,
                        target=2,
                        version="v-test",
                        folder_title="v-test field",
                        view_column="primary_view",
                        config=config,
                        catalog_plan=catalog_plan,
                        release_seal=release_seal,
                        profile=profile,
                        batch_size=100,
                    )
                )

    def test_independent_verifier_carries_release_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photos_db = root / "Photos.sqlite"
            conn = sqlite3.connect(photos_db)
            conn.execute("CREATE TABLE ZGENERICALBUM (Z_PK INTEGER PRIMARY KEY, ZTITLE TEXT, ZUUID TEXT)")
            conn.execute("CREATE TABLE ZASSET (Z_PK INTEGER PRIMARY KEY, ZUUID TEXT)")
            conn.execute("CREATE TABLE Z_30ASSETS (Z_30ALBUMS INTEGER, Z_3ASSETS INTEGER)")
            conn.executemany(
                "INSERT INTO ZGENERICALBUM(Z_PK, ZTITLE, ZUUID) VALUES (?, ?, ?)",
                [(1, "Source", "SOURCE"), (2, "Master", "MASTER")],
            )
            conn.executemany("INSERT INTO ZASSET(Z_PK, ZUUID) VALUES (?, ?)", [(1, "A"), (2, "B")])
            conn.executemany(
                "INSERT INTO Z_30ASSETS(Z_30ALBUMS, Z_3ASSETS) VALUES (?, ?)",
                [(1, 1), (1, 2), (2, 1), (2, 2)],
            )
            conn.commit()
            conn.close()

            source_digest = verifier.membership_sha256({"A", "B"})
            release_bindings = {
                key: str(index + 1)[-1] * 64
                for index, key in enumerate(sorted(verifier.RELEASE_BINDING_KEYS))
            }
            release_bindings["catalog_plan_sha256"] = "2" * 64
            release_bindings["master_assignment_sha256"] = "3" * 64
            release_bindings["source_membership_sha256"] = source_digest
            release_seal = {
                "schema_version": 1,
                "status": "PASS",
                "release_class": "editor-field",
                "publication_clearance": False,
                "candidate_sha256": verifier.canonical_json_sha256(release_bindings),
                "bindings": release_bindings,
                "gates": {key: "PASS" for key in verifier.RELEASE_GATE_KEYS},
            }
            release_seal["release_seal_sha256"] = verifier.release_seal_sha256(release_seal)
            seal_path = root / "release-seal.json"
            seal_path.write_text(json.dumps(release_seal), encoding="utf-8")
            plan = {
                "operation": "snapshot-membership",
                "schema_version": 3,
                "plan_id": "test-plan",
                "safety_mode": "create-folders-albums-and-add-membership-only",
                "source_album_identifier": "SOURCE/L0/001",
                "expected_source_count": 2,
                "source_membership_sha256": source_digest,
                "release_candidate_sha256": release_seal["candidate_sha256"],
                "release_seal_sha256": release_seal["release_seal_sha256"],
                "catalog_plan_sha256": "2" * 64,
                "master_assignment_sha256": "3" * 64,
                "publication_approval_default": "not-approved",
                "albums": [{
                    "title": "Master",
                    "asset_identifiers": ["A/L0/001", "B/L0/001"],
                    "membership_sha256": verifier.membership_sha256({"A", "B"}),
                }],
            }
            plan["plan_sha256"] = verifier.canonical_json_sha256(plan)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            receipt = {
                "plan_id": plan["plan_id"],
                "plan_sha256": plan["plan_sha256"],
                "source_album_identifier": plan["source_album_identifier"],
                "source_count": 2,
                "source_membership_sha256": plan["source_membership_sha256"],
                "release_candidate_sha256": plan["release_candidate_sha256"],
                "release_seal_sha256": plan["release_seal_sha256"],
                "catalog_plan_sha256": plan["catalog_plan_sha256"],
                "master_assignment_sha256": plan["master_assignment_sha256"],
                "safety_mode": "create-folders-albums-and-add-membership-only",
                "albums": [{"title": "Master", "identifier": "MASTER/L0/001", "count": 2}],
            }
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            report = root / "verification.md"
            json_report = root / "verification.json"
            argv = [
                str(VERIFY_SCRIPT),
                "--plan", str(plan_path),
                "--receipt", str(receipt_path),
                "--release-seal", str(seal_path),
                "--report", str(report),
                "--json-report", str(json_report),
                "--photos-db", str(photos_db),
            ]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                verifier.main()
            verified = json.loads(json_report.read_text(encoding="utf-8"))
            self.assertEqual(verified["status"], "PASS")
            self.assertEqual(verified["release_seal_sha256"], release_seal["release_seal_sha256"])
            self.assertFalse(verified["publication_clearance"])

            receipt["release_candidate_sha256"] = "9" * 64
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with mock.patch.object(sys, "argv", argv), self.assertRaisesRegex(RuntimeError, "release_candidate"):
                verifier.main()


if __name__ == "__main__":
    unittest.main()
