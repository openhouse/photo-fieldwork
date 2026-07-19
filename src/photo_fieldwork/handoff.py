from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import PurePosixPath


PUBLIC_FIELDS = ("public_id", "derivative", "alt_text", "caption", "credit", "view_id")


def _status(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "")).strip().lower()


def _exclusion_reasons(row: dict[str, str]) -> list[str]:
    reasons = []
    if _status(row, "rights_status") != "cleared":
        reasons.append("rights_not_cleared")
    if _status(row, "consent_status") not in {"cleared", "not-applicable"}:
        reasons.append("consent_not_cleared")
    if _status(row, "claim_status") not in {"supported", "not-applicable"}:
        reasons.append("claim_not_supported")
    if _status(row, "safety_status") not in {"clear", "clear_for_public_derivative"}:
        reasons.append("safety_not_cleared")
    if _status(row, "publication_status") != "approved":
        reasons.append("publication_not_approved")
    return reasons


def build_public_handoff(rows: list[dict[str, str]]) -> tuple[dict, dict]:
    """Project cleared derivatives into a minimal public manifest.

    The source rows are copied before inspection. Private evidence and source
    identifiers are never included in the returned manifest.
    """
    source = deepcopy(rows)
    included = []
    exclusions = Counter()
    public_ids = set()
    derivatives = set()
    for row in source:
        reasons = _exclusion_reasons(row)
        if reasons:
            exclusions.update(reasons)
            continue
        public_id = str(row.get("public_id", "")).strip()
        derivative = str(row.get("derivative", "")).strip()
        if not public_id or not derivative:
            raise ValueError("cleared public derivatives require public_id and derivative")
        path = PurePosixPath(derivative)
        if path.is_absolute() or ".." in path.parts or "\\" in derivative or "://" in derivative:
            raise ValueError("public derivative must use a repository-relative POSIX path")
        if public_id in public_ids:
            raise ValueError(f"duplicate public_id: {public_id}")
        if derivative in derivatives:
            raise ValueError(f"duplicate derivative: {derivative}")
        public_ids.add(public_id)
        derivatives.add(derivative)
        included.append({field: str(row.get(field, "")) for field in PUBLIC_FIELDS})
    manifest = {
        "schema_version": 1,
        "release_class": "public-derivative",
        "publication_clearance": bool(included),
        "items": included,
    }
    report = {
        "schema_version": 1,
        "status": "PASS" if included else "BLOCKED",
        "source_row_count": len(rows),
        "included_count": len(included),
        "excluded_count": len(rows) - len(included),
        "exclusions_by_reason": dict(sorted(exclusions.items())),
    }
    return manifest, report
