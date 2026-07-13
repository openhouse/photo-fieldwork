from __future__ import annotations

import hashlib
import json
from collections import Counter

from .safety import may_enter_general_master, normalize_safety_state, validate_safety_transition


JUDGMENTS = {"fit", "reject", "uncertain"}
ERROR_CATEGORIES = {
    "retrieval-mismatch",
    "context-collapse",
    "taxonomy-coercion",
    "privacy-miss",
    "relationship-loss",
    "temporal-distortion",
    "redundancy",
    "aesthetic-overreach",
    "visible-fit",
}


def sample_fingerprint(rows: list[dict]) -> str:
    canonical = [
        {
            "uuid": str(row.get("uuid", "")),
            "primary_view": str(row.get("primary_view", "")),
            "score_total": str(row.get("score_total", "")),
        }
        for row in sorted(rows, key=lambda row: str(row.get("uuid", "")))
    ]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def validate_feedback(sample: list[dict], decisions: list[dict], require_complete: bool = True) -> dict[str, dict]:
    sample_ids = [str(row.get("uuid", "")) for row in sample]
    decision_ids = [str(row.get("uuid", "")) for row in decisions]
    if any(not value for value in sample_ids + decision_ids):
        raise ValueError("sample and feedback rows require UUIDs")
    duplicates = sorted(value for value, count in Counter(decision_ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"feedback contains duplicate UUIDs: {', '.join(duplicates)}")
    expected = set(sample_ids)
    actual = set(decision_ids)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise ValueError(f"feedback contains unknown UUIDs: {', '.join(unknown)}")
    if require_complete and missing:
        raise ValueError(f"feedback is missing UUIDs: {', '.join(missing)}")

    fingerprint = sample_fingerprint(sample)
    declared = {str(row.get("sample_hash", "")) for row in decisions}
    if declared != {fingerprint}:
        raise ValueError("feedback sample_hash does not match the sampled manifest")

    by_uuid = {}
    for row in decisions:
        judgment = str(row.get("judgment", "")).strip().lower()
        if judgment not in JUDGMENTS:
            raise ValueError(f"invalid judgment for {row['uuid']}: {judgment or '<blank>'}")
        if not str(row.get("visible_reason", "")).strip():
            raise ValueError(f"feedback requires visible_reason for {row['uuid']}")
        category = str(row.get("error_category", "")).strip().lower()
        if category not in ERROR_CATEGORIES:
            raise ValueError(f"invalid error_category for {row['uuid']}: {category or '<blank>'}")
        normalize_safety_state(row.get("safety_status"))
        if not str(row.get("round_id", "")).strip() or not str(row.get("reviewer_lens", "")).strip():
            raise ValueError(f"feedback requires round_id and reviewer_lens for {row['uuid']}")
        by_uuid[row["uuid"]] = dict(row)
    return by_uuid


def apply_feedback(master: list[dict], sample: list[dict], decisions: list[dict]) -> tuple[list[dict], list[dict], dict]:
    by_uuid = validate_feedback(sample, decisions)
    reviewed = []
    removed = []
    for row in master:
        item = dict(row)
        decision = by_uuid.get(row["uuid"])
        if decision:
            safety_status = normalize_safety_state(decision["safety_status"])
            validate_safety_transition(
                item.get("safety_status", "clear_automated"),
                safety_status,
                str(decision.get("reviewer_actor", "")),
            )
            item.update(
                {
                    "last_judgment": decision["judgment"].strip().lower(),
                    "last_visible_reason": decision["visible_reason"].strip(),
                    "last_error_category": decision["error_category"].strip().lower(),
                    "last_round_id": decision["round_id"].strip(),
                    "last_reviewer_lens": decision["reviewer_lens"].strip(),
                    "last_reviewer_actor": str(decision.get("reviewer_actor", "")).strip(),
                    "safety_status": safety_status,
                }
            )
        if decision and (
            item["last_judgment"] == "reject" or not may_enter_general_master(item.get("safety_status"))
        ):
            removed.append(item)
        else:
            reviewed.append(item)
    report = {
        "sample_hash": sample_fingerprint(sample),
        "decisions_applied": len(by_uuid),
        "master_before": len(master),
        "master_after": len(reviewed),
        "removed_count": len(removed),
        "removed_by_judgment": dict(sorted(Counter(row.get("last_judgment", "") for row in removed).items())),
        "removed_by_safety": dict(sorted(Counter(row.get("safety_status", "") for row in removed).items())),
        "requires_reselection": len(reviewed) != len(master),
    }
    return reviewed, removed, report
