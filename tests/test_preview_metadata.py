import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "curate-apple-photos" / "scripts" / "verify_preview_exports.py"
SPEC = importlib.util.spec_from_file_location("verify_preview_exports", SCRIPT)
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)


class FakeExif(dict):
    def __init__(self, nested):
        super().__init__({34665: 1})
        self.nested = nested

    def get_ifd(self, _):
        return self.nested


class FakeImage:
    width = 1280
    height = 854

    def __init__(self, nested):
        self.exif = FakeExif(nested)

    def getexif(self):
        return self.exif


class PreviewMetadataTests(unittest.TestCase):
    def test_encoder_srgb_and_matching_dimensions_are_not_source_metadata(self):
        image = FakeImage({40961: 1, 40962: 1280, 40963: 854})
        self.assertFalse(preview.has_source_bearing_exif(image))

    def test_encoder_dimensions_without_optional_color_space_are_not_source_metadata(self):
        image = FakeImage({40962: 1280, 40963: 854})
        self.assertFalse(preview.has_source_bearing_exif(image))

    def test_source_exif_and_false_dimensions_fail(self):
        source_tag = FakeImage({40961: 1, 40962: 1280, 40963: 854, 36867: "date"})
        wrong_size = FakeImage({40961: 1, 40962: 1200, 40963: 854})
        wrong_color = FakeImage({40961: 2, 40962: 1280, 40963: 854})
        self.assertTrue(preview.has_source_bearing_exif(source_tag))
        self.assertTrue(preview.has_source_bearing_exif(wrong_size))
        self.assertTrue(preview.has_source_bearing_exif(wrong_color))


if __name__ == "__main__":
    unittest.main()
