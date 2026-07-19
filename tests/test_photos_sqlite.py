import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "curate-apple-photos" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from photos_sqlite import consistent_snapshot, open_query_only  # noqa: E402


class PhotosSQLiteTests(unittest.TestCase):
    def test_keep_requires_explicit_private_directory(self):
        with self.assertRaisesRegex(ValueError, "snapshot_directory"):
            with consistent_snapshot(Path("missing"), keep=True):
                pass

    def test_consistent_snapshot_includes_committed_wal_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Photos.sqlite"
            writer = sqlite3.connect(source)
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("CREATE TABLE example(value TEXT)")
            writer.commit()
            writer.execute("INSERT INTO example(value) VALUES ('from-wal')")
            writer.commit()
            snapshots = root / "snapshots"
            with consistent_snapshot(source, snapshot_directory=snapshots) as (snapshot, metadata):
                self.assertEqual(os.stat(snapshot).st_mode & 0o777, 0o600)
                self.assertTrue(metadata["live_connection_query_only"])
                reader = open_query_only(snapshot, immutable=True)
                self.assertEqual(reader.execute("SELECT value FROM example").fetchall(), [("from-wal",)])
                reader.close()
                snapshot_path = snapshot
            self.assertFalse(snapshot_path.exists())
            writer.close()


if __name__ == "__main__":
    unittest.main()
