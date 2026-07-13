import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.profile import check_profile, load_profile
from photo_fieldwork.review import render_workbench

ROOT = Path(__file__).resolve().parents[1]


class ProfileAndReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def profile(self):
        app = self.root / "Helper.app"
        app.mkdir()
        photos = self.root / "Photos.sqlite"
        photos.touch()
        return {
            "schema_version": 1,
            "name": "test",
            "workspace_root": str(self.root),
            "photos_database": str(photos),
            "helper": {"app_path": str(app), "bundle_id": "test.helper"},
            "default_source": "visible",
            "sources": {
                "visible": {
                    "title": "Visible",
                    "identifier": "visible-library-stills://v1",
                    "expected_count": 10,
                    "inventory_db": None,
                }
            },
            "protected_folders": {
                "root": {"title": "Root", "identifier": "ROOT"},
                "private": {"title": "Private", "identifier": "PRIVATE"},
                "audit": {"title": "Audit", "identifier": "AUDIT"},
            },
        }

    def test_profile_load_and_check(self):
        path = self.root / "profile.json"
        path.write_text(json.dumps(self.profile()), encoding="utf-8")
        profile = load_profile(path)
        report = check_profile(profile, minimum_free_gb=0)
        self.assertEqual(report["status"], "PASS")

    def test_example_profile_matches_loader_contract(self):
        profile = load_profile(ROOT / "config" / "machine-profile.example.json")
        self.assertEqual(profile["default_writer_adapter"], "photokit")

    def test_review_workbench_is_local_and_data_minimized(self):
        output = self.root / "review.html"
        render_workbench(
            [{
                "uuid": "ABC",
                "filename": "example.jpg",
                "primary_view": "01",
                "retrieval_basis": "album:example",
                "persons": "Private Person",
                "place": "Exact private place",
            }],
            self.root / "previews",
            output,
        )
        document = output.read_text(encoding="utf-8")
        self.assertIn("Local review workbench", document)
        self.assertNotIn("Private Person", document)
        self.assertNotIn("Exact private place", document)
        self.assertNotIn("https://", document)
