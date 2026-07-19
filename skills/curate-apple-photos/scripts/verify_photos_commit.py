#!/usr/bin/env python3
"""Independently verify a permissioned-app plan and receipt through read-only Photos SQLite."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


VISIBLE_LIBRARY_STILLS = "visible-library-stills://v1"
RELEASE_FIELDS = (
    "release_candidate_sha256",
    "release_seal_sha256",
    "catalog_plan_sha256",
    "master_assignment_sha256",
)
RELEASE_BINDING_KEYS = {
    "config_sha256", "master_sha256", "master_assignment_sha256",
    "master_membership_sha256", "hold_membership_sha256", "feedback_sha256",
    "evaluation_report_sha256", "validation_report_sha256", "catalog_plan_sha256",
    "decision_ledger_sha256", "holdout_report_sha256", "source_membership_sha256",
    "safety_baseline_sha256",
}
RELEASE_GATE_KEYS = {
    "evaluation_recomputed", "validation_recomputed", "decision_chain",
    "holdout_independence", "catalog_plan_integrity",
}


def base(value: str) -> str:
    return value.split("/", 1)[0]


def album_record(conn: sqlite3.Connection, identifier: str) -> tuple[int, str]:
    rows = conn.execute("SELECT Z_PK, ZTITLE FROM ZGENERICALBUM WHERE ZUUID = ?", (base(identifier),)).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"expected one album for {identifier}; found {len(rows)}")
    return int(rows[0][0]), rows[0][1] or ""


def members(conn: sqlite3.Connection, album_pk: int) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            """
            SELECT a.ZUUID
            FROM Z_30ASSETS membership
            JOIN ZASSET a ON a.Z_PK = membership.Z_3ASSETS
            WHERE membership.Z_30ALBUMS = ?
            """,
            (album_pk,),
        )
    }


def source_members(conn: sqlite3.Connection, identifier: str) -> tuple[set[str], str]:
    if identifier == VISIBLE_LIBRARY_STILLS:
        rows = conn.execute(
            """
            SELECT ZUUID
            FROM ZASSET
            WHERE ZKIND = 0
              AND ZTRASHEDSTATE = 0
              AND ZHIDDEN = 0
              AND ZVISIBILITYSTATE = 0
              AND ZBUNDLESCOPE = 0
            """
        )
        return {row[0] for row in rows}, "Visible Apple Photos library - still photographs"
    source_pk, source_title = album_record(conn, identifier)
    return members(conn, source_pk), source_title


def membership_sha256(values: set[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(base(item) for item in values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def canonical_json_sha256(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "plan_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def release_seal_sha256(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "release_seal_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--release-seal", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--json-report", type=Path)
    parser.add_argument("--photos-db", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    release_seal = json.loads(args.release_seal.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 3:
        raise RuntimeError(f"unsupported plan schema: {plan.get('schema_version')}")
    if plan.get("plan_sha256") != canonical_json_sha256(plan):
        raise RuntimeError("plan digest mismatch")
    if receipt.get("plan_sha256") != plan["plan_sha256"]:
        raise RuntimeError("receipt does not bind to the exact plan digest")
    if receipt.get("plan_id") != plan.get("plan_id"):
        raise RuntimeError("receipt does not bind to the exact plan ID")
    if receipt.get("source_album_identifier") != plan.get("source_album_identifier"):
        raise RuntimeError("receipt does not bind to the exact source identifier")
    if receipt.get("safety_mode") != plan.get("safety_mode"):
        raise RuntimeError("receipt does not bind to the plan safety mode")
    for field in RELEASE_FIELDS:
        value = str(plan.get(field) or "")
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise RuntimeError(f"plan has a missing or malformed {field}")
        if receipt.get(field) != value:
            raise RuntimeError(f"receipt does not bind to plan {field}")
    if release_seal.get("release_seal_sha256") != release_seal_sha256(release_seal):
        raise RuntimeError("release seal digest mismatch")
    if (
        release_seal.get("schema_version") != 1
        or release_seal.get("status") != "PASS"
        or release_seal.get("release_class") != "editor-field"
    ):
        raise RuntimeError("release seal is not a passing editor-field release")
    bindings = release_seal.get("bindings") or {}
    gates = release_seal.get("gates") or {}
    if release_seal.get("candidate_sha256") != canonical_json_sha256(bindings):
        raise RuntimeError("release candidate digest does not match its bindings")
    if set(bindings) != RELEASE_BINDING_KEYS:
        raise RuntimeError("release seal contains incomplete bindings")
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in bindings.values()
    ):
        raise RuntimeError("release seal contains malformed bindings")
    if set(gates) != RELEASE_GATE_KEYS or any(value != "PASS" for value in gates.values()):
        raise RuntimeError("release seal contains an unpassed gate")
    if release_seal.get("release_seal_sha256") != plan["release_seal_sha256"]:
        raise RuntimeError("plan does not bind to the supplied release seal")
    if release_seal.get("candidate_sha256") != plan["release_candidate_sha256"]:
        raise RuntimeError("plan does not bind to the supplied release candidate")
    if release_seal.get("publication_clearance") is not False:
        raise RuntimeError("editor-field release seal cannot grant publication clearance")
    if plan.get("publication_approval_default") != "not-approved":
        raise RuntimeError("writer plan cannot grant publication approval")
    for field in ("catalog_plan_sha256", "master_assignment_sha256", "source_membership_sha256"):
        if bindings.get(field) != plan[field]:
            raise RuntimeError(f"release seal does not bind to plan {field}")
    expected = {
        item["title"]: {base(identifier) for identifier in item["asset_identifiers"]}
        for item in plan["albums"]
    }
    receipt_titles = {item["title"] for item in receipt["albums"]}
    if set(expected) != receipt_titles:
        raise RuntimeError("plan and receipt album titles differ")

    uri = f"file:{args.photos_db}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    source, source_title = source_members(conn, plan["source_album_identifier"])
    if len(source) != plan["expected_source_count"]:
        raise RuntimeError(f"source count changed: {len(source)} != {plan['expected_source_count']}")
    actual_source_digest = membership_sha256(source)
    if actual_source_digest != plan.get("source_membership_sha256"):
        raise RuntimeError("source membership digest changed")
    if receipt.get("source_membership_sha256") != actual_source_digest:
        raise RuntimeError("writer receipt source digest does not match independent verification")
    if receipt.get("source_count") != len(source):
        raise RuntimeError("writer receipt source count does not match independent verification")

    verified = []
    for received in receipt["albums"]:
        title = received["title"]
        album_pk, actual_title = album_record(conn, received["identifier"])
        actual = members(conn, album_pk)
        if actual_title != title:
            raise RuntimeError(f"title mismatch for {title}")
        if received.get("count") != len(actual):
            raise RuntimeError(f"writer receipt count mismatch for {title}")
        if actual != expected[title]:
            raise RuntimeError(f"membership mismatch for {title}: expected {len(expected[title])}, got {len(actual)}")
        if not actual <= source:
            raise RuntimeError(f"{title} contains assets outside source")
        spec = next(item for item in plan["albums"] if item["title"] == title)
        if membership_sha256(actual) != spec.get("membership_sha256"):
            raise RuntimeError(f"membership digest mismatch for {title}")
        verified.append((title, len(actual), received["identifier"]))
    conn.close()

    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        f"- Plan: `{plan['plan_id']}`",
        f"- Source: `{source_title}`",
        f"- Source membership: {len(source):,}",
        f"- Source membership SHA-256: `{actual_source_digest}`",
        f"- Plan SHA-256: `{plan['plan_sha256']}`",
        f"- Release candidate SHA-256: `{plan['release_candidate_sha256']}`",
        f"- Release seal SHA-256: `{plan['release_seal_sha256']}`",
        f"- Catalog plan SHA-256: `{plan['catalog_plan_sha256']}`",
        f"- Master assignment SHA-256: `{plan['master_assignment_sha256']}`",
        "- Publication clearance: not granted",
        f"- Albums exactly verified: {len(verified)}",
        "- Unexpected memberships: 0",
        "- Missing memberships: 0",
        "- Members outside source corpus: 0",
        "",
        "## Albums",
        "",
        *[f"- `{title}`: {count:,} (`{identifier}`)" for title, count, identifier in verified],
        "",
        "Verification used a read-only, immutable, query-only SQLite connection.",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    verification = {
        "schema_version": 1,
        "status": "PASS",
        "verification_kind": "independent-read-only-photos-sqlite",
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "release_candidate_sha256": plan["release_candidate_sha256"],
        "release_seal_sha256": plan["release_seal_sha256"],
        "catalog_plan_sha256": plan["catalog_plan_sha256"],
        "master_assignment_sha256": plan["master_assignment_sha256"],
        "source_membership_sha256": actual_source_digest,
        "source_count": len(source),
        "verified_album_count": len(verified),
        "unexpected_membership_count": 0,
        "missing_membership_count": 0,
        "outside_source_count": 0,
        "publication_clearance": False,
    }
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(
            json.dumps(verification, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"verified_albums={len(verified)}")
    print(f"source_count={len(source)}")


if __name__ == "__main__":
    main()
