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


if __name__ == "__main__":
    unittest.main()
