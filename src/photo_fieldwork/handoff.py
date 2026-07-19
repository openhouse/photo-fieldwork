from __future__ import annotations

import hashlib


PUBLIC_FIELDS = (
    "public_id",
    "primary_view",
    "page_slot",
    "publication_status",
    "publication_destination",
    "rights_status",
    "consent_status",
    "claim_status",
    "alt_text",
    "caption",
    "credit",
    "crop",
    "focal_point",
)

PUBLISHABLE_STATES = {"cleared-for-specific-use", "published"}
RIGHTS_STATES = {"owner-verified", "licensed-for-specific-use"}
CONSENT_STATES = {"cleared-for-use", "not-applicable"}
CLAIM_STATES = {"visible-only", "provenance-backed", "caption-review"}


def public_id(uuid: str, salt: str) -> str:
    if len(salt) < 16:
        raise ValueError("public handoff salt must contain at least 16 characters")
    return hashlib.sha256(f"{salt}:{uuid}".encode("utf-8")).hexdigest()[:20]


def build_public_handoff(
    rows: list[dict[str, str]], salt: str, destination: str
) -> tuple[list[dict[str, str]], list[str]]:
    """Create an allowlisted, destination-scoped public derivative.

    Private UUIDs and operational fields are deliberately omitted. A row that
    claims publication readiness but lacks one independent human gate becomes
    an error rather than silently disappearing.
    """

    if not destination.strip():
        raise ValueError("public handoff requires a specific destination")
    output: list[dict[str, str]] = []
    errors: list[str] = []
    seen_public_ids: set[str] = set()
    for row in rows:
        status = str(row.get("publication_status", "not-reviewed")).strip()
        if status not in PUBLISHABLE_STATES:
            continue
        uuid = str(row.get("uuid", "")).strip()
        if not uuid:
            errors.append("publication row lacks a private source UUID")
            continue
        if row.get("publication_destination", "").strip() != destination:
            errors.append(f"{uuid}: publication clearance is for another destination")
            continue
        if row.get("rights_status") not in RIGHTS_STATES:
            errors.append(f"{uuid}: publication row lacks destination-scoped rights")
            continue
        if row.get("consent_status") not in CONSENT_STATES:
            errors.append(f"{uuid}: publication row lacks scoped consent clearance")
            continue
        if row.get("claim_status") not in CLAIM_STATES:
            errors.append(f"{uuid}: publication row lacks claim status")
            continue
        identifier = public_id(uuid, salt)
        if identifier in seen_public_ids:
            errors.append(f"{uuid}: public identifier collision")
            continue
        seen_public_ids.add(identifier)
        public_row = {
            "public_id": identifier,
            "primary_view": row.get("primary_view", ""),
            "page_slot": row.get("page_slot", ""),
            "publication_status": status,
            "publication_destination": destination,
            "rights_status": row["rights_status"],
            "consent_status": row["consent_status"],
            "claim_status": row["claim_status"],
            "alt_text": row.get("alt_text", ""),
            "caption": row.get("caption", ""),
            "credit": row.get("credit", ""),
            "crop": row.get("crop", ""),
            "focal_point": row.get("focal_point", ""),
        }
        output.append({field: public_row[field] for field in PUBLIC_FIELDS})
    return output, errors
