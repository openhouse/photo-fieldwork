from __future__ import annotations

import hashlib


PUBLIC_FIELDS = (
    "public_id",
    "primary_view",
    "page_slot",
    "publication_status",
    "rights_status",
    "consent_status",
    "claim_status",
    "alt_text",
    "caption",
    "credit",
    "crop",
    "focal_point",
)


def public_id(uuid: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{uuid}".encode()).hexdigest()[:20]


def build_public_handoff(rows: list[dict[str, str]], salt: str) -> tuple[list[dict], list[str]]:
    output: list[dict] = []
    errors: list[str] = []
    for row in rows:
        status = row.get("publication_status", "not-reviewed")
        if status not in {"cleared-for-specific-use", "published"}:
            continue
        uuid = row["uuid"]
        if row.get("rights_status") != "owner-verified":
            errors.append(f"{uuid}: publication row lacks owner-verified rights")
            continue
        if row.get("consent_status") not in {"cleared-for-use", "not-applicable"}:
            errors.append(f"{uuid}: publication row lacks scoped consent clearance")
            continue
        if row.get("claim_status") not in {"visible-only", "provenance-backed", "caption-review"}:
            errors.append(f"{uuid}: publication row lacks claim status")
            continue
        output.append(
            {
                "public_id": public_id(uuid, salt),
                "primary_view": row.get("primary_view", ""),
                "page_slot": row.get("page_slot", ""),
                "publication_status": status,
                "rights_status": row["rights_status"],
                "consent_status": row["consent_status"],
                "claim_status": row["claim_status"],
                "alt_text": row.get("alt_text", ""),
                "caption": row.get("caption", ""),
                "credit": row.get("credit", ""),
                "crop": row.get("crop", ""),
                "focal_point": row.get("focal_point", ""),
            }
        )
    return output, errors
