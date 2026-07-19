from __future__ import annotations

import hashlib
import json


PLAN_FIELDS = {
    "plan_id",
    "attempt_id",
    "release_binding",
    "plan_sha256",
    "source_album_identifier",
    "expected_source_count",
    "albums",
}
RECEIPT_FIELDS = {
    "plan_id",
    "attempt_id",
    "release_binding",
    "plan_sha256",
    "helper_capability_version",
    "helper_bundle_identifier",
    "source_album_identifier",
    "source_count",
    "folders",
    "albums",
}
SHA_FIELDS = {
    "release_plan_sha256",
    "master_sha256",
    "config_sha256",
    "feedback_sha256",
    "source_membership_sha256",
    "evaluation_report_sha256",
    "validation_report_sha256",
}


def _require_fields(value: dict, fields: set[str], label: str) -> None:
    missing = sorted(field for field in fields if field not in value or value[field] in (None, ""))
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(missing)}")


def _content_sha256(value: dict) -> str:
    payload = dict(value)
    payload.pop("plan_sha256", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _planned_albums(plan: dict) -> dict[str, tuple[str, ...]]:
    albums = plan.get("albums")
    if not isinstance(albums, list) or not albums:
        raise ValueError("plan missing nonempty albums")
    result = {}
    for item in albums:
        title = str(item.get("title", ""))
        identifiers = item.get("asset_identifiers")
        if not isinstance(identifiers, list) or any(not str(value).strip() for value in identifiers):
            raise ValueError(f"plan album {title or '<blank>'} has incomplete asset identifiers")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"plan album {title or '<blank>'} has duplicate asset identifiers")
        result[title] = tuple(sorted(str(value) for value in identifiers))
    if "" in result or len(result) != len(albums):
        raise ValueError("plan contains blank or duplicate album titles")
    return result


def _received_albums(receipt: dict) -> dict[str, tuple[str, int]]:
    albums = receipt.get("albums")
    if not isinstance(albums, list) or not albums:
        raise ValueError("receipt missing nonempty albums")
    result = {
        str(item.get("title", "")): (str(item.get("identifier", "")), int(item.get("count", -1)))
        for item in albums
    }
    if "" in result or len(result) != len(albums) or any(not identifier for identifier, _ in result.values()):
        raise ValueError("receipt contains blank or duplicate album identity")
    return result


def _validate_release_binding(binding: object) -> None:
    if not isinstance(binding, dict):
        raise ValueError("release binding must be an object")
    if not str(binding.get("release_plan_id", "")).strip() or not str(
        binding.get("proposal_id", "")
    ).strip():
        raise ValueError("release binding is missing release or proposal identity")
    for field in SHA_FIELDS:
        value = str(binding.get(field, "")).casefold()
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"release binding {field} is not a SHA-256 digest")


def validate_execution_attempt(plan: dict, receipt: dict) -> dict:
    _require_fields(plan, PLAN_FIELDS, "plan")
    _require_fields(receipt, RECEIPT_FIELDS, "receipt")
    _validate_release_binding(plan["release_binding"])
    _validate_release_binding(receipt["release_binding"])
    if plan["plan_sha256"] != _content_sha256(plan):
        raise ValueError("execution plan content does not match plan_sha256")
    if receipt["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("receipt plan_sha256 does not match plan")
    if receipt["plan_id"] != plan["plan_id"]:
        raise ValueError("receipt plan_id does not match plan")
    if receipt["attempt_id"] != plan["attempt_id"]:
        raise ValueError("receipt attempt_id does not match plan")
    if receipt["release_binding"] != plan["release_binding"]:
        raise ValueError("receipt release binding does not match plan")
    if receipt["source_album_identifier"] != plan["source_album_identifier"]:
        raise ValueError("receipt source identifier does not match plan")
    if int(receipt["source_count"]) != int(plan["expected_source_count"]):
        raise ValueError("receipt source count does not match plan")
    if int(receipt["helper_capability_version"]) < 3:
        raise ValueError("receipt helper capability is too old for bound attempts")
    if str(receipt["helper_bundle_identifier"]).strip().casefold() in {"unknown", "unset"}:
        raise ValueError("receipt helper bundle identity is unresolved")
    folders = receipt.get("folders")
    if not isinstance(folders, list) or not folders or any(
        not item.get("identifier") or not item.get("title") for item in folders
    ):
        raise ValueError("receipt missing complete folder identities")
    folder_ids = [item["identifier"] for item in folders]
    if len(folder_ids) != len(set(folder_ids)):
        raise ValueError("receipt contains duplicate folder identities")
    planned = _planned_albums(plan)
    received = _received_albums(receipt)
    if set(planned) != set(received):
        raise ValueError("receipt album titles do not match plan")
    for title, expected_identifiers in planned.items():
        if received[title][1] != len(expected_identifiers):
            raise ValueError(f"receipt count does not match plan for {title}")
    return {
        "status": "PASS",
        "attempt_id": plan["attempt_id"],
        "plan_id": plan["plan_id"],
        "album_count": len(planned),
    }


def compare_execution_attempts(
    first_plan: dict,
    first_receipt: dict,
    second_plan: dict,
    second_receipt: dict,
) -> dict:
    first = validate_execution_attempt(first_plan, first_receipt)
    second = validate_execution_attempt(second_plan, second_receipt)
    if first_plan["attempt_id"] == second_plan["attempt_id"]:
        raise ValueError("idempotence requires two distinct execution attempts")
    if first_plan["release_binding"] != second_plan["release_binding"]:
        raise ValueError("production attempts do not share one release binding")
    if _planned_albums(first_plan) != _planned_albums(second_plan):
        raise ValueError("production attempts do not authorize identical album memberships")
    if _received_albums(first_receipt) != _received_albums(second_receipt):
        raise ValueError("production attempts produced different album identities or counts")
    return {
        "schema_version": 1,
        "status": "PASS",
        "idempotent": True,
        "attempt_ids": [first["attempt_id"], second["attempt_id"]],
        "release_plan_sha256": first_plan["release_binding"]["release_plan_sha256"],
    }
