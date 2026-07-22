import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicBoundaryTests(unittest.TestCase):
    def test_tracked_source_has_no_personal_home_or_photos_volume_paths(self):
        forbidden = (
            "/Users/" + "jburkart",
            "/Volumes/" + "apple-photos",
            "/Volumes/" + "16TB_SSD/Sites/photo-fieldwork",
        )
        violations = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "runs" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for value in forbidden:
                if value in text:
                    violations.append(f"{path.relative_to(ROOT)} contains {value}")
        self.assertEqual(violations, [])

    def test_ci_runs_core_checks_and_macos_helper_contract(self):
        workflow = (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")
        self.assertIn("make check", workflow)
        self.assertIn("macos-latest", workflow)
        self.assertIn("swiftc -typecheck", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)

    def test_helper_minimizes_preview_metadata_and_exports_private_original_properties(self):
        source = (
            ROOT / "integrations" / "jamie-photo-archive" / "JamiePhotoArchive.swift"
        ).read_text(encoding="utf-8")
        self.assertIn("CGImageDestinationCreateWithURL", source)
        self.assertIn("CGImageSourceCopyPropertiesAtIndex", source)
        self.assertIn("pixel-only CGImage", source)
        self.assertIn("mandatory independent verifier", source)
        self.assertIn("discarded_nonreusable_rows", source)
        self.assertIn("requestImageDataAndOrientation", source)
        self.assertIn("existing folder identifier must be a typed PhotoKit", source)
        self.assertIn("original_image_properties_json", source)
        self.assertIn("options.version = .original", source)
        self.assertNotIn("bitmap.representation(using: .jpeg", source)

    def test_helper_rejects_bare_database_collection_ids_before_photokit_fetch(self):
        source = (
            ROOT / "integrations" / "jamie-photo-archive" / "JamiePhotoArchive.swift"
        ).read_text(encoding="utf-8")
        archive_runner = source.split("final class ArchiveRunner", 1)[1]
        folder_function = archive_runner.split(
            "private func fetchFolder(identifier: String)", 1
        )[1].split("private func fetchAlbum(identifier: String)", 1)[0]
        album_function = archive_runner.split(
            "private func fetchAlbum(identifier: String)", 1
        )[1].split("private func children(of parent", 1)[0]
        for function, fetch_call, message in (
            (
                folder_function,
                "PHCollectionList.fetchCollectionLists",
                "existing folder identifier must be a typed PhotoKit local identifier",
            ),
            (
                album_function,
                "PHAssetCollection.fetchAssetCollections",
                "existing album identifier must be a typed PhotoKit local identifier",
            ),
        ):
            self.assertIn('#"/L0/[0-9]{3}$"#', function)
            self.assertLess(function.index(message), function.index(fetch_call))


if __name__ == "__main__":
    unittest.main()
