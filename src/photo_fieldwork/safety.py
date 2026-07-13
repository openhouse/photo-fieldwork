from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import canonical_asset_id, split_values


PRECEDENCE = {"clear": 0, "needs-review": 1, "hold": 2}
ALLOWED_RELATIONS = {"uuid", "persons", "albums", "event_cluster", "labels"}


def _matches(row: dict[str, str], rule: dict[str, Any]) -> bool:
    relation = str(rule.get("relation") or "")
    if relation not in ALLOWED_RELATIONS:
        raise ValueError(f"unsupported safety relation: {relation}")
    values = [str(value).casefold() for value in rule.get("values", []) if str(value).strip()]
    if not values:
        return False
    if relation == "uuid":
        haystack = [canonical_asset_id(row.get("uuid"))]
    else:
        haystack = [value.casefold() for value in split_values(row.get(relation))]
    match = str(rule.get("match") or "exact")
    if match == "exact":
        return any(item == value for item in haystack for value in values)
    if match == "contains":
        return any(value in item for item in haystack for value in values)
    raise ValueError(f"unsupported safety match: {match}")


def apply_safety_policy(
    rows: list[dict[str, str]], policy: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    if int(policy.get("schema_version", 0)) != 1:
        raise ValueError("unsupported safety policy schema_version")
    rules = policy.get("rules") or []
    updated: list[dict[str, str]] = []
    decisions: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for original in rows:
        row = dict(original)
        source_faces = int(float(row.get("source_face_count") or row.get("face_count") or 0))
        inspected_faces = int(float(row.get("inspected_face_count") or row.get("detected_face_count") or 0))
        row["source_face_count"] = str(source_faces)
        row["inspected_face_count"] = str(inspected_faces)
        row["known_face_count"] = str(max(source_faces, inspected_faces))
        state = str(row.get("safety_status") or "clear").lower()
        if state not in PRECEDENCE:
            raise ValueError(f"invalid safety_status: {state}")
        reasons = split_values(row.get("safety_reason"))
        for rule in rules:
            if not _matches(row, rule):
                continue
            action = str(rule.get("action") or "hold")
            if action not in PRECEDENCE:
                raise ValueError(f"unsupported safety action: {action}")
            reason = str(rule.get("reason") or "protected relation")
            if PRECEDENCE[action] > PRECEDENCE[state]:
                state = action
            if reason not in reasons:
                reasons.append(reason)
            decisions.append(
                {
                    "uuid": canonical_asset_id(row["uuid"]),
                    "decision": action,
                    "rule_id": str(rule.get("id") or "unnamed-rule"),
                    "relation": str(rule["relation"]),
                    "reason": reason,
                    "decided_at": now,
                }
            )
        row["safety_status"] = state
        row["safety_reason"] = ";".join(reasons)
        updated.append(row)
    return updated, decisions
