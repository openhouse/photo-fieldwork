from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_event (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  occurred_at TEXT NOT NULL,
  run_id TEXT NOT NULL,
  round_id TEXT,
  asset_uuid TEXT,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL,
  previous_state TEXT,
  new_state TEXT,
  reason TEXT,
  payload_json TEXT NOT NULL,
  config_hash TEXT,
  inspection_profile_hash TEXT,
  code_version TEXT
);
CREATE INDEX IF NOT EXISTS idx_decision_asset ON decision_event(asset_uuid, sequence);
CREATE INDEX IF NOT EXISTS idx_decision_round ON decision_event(round_id, sequence);
CREATE TRIGGER IF NOT EXISTS decision_event_no_update
BEFORE UPDATE ON decision_event
BEGIN
  SELECT RAISE(ABORT, 'decision_event is append-only');
END;
CREATE TRIGGER IF NOT EXISTS decision_event_no_delete
BEFORE DELETE ON decision_event
BEGIN
  SELECT RAISE(ABORT, 'decision_event is append-only');
END;
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO ledger_meta(key, value) VALUES ('schema_version', '1')"
    )
    conn.commit()
    return conn


def append_event(
    path: Path,
    *,
    run_id: str,
    event_type: str,
    actor: str,
    asset_uuid: str | None = None,
    round_id: str | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    reason: str | None = None,
    payload: dict | None = None,
    config_hash: str | None = None,
    inspection_profile_hash: str | None = None,
    code_version: str | None = None,
    occurred_at: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
    conn = connect(path)
    try:
        conn.execute(
            """
            INSERT INTO decision_event(
              event_id, occurred_at, run_id, round_id, asset_uuid, event_type,
              actor, previous_state, new_state, reason, payload_json,
              config_hash, inspection_profile_hash, code_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                timestamp,
                run_id,
                round_id,
                asset_uuid,
                event_type,
                actor,
                previous_state,
                new_state,
                reason,
                json.dumps(payload or {}, sort_keys=True, separators=(",", ":")),
                config_hash,
                inspection_profile_hash,
                code_version,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return event_id


def append_events(path: Path, events: Iterable[dict]) -> list[str]:
    identifiers = []
    for event in events:
        identifiers.append(append_event(path, **event))
    return identifiers


def read_events(path: Path, *, asset_uuid: str | None = None) -> list[dict]:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    query = "SELECT * FROM decision_event"
    params: tuple = ()
    if asset_uuid:
        query += " WHERE asset_uuid = ?"
        params = (asset_uuid,)
    query += " ORDER BY sequence"
    rows = []
    for record in conn.execute(query, params):
        row = dict(record)
        row["payload"] = json.loads(row.pop("payload_json"))
        rows.append(row)
    conn.close()
    return rows


def export_jsonl(path: Path, output: Path) -> int:
    rows = read_events(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return len(rows)
