import csv
import argparse
import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from photo_fieldwork.review import build_review_workbench
from photo_fieldwork.cli import command_review
from photo_fieldwork.pipeline import write_csv


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "verify_preview_exports.py"
SPEC = importlib.util.spec_from_file_location("verify_preview_exports", VERIFY_SCRIPT)
verify_preview_exports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_preview_exports)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReviewTests(unittest.TestCase):
    def sample(self):
        return [
            {
                "uuid": "PHOTO-001",
                "filename": "private-name.jpg",
                "primary_view": "work",
                "assigned_view": "work",
                "score_total": "9.5",
                "sampling_reason": "score boundary",
                "view_selected_count": "12",
                "proposal_id": "pfp-1234567890abcdef",
                "master_sha256": "a" * 64,
                "config_sha256": "b" * 64,
                "round_id": "round-06",
                "sample_sha256": "c" * 64,
                "safety_status": "clear-automated",
                "persons": "Private Person",
                "local_path": "/private/archive/original.jpg",
                "raw_ocr": "private letter",
            }
        ]

    def make_preview(self, root: Path) -> Path:
        root.mkdir(mode=0o700)
        path = root / "PHOTO-001.jpg"
        Image.new("RGB", (24, 16), (20, 100, 180)).save(path, format="JPEG")
        path.chmod(0o600)
        return path

    def test_verifier_writes_complete_digest_bound_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = self.make_preview(root / "previews")
            inspection = root / "inspection.jsonl"
            inspection.write_text(
                '{"asset_identifier":"PHOTO-001","preview_exported":true}\n',
                encoding="utf-8",
            )
            rows = verify_preview_exports.verify_preview_rows(inspection, preview.parent)
            self.assertEqual(rows[0]["decode_status"], "ok")
            self.assertEqual(rows[0]["preview_sha256"], sha256(preview))
            self.assertEqual(rows[0]["width"], 24)
            output = root / "private" / "preview-index.csv"
            verify_preview_exports.write_index(output, rows)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            with output.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(next(csv.DictReader(handle))["uuid"], "PHOTO-001")

    def test_workbench_accepts_only_verified_evidence_and_allowlisted_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = self.make_preview(root / "previews")
            index = [
                {
                    "uuid": "PHOTO-001",
                    "filename": "index-required-by-reader.jpg",
                    "preview_path": str(preview.resolve()),
                    "preview_sha256": sha256(preview),
                    "decode_status": "ok",
                }
            ]
            output = root / "private-review" / "index.html"
            build_review_workbench(self.sample(), index, preview.parent, output)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("connect-src 'none'", rendered)
            self.assertIn("delegated-editorial-inference", rendered)
            self.assertIn('lens==="human-review"?"clear":"human-needs-review"', rendered)
            self.assertIn("judge every row with a visible reason", rendered)
            self.assertNotIn("file://", rendered)
            for forbidden in ("Private Person", "/private/archive", "private letter", "private-name.jpg"):
                self.assertNotIn(forbidden, rendered)
            copied_name = sha256(preview)[:24] + ".jpg"
            copied = output.parent / "review-assets" / copied_name
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(copied).st_mode & 0o777, 0o600)

    def test_review_cli_accepts_verified_index_without_inventory_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = self.make_preview(root / "previews")
            sample_path = root / "private" / "sample.csv"
            write_csv(sample_path, self.sample())
            index_path = root / "private" / "preview-index.csv"
            verify_preview_exports.write_index(
                index_path,
                [{
                    "uuid": "PHOTO-001",
                    "local_identifier": "PHOTO-001",
                    "preview_path": str(preview.resolve()),
                    "preview_sha256": sha256(preview),
                    "bytes": preview.stat().st_size,
                    "width": 24,
                    "height": 16,
                    "decode_status": "ok",
                    "reason": "",
                }],
            )
            output = root / "private-review" / "index.html"
            code = command_review(
                argparse.Namespace(
                    sample=sample_path,
                    preview_index=index_path,
                    preview_root=preview.parent,
                    output=output,
                )
            )
            self.assertEqual(code, 0)
            self.assertTrue(output.is_file())

    def test_workbench_rejects_digest_mismatch_outside_root_and_blocked_safety(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = self.make_preview(root / "previews")
            index = [{"uuid": "PHOTO-001", "preview_path": str(preview), "preview_sha256": "0" * 64, "decode_status": "ok"}]
            with self.assertRaisesRegex(ValueError, "digest differs"):
                build_review_workbench(self.sample(), index, preview.parent, root / "review" / "index.html")
            index[0]["preview_sha256"] = sha256(preview)
            other_root = root / "other"
            other_root.mkdir()
            with self.assertRaisesRegex(ValueError, "outside"):
                build_review_workbench(self.sample(), index, other_root, root / "review" / "index.html")
            blocked = self.sample()
            blocked[0]["safety_status"] = "hold"
            with self.assertRaisesRegex(ValueError, "blocked safety"):
                build_review_workbench(blocked, index, preview.parent, root / "review" / "index.html")

    def test_workbench_rejects_symlink_output_and_never_uses_uuid_as_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preview = self.make_preview(root / "previews")
            sample = self.sample()
            sample[0]["uuid"] = "../escape"
            index = [{"uuid": "../escape", "preview_path": str(preview), "preview_sha256": sha256(preview), "decode_status": "ok"}]
            output = root / "private-review" / "index.html"
            build_review_workbench(sample, index, preview.parent, output)
            self.assertFalse((root / "escape.jpg").exists())
            self.assertNotIn("../escape.jpg", output.read_text(encoding="utf-8"))
            redirected = root / "redirected"
            redirected.mkdir()
            symlink_parent = root / "linked-review"
            symlink_parent.symlink_to(redirected, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "must not be symlinks"):
                build_review_workbench(self.sample(), [{"uuid": "PHOTO-001", "preview_path": str(preview), "preview_sha256": sha256(preview), "decode_status": "ok"}], preview.parent, symlink_parent / "index.html")
            asset_root = root / "asset-symlink-review" / "review-assets"
            asset_root.mkdir(parents=True)
            outside = root / "outside.jpg"
            outside.write_bytes(b"unchanged")
            copied_name = sha256(preview)[:24] + ".jpg"
            (asset_root / copied_name).symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "asset destination"):
                build_review_workbench(self.sample(), [{"uuid": "PHOTO-001", "preview_path": str(preview), "preview_sha256": sha256(preview), "decode_status": "ok"}], preview.parent, asset_root.parent / "index.html")
            self.assertEqual(outside.read_bytes(), b"unchanged")

    def test_verifier_rejects_duplicate_canonical_uuid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previews = root / "previews"
            previews.mkdir()
            inspection = root / "inspection.jsonl"
            inspection.write_text(
                '{"asset_identifier":"PHOTO-001/L0/001","preview_exported":false}\n'
                '{"asset_identifier":"PHOTO-001/L0/002","preview_exported":false}\n',
                encoding="utf-8",
            )
            rows = verify_preview_exports.verify_preview_rows(inspection, previews)
            self.assertEqual(rows[1]["decode_status"], "invalid")
            self.assertIn("duplicate canonical UUID", str(rows[1]["reason"]))


if __name__ == "__main__":
    unittest.main()
