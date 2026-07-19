from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


EVENT_TYPES = {"assignment", "evaluation", "safety"}
ASSIGNMENT_STATES = {"assigned", "unclassified", "sparse-hypothesis"}
EVALUATION_STATES = {"fit", "reject", "uncertain"}
SAFETY_STATES = {"clear", "review-required", "hold", "unavailable"}


def _canonical(event: dict) -> bytes:
    payload = {key: value for key, value in event.items() if key != "event_sha256"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _event_sha256(event: dict) -> str:
    return hashlib.sha256(_canonical(event)).hexdigest()


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"malformed decision ledger row {line_number}: {error.msg}") from error
    return events


def audit_events(events: Iterable[dict]) -> dict:
    events = list(events)
    errors: list[str] = []
    seen_ids: dict[str, dict] = {}
    previous_hash = ""
    event_count = 0
    for expected_sequence, event in enumerate(events, start=1):
        event_count += 1
        event_id = str(event.get("event_id", "")).strip()
        if not event_id:
            errors.append(f"sequence {expected_sequence}: missing event_id")
        elif event_id in seen_ids:
            errors.append(f"sequence {expected_sequence}: duplicate event_id {event_id}")
        if int(event.get("sequence", 0)) != expected_sequence:
            errors.append(f"sequence {expected_sequence}: sequence number mismatch")
        if event.get("previous_event_sha256", "") != previous_hash:
            errors.append(f"sequence {expected_sequence}: hash-chain predecessor mismatch")
        calculated = _event_sha256(event)
        if event.get("event_sha256") != calculated:
            errors.append(f"sequence {expected_sequence}: event hash mismatch")
        supersedes = str(event.get("supersedes_event_id", "")).strip()
        if supersedes:
            predecessor = seen_ids.get(supersedes)
            if predecessor is None:
                errors.append(f"sequence {expected_sequence}: supersedes unknown event {supersedes}")
            elif (
                predecessor.get("asset_uuid"), predecessor.get("event_type"), predecessor.get("view_id", "")
            ) != (event.get("asset_uuid"), event.get("event_type"), event.get("view_id", "")):
                errors.append(f"sequence {expected_sequence}: supersedes a different decision subject")
        if event_id:
            seen_ids[event_id] = event
        previous_hash = str(event.get("event_sha256", ""))
    ledger_sha256 = hashlib.sha256(
        ("\n".join(str(event.get("event_sha256", "")) for event in events) + ("\n" if event_count else "")).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "event_count": event_count,
        "ledger_sha256": ledger_sha256,
        "errors": errors,
    }


def audit_ledger(path: Path) -> dict:
    return audit_events(read_ledger(path))


def _validate_incoming(source: dict) -> None:
    event_type = str(source.get("event_type", "")).strip()
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported decision event_type {event_type or '<empty>'}")
    for field in ("asset_uuid", "actor", "reason"):
        if not str(source.get(field, "")).strip():
            raise ValueError(f"decision event requires {field}")
    state = str(source.get("state", "")).strip().lower()
    allowed = {
        "assignment": ASSIGNMENT_STATES,
        "evaluation": EVALUATION_STATES,
        "safety": SAFETY_STATES,
    }[event_type]
    if state not in allowed:
        raise ValueError(f"invalid {event_type} state {state or '<empty>'}")
    if event_type in {"assignment", "evaluation"} and not str(source.get("view_id", "")).strip():
        raise ValueError(f"{event_type} event requires view_id")
    if event_type == "safety" and state == "clear" and source.get("authority") != "human":
        raise ValueError("only an identified human authority may record safety clearance")


