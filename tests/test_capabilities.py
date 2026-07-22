import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "report_capabilities.py"
SPEC = importlib.util.spec_from_file_location("report_capabilities", SCRIPT)
capabilities = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capabilities)
CONTRACT = json.loads(
    (ROOT / "skills" / "curate-apple-photos" / "references" / "capability-contract.json")
    .read_text(encoding="utf-8")
)


class CapabilityTests(unittest.TestCase):
    def inventory(self, root: Path) -> Path:
        path = root / "inventory.sqlite"
        connection = sqlite3.connect(path)
        fields = ", ".join(f"{name} TEXT" for name in sorted(capabilities.ASSET_FIELDS))
        connection.execute(f"CREATE TABLE asset ({fields})")
        for table in capabilities.RELATION_TABLES:
            connection.execute(f"CREATE TABLE {table} (uuid TEXT)")
        connection.commit()
        connection.close()
        return path

    def executable(self, root: Path, name: str) -> Path:
        path = root / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o700)
        return path

    def test_report_enumerates_full_contract_without_private_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = {
                "inventory_db": str(self.inventory(root)),
                "app_executable": str(self.executable(root, "helper")),
                "tools": {
                    "osxphotos": str(self.executable(root, "osxphotos")),
                    "exiftool": str(self.executable(root, "exiftool")),
                },
            }
            report = capabilities.build_report(profile, CONTRACT)
            self.assertEqual(
                [item["id"] for item in report["capabilities"]],
                [item["id"] for item in CONTRACT["capabilities"]],
            )
            encoded = json.dumps(report)
            self.assertNotIn(str(root), encoded)
            self.assertFalse(report["privacy"]["paths_emitted"])
            self.assertFalse(report["privacy"]["publication_clearance"])

    def test_missing_tools_are_visible_not_silently_degraded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = {
                "inventory_db": str(self.inventory(root)),
                "app_executable": str(root / "missing-helper"),
                "tools": {
                    "osxphotos": str(root / "missing-osxphotos"),
                    "exiftool": str(root / "missing-exiftool"),
                },
            }
            report = capabilities.build_report(profile, CONTRACT)
            self.assertEqual(report["overall_state"], "NEEDS-LIVE-PROBES")
            self.assertTrue(report["gaps"])
            self.assertTrue(
                any(item["state"] == "UNAVAILABLE" for item in report["capabilities"])
            )

    def test_live_receipts_promote_providers_without_exposing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = {
                "inventory_db": str(self.inventory(root)),
                "app_executable": str(self.executable(root, "helper")),
                "tools": {
                    "osxphotos": str(self.executable(root, "osxphotos")),
                    "exiftool": str(self.executable(root, "exiftool")),
                },
                "default_source": {"identifier": "source", "expected_count": 5},
            }
            receipt = {
                "source_album_identifier": "source",
                "source_count": 5,
                "network_access_allowed": False,
                "external_uploads_performed": False,
                "requested_count": 1,
                "completed_count": 1,
            }
            probe = [{"uuid": "PRIVATE-ID", "persons": ["Private Person"]}]
            report = capabilities.build_report(profile, CONTRACT, receipt, probe)
            self.assertEqual(report["overall_state"], "READY")
            encoded = json.dumps(report)
            self.assertNotIn("PRIVATE-ID", encoded)
            self.assertNotIn("Private Person", encoded)


if __name__ == "__main__":
    unittest.main()
