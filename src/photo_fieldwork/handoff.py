from __future__ import annotations

import hashlib
from collections import Counter

from .pipeline import canonical_id


PUBLIC_FIELDS = [
    "public_id",
    "primary_view",
    "page_slot",
    "publication_status",
    "rights_status",
    "consent_status",
    "claim_status",
    "public_safety_status",
    "alt_text",
    "caption",
    "credit",
    "crop",
    "focal_point",
]

PUBLICATION_READY = {"cleared-for-specific-use", "published"}
RIGHTS_READY = {"owner-verified"}
CONSENT_READY = {"cleared-for-use", "not-applicable"}
CLAIM_READY = {"visible-only", "provenance-backed", "reviewed-for-publication", "not-applicable"}
SAFETY_READY = {"clear"}


def public_id(uuid: str, salt: str) -> str:
    if not salt:
        raise ValueError("a non-empty private salt is required for public IDs")
    return hashlib.sha256(f"{salt}:{canonical_id(uuid)}".encode("utf-8")).hexdigest()[:20]


def build_public_handoff(rows: list[dict[str, str]], salt: str) -> tuple[list[dict[str, str]], dict]:
    """Project only individually cleared records into a data-minimized public artifact."""
    output: list[dict[str, str]] = []
    blocked = Counter()
    seen_public_ids: set[str] = set()
    for row in rows:
        checks = {
            "publication": str(row.get("publication_status", "")).strip().lower() in PUBLICATION_READY,
            "rights": str(row.get("rights_status", "")).strip().lower() in RIGHTS_READY,
            "consent": str(row.get("consent_status", "")).strip().lower() in CONSENT_READY,
            "claim": str(row.get("claim_status", "")).strip().lower() in CLAIM_READY,
            "public_safety": str(row.get("public_safety_status", "")).strip().lower() in SAFETY_READY,
        }
        if not all(checks.values()):
            blocked.update(key for key, passed in checks.items() if not passed)
            continue
        identifier = public_id(row["uuid"], salt)
        if identifier in seen_public_ids:
            raise ValueError("public ID collision or duplicate source UUID in handoff")
        seen_public_ids.add(identifier)
        item = {field: str(row.get(field, "")) for field in PUBLIC_FIELDS}
        item["public_id"] = identifier
        output.append(item)
    report = {
        "status": "PASS",
        "input_count": len(rows),
        "public_count": len(output),
        "withheld_count": len(rows) - len(output),
        "withheld_by_gate": dict(sorted(blocked.items())),
        "public_fields": PUBLIC_FIELDS,
        "excluded_private_fields": sorted(
            {
                key
                for row in rows
                for key in row
                if key not in PUBLIC_FIELDS and key != "uuid"
            }
            | {"uuid"}
        ),
        "boundary_statement": (
            "Editor-field inclusion is neither publication permission nor a testimonial. "
            "Only separately cleared rows are projected here."
        ),
    }
    return output, report
