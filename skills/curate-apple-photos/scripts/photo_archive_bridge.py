#!/usr/bin/env python3
"""Bridge Photo Fieldwork manifests to the permissioned Jamie Photo Archive app."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_PROFILE = Path(os.environ.get("PHOTO_FIELDWORK_PROFILE", ".photo-fieldwork.local.json"))
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


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_profile(path: Path) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8"))
    required = {"workspace_root", "photos_database", "permissioned_app", "source", "folders"}
    missing = sorted(required - set(profile))
    if missing:
        raise ValueError(f"local profile is missing: {', '.join(missing)}")
    source_required = {"kind", "identifier", "expected_count"}
    source_missing = sorted(source_required - set(profile["source"]))
    if source_missing:
        raise ValueError(f"local profile source is missing: {', '.join(source_missing)}")
    folder_required = {"root_identifier", "private_identifier", "audit_identifier"}
    folder_missing = sorted(folder_required - set(profile["folders"]))
    if folder_missing:
        raise ValueError(f"local profile folders are missing: {', '.join(folder_missing)}")
    return profile


def membership_sha256(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted({base_identifier(item) for item in values}):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def assignment_sha256(rows: list[dict[str, str]]) -> str:
    values = []
    seen = set()
    for row in rows:
        identifier = base_identifier(str(row.get("uuid") or ""))
        if not identifier or identifier in seen:
            raise ValueError("master assignments require unique canonical UUIDs")
        seen.add(identifier)
        values.append({
            "uuid": identifier,
            "primary_view": str(row.get("primary_view") or "").strip(),
            "safety_status": str(row.get("safety_status") or "").strip().lower(),
        })
    return hashlib.sha256(json.dumps(
        sorted(values, key=lambda item: item["uuid"]),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")).hexdigest()


def manifest_fingerprint(rows: list[dict[str, str]]) -> str:
    values = []
    seen = set()
    for row in rows:
        identifier = base_identifier(str(row.get("uuid") or ""))
        if not identifier or identifier in seen:
            raise ValueError("master manifest requires unique canonical UUIDs")
        seen.add(identifier)
        values.append({
            "uuid": identifier,
            "primary_view": str(row.get("primary_view") or "").strip(),
            "safety_status": str(row.get("safety_status") or "").strip().lower(),
            "publication_status": str(row.get("publication_status") or "not-approved").strip().lower(),
        })
    return hashlib.sha256(json.dumps(
        sorted(values, key=lambda item: item["uuid"]),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")).hexdigest()


def canonical_json_sha256(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "plan_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def attach_plan_digest(plan: dict) -> dict:
    plan["plan_sha256"] = canonical_json_sha256(plan)
    return plan


def verify_plan_digest(plan: dict) -> None:
    expected = plan.get("plan_sha256")
    if not expected or expected != canonical_json_sha256(plan):
        raise ValueError("plan digest is missing or does not match its contents")


def verify_release_binding(
    seal: dict,
    catalog_plan: dict,
    config: dict,
    master_rows: list[dict[str, str]],
    hold_rows: list[dict[str, str]],
    source: dict,
) -> dict:
    payload = {key: value for key, value in seal.items() if key != "release_seal_sha256"}
    bindings = seal.get("bindings") or {}
    gates = seal.get("gates") or {}
    if (
        seal.get("schema_version") != 1
        or seal.get("status") != "PASS"
        or seal.get("release_class") != "editor-field"
        or seal.get("publication_clearance") is not False
        or set(gates) != RELEASE_GATE_KEYS
        or any(value != "PASS" for value in gates.values())
        or set(bindings) != RELEASE_BINDING_KEYS
        or any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in bindings.values()
        )
    ):
        raise ValueError("release seal does not represent a closed, passing editor-field candidate")
    if seal.get("candidate_sha256") != canonical_json_sha256(bindings):
        raise ValueError("release candidate digest does not match its bindings")
    if seal.get("release_seal_sha256") != hashlib.sha256(json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")).hexdigest():
        raise ValueError("release seal digest does not match its contents")
    verify_plan_digest(catalog_plan)
    expected = {
        "config_sha256": hashlib.sha256(json.dumps(
            config,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")).hexdigest(),
        "master_sha256": manifest_fingerprint(master_rows),
        "master_membership_sha256": membership_sha256([row["uuid"] for row in master_rows]),
        "master_assignment_sha256": assignment_sha256(master_rows),
        "hold_membership_sha256": membership_sha256([row["uuid"] for row in hold_rows]),
        "catalog_plan_sha256": catalog_plan.get("plan_sha256"),
        "source_membership_sha256": source["membership_sha256"],
    }
    mismatches = [key for key, value in expected.items() if bindings.get(key) != value]
    if mismatches:
        raise ValueError(f"release seal binding mismatch: {', '.join(mismatches)}")
    if (
        catalog_plan.get("master_membership_sha256") != expected["master_membership_sha256"]
        or catalog_plan.get("master_assignment_sha256") != expected["master_assignment_sha256"]
        or (catalog_plan.get("source") or {}).get("membership_sha256") != source["membership_sha256"]
        or (catalog_plan.get("source") or {}).get("count") != source["count"]
    ):
        raise ValueError("catalog plan does not match the sealed source and master")
    return {
        "release_candidate_sha256": seal["candidate_sha256"],
        "release_seal_sha256": seal["release_seal_sha256"],
        "catalog_plan_sha256": catalog_plan["plan_sha256"],
        "master_assignment_sha256": expected["master_assignment_sha256"],
    }


def verify_writer_receipt(plan: dict, receipt: dict) -> None:
    allowed_fields = {
        "completed_at", "plan_id", "plan_sha256", "source_album_identifier",
        "source_count", "source_membership_sha256", "release_candidate_sha256",
        "release_seal_sha256", "catalog_plan_sha256", "master_assignment_sha256",
        "safety_mode", "folders", "albums",
    }
    expected_fields = (
        "plan_id",
        "plan_sha256",
        "safety_mode",
        "source_album_identifier",
        "source_membership_sha256",
        "release_candidate_sha256",
        "release_seal_sha256",
        "catalog_plan_sha256",
        "master_assignment_sha256",
    )
    mismatches = [field for field in expected_fields if receipt.get(field) != plan.get(field)]
    if set(receipt) != allowed_fields:
        mismatches.append("receipt_fields")
    if not isinstance(receipt.get("completed_at"), str) or not receipt["completed_at"].strip():
        mismatches.append("completed_at")
    folders = receipt.get("folders")
    valid_folders = (
        isinstance(folders, list)
        and bool(folders)
        and all(
            isinstance(item, dict)
            and set(item) == {"key", "title", "identifier"}
            and all(isinstance(item.get(key), str) and bool(item[key].strip()) for key in ("key", "title", "identifier"))
            for item in folders
        )
    )
    expected_folders = {item["key"]: item["title"] for item in plan.get("folders", [])}
    received_folders = {item["key"]: item["title"] for item in folders} if valid_folders else {}
    if (
        not valid_folders
        or len(received_folders) != len(folders)
        or expected_folders != received_folders
    ):
        mismatches.append("folders")
    if receipt.get("source_count") != plan.get("expected_source_count"):
        mismatches.append("source_count")
    expected_albums = {item["title"]: len(item["asset_identifiers"]) for item in plan.get("albums", [])}
    albums = receipt.get("albums")
    valid_albums = (
        isinstance(albums, list)
        and bool(albums)
        and all(
            isinstance(item, dict)
            and set(item) == {"title", "identifier", "count"}
            and isinstance(item.get("title"), str)
            and bool(item["title"].strip())
            and isinstance(item.get("identifier"), str)
            and bool(item["identifier"].strip())
            and isinstance(item.get("count"), int)
            and item["count"] >= 1
            for item in albums
        )
    )
    received_albums = {item["title"]: item["count"] for item in albums} if valid_albums else {}
    if not valid_albums or len(received_albums) != len(albums) or expected_albums != received_albums:
        mismatches.append("albums")
    if mismatches:
        raise ValueError(f"writer receipt does not match plan: {', '.join(mismatches)}")


def inventory_source(profile: dict) -> dict:
    inventory_path = Path(profile.get("inventory_database") or "")
    if not inventory_path.is_file():
        raise ValueError(f"inventory database not found: {inventory_path}")
    conn = sqlite3.connect(f"file:{inventory_path}?mode=ro&immutable=1", uri=True)
    conn.execute("PRAGMA query_only=ON")
    meta = {key: value for key, value in conn.execute("SELECT key, value FROM meta")}
    conn.close()
    identifier = meta.get("source_identifier") or meta.get("source_album_uuid")
    count = int(meta.get("source_count") or meta.get("source_album_count") or 0)
    digest = meta.get("source_membership_sha256")
    expected_identifier = base_identifier(profile["source"]["identifier"])
    if base_identifier(str(identifier or "")) != expected_identifier:
        raise ValueError("inventory source identifier does not match local profile")
    if count != int(profile["source"]["expected_count"]):
        raise ValueError("inventory source count does not match local profile")
    if not digest:
        raise ValueError("inventory is missing source_membership_sha256; rebuild the source snapshot")
    return {"identifier": profile["source"]["identifier"], "count": count, "membership_sha256": digest}


def local_identifier(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("empty asset identifier")
    return value if value.endswith("/L0/001") else f"{value.split('/', 1)[0]}/L0/001"


def base_identifier(value: str) -> str:
    return value.split("/", 1)[0]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "uuid" not in rows[0]:
        raise ValueError(f"CSV requires uuid rows: {path}")
    return rows


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "photo-field"


def command_doctor(args: argparse.Namespace) -> int:
    profile = read_profile(args.profile)
    app = Path(profile["permissioned_app"])
    executable = app / "Contents/MacOS" / app.stem
    plist_path = app / "Contents/Info.plist"
    inventory_path = Path(profile.get("inventory_database") or "")
    photos_db = Path(profile["photos_database"])
    workspace_root = Path(profile["workspace_root"])
    checks = {
        "permissioned_app": app.is_dir(),
        "app_executable": executable.is_file() and os.access(executable, os.X_OK),
        "app_plist": plist_path.is_file(),
        "shared_inventory": inventory_path.is_file(),
        "photos_database": photos_db.is_file(),
        "workspace_root": workspace_root.is_dir(),
    }
    bundle = None
    version = None
    inventory_meta = {}
    if plist_path.is_file():
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
        bundle = plist.get("CFBundleIdentifier")
        version = plist.get("CFBundleShortVersionString")
        expected_bundle = profile.get("permissioned_app_bundle_id")
        checks["stable_bundle_identifier"] = not expected_bundle or bundle == expected_bundle
    if inventory_path.is_file():
        conn = sqlite3.connect(f"file:{inventory_path}?mode=ro&immutable=1", uri=True)
        inventory_meta = {key: value for key, value in conn.execute("SELECT key, value FROM meta")}
        conn.close()
        identifier = inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid")
        count = inventory_meta.get("source_count") or inventory_meta.get("source_album_count") or 0
        checks["inventory_source_identifier"] = base_identifier(str(identifier or "")) == base_identifier(profile["source"]["identifier"])
        checks["inventory_source_count"] = int(count) == int(profile["source"]["expected_count"])
        checks["inventory_source_digest"] = bool(inventory_meta.get("source_membership_sha256"))
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    profile = read_profile(args.profile)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    workspace_root = args.workspace_root or Path(profile["workspace_root"])
    root = (workspace_root / f"{args.version}-{safe_slug(args.slug)}-{stamp}").resolve()
    if root.exists():
        raise ValueError(f"workspace already exists: {root}")
    for name in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets", "scripts"):
        (root / name).mkdir(parents=True, exist_ok=False)
    state = {
        "schema_version": 1,
        "run_id": root.name,
        "status": "initialized",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": args.version,
        "target_count": args.target,
        "source_album_identifier": profile["source"]["identifier"],
        "expected_source_count": profile["source"]["expected_count"],
        "phases": {
            "brief": "pending",
            "retrieval": "pending",
            "local_inspection": "pending",
            "recursive_evaluation": "pending",
            "validation": "pending",
            "write_test": "pending",
            "production_commit": "pending",
            "independent_verification": "pending",
        },
    }
    dump_json(root / "run-state.json", state)
    (root / "README.md").write_text(
        f"# {args.version}: {args.slug}\n\n"
        f"- Target: {args.target:,} unique still photographs\n"
        f"- Immutable source identifier: `{profile['source']['identifier']}`\n"
        f"- Expected source count: {profile['source']['expected_count']:,}\n"
        "- Final publication edit performed: no\n"
        "- External image or metadata upload permitted: no\n",
        encoding="utf-8",
    )
    print(root)
    return 0


def command_inspection_plan(args: argparse.Namespace) -> int:
    profile = read_profile(args.profile)
    source = inventory_source(profile)
    rows = read_csv(args.input)
    identifiers = list(dict.fromkeys(local_identifier(row["uuid"]) for row in rows))
    if args.limit:
        identifiers = identifiers[: args.limit]
    root = args.workspace.resolve()
    plan = {
        "operation": "inspect-local-images",
        "schema_version": 1,
        "plan_id": args.plan_id,
        "safety_mode": "read-only-local-inspection-and-preview-export",
        "source_album_identifier": source["identifier"],
        "expected_source_count": source["count"],
        "source_membership_sha256": source["membership_sha256"],
        "asset_identifiers": identifiers,
        "output_jsonl_path": str(root / "manifests" / f"{args.plan_id}-inspection.jsonl"),
        "receipt_path": str(root / "manifests" / f"{args.plan_id}-receipt.json"),
        "log_path": str(root / "logs" / "jamie-photo-archive-app.log"),
        "preview_directory": str(root / "previews" / args.plan_id),
        "target_long_edge": args.target_long_edge,
        "export_previews": not args.no_previews,
        "ocr_all": not args.no_ocr,
        "classify_all": not args.no_classify,
        "detect_faces": not args.no_face_detection,
        "network_access_allowed": False,
    }
    dump_json(args.output, attach_plan_digest(plan))
    print(f"inspection_assets={len(identifiers)}")
    print(f"plan={args.output}")
    return 0


def command_shard_plan(args: argparse.Namespace) -> int:
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    verify_plan_digest(plan)
    identifiers = list(plan.get("asset_identifiers") or [])
    if not identifiers:
        raise ValueError("inspection plan has no asset identifiers")
    if args.shards < 1 or args.shards > len(identifiers):
        raise ValueError("shards must be between 1 and the asset count")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    width = math.ceil(len(identifiers) / args.shards)
    created = []
    for index in range(args.shards):
        chunk = identifiers[index * width : (index + 1) * width]
        shard = dict(plan)
        shard_id = f"{plan['plan_id']}-shard-{index + 1:02d}"
        shard.update(
            {
                "plan_id": shard_id,
                "parent_plan_sha256": plan["plan_sha256"],
                "asset_identifiers": chunk,
                "output_jsonl_path": str(args.output_dir / f"{shard_id}-inspection.jsonl"),
                "receipt_path": str(args.output_dir / f"{shard_id}-receipt.json"),
                "log_path": str(args.output_dir / f"{shard_id}.log"),
                "preview_directory": str(args.output_dir / "previews" / shard_id),
            }
        )
        shard = attach_plan_digest(shard)
        path = args.output_dir / f"{shard_id}-plan.json"
        dump_json(path, shard)
        created.append({"plan": str(path), "assets": len(chunk), "plan_sha256": shard["plan_sha256"]})
    print(json.dumps(created, indent=2))
    return 0


def command_combine_inspection(args: argparse.Namespace) -> int:
    rows = []
    receipts = []
    identifiers = set()
    source_identity = None
    for plan_path in args.plan:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        verify_plan_digest(plan)
        planned_identifiers = [local_identifier(value) for value in plan.get("asset_identifiers") or []]
        if not planned_identifiers or len(planned_identifiers) != len(set(planned_identifiers)):
            raise ValueError(f"inspection shard has empty or duplicate planned membership: {plan_path}")
        receipt_path = Path(plan["receipt_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("plan_id") != plan.get("plan_id"):
            raise ValueError(f"receipt does not match plan ID: {receipt_path}")
        if receipt.get("plan_sha256") != plan["plan_sha256"]:
            raise ValueError(f"receipt does not match plan digest: {receipt_path}")
        if receipt.get("source_membership_sha256") != plan.get("source_membership_sha256"):
            raise ValueError(f"receipt does not match frozen source digest: {receipt_path}")
        if receipt.get("source_count") != plan.get("expected_source_count"):
            raise ValueError(f"receipt source count does not match shard plan: {receipt_path}")
        if receipt.get("requested_count") != len(planned_identifiers):
            raise ValueError(f"receipt requested count does not match shard plan: {receipt_path}")
        if receipt.get("completed_count") != len(planned_identifiers):
            raise ValueError(f"receipt completed count does not match shard plan: {receipt_path}")
        identity = (
            receipt.get("source_count"),
            plan.get("source_album_identifier"),
            receipt.get("source_membership_sha256"),
        )
        if source_identity is None:
            source_identity = identity
        elif identity != source_identity:
            raise ValueError("inspection shards do not share one source identity")
        if receipt.get("network_access_allowed") or receipt.get("external_uploads_performed"):
            raise ValueError("inspection receipt reports network access or external upload")
        inspection_path = Path(plan["output_jsonl_path"])
        shard_rows = []
        shard_identifiers = []
        for line in inspection_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            identifier = local_identifier(row.get("asset_identifier") or row.get("uuid") or "")
            shard_identifiers.append(identifier)
            shard_rows.append(row)
        if len(shard_identifiers) != len(set(shard_identifiers)):
            raise ValueError(f"duplicate inspection identifier within shard: {inspection_path}")
        missing = set(planned_identifiers) - set(shard_identifiers)
        unexpected = set(shard_identifiers) - set(planned_identifiers)
        if missing or unexpected:
            raise ValueError(
                f"inspection shard membership mismatch: missing={len(missing)} unexpected={len(unexpected)}"
            )
        for row, identifier in zip(shard_rows, shard_identifiers, strict=True):
            if identifier in identifiers:
                raise ValueError(f"duplicate inspection identifier across shards: {identifier}")
            identifiers.add(identifier)
            rows.append(row)
        receipts.append(receipt)
    if args.expected is not None and len(rows) != args.expected:
        raise ValueError(f"combined inspection count mismatch: {len(rows)} != {args.expected}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    combined = {
        "schema_version": 2,
        "operation": "combined-local-inspection-receipt",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_album_identifier": source_identity[1] if source_identity else None,
        "source_count": source_identity[0] if source_identity else None,
        "source_membership_sha256": source_identity[2] if source_identity else None,
        "completed_count": len(rows),
        "inspection_membership_sha256": membership_sha256(list(identifiers)),
        "network_access_allowed": False,
        "external_uploads_performed": False,
        "shard_plan_sha256": [receipt["plan_sha256"] for receipt in receipts],
    }
    dump_json(args.receipt, combined)
    print(json.dumps(combined, indent=2))
    return 0


def folder_specs(version_title: str, include_version: bool, profile: dict) -> list[dict]:
    folders = [
        {
            "key": "root",
            "title": "JAMIE PHOTO EDIT — 2026",
            "parent_key": None,
            "existing_identifier": profile["folders"]["root_identifier"],
        },
        {
            "key": "private",
            "title": "90 PRIVATE REVIEW — DO NOT SHARE",
            "parent_key": "root",
            "existing_identifier": profile["folders"]["private_identifier"],
        },
        {
            "key": "audit",
            "title": "99 WRITE TESTS / AUDIT",
            "parent_key": "root",
            "existing_identifier": profile["folders"]["audit_identifier"],
        },
    ]
    if include_version:
        folders.insert(
            1,
            {
                "key": "version",
                "title": version_title,
                "parent_key": "root",
                "existing_identifier": None,
            },
        )
    return folders


def album(title: str, parent: str, uuids: list[str]) -> dict:
    identifiers = list(dict.fromkeys(local_identifier(value) for value in uuids))
    return {
        "title": title,
        "parent_folder_key": parent,
        "existing_identifier": None,
        "asset_identifiers": identifiers,
        "membership_sha256": membership_sha256(identifiers),
    }


def snapshot_plan(
    args: argparse.Namespace,
    source: dict,
    plan_id: str,
    folders: list[dict],
    albums: list[dict],
    receipt: str,
) -> dict:
    plan = {
        "operation": "snapshot-membership",
        "schema_version": 3,
        "plan_id": plan_id,
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": source["identifier"],
        "expected_source_count": source["count"],
        "source_membership_sha256": source["membership_sha256"],
        **args.release_binding,
        "publication_approval_default": "not-approved",
        "batch_size": args.batch_size,
        "log_path": str(args.workspace / "logs" / "jamie-photo-archive-app.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
    }
    return attach_plan_digest(plan)


def command_snapshot_plans(args: argparse.Namespace) -> int:
    if getattr(args, "view_column", "primary_view") != "primary_view":
        raise ValueError("snapshot plans are sealed to the primary_view assignment field")
    profile = read_profile(args.profile)
    source = inventory_source(profile)
    master_rows = read_csv(args.master)
    hold_rows = read_csv(args.holds)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    catalog_plan = json.loads(args.catalog_plan.read_text(encoding="utf-8"))
    release_seal = json.loads(args.release_seal.read_text(encoding="utf-8"))
    args.release_binding = verify_release_binding(
        release_seal,
        catalog_plan,
        config,
        master_rows,
        hold_rows,
        source,
    )
    master_ids = [base_identifier(row["uuid"]) for row in master_rows]
    hold_ids = [base_identifier(row["uuid"]) for row in hold_rows]
    if len(master_ids) != args.target or len(set(master_ids)) != args.target:
        raise ValueError(f"master must contain exactly {args.target} unique IDs")
    overlap = set(master_ids) & set(hold_ids)
    if overlap:
        raise ValueError(f"master overlaps HOLD by {len(overlap)} IDs")
    if not all(row.get("selection_reason") or row.get("selection_reasons") or row.get("editorial_reasons") for row in master_rows):
        raise ValueError("every master row must have a selection reason")

    by_view: dict[str, list[str]] = {}
    view_labels = {}
    view_labels = {str(view["id"]): str(view["label"]) for view in config.get("views", [])}
    for row in master_rows:
        view = row.get("primary_view", "").strip() or "00"
        by_view.setdefault(view, []).append(base_identifier(row["uuid"]))
    named = [base_identifier(row["uuid"]) for row in master_rows if row.get("persons", "").strip()]
    uncertain = [
        base_identifier(row["uuid"])
        for row in master_rows
        if str(row.get("evidence_confidence", row.get("project_confidence", "unknown"))).lower()
        in {"unknown", "low", "low-context", "visible-general"}
    ]
    test_ids = [
        base_identifier(row["uuid"])
        for row in master_rows
        if str(row.get("evidence_confidence", row.get("project_confidence", ""))).lower() in {"high", "frozen-eval"}
    ][:10]
    for value in master_ids:
        if len(test_ids) == min(10, len(master_ids)):
            break
        if value not in test_ids:
            test_ids.append(value)

    test_title = f"{args.version} — WRITE TEST — VERIFIED {len(test_ids)}"
    test = snapshot_plan(
        args,
        source,
        f"{args.version}-write-test",
        folder_specs(args.folder_title, include_version=False, profile=profile),
        [album(test_title, "audit", test_ids)],
        f"{args.version}-write-test-receipt.json",
    )
    production_albums = [album(f"00 MASTER — {args.target:,}", "version", master_ids)]
    for view, values in sorted(by_view.items()):
        label = view_labels.get(view, "EDITOR VIEW")
        production_albums.append(album(f"{view} {label} — {len(values):,}", "version", values))
    if named:
        production_albums.append(album(f"90 PEOPLE / NAMED ASSOCIATIONS — {len(named):,}", "version", named))
    if uncertain:
        production_albums.append(album(f"91 CONTEXT UNCERTAIN — EDITOR REVIEW — {len(uncertain):,}", "version", uncertain))
    if hold_ids:
        production_albums.append(album(f"{args.version} — AUTOMATED SAFETY HOLD — {len(hold_ids):,}", "private", hold_ids))
    production_albums.append(album(test_title, "audit", test_ids))
    production = snapshot_plan(
        args,
        source,
        f"{args.version}-production",
        folder_specs(args.folder_title, include_version=True, profile=profile),
        production_albums,
        f"{args.version}-photo-archive-receipt.json",
    )
    test_path = args.workspace / "manifests" / f"{args.version}-write-test-plan.json"
    production_path = args.workspace / "manifests" / f"{args.version}-production-plan.json"
    dump_json(test_path, test)
    dump_json(production_path, production)
    print(f"test_plan={test_path}")
    print(f"production_plan={production_path}")
    print(f"production_albums={len(production_albums)}")
    print(f"production_memberships={sum(len(item['asset_identifiers']) for item in production_albums)}")
    return 0


def command_run_plan(args: argparse.Namespace) -> int:
    profile = read_profile(args.profile)
    app = Path(profile["permissioned_app"])
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    verify_plan_digest(plan)
    receipt_path = Path(plan["receipt_path"])
    if not app.is_dir():
        raise ValueError(f"permissioned app not found: {app}")
    before = receipt_path.stat().st_mtime_ns if receipt_path.exists() else None
    command = ["/usr/bin/open", "-W", "-n", str(app), "--args", "--plan", str(plan_path)]
    print("launching permissioned helper; this may run for a long time", flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise ValueError(f"helper launcher failed with exit code {completed.returncode}")
    if not receipt_path.exists():
        raise ValueError(f"helper finished without receipt: {receipt_path}")
    after = receipt_path.stat().st_mtime_ns
    if before is not None and before == after:
        raise ValueError(f"receipt was not refreshed: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    verify_writer_receipt(plan, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    doctor.set_defaults(func=command_doctor)

    init = sub.add_parser("init-run", help="create a durable versioned run workspace")
    init.add_argument("--slug", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--target", type=int, required=True)
    init.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    init.add_argument("--workspace-root", type=Path)
    init.set_defaults(func=command_init)

    inspect = sub.add_parser("inspection-plan", help="build an exact plan for local PhotoKit inspection")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    inspect.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    inspect.add_argument("--target-long-edge", type=int, default=1280)
    inspect.add_argument("--limit", type=int)
    inspect.add_argument("--no-previews", action="store_true")
    inspect.add_argument("--no-ocr", action="store_true")
    inspect.add_argument("--no-classify", action="store_true")
    inspect.add_argument("--no-face-detection", action="store_true")
    inspect.set_defaults(func=command_inspection_plan)

    plans = sub.add_parser("snapshot-plans", help="build test-first app plans from a validated master")
    plans.add_argument("--workspace", type=Path, required=True)
    plans.add_argument("--master", type=Path, required=True)
    plans.add_argument("--holds", type=Path, required=True)
    plans.add_argument("--target", type=int, required=True)
    plans.add_argument("--version", required=True)
    plans.add_argument("--folder-title", required=True)
    plans.add_argument("--config", type=Path, required=True)
    plans.add_argument("--catalog-plan", type=Path, required=True)
    plans.add_argument("--release-seal", type=Path, required=True)
    plans.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    plans.add_argument("--batch-size", type=int, default=500)
    plans.set_defaults(func=command_snapshot_plans)

    run = sub.add_parser("run-plan", help="launch a plan through the stable permissioned app bundle")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    run.set_defaults(func=command_run_plan)

    shard = sub.add_parser("shard-plan", help="split one inspection plan into independently resumable shards")
    shard.add_argument("--plan", type=Path, required=True)
    shard.add_argument("--output-dir", type=Path, required=True)
    shard.add_argument("--shards", type=int, default=4)
    shard.set_defaults(func=command_shard_plan)

    combine = sub.add_parser("combine-inspection", help="verify and combine completed inspection shards")
    combine.add_argument("--plan", type=Path, action="append", required=True)
    combine.add_argument("--output", type=Path, required=True)
    combine.add_argument("--receipt", type=Path, required=True)
    combine.add_argument("--expected", type=int)
    combine.set_defaults(func=command_combine_inspection)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
