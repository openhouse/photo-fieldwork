#!/usr/bin/env python3
"""Bridge Photo Fieldwork manifests to the permissioned Jamie Photo Archive app."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import plistlib
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path


APP = Path("/Applications/Jamie Photo Archive.app")
APP_EXECUTABLE = APP / "Contents/MacOS/JamiePhotoArchive"
APP_PLIST = APP / "Contents/Info.plist"
BUNDLE_ID = "art.jamieburkart.jamiephotoarchive"
WORKSPACE_ROOT = Path("/Users/jburkart/Documents/Jamie-Photo-Archive-2026")
INVENTORY_DB = WORKSPACE_ROOT / "shared/wide-corpus.sqlite"
PHOTOS_DB = Path(
    "/Volumes/apple-photos-8tb-external-ssd/Photos Library.photoslibrary/database/Photos.sqlite"
)
SOURCE_ID = "360ED78F-FB05-490A-8FFD-F3CB951D0D0A/L0/040"
SOURCE_COUNT = 124_484
ROOT_FOLDER_ID = "92BBCF49-B077-478D-B9EE-DD94FAAFEAB5/L0/020"
PRIVATE_FOLDER_ID = "1095845F-B6FA-41D0-8A22-D156C3071631/L0/020"
AUDIT_FOLDER_ID = "7F9EB400-C06D-412C-9443-300A2C47CCE7/L0/020"
VISIBLE_LIBRARY_STILLS = "visible-library-stills://v1"


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def decode_meta(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def identifier_rows_sha256(rows) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(str(row[0]).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_catalog_plan(plan: dict) -> dict:
    if plan.get("schema_version") != 2:
        raise ValueError("catalog plan schema_version must be 2")
    payload = dict(plan)
    observed = payload.pop("plan_sha256", None)
    if observed != canonical_sha256(payload):
        raise ValueError("catalog plan digest does not match its contents")
    candidate = plan.get("release_candidate", {})
    if not isinstance(candidate, dict) or plan.get("candidate_id") != candidate.get("candidate_id"):
        raise ValueError("catalog plan release candidate binding is invalid")
    if candidate.get("publication_clearance") is not False:
        raise ValueError("editor-field catalog plans cannot imply publication clearance")
    if plan.get("safety_mode") != "create-folders-albums-and-add-membership-only":
        raise ValueError("catalog plan requests an unsupported mutation boundary")
    return plan


def master_assignment_sha256(rows: list[dict[str, str]], view_column: str) -> str:
    assignments = [
        {"uuid": base_identifier(row["uuid"]), "primary_view": row.get(view_column, "").strip()}
        for row in rows
    ]
    assignments.sort(key=lambda row: (row["primary_view"], row["uuid"]))
    return canonical_sha256(assignments)


def command_doctor(args: argparse.Namespace) -> int:
    free_gb = shutil.disk_usage(args.workspace_root).free / 1024**3 if args.workspace_root.exists() else 0
    checks = {
        "permissioned_app": APP.is_dir(),
        "app_executable": APP_EXECUTABLE.is_file() and os.access(APP_EXECUTABLE, os.X_OK),
        "app_plist": APP_PLIST.is_file(),
        "shared_inventory": args.inventory_db.exists(),
        "photos_database": args.photos_db.exists(),
        "workspace_root": args.workspace_root.is_dir(),
        "workspace_free_space": free_gb >= args.minimum_free_gb,
        "photo_fieldwork_cli": Path(
            "/Volumes/16TB_SSD/Sites/photo-fieldwork/bin/photo-fieldwork"
        ).is_file(),
    }
    bundle = None
    version = None
    helper_contract_version = None
    inventory_meta = {}
    photos_visible_count = None
    live_source_membership_sha256 = None
    inventory_integrity = None
    if APP_PLIST.is_file():
        with APP_PLIST.open("rb") as handle:
            plist = plistlib.load(handle)
        bundle = plist.get("CFBundleIdentifier")
        version = plist.get("CFBundleShortVersionString")
        helper_contract_version = plist.get("PhotoFieldworkHelperContractVersion")
        checks["stable_bundle_identifier"] = bundle == BUNDLE_ID
        checks["helper_contract_version"] = helper_contract_version == 2
    if args.inventory_db.exists():
        conn = sqlite3.connect(f"file:{args.inventory_db}?mode=ro&immutable=1", uri=True)
        inventory_meta = {key: decode_meta(value) for key, value in conn.execute("SELECT key, value FROM meta")}
        inventory_integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        conn.close()
        inventory_source = inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid")
        inventory_count = inventory_meta.get("source_count") or inventory_meta.get("source_album_count")
        expected_id = args.source_id if args.source_id == VISIBLE_LIBRARY_STILLS else base_identifier(args.source_id)
        checks["inventory_integrity"] = inventory_integrity == "ok"
        checks["inventory_source_identifier"] = inventory_source == expected_id
        checks["inventory_source_count"] = int(inventory_count or 0) == args.source_count
        if args.source_membership_sha256:
            checks["inventory_source_membership"] = (
                inventory_meta.get("source_membership_sha256") == args.source_membership_sha256
            )
    if args.photos_db.exists():
        conn = sqlite3.connect(f"file:{args.photos_db}?mode=ro&immutable=1", uri=True, timeout=30)
        conn.execute("PRAGMA query_only=ON")
        if args.source_id == VISIBLE_LIBRARY_STILLS:
            photos_visible_count = conn.execute(
                """
                SELECT count(*) FROM ZASSET
                WHERE ZKIND = 0 AND ZTRASHEDSTATE = 0 AND ZHIDDEN = 0
                  AND ZVISIBILITYSTATE = 0 AND ZBUNDLESCOPE = 0
                """
            ).fetchone()[0]
            checks["live_source_count"] = photos_visible_count == args.source_count
            if args.source_membership_sha256:
                live_source_membership_sha256 = identifier_rows_sha256(
                    conn.execute(
                        """
                        SELECT ZUUID FROM ZASSET
                        WHERE ZKIND = 0 AND ZTRASHEDSTATE = 0 AND ZHIDDEN = 0
                          AND ZVISIBILITYSTATE = 0 AND ZBUNDLESCOPE = 0
                        ORDER BY ZUUID
                        """
                    )
                )
                checks["live_source_membership"] = live_source_membership_sha256 == args.source_membership_sha256
        conn.close()
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "helper_contract_version": helper_contract_version,
        "app_executable_sha256": file_hash(APP_EXECUTABLE) if APP_EXECUTABLE.is_file() else None,
        "workspace_free_gb": round(free_gb, 2),
        "minimum_free_gb": args.minimum_free_gb,
        "inventory_integrity": inventory_integrity,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_identifier": inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid"),
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
        "live_visible_source_count": photos_visible_count,
        "live_source_membership_sha256": live_source_membership_sha256,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    root = (args.workspace_root / f"{args.version}-{safe_slug(args.slug)}-{stamp}").resolve()
    if root.exists():
        raise ValueError(f"workspace already exists: {root}")
    for name in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets", "scripts"):
        (root / name).mkdir(parents=True, exist_ok=False)
    state = {
        "schema_version": 2,
        "run_id": root.name,
        "status": "active",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": args.version,
        "target_count": args.target,
        "source_identifier": args.source_id,
        "phase": "briefed",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "history": [{"phase": "briefed", "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"), "receipts": []}],
    }
    dump_json(root / "run-state.json", state)
    (root / "README.md").write_text(
        f"# {args.version}: {args.slug}\n\n"
        f"- Target: {args.target:,} unique still photographs\n"
        f"- Immutable source identifier: `{args.source_id}`\n"
        f"- Expected source count: {args.source_count:,}\n"
        "- Final publication edit performed: no\n"
        "- External image or metadata upload permitted: no\n",
        encoding="utf-8",
    )
    print(root)
    return 0


def command_inspection_plan(args: argparse.Namespace) -> int:
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
        "source_album_identifier": args.source_id,
        "expected_source_count": args.source_count,
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
    dump_json(args.output, plan)
    print(f"inspection_assets={len(identifiers)}")
    print(f"plan={args.output}")
    return 0


def folder_specs(version_title: str, include_version: bool) -> list[dict]:
    folders = [
        {
            "key": "root",
            "title": "JAMIE PHOTO EDIT — 2026",
            "parent_key": None,
            "existing_identifier": ROOT_FOLDER_ID,
        },
        {
            "key": "private",
            "title": "90 PRIVATE REVIEW — DO NOT SHARE",
            "parent_key": "root",
            "existing_identifier": PRIVATE_FOLDER_ID,
        },
        {
            "key": "audit",
            "title": "99 WRITE TESTS / AUDIT",
            "parent_key": "root",
            "existing_identifier": AUDIT_FOLDER_ID,
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
    }


def snapshot_plan(
    args: argparse.Namespace,
    plan_id: str,
    folders: list[dict],
    albums: list[dict],
    receipt: str,
    release_binding: dict,
) -> dict:
    return {
        "operation": "snapshot-membership",
        "schema_version": 2,
        "plan_id": plan_id,
        "candidate_id": release_binding["candidate_id"],
        "plan_sha256": release_binding["plan_sha256"],
        "source_membership_sha256": release_binding["source_membership_sha256"],
        "execution_nonce": "",
        "helper_contract_version": 2,
        "helper": {},
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": args.source_id,
        "expected_source_count": args.source_count,
        "batch_size": args.batch_size,
        "log_path": str(args.workspace / "logs" / "jamie-photo-archive-app.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
    }


def command_snapshot_plans(args: argparse.Namespace) -> int:
    catalog_plan = validate_catalog_plan(json.loads(args.catalog_plan.read_text(encoding="utf-8")))
    release_candidate = catalog_plan["release_candidate"]
    release_binding = {
        "candidate_id": catalog_plan["candidate_id"],
        "plan_sha256": catalog_plan["plan_sha256"],
        "source_membership_sha256": catalog_plan["source_membership_sha256"],
    }
    master_rows = read_csv(args.master)
    hold_rows = read_csv(args.holds)
    master_ids = [base_identifier(row["uuid"]) for row in master_rows]
    hold_ids = [base_identifier(row["uuid"]) for row in hold_rows]
    if len(master_ids) != args.target or len(set(master_ids)) != args.target:
        raise ValueError(f"master must contain exactly {args.target} unique IDs")
    overlap = set(master_ids) & set(hold_ids)
    if overlap:
        raise ValueError(f"master overlaps HOLD by {len(overlap)} IDs")
    if not all(row.get("selection_reason") or row.get("selection_reasons") or row.get("editorial_reasons") for row in master_rows):
        raise ValueError("every master row must have a selection reason")
    if release_candidate.get("master_sha256") != master_assignment_sha256(master_rows, args.view_column):
        raise ValueError("master CSV assignments do not match the authorized release candidate")
    catalog_master = next((item for item in catalog_plan.get("albums", []) if item.get("key") == "master"), None)
    if not catalog_master:
        raise ValueError("catalog plan lacks a master album")
    catalog_master_ids = {base_identifier(value) for value in catalog_master.get("asset_identifiers", [])}
    if catalog_master_ids != set(master_ids):
        raise ValueError("master CSV membership does not match the authorized catalog plan")
    source = catalog_plan.get("source", {})
    if source.get("source_identifier") != args.source_id:
        raise ValueError("source identifier does not match the authorized catalog plan")
    if int(source.get("observed_count", 0)) != args.source_count:
        raise ValueError("source count does not match the authorized catalog plan")

    by_view: dict[str, list[str]] = {}
    view_labels = {}
    if args.config:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        view_labels = {str(view["id"]): str(view["label"]) for view in config.get("views", [])}
    for row in master_rows:
        view = row.get(args.view_column, "").strip() or "00"
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
        f"{args.version}-write-test",
        folder_specs(args.folder_title, include_version=False),
        [album(test_title, "audit", test_ids)],
        f"{args.version}-write-test-receipt.json",
        release_binding,
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
        f"{args.version}-production",
        folder_specs(args.folder_title, include_version=True),
        production_albums,
        f"{args.version}-photo-archive-receipt.json",
        release_binding,
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
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    required = {"candidate_id", "plan_sha256", "source_membership_sha256"}
    missing = required - set(plan)
    if plan.get("schema_version") != 2 or missing:
        raise ValueError(f"production plan lacks helper contract 2 fields: {sorted(missing)}")
    if plan.get("execution_nonce"):
        raise ValueError("base production plan already contains an execution nonce")
    if not APP.is_dir():
        raise ValueError(f"permissioned app not found: {APP}")
    with APP_PLIST.open("rb") as handle:
        plist = plistlib.load(handle)
    helper = {
        "bundle_id": plist.get("CFBundleIdentifier", ""),
        "version": plist.get("CFBundleShortVersionString", ""),
        "binary_sha256": file_hash(APP_EXECUTABLE),
    }
    if helper["bundle_id"] != BUNDLE_ID or not helper["version"] or plist.get("PhotoFieldworkHelperContractVersion") != 2:
        raise ValueError("installed helper identity does not match the reviewed contract")
    execution_nonce = str(uuid.uuid4())
    attempts = plan_path.parent / "attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    attempt_plan = dict(plan)
    attempt_plan["execution_nonce"] = execution_nonce
    attempt_plan["helper"] = helper
    receipt_path = attempts / f"{plan_path.stem}-{execution_nonce}-receipt.json"
    attempt_plan["receipt_path"] = str(receipt_path.resolve())
    attempt_plan_path = attempts / f"{plan_path.stem}-{execution_nonce}.json"
    dump_json(attempt_plan_path, attempt_plan)
    command = ["/usr/bin/open", "-W", "-n", str(APP), "--args", "--plan", str(attempt_plan_path)]
    print("launching permissioned helper; this may run for a long time", flush=True)
    started = time.monotonic()
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise ValueError(f"helper launcher failed with exit code {completed.returncode}")
    if not receipt_path.exists():
        raise ValueError(f"helper finished without receipt: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected_identity = {
        "schema_version": 2,
        "plan_id": plan["plan_id"],
        "candidate_id": plan["candidate_id"],
        "plan_sha256": plan["plan_sha256"],
        "source_membership_sha256": plan["source_membership_sha256"],
        "execution_nonce": execution_nonce,
        "helper_contract_version": 2,
        "helper": helper,
        "safety_mode": "create-folders-albums-and-add-membership-only",
    }
    mismatches = [field for field, value in expected_identity.items() if receipt.get(field) != value]
    expected_albums = {item["title"]: len(set(item["asset_identifiers"])) for item in plan.get("albums", [])}
    observed_albums = {item["title"]: int(item["count"]) for item in receipt.get("albums", [])}
    if expected_albums != observed_albums:
        mismatches.append("albums")
    if mismatches:
        raise ValueError(f"helper receipt does not match the authorized execution: {sorted(mismatches)}")
    receipt["launcher_elapsed_seconds"] = round(time.monotonic() - started, 3)
    receipt["attempt_plan_sha256"] = canonical_sha256(attempt_plan)
    dump_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.add_argument("--workspace-root", type=Path, default=WORKSPACE_ROOT)
    doctor.add_argument("--inventory-db", type=Path, default=INVENTORY_DB)
    doctor.add_argument("--photos-db", type=Path, default=PHOTOS_DB)
    doctor.add_argument("--minimum-free-gb", type=float, default=20.0)
    doctor.add_argument("--source-id", default=SOURCE_ID)
    doctor.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    doctor.add_argument("--source-membership-sha256", default="")
    doctor.set_defaults(func=command_doctor)

    init = sub.add_parser("init-run", help="create a durable versioned run workspace")
    init.add_argument("--slug", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--target", type=int, required=True)
    init.add_argument("--workspace-root", type=Path, default=WORKSPACE_ROOT)
    init.add_argument("--source-id", default=SOURCE_ID)
    init.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    init.set_defaults(func=command_init)

    inspect = sub.add_parser("inspection-plan", help="build an exact plan for local PhotoKit inspection")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    inspect.add_argument("--source-id", default=SOURCE_ID)
    inspect.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    inspect.add_argument("--target-long-edge", type=int, default=1280)
    inspect.add_argument("--limit", type=int)
    inspect.add_argument("--no-previews", action="store_true")
    inspect.add_argument("--no-ocr", action="store_true")
    inspect.add_argument("--no-classify", action="store_true")
    inspect.add_argument("--no-face-detection", action="store_true")
    inspect.set_defaults(func=command_inspection_plan)

    plans = sub.add_parser("snapshot-plans", help="build test-first app plans from a validated master")
    plans.add_argument("--workspace", type=Path, required=True)
    plans.add_argument("--catalog-plan", type=Path, required=True)
    plans.add_argument("--master", type=Path, required=True)
    plans.add_argument("--holds", type=Path, required=True)
    plans.add_argument("--target", type=int, required=True)
    plans.add_argument("--version", required=True)
    plans.add_argument("--folder-title", required=True)
    plans.add_argument("--view-column", default="primary_view")
    plans.add_argument("--config", type=Path)
    plans.add_argument("--source-id", default=SOURCE_ID)
    plans.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    plans.add_argument("--batch-size", type=int, default=500)
    plans.set_defaults(func=command_snapshot_plans)

    run = sub.add_parser("run-plan", help="launch a plan through the stable permissioned app bundle")
    run.add_argument("--plan", type=Path, required=True)
    run.set_defaults(func=command_run_plan)
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
