from __future__ import annotations

import re
from datetime import datetime

from .integrity import canonical_json_fingerprint


SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
NONCE = re.compile(r"[0-9a-f]{32}")
REQUIRED_HELPER_CAPABILITIES = (
    "membership-only-write",
    "receipt-plan-digest",
    "launch-nonce",
    "exact-folder-topology",
)


def validate_helper_profile(
    profile: dict,
    required_capabilities: list[str] | tuple[str, ...] = REQUIRED_HELPER_CAPABILITIES,
    plan_schema_version: int = 2,
) -> list[str]:
    errors = []
    if int(profile.get("schema_version", -1)) != 1:
        errors.append("helper profile schema is unsupported")
    bundle_identifier = str(profile.get("bundle_identifier", ""))
    if not re.fullmatch(r"[A-Za-z0-9.-]+", bundle_identifier):
        errors.append("helper bundle identifier is missing or malformed")
    if not SHA256.fullmatch(str(profile.get("binary_sha256", ""))):
        errors.append("helper binary_sha256 is missing or malformed")
    capabilities = profile.get("capabilities")
    if not isinstance(capabilities, list) or any(not isinstance(value, str) for value in capabilities):
        errors.append("helper capabilities must be a list of strings")
        capabilities = []
    if len(capabilities) != len(set(capabilities)):
        errors.append("helper capabilities contain duplicates")
    for capability in sorted(set(required_capabilities) - set(capabilities)):
        errors.append(f"helper lacks required capability: {capability}")
    versions = profile.get("supported_plan_schema_versions")
    if not isinstance(versions, list) or plan_schema_version not in versions:
        errors.append(f"helper does not support plan schema {plan_schema_version}")
    return errors


def _folder_topology(plan: dict, receipt: dict) -> list[str]:
    errors = []
    planned = {item["key"]: item for item in plan.get("folders", [])}
    received_rows = receipt.get("folders")
    if not isinstance(received_rows, list):
        return ["receipt folders must be a list"]
    received = {item.get("key"): item for item in received_rows}
    if None in received or len(received) != len(received_rows):
        errors.append("receipt folder keys are missing or duplicated")
    if set(planned) != set(received):
        errors.append("receipt folder topology differs from plan")
        return errors
    identifiers = {key: item.get("identifier") for key, item in received.items()}
    if any(not value for value in identifiers.values()) or len(set(identifiers.values())) != len(identifiers):
        errors.append("receipt folder identifiers are missing or duplicated")
    for key, spec in planned.items():
        item = received[key]
        if item.get("title") != spec.get("title"):
            errors.append(f"receipt folder title differs for {key}")
        parent_key = spec.get("parent_key")
        expected_parent = identifiers.get(parent_key) if parent_key else None
        if item.get("parent_identifier") != expected_parent:
            errors.append(f"receipt folder topology differs for {key}")
    return errors


def _album_topology(plan: dict, receipt: dict) -> list[str]:
    errors = []
    planned = {item["key"]: item for item in plan.get("albums", [])}
    received_rows = receipt.get("albums")
    if not isinstance(received_rows, list):
        return ["receipt albums must be a list"]
    received = {item.get("key"): item for item in received_rows}
    if None in received or len(received) != len(received_rows):
        errors.append("receipt album keys are missing or duplicated")
    if set(planned) != set(received):
        errors.append("receipt album topology differs from plan")
        return errors
    folder_ids = {item.get("key"): item.get("identifier") for item in receipt.get("folders", [])}
    album_ids = [item.get("identifier") for item in received_rows]
    if any(not value for value in album_ids) or len(set(album_ids)) != len(album_ids):
        errors.append("receipt album identifiers are missing or duplicated")
    for key, spec in planned.items():
        item = received[key]
        if item.get("title") != spec.get("title"):
            errors.append(f"receipt album title differs for {key}")
        if int(item.get("count", -1)) != len(spec.get("asset_identifiers", [])):
            errors.append(f"receipt album count differs for {key}")
        expected_parent = folder_ids.get(spec.get("parent_folder_key"))
        if item.get("parent_identifier") != expected_parent:
            errors.append(f"receipt album topology differs for {key}")
    return errors


