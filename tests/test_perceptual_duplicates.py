import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts"
sys.path.insert(0, str(SCRIPTS))

try:
    from PIL import Image
    from cluster_perceptual_duplicates import difference_hash, hamming
except ImportError:
    Image = None
    difference_hash = None
    hamming = None


@unittest.skipIf(Image is None, "Pillow is optional for the core synthetic workflow")
class PerceptualDuplicateTests(unittest.TestCase):
    def test_identical_local_previews_have_zero_hash_distance(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.jpg"
            second = Path(temporary) / "second.jpg"
            image = Image.new("RGB", (20, 20), "white")
            image.save(first)
            image.save(second)
            self.assertEqual(hamming(difference_hash(first), difference_hash(second)), 0)


if __name__ == "__main__":
    unittest.main()
