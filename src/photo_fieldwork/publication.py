from __future__ import annotations

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
APPROVAL_FIELDS = {
    "participant_consent",
    "collaborator_approval",
    "artwork_review",
    "crop_approved",
    "sensitive_context_review",
}
APPROVED_VALUES = {"1", "true", "yes", "y", "approved", "cleared", "not-applicable", "n/a"}
CLEARANCE_TRUE_VALUES = {"1", "true", "yes", "y"}
FALSE_VALUES = {"", "0", "false", "no", "n"}


def scaffold(master: list[dict[str, str]]) -> list[dict[str, str]]:
    identifiers = [str(row.get("uuid", "")).strip() for row in master]
    if any(not identifier for identifier in identifiers):
        raise ValueError("master rows require UUIDs")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("master contains duplicate UUIDs")
    return [
        {
            "uuid": row["uuid"],
            "filename": row.get("filename", ""),
            **{field: "false" if field == "publication_cleared" else "" for field in CLEARANCE_FIELDS[2:]},
        }
        for row in master
    ]


def validate_clearance(
    rows: list[dict[str, str]],
    *,
    master_ids: set[str] | None = None,
) -> tuple[list[str], dict]:
    errors = []
    identifiers = [str(row.get("uuid", "")).strip() for row in rows]
    if any(not identifier for identifier in identifiers):
        errors.append("publication rows require UUIDs")
    duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicates:
        errors.append(f"publication ledger contains duplicate UUIDs: {', '.join(duplicates)}")
    if master_ids is not None:
        observed = set(identifiers)
        missing = sorted(master_ids - observed)
        unexpected = sorted(observed - master_ids)
        if missing:
            errors.append(f"publication ledger missing master UUIDs: {', '.join(missing)}")
        if unexpected:
            errors.append(f"publication ledger contains non-master UUIDs: {', '.join(unexpected)}")

    required_when_cleared = CLEARANCE_FIELDS[3:]
    cleared = 0
    for row in rows:
        clearance_value = str(row.get("publication_cleared", "")).strip().lower()
        if clearance_value not in CLEARANCE_TRUE_VALUES | FALSE_VALUES:
            errors.append(f"{row.get('uuid', '<blank>')} has invalid publication_cleared value")
            continue
        if clearance_value not in CLEARANCE_TRUE_VALUES:
            continue
        cleared += 1
        missing = [field for field in required_when_cleared if not str(row.get(field, "")).strip()]
        if missing:
            errors.append(f"{row.get('uuid', '<blank>')} is cleared but missing: {', '.join(missing)}")
            continue
        unresolved = [
            field
            for field in APPROVAL_FIELDS
            if str(row.get(field, "")).strip().lower() not in APPROVED_VALUES
        ]
        rights = str(row.get("rights_status", "")).strip().lower()
        if rights in {"unknown", "pending", "unreviewed", "not-cleared", "false", "no"}:
            unresolved.append("rights_status")
        if unresolved:
            errors.append(f"{row.get('uuid', '<blank>')} is cleared but unresolved: {', '.join(sorted(unresolved))}")
    return errors, {
        "rows": len(rows),
        "publication_cleared": cleared,
        "publication_blocked": len(rows) - cleared,
        "status": "PASS" if not errors else "FAIL",
    }
