import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from photo_fieldwork.cli import command_studio
from photo_fieldwork.pipeline import write_csv
from photo_fieldwork.studio import build_studio_workbench


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StudioTests(unittest.TestCase):
    def field(self):
        return [
            {
                "uuid": "PHOTO-001",
                "primary_view": "people-path",
                "assigned_view": "people-path",
                "score_total": "8.5",
                "sampling_reason": "bounded encounter",
                "round_id": "encounter-01",
                "safety_status": "clear-automated",
                "persons": "Private Person",
                "date": "2007-06-01",
                "local_path": "/private/archive/original.jpg",
                "filename": "private-original.jpg",
            },
            {
                "uuid": "PHOTO-002",
                "primary_view": "chance-path",
                "assigned_view": "unclassified",
                "score_total": "2.0",
                "sampling_reason": "counter-search",
                "round_id": "encounter-01",
                "safety_status": "clear-automated",
                "persons": "",
                "date": "2014-10-03",
                "filename": "another-private-name.jpg",
            },
        ]

    def previews(self, root: Path):
        root.mkdir(mode=0o700)
        rows = []
        for number, color in ((1, (20, 100, 180)), (2, (180, 70, 40))):
            uuid = f"PHOTO-{number:03d}"
            path = root / f"{uuid}.jpg"
            Image.new("RGB", (32, 24), color).save(path, format="JPEG")
            path.chmod(0o600)
            rows.append(
                {
                    "uuid": uuid,
                    "preview_path": str(path.resolve()),
                    "preview_sha256": sha256(path),
                    "decode_status": "ok",
                }
            )
        return rows

    def metadata(self):
        return [
            {
                "uuid": "PHOTO-001",
                "asset": {
                    "filename": "source-secret.jpg",
                    "date_created": "2007-06-01T12:30:00",
                    "camera_make": "Example Camera",
                    "latitude": 40.123456,
                    "longitude": -73.123456,
                    "face_count": 1,
                },
                "relationships": {
                    "people": [{"person": "Private Person"}],
                    "albums": [{"album_title": "Residency source"}],
                    "keywords": [{"keyword": "hands"}],
                    "labels": [{"label": "table"}],
                    "places": [{"place": "New York"}],
                    "search_associations": [
                        {"category_name": "activity", "content_string": "meeting"}
                    ],
                },
            },
            {
                "uuid": "PHOTO-002",
                "asset": {"date_created": "2014-10-03T08:00:00", "face_count": 0},
                "relationships": {},
            },
        ]

    def test_studio_is_private_resumable_exploration_not_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previews = self.previews(root / "previews")
            output = root / "studio" / "index.html"
            studio_id = build_studio_workbench(
                self.field(),
                previews,
                root / "previews",
                output,
                metadata=self.metadata(),
                title="Residency workspace",
                seed=20260722,
            )
            rendered = output.read_text(encoding="utf-8")
            self.assertEqual(len(studio_id), 16)
            for expected in (
                "connect-src 'none'",
                "Chance walk",
                "Pin for comparison",
                "Return later",
                "Observation",
                "Association",
                "Question",
                "Claim candidate",
                'purpose: "private-exploration"',
                'evaluation_state: "not-evaluation"',
                'publication_state: "review-required"',
                "Private Person",
                "Residency source",
                "Example Camera",
            ):
                self.assertIn(expected, rendered)
            for forbidden in (
                "/private/archive",
                "private-original.jpg",
                "source-secret.jpg",
                "40.123456",
                "-73.123456",
            ):
                self.assertNotIn(forbidden, rendered)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            copied = list((output.parent / "studio-assets").iterdir())
            self.assertEqual(len(copied), 2)
            self.assertTrue(all(os.stat(path).st_mode & 0o777 == 0o600 for path in copied))

    def test_studio_requires_exact_metadata_and_verified_previews(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previews = self.previews(root / "previews")
            with self.assertRaisesRegex(ValueError, "exactly match"):
                build_studio_workbench(
                    self.field(),
                    previews,
                    root / "previews",
                    root / "studio" / "index.html",
                    metadata=self.metadata()[:1],
                )
            previews[0]["preview_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "digest differs"):
                build_studio_workbench(
                    self.field(),
                    previews,
                    root / "previews",
                    root / "other-studio" / "index.html",
                )

    @unittest.skipUnless(shutil.which("node"), "Node is required for generated JavaScript syntax check")
    def test_generated_studio_javascript_parses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previews = self.previews(root / "previews")
            output = root / "studio" / "index.html"
            build_studio_workbench(
                self.field(),
                previews,
                root / "previews",
                output,
                metadata=self.metadata(),
            )
            rendered = output.read_text(encoding="utf-8")
            script = rendered.split("<script>", 1)[1].split("</script>", 1)[0]
            script_path = root / "studio.js"
            script_path.write_text(script, encoding="utf-8")
            completed = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_studio_cli_accepts_private_metadata_jsonl(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previews = self.previews(root / "previews")
            field_path = root / "private" / "field.csv"
            write_csv(field_path, self.field())
            index_path = root / "private" / "preview-index.csv"
            with index_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(previews[0]))
                writer.writeheader()
                writer.writerows(previews)
            index_path.chmod(0o600)
            metadata_path = root / "private" / "metadata.jsonl"
            metadata_path.write_text(
                "".join(json.dumps(record) + "\n" for record in self.metadata()),
                encoding="utf-8",
            )
            metadata_path.chmod(0o600)
            output = root / "studio" / "index.html"
            code = command_studio(
                argparse.Namespace(
                    field=field_path,
                    preview_index=index_path,
                    preview_root=root / "previews",
                    metadata=metadata_path,
                    output=output,
                    title="Residency workspace",
                    seed=20260722,
                )
            )
            self.assertEqual(code, 0)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
