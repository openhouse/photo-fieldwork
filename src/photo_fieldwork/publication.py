from __future__ import annotations

import hashlib
import hmac
from datetime import date

from .pipeline import master_sha256


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
    "public_destination",
    "publication_decision_id",
    "review_date",
)

RIGHTS_CLEAR = {"owner-verified", "licensed", "public-domain"}
CONSENT_CLEAR = {"cleared-for-use", "not-applicable"}
CLAIM_CLEAR = {"visible-only", "provenance-backed"}
PUBLICATION_CLEAR = {"cleared-for-specific-use", "published"}


def public_id(uuid: str, salt: str, destination: str) -> str:
    if len(salt) < 16:
        raise ValueError("public ID salt must contain at least 16 characters")
    material = f"{destination}\x1f{uuid}"
    return hmac.new(salt.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def public_text_error(value: str) -> str:
    if "\x00" in value:
        return "contains a null byte"
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "begins with a spreadsheet formula marker"
    return ""


def bound_master_identity(master: list[dict[str, str]]) -> tuple[str, str]:
    if not master:
        raise ValueError("publication requires a non-empty master")
    digest = master_sha256(master)
    proposal_id = f"pfp-{digest[:16]}"
    identifiers = [str(row.get("uuid") or "").strip() for row in master]
    if "" in identifiers or len(identifiers) != len(set(identifiers)):
        raise ValueError("publication requires unique non-empty master UUIDs")
    for row in master:
        if row.get("master_sha256") != digest or row.get("proposal_id") != proposal_id:
            raise ValueError("publication requires the exact bound master")
    return digest, proposal_id


def scaffold_clearance(master: list[dict[str, str]]) -> list[dict[str, str]]:
    digest, proposal_id = bound_master_identity(master)
    rows = []
    for source in master:
        rows.append(
            {
                "uuid": source["uuid"],
                "filename": source.get("filename", ""),
                "primary_view": source.get("primary_view", ""),
                "proposal_id": proposal_id,
                "master_sha256": digest,
                "publication_status": "not-reviewed",
                "rights_status": "unknown",
                "consent_status": "unknown",
                "claim_status": "caption-review",
                "safety_status": "human-needs-review",
                "caption": "",
                "alt_text": "",
                "credit": "",
                "crop": "",
                "focal_point": "",
                "page_slot": "",
                "public_destination": "",
                "reviewer_actor": "",
                "reviewer_lens": "",
                "review_date": "",
            }
        )
    return rows


def publication_decision_id(row: dict[str, str]) -> str:
    fields = (
        "uuid",
        "proposal_id",
        "master_sha256",
        "publication_status",
        "rights_status",
        "consent_status",
        "claim_status",
        "safety_status",
        "caption",
        "alt_text",
        "credit",
        "crop",
        "focal_point",
        "page_slot",
        "public_destination",
        "reviewer_actor",
        "reviewer_lens",
        "review_date",
    )
    material = "\x1f".join(str(row.get(field, "")).strip() for field in fields)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_public_handoff(
    master: list[dict[str, str]],
    clearance: list[dict[str, str]],
    salt: str,
    destination: str,
) -> tuple[list[dict[str, str]], list[str]]:
    """Project specifically cleared rows through an allowlist.

    The private clearance ledger remains authoritative. This projection never
    exposes archive UUIDs, paths, People associations, safety reasons, or raw
    evidence fields.
    """
    destination = destination.strip()
    if not destination:
        raise ValueError("public destination must be non-empty")
    destination_problem = public_text_error(destination)
    if destination_problem:
        raise ValueError(f"public destination {destination_problem}")
    digest, proposal_id = bound_master_identity(master)
    master_ids = [row["uuid"].strip() for row in master]
    by_id = {row["uuid"]: row for row in master}
    clearance_ids = [row.get("uuid", "").strip() for row in clearance]
    if "" in clearance_ids or len(clearance_ids) != len(set(clearance_ids)):
        raise ValueError("publication clearance rows require unique non-empty UUIDs")
    unknown = sorted(set(clearance_ids) - set(by_id))
    if unknown:
        raise ValueError("publication clearance contains rows outside the exact master")

    output: list[dict[str, str]] = []
    errors: list[str] = []
    for row in clearance:
        uuid = row["uuid"]
        status = row.get("publication_status", "not-reviewed").strip().lower()
        if status not in PUBLICATION_CLEAR:
            continue
        row_errors = []
        if row.get("proposal_id", "").strip() != proposal_id:
            row_errors.append("proposal identity")
        if row.get("master_sha256", "").strip() != digest:
            row_errors.append("master identity")
        if row.get("rights_status", "").strip().lower() not in RIGHTS_CLEAR:
            row_errors.append("rights clearance")
        if row.get("consent_status", "").strip().lower() not in CONSENT_CLEAR:
            row_errors.append("scoped consent")
        if row.get("claim_status", "").strip().lower() not in CLAIM_CLEAR:
            row_errors.append("claim support")
        if row.get("safety_status", "").strip().lower() != "clear":
            row_errors.append("human safety review")
        if row.get("public_destination", "").strip() != destination:
            row_errors.append("destination binding")
        if row.get("reviewer_lens", "").strip().lower() != "human-review":
            row_errors.append("human publication authority")
        primary_view_problem = public_text_error(str(by_id[uuid].get("primary_view") or ""))
        if primary_view_problem:
            row_errors.append(f"primary_view {primary_view_problem}")
        for field, label in (
            ("reviewer_actor", "identified reviewer"),
            ("review_date", "review date"),
            ("caption", "caption"),
            ("alt_text", "alt text"),
            ("credit", "credit"),
        ):
            if not row.get(field, "").strip():
                row_errors.append(label)
        for field in ("caption", "alt_text", "credit", "crop", "focal_point", "page_slot"):
            problem = public_text_error(str(row.get(field) or ""))
            if problem:
                row_errors.append(f"{field} {problem}")
        try:
            date.fromisoformat(row.get("review_date", ""))
        except ValueError:
            if "review date" not in row_errors:
                row_errors.append("ISO review date")
        if row_errors:
            errors.append(f"{uuid}: missing or invalid {', '.join(row_errors)}")
            continue

        decision_id = publication_decision_id(row)
        projected = {
            "public_id": public_id(uuid, salt, destination),
            "primary_view": by_id[uuid].get("primary_view", ""),
            "page_slot": row.get("page_slot", ""),
            "publication_status": status,
            "rights_status": row["rights_status"].strip().lower(),
            "consent_status": row["consent_status"].strip().lower(),
            "claim_status": row["claim_status"].strip().lower(),
            "alt_text": row["alt_text"].strip(),
            "caption": row["caption"].strip(),
            "credit": row["credit"].strip(),
            "crop": row.get("crop", "").strip(),
            "focal_point": row.get("focal_point", "").strip(),
            "public_destination": destination,
            "publication_decision_id": decision_id,
            "review_date": row["review_date"].strip(),
        }
        output.append({field: projected[field] for field in PUBLIC_FIELDS})
    if errors:
        return [], errors
    if len({row["public_id"] for row in output}) != len(output):
        raise ValueError("public ID collision")
    return output, []
