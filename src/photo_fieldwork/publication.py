from __future__ import annotations

from .pipeline import truthy


REVIEW_FIELDS = [
    "uuid",
    "filename",
    "rights_status",
    "consent_status",
    "claim_status",
    "context_status",
    "destination",
    "credit",
    "caption",
    "alt_text",
    "reviewer_actor",
    "reviewed_at",
    "publication_approved",
]


def scaffold(master: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "uuid": row["uuid"],
            "filename": row.get("filename", ""),
            "rights_status": "unresolved",
            "consent_status": "unresolved",
            "claim_status": "unresolved",
            "context_status": "unresolved",
            "destination": "",
            "credit": "",
            "caption": "",
            "alt_text": "",
            "reviewer_actor": "",
            "reviewed_at": "",
            "publication_approved": "false",
        }
        for row in master
    ]


def validate(rows: list[dict[str, str]]) -> tuple[list[str], dict]:
    errors = []
    approved = 0
    required_statuses = {
        "rights_status": {"approved", "not-applicable"},
        "consent_status": {"approved", "not-applicable"},
        "claim_status": {"approved", "not-applicable"},
        "context_status": {"approved"},
    }
    required_text = ("destination", "credit", "caption", "alt_text", "reviewer_actor", "reviewed_at")
    for row in rows:
        if not truthy(row.get("publication_approved")):
            continue
        approved += 1
        unresolved = [
            field for field, allowed in required_statuses.items()
            if row.get(field, "").strip() not in allowed
        ]
        missing = [field for field in required_text if not row.get(field, "").strip()]
        if unresolved or missing:
            details = [*(f"{field} not approved" for field in unresolved), *(f"{field} missing" for field in missing)]
            errors.append(f"{row.get('uuid', '<unknown>')}: {', '.join(details)}")
    return errors, {
        "schema_version": 1,
        "rows": len(rows),
        "publication_approved": approved,
        "status": "PASS" if not errors else "FAIL",
        "editor_field_membership_is_publication_permission": False,
    }
