from __future__ import annotations

from collections import Counter
from typing import Mapping

from .release import validate_plan


def _album_counts_from_plan(plan: Mapping[str, object]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for album in plan.get("albums", []):
        if not isinstance(album, Mapping):
            raise ValueError("catalog plan albums must be objects")
        title = str(album.get("title", "")).strip()
        identifiers = album.get("asset_identifiers", [])
        if not title or not isinstance(identifiers, list):
            raise ValueError("catalog plan albums require a title and asset_identifiers")
        if title in counts:
            raise ValueError(f"catalog plan repeats album title: {title}")
        counts[title] = len(set(str(value) for value in identifiers))
    return counts


def _album_counts_from_receipt(receipt: Mapping[str, object]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for album in receipt.get("albums", []):
        if not isinstance(album, Mapping):
            raise ValueError("write receipt albums must be objects")
        title = str(album.get("title", "")).strip()
        if not title or title in counts:
            raise ValueError("write receipt album titles must be non-empty and unique")
        counts[title] = int(album.get("count", -1))
    return counts


def verify_write_receipt(plan: Mapping[str, object], receipt: Mapping[str, object]) -> dict[str, object]:
    validated_plan = validate_plan(plan)
    candidate = validated_plan["release_candidate"]
    errors = []
    expected = {
        "schema_version": 2,
        "plan_id": validated_plan["plan_id"],
        "plan_sha256": validated_plan["plan_sha256"],
        "candidate_id": candidate["candidate_id"],
        "source_membership_sha256": candidate["source_membership_sha256"],
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "helper_contract_version": 2,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            errors.append(f"receipt {field} does not match the authorized plan")
    if not str(receipt.get("execution_nonce", "")).strip():
        errors.append("receipt lacks a bridge-generated execution_nonce")
    helper = receipt.get("helper")
    if not isinstance(helper, Mapping):
        errors.append("receipt lacks helper identity")
    else:
        for field in ("bundle_id", "version", "binary_sha256"):
            if not str(helper.get(field, "")).strip():
                errors.append(f"receipt helper identity lacks {field}")
    try:
        expected_albums = _album_counts_from_plan(validated_plan)
        observed_albums = _album_counts_from_receipt(receipt)
        if expected_albums != observed_albums:
            errors.append("receipt album titles or counts do not match the authorized plan")
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
        expected_albums = Counter()
        observed_albums = Counter()
    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "candidate_id": candidate["candidate_id"],
        "plan_sha256": validated_plan["plan_sha256"],
        "execution_nonce": receipt.get("execution_nonce", ""),
        "expected_album_counts": dict(sorted(expected_albums.items())),
        "observed_album_counts": dict(sorted(observed_albums.items())),
        "errors": errors,
    }


def compare_idempotent_receipts(first: Mapping[str, object], second: Mapping[str, object]) -> dict[str, object]:
    errors = []
    for field in ("plan_sha256", "candidate_id", "source_membership_sha256", "safety_mode"):
        if first.get(field) != second.get(field):
            errors.append(f"idempotence receipts disagree on {field}")
    first_nonce = str(first.get("execution_nonce", "")).strip()
    second_nonce = str(second.get("execution_nonce", "")).strip()
    if not first_nonce or not second_nonce or first_nonce == second_nonce:
        errors.append("idempotence requires two distinct non-empty execution nonces")
    try:
        first_albums = _album_counts_from_receipt(first)
        second_albums = _album_counts_from_receipt(second)
        if first_albums != second_albums:
            errors.append("idempotence receipts disagree on album topology or counts")
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "same_plan": first.get("plan_sha256") == second.get("plan_sha256"),
        "distinct_executions": bool(first_nonce and second_nonce and first_nonce != second_nonce),
        "errors": errors,
    }
