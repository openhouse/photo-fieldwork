from __future__ import annotations

from .pipeline import truthy


CLEARANCE_FIELDS = [
    "uuid",
    "filename",
    "publication_cleared",
    "rights_status",
    "participant_consent",
    "collaborator_approval",
    "artwork_review",
    "caption",
    "caption_provenance",
    "credit",
    "crop_approved",
    "alt_text",
    "sensitive_context_review",
    "public_destination",
    "review_date",
]


def scaffold(master: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "uuid": row["uuid"],
            "filename": row.get("filename", ""),
            **{field: "false" if field == "publication_cleared" else "" for field in CLEARANCE_FIELDS[2:]},
        }
        for row in master
    ]


def validate_clearance(rows: list[dict[str, str]]) -> tuple[list[str], dict]:
    errors = []
    required_when_cleared = [
        "rights_status",
        "participant_consent",
        "collaborator_approval",
        "artwork_review",
        "caption",
        "caption_provenance",
        "credit",
        "crop_approved",
        "alt_text",
        "sensitive_context_review",
        "public_destination",
        "review_date",
    ]
    cleared = 0
    for row in rows:
        if not truthy(row.get("publication_cleared")):
            continue
        cleared += 1
        missing = [field for field in required_when_cleared if not row.get(field, "").strip()]
        if missing:
            errors.append(f"{row['uuid']} is cleared but missing: {', '.join(missing)}")
    return errors, {
        "rows": len(rows),
        "publication_cleared": cleared,
        "status": "PASS" if not errors else "FAIL",
    }