def verify_execution_receipt(
    receipt: dict,
    plan: dict,
    helper_profile: dict,
    plan_file_sha256: str | None = None,
) -> list[str]:
    requirement = plan.get("helper_requirement") or {}
    required_capabilities = requirement.get("required_capabilities", REQUIRED_HELPER_CAPABILITIES)
    required_schema = int(requirement.get("plan_schema_version", plan.get("schema_version", -1)))
    errors = validate_helper_profile(helper_profile, required_capabilities, required_schema)
    if not requirement:
        errors.append("plan lacks an authorized helper requirement")
    else:
        if helper_profile.get("bundle_identifier") != requirement.get("bundle_identifier"):
            errors.append("supplied profile differs from authorized helper bundle identifier")
        if helper_profile.get("binary_sha256") != requirement.get("binary_sha256"):
            errors.append("supplied profile differs from authorized helper binary digest")
    if int(receipt.get("schema_version", -1)) != 1:
        errors.append("receipt schema is unsupported")
    try:
        datetime.fromisoformat(str(receipt.get("completed_at", "")).replace("Z", "+00:00"))
    except ValueError:
        errors.append("receipt completed_at is not an ISO-8601 timestamp")
    if not NONCE.fullmatch(str(receipt.get("execution_nonce", ""))):
        errors.append("receipt execution_nonce is missing or malformed")
    if receipt.get("plan_id") != plan.get("plan_id"):
        errors.append("receipt plan_id differs from plan")
    if receipt.get("plan_fingerprint") != canonical_json_fingerprint(plan):
        errors.append("receipt plan fingerprint differs from the authorized plan")
    receipt_plan_file_sha256 = str(receipt.get("plan_file_sha256", ""))
    if not SHA256.fullmatch(receipt_plan_file_sha256):
        errors.append("receipt plan_file_sha256 is missing or malformed")
    elif plan_file_sha256 is not None and receipt_plan_file_sha256 != plan_file_sha256:
        errors.append("receipt plan_file_sha256 differs from the executed plan bytes")
    source = plan.get("source") or {}
    expected_source = {
        "source_id": source.get("id"),
        "source_count": source.get("actual_count"),
        "source_fingerprint": source.get("fingerprint"),
    }
    for field, expected in expected_source.items():
        if receipt.get(field) != expected:
            errors.append(f"receipt {field} differs from plan source")
    helper = receipt.get("helper") or {}
    if helper.get("bundle_identifier") != helper_profile.get("bundle_identifier"):
        errors.append("receipt helper bundle identifier differs from profile")
    if helper.get("binary_sha256") != helper_profile.get("binary_sha256"):
        errors.append("receipt helper binary digest differs from profile")
    errors.extend(_folder_topology(plan, receipt))
    errors.extend(_album_topology(plan, receipt))
    return errors


def _result_topology(receipt: dict) -> dict:
    return {
        "folders": sorted(
            (
                item.get("key"),
                item.get("title"),
                item.get("identifier"),
                item.get("parent_identifier"),
            )
            for item in receipt.get("folders", [])
        ),
        "albums": sorted(
            (
                item.get("key"),
                item.get("title"),
                item.get("identifier"),
                item.get("parent_identifier"),
                item.get("count"),
            )
            for item in receipt.get("albums", [])
        ),
    }


def compare_execution_receipts(first: dict, second: dict, plan: dict, helper_profile: dict) -> dict:
    errors = [f"first: {error}" for error in verify_execution_receipt(first, plan, helper_profile)]
    errors.extend(f"second: {error}" for error in verify_execution_receipt(second, plan, helper_profile))
    if first.get("execution_nonce") == second.get("execution_nonce"):
        errors.append("idempotence requires distinct execution nonce values")
    if first.get("completed_at") == second.get("completed_at"):
        errors.append("idempotence requires distinct completion times")
    if first.get("plan_file_sha256") != second.get("plan_file_sha256"):
        errors.append("idempotence executions used different plan bytes")
    if _result_topology(first) != _result_topology(second):
        errors.append("idempotence result topology differs between executions")
    return {
        "schema_version": 1,
        "passed": not errors,
        "errors": errors,
        "execution_fingerprints": [
            canonical_json_fingerprint(first),
            canonical_json_fingerprint(second),
        ],
        "plan_fingerprint": canonical_json_fingerprint(plan),
    }