def append_events(path: Path, incoming: Iterable[dict]) -> dict:
    existing = read_ledger(path)
    before = audit_events(existing)
    if before["status"] != "PASS":
        raise ValueError("cannot append to a decision ledger that fails integrity audit")
    known_ids = {str(event["event_id"]): event for event in existing}
    latest: dict[tuple[str, str, str], dict] = {}
    for event in existing:
        latest[(event["asset_uuid"], event["event_type"], event.get("view_id", ""))] = event
    previous_hash = str(existing[-1]["event_sha256"]) if existing else ""
    prepared = []
    now = datetime.now(timezone.utc).isoformat()
    for offset, source in enumerate(incoming, start=1):
        source = dict(source)
        _validate_incoming(source)
        key = (
            str(source["asset_uuid"]).split("/", 1)[0],
            str(source["event_type"]).strip(),
            str(source.get("view_id", "")).strip(),
        )
        predecessor = latest.get(key)
        event = {
            "schema_version": 1,
            "sequence": len(existing) + offset,
            "event_id": str(source.get("event_id", "")).strip(),
            "occurred_at": str(source.get("occurred_at", "")).strip() or now,
            "asset_uuid": key[0],
            "event_type": key[1],
            "view_id": key[2],
            "state": str(source["state"]).strip().lower(),
            "actor": str(source["actor"]).strip(),
            "authority": str(source.get("authority", "")).strip(),
            "reason": str(source["reason"]).strip(),
            "round_id": str(source.get("round_id", "")).strip(),
            "proposal_id": str(source.get("proposal_id", "")).strip(),
            "master_sha256": str(source.get("master_sha256", "")).strip(),
            "supersedes_event_id": str(source.get("supersedes_event_id", "")).strip(),
            "previous_event_sha256": previous_hash,
        }
        if not event["event_id"]:
            material = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            event["event_id"] = f"pfd-{hashlib.sha256(material.encode()).hexdigest()[:20]}"
        if event["event_id"] in known_ids:
            raise ValueError(f"duplicate decision event_id {event['event_id']}")
        if predecessor:
            if not event["supersedes_event_id"]:
                event["supersedes_event_id"] = predecessor["event_id"]
            elif event["supersedes_event_id"] != predecessor["event_id"]:
                raise ValueError("decision must supersede the latest event for the same subject")
        elif event["supersedes_event_id"]:
            raise ValueError("first decision for a subject cannot supersede another event")
        event["event_sha256"] = _event_sha256(event)
        previous_hash = event["event_sha256"]
        prepared.append(event)
        known_ids[event["event_id"]] = event
        latest[key] = event
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in prepared:
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n")
    report = audit_ledger(path)
    if report["status"] != "PASS":
        raise ValueError("decision ledger failed integrity audit after append")
    report["appended"] = len(prepared)
    return report


def materialize(inventory: list[dict[str, str]], events: Iterable[dict]) -> tuple[list[dict[str, str]], dict]:
    events = list(events)
    audit = audit_events(events)
    if audit["status"] != "PASS":
        raise ValueError("cannot materialize a decision ledger that fails integrity audit")
    latest: dict[tuple[str, str, str], dict] = {}
    for event in events:
        latest[(event["asset_uuid"], event["event_type"], event.get("view_id", ""))] = event

    rows = [dict(row) for row in inventory]
    by_uuid = {str(row["uuid"]).split("/", 1)[0]: row for row in rows}
    held: set[str] = set()
    for (asset_uuid, event_type, view_id), event in latest.items():
        row = by_uuid.get(asset_uuid)
        if row is None:
            continue
        if event_type == "assignment":
            row["assigned_view"] = view_id
            row["assignment_status"] = event["state"]
            row["assignment_reason"] = event["reason"]
            row["assignment_event_id"] = event["event_id"]
        elif event_type == "evaluation" and event["state"] == "reject":
            excluded = {value for value in str(row.get("excluded_views", "")).split(";") if value}
            excluded.add(view_id)
            row["excluded_views"] = ";".join(sorted(excluded))
        elif event_type == "safety":
            row["safety_status"] = event["state"]
            row["safety_reason"] = event["reason"]
            row["safety_event_id"] = event["event_id"]
            if event["state"] in {"hold", "unavailable", "review-required"}:
                held.add(asset_uuid)

    cluster_members: dict[tuple[str, str], set[str]] = defaultdict(set)
    for asset_uuid, row in by_uuid.items():
        for field in ("perceptual_cluster_id", "duplicate_group", "duplicate_group_id", "burst_group"):
            value = str(row.get(field, "")).strip()
            if value:
                cluster_members[(field, value)].add(asset_uuid)
    propagated = set(held)
    for asset_uuid in list(held):
        row = by_uuid.get(asset_uuid, {})
        for field in ("perceptual_cluster_id", "duplicate_group", "duplicate_group_id", "burst_group"):
            value = str(row.get(field, "")).strip()
            if value:
                propagated.update(cluster_members[(field, value)])
    for asset_uuid in propagated - held:
        row = by_uuid[asset_uuid]
        row["safety_status"] = "hold"
        row["safety_reason"] = "related-frame hold propagated from decision ledger"
        row["safety_event_id"] = "propagated"
    return rows, {
        "schema_version": 1,
        "status": "PASS",
        "ledger_sha256": audit["ledger_sha256"],
        "event_count": audit["event_count"],
        "materialized_rows": len(rows),
        "held_or_related_rows": len(propagated),
    }
