from __future__ import annotations

from .pipeline import truthy


PUBLICATION_FIELDS = (
    "uuid",
    "filename",
    "publication_cleared",
    "rights_status",
    "consent_status",
    "collaborator_approval",
    "caption",
    "caption_provenance",
    "credit",
    "alt_text",
    "public_destination",
    "reviewer_actor",
    "reviewer_kind",
    "review_date",
)


def scaffold_publication_clearance(
    master: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "uuid": row["uuid"],
            "filename": row.get("filename", ""),
            "publication_cleared": "false",
            **{field: "" for field in PUBLICATION_FIELDS[3:]},
        }
        for row in master
    ]


def validate_publication_clearance(
    rows: list[dict[str, str]],
) -> tuple[list[str], dict]:
    errors: list[str] = []
    seen: set[str] = set()
    cleared = 0
    required_text = (
        "caption",
        "caption_provenance",
        "credit",
        "alt_text",
        "public_destination",
        "reviewer_actor",
        "review_date",
    )
    for row in rows:
        uuid = str(row.get("uuid", "")).strip()
        if not uuid:
            errors.append("publication row is missing UUID")
            continue
        if uuid in seen:
            errors.append(f"{uuid}: duplicate publication row")
        seen.add(uuid)
        if not truthy(row.get("publication_cleared")):
            continue
        cleared += 1
        missing = [field for field in required_text if not str(row.get(field, "")).strip()]
        if missing:
            errors.append(f"{uuid}: cleared publication row missing {', '.join(missing)}")
        if str(row.get("reviewer_kind", "")).strip().casefold() != "human":
            errors.append(f"{uuid}: publication clearance requires an identified human reviewer")
        if str(row.get("rights_status", "")).strip().casefold() not in {"cleared", "not-needed"}:
            errors.append(f"{uuid}: rights_status is not cleared")
        if str(row.get("consent_status", "")).strip().casefold() not in {"cleared", "not-needed"}:
            errors.append(f"{uuid}: consent_status is not cleared")
        if str(row.get("collaborator_approval", "")).strip().casefold() not in {"approved", "not-needed"}:
            errors.append(f"{uuid}: collaborator approval is not cleared")
    return errors, {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "row_count": len(rows),
        "publication_cleared_count": cleared,
        "publication_state": (
            "item-level-clearance-recorded" if cleared and not errors
            else "publication-review-required"
        ),
    }
