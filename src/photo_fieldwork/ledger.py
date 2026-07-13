from __future__ import annotations

import hashlib
import json


def event(event_type: str, row: dict[str, str], details: dict) -> dict:
    value = {
        "schema_version": 1,
        "asset_id": row["uuid"],
        "event_type": event_type,
        "proposal_id": row.get("proposal_id", ""),
        "master_sha256": row.get("master_sha256", ""),
        "details": details,
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    value["event_id"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return value


def build_events(
    master: list[dict[str, str]],
    holds: list[dict[str, str]],
    feedback: list[dict[str, str]],
) -> list[dict]:
    events = []
    for row in master:
        events.append(
            event(
                "selected",
                row,
                {
                    "primary_view": row.get("primary_view", ""),
                    "selection_tier": row.get("selection_tier", ""),
                    "selection_reason": row.get("selection_reason", ""),
                    "retrieval_hypotheses": row.get("candidate_views", ""),
                    "visible_description": row.get("visible_context", ""),
                    "verified_contexts": row.get("verified_contexts", ""),
                    "safety_state": row.get("safety_state") or row.get("safety_status") or "",
                },
            )
        )
    for row in holds:
        events.append(
            event(
                "held",
                row,
                {
                    "safety_state": row.get("safety_state") or row.get("safety_status") or "",
                    "generalized_reason": row.get("safety_reason", ""),
                },
            )
        )
    for row in feedback:
        events.append(
            event(
                "evaluated",
                row,
                {
                    "round_id": row.get("round_id", ""),
                    "judgment": row.get("judgment", ""),
                    "visible_reason": row.get("visible_reason") or row.get("evaluation_note") or "",
                    "error_category": row.get("error_category", ""),
                    "reviewer_lens": row.get("reviewer_lens", ""),
                },
            )
        )
    return sorted(events, key=lambda item: (item["asset_id"], item["event_type"], item["event_id"]))
