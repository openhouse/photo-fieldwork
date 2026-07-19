from __future__ import annotations

import re

from .integrity import canonical_json_fingerprint


def receipt_binding(receipt: dict) -> dict:
    if "albums" in receipt or "folders" in receipt:
        return {
            "folders": receipt.get("folders", []),
            "albums": receipt.get("albums", []),
        }
    volatile = {"completed_at", "captured_at", "resumed_count", "execution_nonce"}
    return {key: value for key, value in receipt.items() if key not in volatile}


def audit_idempotence_evidence(
    attempts: list[dict],
    verifications: list[dict],
    expected_plan_sha256: str,
) -> dict:
    errors = []
    if len(attempts) < 2:
        errors.append("idempotence requires at least two execution attempts")
    attempt_ids = [str(item.get("attempt_id", "")).strip() for item in attempts]
    nonces = [str(item.get("execution_nonce", "")).strip() for item in attempts]
    if any(not value for value in attempt_ids) or len(attempt_ids) != len(set(attempt_ids)):
        errors.append("attempt IDs must be non-empty and distinct")
    if any(not re.fullmatch(r"[a-f0-9]{32}", value) for value in nonces) or len(nonces) != len(set(nonces)):
        errors.append("execution nonces must be distinct 32-character lowercase hex values")
    if any(item.get("plan_sha256") != expected_plan_sha256 for item in attempts):
        errors.append("every attempt must bind the expected plan SHA-256")
    if any(
        (item.get("receipt") or {}).get("execution_nonce") != item.get("execution_nonce")
        for item in attempts
    ):
        errors.append("every helper receipt must attest its archived execution nonce")
    fingerprints = [item.get("execution_fingerprint") or {} for item in attempts]
    if any(fingerprint.get("plan_sha256") != expected_plan_sha256 for fingerprint in fingerprints):
        errors.append("every execution fingerprint must bind the expected plan SHA-256")
    bundle_ids = {fingerprint.get("app_bundle_identifier") for fingerprint in fingerprints}
    binary_hashes = {fingerprint.get("app_binary_sha256") for fingerprint in fingerprints}
    if None in bundle_ids or "" in bundle_ids or len(bundle_ids) != 1:
        errors.append("all attempts must use one non-empty app bundle identifier")
    if (
        None in binary_hashes
        or "" in binary_hashes
        or len(binary_hashes) != 1
        or any(not re.fullmatch(r"[a-f0-9]{64}", str(value or "")) for value in binary_hashes)
    ):
        errors.append("all attempts must use one valid app binary SHA-256")

    bindings = [canonical_json_fingerprint(receipt_binding(item.get("receipt") or {})) for item in attempts]
    same_bindings = bool(bindings) and len(set(bindings)) == 1
    if not same_bindings:
        errors.append("catalog bindings changed across execution receipts")

    verification_by_attempt = {}
    for report in verifications:
        attempt_id = str(report.get("attempt_id", "")).strip()
        if not attempt_id or attempt_id in verification_by_attempt:
            errors.append("verification reports require unique non-empty attempt IDs")
            continue
        verification_by_attempt[attempt_id] = report
    for attempt_id in attempt_ids:
        report = verification_by_attempt.get(attempt_id)
        if report is None:
            errors.append(f"missing independent verification for attempt {attempt_id}")
            continue
        if report.get("plan_sha256") != expected_plan_sha256:
            errors.append(f"verification for {attempt_id} binds a different plan")
        if str(report.get("status", "")).upper() != "PASS":
            errors.append(f"verification for {attempt_id} did not pass")
        if report.get("exact_membership") is not True:
            errors.append(f"verification for {attempt_id} lacks exact membership proof")
        if report.get("exact_topology") is not True:
            errors.append(f"verification for {attempt_id} lacks exact topology proof")

    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "attempt_count": len(attempts),
        "verification_count": len(verifications),
        "plan_sha256": expected_plan_sha256,
        "same_catalog_bindings": same_bindings,
        "app_bundle_identifier": next(iter(bundle_ids)) if len(bundle_ids) == 1 else None,
        "app_binary_sha256": next(iter(binary_hashes)) if len(binary_hashes) == 1 else None,
    }
