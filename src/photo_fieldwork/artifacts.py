from __future__ import annotations

import json
from pathlib import Path

from .pipeline import read_csv, write_csv


def union_csv(paths: list[Path]) -> tuple[list[dict[str, str]], dict]:
    rows = []
    seen: dict[str, dict[str, str]] = {}
    for path in paths:
        for row in read_csv(path):
            uuid = row["uuid"]
            if uuid in seen and row != seen[uuid]:
                raise ValueError(f"conflicting duplicate UUID in candidate union: {uuid}")
            if uuid not in seen:
                seen[uuid] = row
                rows.append(row)
    return rows, {"inputs": len(paths), "rows": len(rows), "unique": len(seen)}


def subtract_csv(source: Path, existing: list[Path]) -> tuple[list[dict[str, str]], dict]:
    excluded = {row["uuid"] for path in existing for row in read_csv(path)}
    source_rows = read_csv(source)
    rows = [row for row in source_rows if row["uuid"] not in excluded]
    return rows, {
        "source_rows": len(source_rows),
        "excluded_ids": len(excluded),
        "remaining_rows": len(rows),
    }


def diff_csv(before: Path, after: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], dict]:
    first = {row["uuid"]: row for row in read_csv(before)}
    second = {row["uuid"]: row for row in read_csv(after)}
    added = [second[uuid] for uuid in sorted(set(second) - set(first))]
    removed = [first[uuid] for uuid in sorted(set(first) - set(second))]
    changed = sum(first[uuid] != second[uuid] for uuid in set(first) & set(second))
    return added, removed, {
        "before": len(first),
        "after": len(second),
        "added": len(added),
        "removed": len(removed),
        "changed_shared_rows": changed,
    }


def merge_jsonl(paths: list[Path], identifier_field: str = "asset_identifier") -> tuple[list[dict], dict]:
    rows = []
    seen: dict[str, dict] = {}
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            identifier = row.get(identifier_field) or row.get("uuid")
            if not identifier:
                raise ValueError(f"missing identifier in {path}:{number}")
            base = str(identifier).split("/", 1)[0]
            if base in seen and row != seen[base]:
                raise ValueError(f"conflicting inspection result for {base}")
            if base not in seen:
                seen[base] = row
                rows.append(row)
    return rows, {"inputs": len(paths), "rows": len(rows), "unique": len(seen)}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def replacement_audit(master: Path, evaluated: list[Path]) -> tuple[list[dict[str, str]], dict]:
    evaluated_ids = {row["uuid"] for path in evaluated for row in read_csv(path)}
    master_rows = read_csv(master)
    entrants = [row for row in master_rows if row["uuid"] not in evaluated_ids]
    return entrants, {
        "master_count": len(master_rows),
        "evaluated_unique": len(evaluated_ids),
        "unevaluated_final_entrants": len(entrants),
        "status": "PASS" if not entrants else "REVIEW_REQUIRED",
    }
