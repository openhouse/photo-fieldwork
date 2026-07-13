import importlib.util
import tempfile
import unittest
import argparse
import contextlib
import csv
import io
import json
import sqlite3
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts" / "photo_archive_bridge.py"
SPEC = importlib.util.spec_from_file_location("photo_archive_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


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
            master = root / "master.csv"
            with master.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["uuid", "selection_reason", "primary_view"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"uuid": "A", "selection_reason": "reason", "primary_view": "00"},
                        {"uuid": "B", "selection_reason": "reason", "primary_view": "00"},
                    ]
                )
            holds = root / "holds.csv"
            with holds.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["uuid"])
                writer.writeheader()
                writer.writerow({"uuid": "HOLD"})
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
                        config=None,
                        profile=profile,
                        batch_size=100,
                    )
                )
            self.assertEqual(code, 0)
            plan = json.loads((root / "manifests" / "v-test-production-plan.json").read_text(encoding="utf-8"))
            bridge.verify_plan_digest(plan)
            self.assertEqual(plan["source_membership_sha256"], bridge.membership_sha256(["A", "B"]))
            self.assertTrue(all(item["membership_sha256"] for item in plan["albums"]))


if __name__ == "__main__":
    unittest.main()
