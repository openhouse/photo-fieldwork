from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone


DECISION_FIELDS = [
    "decision_id",
    "uuid",
    "filename",
    "view_id",
    "judgment",
    "visible_reason",
    "error_category",
    "safety_status",
    "provenance_status",
    "reviewer_actor",
    "reviewer_lens",
    "round_id",
    "decision_at",
    "supersedes",
]


def decision_id(row: dict[str, str]) -> str:
    material = "\x1f".join(
        str(row.get(field, ""))
        for field in [
            "uuid",
            "view_id",
            "judgment",
            "visible_reason",
            "safety_status",
            "reviewer_actor",
            "round_id",
            "decision_at",
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()[:20]


def normalize_feedback(
    rows: list[dict[str, str]],
    round_id: str = "",
    reviewer_actor: str = "",
) -> list[dict[str, str]]:
    now = datetime.now(timezone.utc).isoformat()
    normalized = []
    for source in rows:
        judgment = source.get("judgment", "").strip().lower()
        if judgment not in {"fit", "reject", "uncertain"}:
            continue
        row = {
            "decision_id": "",
            "uuid": source["uuid"],
            "filename": source.get("filename", ""),
            "view_id": source.get("view_id") or source.get("primary_view", ""),
            "judgment": judgment,
            "visible_reason": source.get("visible_reason") or source.get("evaluation_note", ""),
            "error_category": source.get("error_category", ""),
            "safety_status": source.get("editorial_safety_status") or source.get("safety_status", "clear"),
            "provenance_status": source.get("provenance_status", "hypothesis"),
            "reviewer_actor": source.get("reviewer_actor") or reviewer_actor,
            "reviewer_lens": source.get("reviewer_lens", ""),
            "round_id": source.get("round_id") or round_id,
            "decision_at": source.get("decision_at") or now,
            "supersedes": source.get("supersedes", ""),
        }
        row["decision_id"] = source.get("decision_id") or decision_id(row)
        normalized.append(row)
    return normalized


def append_decisions(
    existing: list[dict[str, str]],
    incoming: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows = [dict(row) for row in existing]
    seen = {row.get("decision_id") for row in rows}
    latest = {(row.get("uuid", ""), row.get("view_id", "")): row.get("decision_id", "") for row in rows}
    for source in incoming:
        row = dict(source)
        key = (row.get("uuid", ""), row.get("view_id", ""))
        if not row.get("supersedes") and latest.get(key):
            row["supersedes"] = latest[key]
        if row["decision_id"] not in seen:
            rows.append(row)
            seen.add(row["decision_id"])
            latest[key] = row["decision_id"]
    return rows


def apply_decisions(
    inventory: list[dict[str, str]],
    decisions: list[dict[str, str]],
    propagate_holds: bool = True,
) -> tuple[list[dict[str, str]], dict]:
    """Apply latest decisions without erasing their append-only history."""

    latest: dict[tuple[str, str], dict[str, str]] = {}
    for row in decisions:
        latest[(row["uuid"], row.get("view_id", ""))] = row

    held_ids = {
        row["uuid"]
        for row in latest.values()
        if row.get("safety_status", "").lower() == "hold"
    }
    if propagate_holds:
        clusters: dict[tuple[str, str], set[str]] = defaultdict(set)
        by_id = {row["uuid"]: row for row in inventory}
        for row in inventory:
            for field in ("duplicate_group", "burst_group"):
                value = row.get(field, "").strip()
                if value:
                    clusters[(field, value)].add(row["uuid"])
        for uuid in list(held_ids):
            row = by_id.get(uuid, {})
            for field in ("duplicate_group", "burst_group"):
                value = row.get(field, "").strip()
                if value:
                    held_ids.update(clusters[(field, value)])

    output = []
    rejected_view_count = 0
    fit_view_count = 0
    for source in inventory:
        row = dict(source)
        if row["uuid"] in held_ids:
            row["safety_status"] = "hold"
            row["safety_reason"] = row.get("safety_reason") or "editorial decision or cluster propagation"

        candidates = [value for value in row.get("candidate_views", "").split(";") if value]
        excluded = {value for value in row.get("excluded_views", "").split(";") if value}
        approved = []
        for (uuid, view), decision in latest.items():
            if uuid != row["uuid"]:
                continue
            if decision["judgment"] == "reject" and view:
                excluded.add(view)
                rejected_view_count += 1
            if decision["judgment"] == "fit" and view:
                approved.append(view)
                fit_view_count += 1
        candidates = [view for view in candidates if view not in excluded]
        row["candidate_views"] = ";".join(dict.fromkeys([*approved, *candidates]))
        row["excluded_views"] = ";".join(sorted(excluded))
        output.append(row)

    return output, {
        "inventory_count": len(inventory),
        "decision_count": len(decisions),
        "held_or_propagated_count": len(held_ids),
        "rejected_view_applications": rejected_view_count,
        "fit_view_applications": fit_view_count,
    }


def merge_compact_feedback(
    sample: list[dict[str, str]], compact: list[dict[str, str]]
) -> list[dict[str, str]]:
    compact_by_id = {row["uuid"]: row for row in compact}
    if len(compact_by_id) != len(compact):
        raise ValueError("compact feedback contains duplicate UUIDs")
    merged = []
    for source in sample:
        if source["uuid"] not in compact_by_id:
            raise ValueError(f"missing compact feedback for {source['uuid']}")
        row = dict(source)
        row.update(compact_by_id[source["uuid"]])
        row["evaluation_note"] = row.get("visible_reason", row.get("evaluation_note", ""))
        merged.append(row)
    extra = set(compact_by_id) - {row["uuid"] for row in sample}
    if extra:
        raise ValueError(f"compact feedback contains {len(extra)} unexpected UUIDs")
    return merged
