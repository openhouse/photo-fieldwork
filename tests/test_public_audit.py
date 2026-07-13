import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.audit import audit_paths


class PublicAuditTests(unittest.TestCase):
    def test_private_run_artifacts_and_real_images_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                root / "runs" / "v01" / "manifest.csv",
                root / "manifests" / "v01-receipt.json",
                root / "docs" / "private-photo.jpg",
            ]
            failures = audit_paths(root, paths)
            self.assertEqual(len(failures), 3)

    def test_synthetic_images_and_source_files_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / "tests" / "fixtures" / "synthetic" / "sample.jpg", root / "src" / "tool.py"]
            self.assertEqual(audit_paths(root, paths), [])
