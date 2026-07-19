import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from source_contract import (  # noqa: E402
    VISIBLE_LIBRARY_STILLS,
    fallback_source,
    load_source,
    visible_stills_predicate,
)


class SourceContractTests(unittest.TestCase):
    def test_whole_library_source_is_versioned_and_canonical(self):
        source = fallback_source(VISIBLE_LIBRARY_STILLS, 603_137, "Visible stills")
        self.assertEqual(source.kind, "visible-library-stills")
        self.assertEqual(source.predicate_version, "apple-photos-visible-stills-v1")
        predicate = visible_stills_predicate("photo")
        for column in ("ZKIND", "ZTRASHEDSTATE", "ZHIDDEN", "ZVISIBILITYSTATE", "ZBUNDLESCOPE"):
            self.assertIn(f"photo.{column}", predicate)

    def test_invalid_source_count_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "kind": "visible-library-stills",
                "identifier": VISIBLE_LIBRARY_STILLS,
                "title": "Visible stills",
                "snapshot_count": 0,
                "predicate_version": "apple-photos-visible-stills-v1",
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_source(path)


if __name__ == "__main__":
    unittest.main()
