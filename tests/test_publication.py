import argparse
import csv
import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.cli import command_public_handoff
from photo_fieldwork.publication import (
    PUBLIC_FIELDS,
    build_public_handoff,
    public_id,
    write_private_report,
    write_public_package,
)


class PublicationHandoffTests(unittest.TestCase):
    def cleared_row(self, **changes):
        row = {
            "uuid": "PRIVATE-ASSET-001/L0/001",
            "filename": "private-name.jpg",
            "local_path": "/private/archive/private-name.jpg",
            "people_names": "Private Person",
            "gps": "40.0,-73.0",
            "raw_ocr": "private words",
            "publication_status": "cleared-for-specific-use",
            "rights_status": "owner-verified",
            "consent_status": "cleared-for-use",
            "claim_status": "provenance-backed",
            "safety_review_status": "human-cleared",
            "editorial_status": "approved",
            "public_destination": "portfolio-case-study",
            "review_actor": "authorized-editor",
            "review_date": "2026-07-19",
            "primary_view": "collective-work",
            "page_slot": "project-01",
            "alt_text": "People working together around a long table.",
            "caption": "A collective working session.",
            "credit": "Photo courtesy of the project archive.",
            "crop": "landscape",
            "focal_point": "center",
        }
        row.update(changes)
        return row

    def test_cleared_row_emits_only_allowlisted_public_fields(self):
        package, report = build_public_handoff(
            [self.cleared_row()], "synthetic-test-salt-value", "portfolio-case-study"
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(package["row_count"], 1)
        self.assertEqual(tuple(package["rows"][0]), PUBLIC_FIELDS)
        rendered = json.dumps(package)
        for private_value in (
            "PRIVATE-ASSET-001",
            "private-name.jpg",
            "/private/archive",
            "Private Person",
            "40.0,-73.0",
            "private words",
            "authorized-editor",
        ):
            self.assertNotIn(private_value, rendered)

    def test_unresolved_positive_clearance_fails_closed(self):
        package, report = build_public_handoff(
            [
                self.cleared_row(consent_status="pending"),
                self.cleared_row(uuid="PRIVATE-ASSET-002", public_destination="another-site"),
            ],
            "synthetic-test-salt-value",
            "portfolio-case-study",
        )
        self.assertEqual(package["row_count"], 0)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(len(report["blocked_rows"]), 2)
        self.assertIn("consent", " ".join(report["blocked_rows"][0]["reasons"]))
        self.assertIn("destination", " ".join(report["blocked_rows"][1]["reasons"]))

    def test_closed_row_is_excluded_without_claiming_an_error(self):
        package, report = build_public_handoff(
            [self.cleared_row(publication_status="not-reviewed")],
            "synthetic-test-salt-value",
            "portfolio-case-study",
        )
        self.assertEqual(package["row_count"], 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["closed_rows"], 1)

    def test_public_identifier_is_stable_and_destination_scoped(self):
        first = public_id("ASSET-1", "synthetic-test-salt-value", "portfolio")
        repeat = public_id("ASSET-1", "synthetic-test-salt-value", "portfolio")
        elsewhere = public_id("ASSET-1", "synthetic-test-salt-value", "press")
        self.assertEqual(first, repeat)
        self.assertNotEqual(first, elsewhere)
        self.assertEqual(len(first), 24)

    def test_short_salt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least 16"):
            build_public_handoff([self.cleared_row()], "too-short", "portfolio-case-study")

    def test_public_and_private_outputs_have_distinct_permissions(self):
        package, report = build_public_handoff(
            [self.cleared_row()], "synthetic-test-salt-value", "portfolio-case-study"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            public_path = root / "public" / "handoff.json"
            private_path = root / "private" / "blocked.json"
            write_public_package(public_path, package)
            write_private_report(private_path, report)
            self.assertEqual(public_path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(private_path.stat().st_mode & 0o777, 0o600)

    def test_public_writer_rejects_a_symlink_target(self):
        package, _ = build_public_handoff(
            [self.cleared_row()], "synthetic-test-salt-value", "portfolio-case-study"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("unchanged", encoding="utf-8")
            link = root / "handoff.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                write_public_package(link, package)
            self.assertEqual(target.read_text(encoding="utf-8"), "unchanged")

    def test_cli_rejects_nonprivate_salt_and_colliding_output_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "publication.csv"
            row = self.cleared_row()
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            salt = root / "salt.txt"
            salt.write_text("synthetic-test-salt-value", encoding="utf-8")
            salt.chmod(0o644)
            shared_output = root / "handoff.json"
            args = argparse.Namespace(
                input=manifest,
                destination="portfolio-case-study",
                salt_file=salt,
                output=shared_output,
                blocked_report=shared_output,
            )
            with self.assertRaisesRegex(ValueError, "0600"):
                command_public_handoff(args)
            salt.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "different paths"):
                command_public_handoff(args)


if __name__ == "__main__":
    unittest.main()
