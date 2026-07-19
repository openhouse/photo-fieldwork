from __future__ import annotations

import hashlib
import re


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

PUBLIC_CONTENT_PATTERNS = {
    "local filesystem path": re.compile(r"(?:/Users/|/Volumes/|file://|Photos Library\.photoslibrary)", re.I),
    "private operational field": re.compile(
        r"\b(?:raw[_ -]?ocr|people_names|local_path|asset_identifier|source_album_identifier|receipt_path)\b",
        re.I,
    ),
    "possible account or credential data": re.compile(
        r"\b(?:account number|routing number|api[ _-]?key|password|passcode|credential)\b",
        re.I,
    ),
    "exact coordinates": re.compile(r"(?<!\d)-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}(?!\d)"),
}


def public_identifier(uuid: str, salt: str) -> str:
    if len(salt.strip()) < 16:
        raise ValueError("publication salt must contain at least 16 characters")
    return hashlib.sha256(f"{salt}:{uuid}".encode("utf-8")).hexdigest()[:20]


def lint_public_content(row: dict, private_identifier: str) -> list[str]:
    errors = []
    for field in PUBLIC_FIELDS:
        if field == "public_id":
            continue
        value = str(row.get(field, ""))
        if private_identifier and private_identifier in value:
            errors.append(f"{field} contains the private archive identifier")
        for label, pattern in PUBLIC_CONTENT_PATTERNS.items():
            if pattern.search(value):
                errors.append(f"{field} contains {label}")
    return errors


def build_public_handoff(rows: list[dict], salt: str) -> tuple[list[dict], list[str]]:
    output = []
    errors = []
    for row in rows:
        publication = str(row.get("publication_status", "not-reviewed")).strip().lower()
        if publication not in {"cleared-for-specific-use", "published"}:
            continue
        identifier = str(row.get("uuid", "")).strip()
        if not identifier:
            errors.append("publication-cleared row lacks UUID")
            continue
        if row.get("rights_status") != "owner-verified":
            errors.append(f"{identifier}: publication row lacks owner-verified rights")
            continue
        if row.get("consent_status") not in {"cleared-for-use", "not-applicable"}:
            errors.append(f"{identifier}: publication row lacks scoped consent clearance")
            continue
        if row.get("claim_status") not in {"visible-only", "provenance-backed", "not-applicable"}:
            errors.append(f"{identifier}: publication row lacks claim status")
            continue
        public_row = {
            "public_id": public_identifier(identifier, salt),
            "primary_view": row.get("primary_view", ""),
            "page_slot": row.get("page_slot", ""),
            "publication_status": publication,
            "rights_status": row["rights_status"],
            "consent_status": row["consent_status"],
            "claim_status": row["claim_status"],
            "alt_text": row.get("alt_text", ""),
            "caption": row.get("caption", ""),
            "credit": row.get("credit", ""),
            "crop": row.get("crop", ""),
            "focal_point": row.get("focal_point", ""),
        }
        content_errors = lint_public_content(public_row, identifier)
        if content_errors:
            errors.extend(f"{identifier}: public content {error}" for error in content_errors)
            continue
        output.append({field: public_row[field] for field in PUBLIC_FIELDS})
    return output, errors
