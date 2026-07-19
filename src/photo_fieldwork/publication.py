from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .pipeline import ensure_private_directory, write_private_text


PUBLIC_FIELDS = (
    "public_id",
    "primary_view",
    "page_slot",
    "publication_status",
    "rights_status",
    "consent_status",
    "claim_status",
    "safety_review_status",
    "editorial_status",
    "public_destination",
    "review_date",
    "alt_text",
    "caption",
    "credit",
    "crop",
    "focal_point",
)
PUBLICATION_STATUSES = {"cleared-for-specific-use", "published"}
RIGHTS_STATUSES = {"owner-verified", "license-verified"}
CONSENT_STATUSES = {"cleared-for-use", "not-applicable"}
CLAIM_STATUSES = {"visible-only", "provenance-backed"}
SAFETY_STATUSES = {"human-cleared", "not-applicable"}


def read_publication_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if "uuid" not in (reader.fieldnames or []):
            raise ValueError("publication manifest lacks uuid column")
        return [dict(row) for row in reader]


def public_id(uuid: str, salt: str, destination: str) -> str:
    if len(salt.strip()) < 16:
        raise ValueError("publication salt must contain at least 16 non-whitespace characters")
    payload = f"photo-fieldwork-public-id:v1:{salt.strip()}:{destination.strip()}:{uuid.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _blocked(uuid: str, reasons: list[str]) -> dict[str, object]:
    return {"uuid": uuid or "<missing>", "reasons": reasons}


def build_public_handoff(
    rows: list[dict[str, str]], salt: str, destination: str
) -> tuple[dict, dict]:
    """Build an allowlisted, destination-scoped public package.

    Rows without a positive publication status remain closed and are counted,
    while rows claiming clearance but missing any gate are blocked with private
    reasons. Private identifiers never enter the public package.
    """

    destination = destination.strip()
    if not destination:
        raise ValueError("public destination is required")
    if len(salt.strip()) < 16:
        raise ValueError("publication salt must contain at least 16 non-whitespace characters")

    output: list[dict[str, str]] = []
    blocked: list[dict[str, object]] = []
    closed_count = 0
    seen_private: set[str] = set()
    seen_public: set[str] = set()

    for row in rows:
        status = str(row.get("publication_status") or "not-reviewed").strip()
        if status not in PUBLICATION_STATUSES:
            closed_count += 1
            continue

        uuid = str(row.get("uuid") or "").strip()
        reasons: list[str] = []
        if not uuid:
            reasons.append("missing private source identifier")
        elif uuid in seen_private:
            reasons.append("duplicate private source identifier")
        if row.get("rights_status", "").strip() not in RIGHTS_STATUSES:
            reasons.append("rights are not positively verified")
        if row.get("consent_status", "").strip() not in CONSENT_STATUSES:
            reasons.append("scoped participant consent is unresolved")
        if row.get("claim_status", "").strip() not in CLAIM_STATUSES:
            reasons.append("caption claims are not visible-only or provenance-backed")
        if row.get("safety_review_status", "").strip() not in SAFETY_STATUSES:
            reasons.append("human safety review is unresolved")
        if row.get("editorial_status", "").strip() != "approved":
            reasons.append("editorial approval is unresolved")
        if row.get("public_destination", "").strip() != destination:
            reasons.append("clearance does not match the requested public destination")
        for field in ("review_actor", "review_date", "alt_text", "credit"):
            if not row.get(field, "").strip():
                reasons.append(f"missing required {field}")

        if uuid:
            seen_private.add(uuid)
        if reasons:
            blocked.append(_blocked(uuid, reasons))
            continue

        opaque_id = public_id(uuid, salt, destination)
        if opaque_id in seen_public:
            blocked.append(_blocked(uuid, ["opaque public identifier collision"]))
            continue
        seen_public.add(opaque_id)
        candidate = {
            "public_id": opaque_id,
            "primary_view": row.get("primary_view", "").strip(),
            "page_slot": row.get("page_slot", "").strip(),
            "publication_status": status,
            "rights_status": row.get("rights_status", "").strip(),
            "consent_status": row.get("consent_status", "").strip(),
            "claim_status": row.get("claim_status", "").strip(),
            "safety_review_status": row.get("safety_review_status", "").strip(),
            "editorial_status": row.get("editorial_status", "").strip(),
            "public_destination": destination,
            "review_date": row.get("review_date", "").strip(),
            "alt_text": row.get("alt_text", "").strip(),
            "caption": row.get("caption", "").strip(),
            "credit": row.get("credit", "").strip(),
            "crop": row.get("crop", "").strip(),
            "focal_point": row.get("focal_point", "").strip(),
        }
        output.append({field: candidate[field] for field in PUBLIC_FIELDS})

    public_package = {
        "schema_version": 1,
        "public_destination": destination,
        "row_count": len(output),
        "rows": output,
    }
    private_report = {
        "schema_version": 1,
        "status": "PASS" if not blocked else "FAIL",
        "public_destination": destination,
        "input_rows": len(rows),
        "exported_rows": len(output),
        "closed_rows": closed_count,
        "blocked_rows": blocked,
    }
    return public_package, private_report


def write_public_package(path: Path, package: dict) -> None:
    if path.is_symlink():
        raise ValueError("public package path may not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(package, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    path.chmod(0o644)


def write_private_report(path: Path, report: dict) -> None:
    if path.is_symlink():
        raise ValueError("private report path may not be a symlink")
    ensure_private_directory(path.parent)
    write_private_text(path, json.dumps(report, indent=2, ensure_ascii=True) + "\n")
