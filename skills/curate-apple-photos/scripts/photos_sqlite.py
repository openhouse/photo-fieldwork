#!/usr/bin/env python3
"""Create and open consistent, read-only Apple Photos SQLite snapshots."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote


def sqlite_uri(path: Path, mode: str, immutable: bool = False) -> str:
    suffix = f"mode={mode}"
    if immutable:
        suffix += "&immutable=1"
    return f"file:{quote(str(path.resolve()))}?{suffix}"


def open_query_only(path: Path, *, immutable: bool) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(
        sqlite_uri(path, "ro", immutable=immutable),
        uri=True,
        timeout=120,
    )
    connection.execute("PRAGMA query_only=ON")
    query_only = connection.execute("PRAGMA query_only").fetchone()[0]
    if query_only != 1:
        connection.close()
        raise RuntimeError("could not enforce SQLite query_only mode")
    return connection


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


@contextmanager
def consistent_snapshot(
    source: Path,
    *,
    snapshot_directory: Path | None = None,
    keep: bool = False,
):
    """Yield an immutable snapshot that includes committed live WAL content.

    The live database is opened with ``mode=ro`` and ``query_only=ON``. SQLite's
    backup API copies a transactionally consistent view to a separate private
    database. Consumers then open only that frozen file with ``immutable=1``.
    """
    if keep and snapshot_directory is None:
        raise ValueError("keep=True requires an explicit private snapshot_directory")
    if snapshot_directory is None:
        root = Path(tempfile.mkdtemp(prefix="photo-fieldwork-snapshot-"))
        temporary_root = True
    else:
        root = snapshot_directory.resolve()
        private_directory(root)
        temporary_root = False
    root.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix="photos-", suffix=".sqlite", dir=root)
    os.close(descriptor)
    snapshot = Path(name)
    snapshot.chmod(0o600)
    source_connection = None
    destination = None
    try:
        source_connection = open_query_only(source, immutable=False)
        user_version = source_connection.execute("PRAGMA user_version").fetchone()[0]
        destination = sqlite3.connect(snapshot)
        source_connection.backup(destination)
        destination.close()
        destination = None
        snapshot.chmod(0o600)
        yield snapshot, {
            "snapshot_bytes": snapshot.stat().st_size,
            "sqlite_user_version": user_version,
            "live_connection_mode": "ro",
            "live_connection_query_only": True,
            "snapshot_connection_mode": "ro-immutable",
        }
    finally:
        if destination is not None:
            destination.close()
        if source_connection is not None:
            source_connection.close()
        if not keep:
            snapshot.unlink(missing_ok=True)
            if temporary_root:
                shutil.rmtree(root, ignore_errors=True)
