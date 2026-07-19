from __future__ import annotations

import re


ALLOWED_STATUSES = {"draft", "approved-for-handoff"}
PROHIBITED_KEYS = {
    "asset_id",
    "asset_ids",
    "uuid",
    "filename",
    "local_path",
    "preview_path",
    "persons",
    "coordinates",
    "raw_ocr",
}
ALLOWED_KEYS = {
    "id",
    "public_safe_observation",
    "may_corroborate",
    "does_not_establish",
    "publication_boundary",
    "related_claim_ids",
    "status",
    "reviewed_at",
}
PRIVATE_PATTERNS = (
    re.compile(r"(?:/(?:Users|Volumes|home|private|tmp)/|~[/\\])"),
    re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]*"),
    re.compile(r"\b[A-F0-9]{8}(?:-[A-F0-9]{4}){3}-[A-F0-9]{12}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-])\d{3}[\s.-]\d{4}(?!\d)"),
    re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b"),
)


def validate_handoff(data: dict) -> list[dict]:
    records = data.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("evidence handoff requires a non-empty records array")
    required = {
        "id",
        "public_safe_observation",
        "may_corroborate",
        "does_not_establish",
        "publication_boundary",
        "status",
        "reviewed_at",
    }
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"evidence record {index} must be an object")
        prohibited = sorted(PROHIBITED_KEYS & set(record))
        if prohibited:
            raise ValueError(f"evidence record {index} contains prohibited fields: {', '.join(prohibited)}")
        unexpected = sorted(set(record) - ALLOWED_KEYS)
        if unexpected:
            raise ValueError(f"evidence record {index} contains unsupported fields: {', '.join(unexpected)}")
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"evidence record {index} is missing: {', '.join(missing)}")
        if record["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"evidence record {index} has unsupported status: {record['status']}")
        for key in ("may_corroborate", "does_not_establish"):
            if not isinstance(record[key], list) or not all(isinstance(value, str) for value in record[key]):
                raise ValueError(f"evidence record {index} field {key} must be a string array")
        serialized = repr(record)
        if any(pattern.search(serialized) for pattern in PRIVATE_PATTERNS):
            raise ValueError(f"evidence record {index} contains a private path, identifier, or contact detail")
    return records


def render_handoff(data: dict) -> str:
    records = validate_handoff(data)
    lines = [
        "# Public-Safe Visual Corroboration Handoff",
        "",
        "Photographs are supporting evidence only. This report does not establish authorship, causation, outcomes, endorsement, consent, credit, or publication rights.",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## {record['id']}",
                "",
                f"**Observation:** {record['public_safe_observation']}",
                "",
                "**May corroborate**",
                "",
                *[f"- {value}" for value in record["may_corroborate"]],
                "",
                "**Does not establish**",
                "",
                *[f"- {value}" for value in record["does_not_establish"]],
                "",
                f"**Publication boundary:** {record['publication_boundary']}",
                "",
                f"**Status:** {record['status']}",
                "",
                f"**Reviewed:** {record['reviewed_at']}",
                "",
            ]
        )
        related = record.get("related_claim_ids") or []
        if related:
            lines.extend(["**Related claim IDs**", "", *[f"- `{value}`" for value in related], ""])
    return "\n".join(lines)
