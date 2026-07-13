#!/usr/bin/env python3
"""Bridge Photo Fieldwork manifests to the permissioned Jamie Photo Archive app."""

from __future__ import annotations

import argparse
import csv
import json
import os
import plistlib
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from photo_fieldwork.contracts import load_source_profile, seal_plan, verify_plan_digest  # noqa: E402
from photo_fieldwork.workflow import transition_run_state  # noqa: E402


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


def source_contract(args: argparse.Namespace) -> tuple[str, int, dict | None]:
    profile_path = getattr(args, "source_profile", None)
    if profile_path:
        profile = load_source_profile(profile_path)
        return str(profile["id"]), int(profile["expected_count"]), profile
    return str(args.source_id), int(args.source_count), None


def parse_meta_value(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def command_doctor(args: argparse.Namespace) -> int:
    source_id, source_count, profile = source_contract(args)
    inventory_db = Path(profile.get("inventory_path") or INVENTORY_DB) if profile else INVENTORY_DB
    checks = {
        "permissioned_app": APP.is_dir(),
        "app_executable": APP_EXECUTABLE.is_file() and os.access(APP_EXECUTABLE, os.X_OK),
        "app_plist": APP_PLIST.is_file(),
        "shared_inventory": inventory_db.exists(),
        "photos_database": PHOTOS_DB.exists(),
        "workspace_root": WORKSPACE_ROOT.is_dir(),
        "photo_fieldwork_cli": Path(
            "/Volumes/16TB_SSD/Sites/photo-fieldwork/bin/photo-fieldwork"
        ).is_file(),
    }
    bundle = None
    version = None
    inventory_meta = {}
    if APP_PLIST.is_file():
        with APP_PLIST.open("rb") as handle:
            plist = plistlib.load(handle)
        bundle = plist.get("CFBundleIdentifier")
        version = plist.get("CFBundleShortVersionString")
        checks["stable_bundle_identifier"] = bundle == BUNDLE_ID
    if inventory_db.exists():
        conn = sqlite3.connect(f"file:{inventory_db}?mode=ro&immutable=1", uri=True)
        inventory_meta = {key: parse_meta_value(value) for key, value in conn.execute("SELECT key, value FROM meta")}
        conn.close()
        inventory_source = inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid")
        inventory_count = inventory_meta.get("source_count") or inventory_meta.get("source_album_count")
        checks["inventory_source_identifier"] = str(inventory_source) in {source_id, base_identifier(source_id)}
        checks["inventory_source_count"] = int(inventory_count or 0) == source_count
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "active_source_identifier": source_id,
        "active_source_count": source_count,
        "source_profile_fingerprint": profile.get("fingerprint") if profile else None,
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    source_id, source_count, profile = source_contract(args)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    root = (args.workspace_root / f"{args.version}-{safe_slug(args.slug)}-{stamp}").resolve()
    if root.exists():
        raise ValueError(f"workspace already exists: {root}")
    for name in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets", "scripts"):
        (root / name).mkdir(parents=True, exist_ok=False)
    state = {
        "schema_version": 2,
        "run_id": root.name,
        "status": "initialized",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": args.version,
        "target_count": args.target,
        "source": {
            "id": source_id,
            "expected_count": source_count,
            "profile_fingerprint": profile.get("fingerprint") if profile else None,
        },
        "phases": {
            "brief": "pending",
            "retrieval": "pending",
            "local_inspection": "pending",
            "recursive_evaluation": "pending",
            "duplicate_audit": "pending",
            "replacement_review": "pending",
            "validation": "pending",
            "plan_lint": "pending",
            "write_test": "pending",
            "production_commit": "pending",
            "idempotence_check": "pending",
            "independent_verification": "pending",
        },
        "history": [],
    }
    dump_json(root / "run-state.json", state)
    if profile:
        dump_json(root / "source-profile.json", profile)
    (root / "README.md").write_text(
        f"# {args.version}: {args.slug}\n\n"
        f"- Target: {args.target:,} unique still photographs\n"
        f"- Immutable source identifier: `{source_id}`\n"
        f"- Expected source count: {source_count:,}\n"
        "- Final publication edit performed: no\n"
        "- External image or metadata upload permitted: no\n",
        encoding="utf-8",
    )
    print(root)
    return 0


def command_inspection_plan(args: argparse.Namespace) -> int:
    source_id, source_count, profile = source_contract(args)
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
        "source_album_identifier": source_id,
        "expected_source_count": source_count,
        "source_profile_fingerprint": profile.get("fingerprint") if profile else None,
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
        "lint_status": "PASS",
    }
    dump_json(args.output, seal_plan(plan))
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


def snapshot_plan(args: argparse.Namespace, plan_id: str, folders: list[dict], albums: list[dict], receipt: str) -> dict:
    source_id, source_count, profile = source_contract(args)
    return seal_plan({
        "operation": "snapshot-membership",
        "schema_version": 1,
        "plan_id": plan_id,
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": source_id,
        "expected_source_count": source_count,
        "source_profile_fingerprint": profile.get("fingerprint") if profile else None,
        "batch_size": args.batch_size,
        "log_path": str(args.workspace / "logs" / "jamie-photo-archive-app.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
        "lint_status": "PASS",
    })


def command_snapshot_plans(args: argparse.Namespace) -> int:
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
    if bool(args.run_state) != bool(args.phase):
        raise ValueError("--run-state and --phase must be provided together")
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("lint_status") != "PASS":
        raise ValueError("plan has not passed pre-write linting")
    if not verify_plan_digest(plan):
        raise ValueError("plan is unsealed or its digest no longer matches")
    receipt_path = Path(plan["receipt_path"])
    if not APP.is_dir():
        raise ValueError(f"permissioned app not found: {APP}")
    before = receipt_path.stat().st_mtime_ns if receipt_path.exists() else None
    previous_receipt = None
    if receipt_path.exists():
        previous_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        archive = receipt_path.with_name(f"{receipt_path.stem}-previous-{stamp}{receipt_path.suffix}")
        shutil.copy2(receipt_path, archive)
    command = ["/usr/bin/open", "-W", "-n", str(APP), "--args", "--plan", str(plan_path)]
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
    if previous_receipt and plan.get("operation") == "snapshot-membership":
        previous_folders = {item["title"]: item["identifier"] for item in previous_receipt.get("folders", [])}
        current_folders = {item["title"]: item["identifier"] for item in receipt.get("folders", [])}
        previous_albums = {item["title"]: (item["identifier"], item["count"]) for item in previous_receipt.get("albums", [])}
        current_albums = {item["title"]: (item["identifier"], item["count"]) for item in receipt.get("albums", [])}
        idempotence = {
            "status": "PASS" if previous_folders == current_folders and previous_albums == current_albums else "FAIL",
            "stable_folder_identifiers": previous_folders == current_folders,
            "stable_album_identifiers_and_counts": previous_albums == current_albums,
            "first_receipt_completed_at": previous_receipt.get("completed_at"),
            "second_receipt_completed_at": receipt.get("completed_at"),
        }
        idempotence_path = receipt_path.with_name(f"{receipt_path.stem}-idempotence.json")
        dump_json(idempotence_path, idempotence)
        if idempotence["status"] != "PASS":
            raise ValueError(f"idempotence mismatch: {idempotence_path}")
    if args.run_state and args.phase:
        transition_run_state(args.run_state, args.phase, "completed", str(receipt_path))
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


def command_release_status(args: argparse.Namespace) -> int:
    state = json.loads(args.run_state.read_text(encoding="utf-8"))
    phases = state.get("phases") or {}
    next_phase = next((name for name, status in phases.items() if status != "completed"), None)
    report = {
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "next_phase": next_phase,
        "next_phase_status": phases.get(next_phase) if next_phase else None,
        "complete": next_phase is None,
    }
    print(json.dumps(report, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.add_argument("--source-profile", type=Path)
    doctor.add_argument("--source-id", default=SOURCE_ID)
    doctor.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    doctor.set_defaults(func=command_doctor)

    init = sub.add_parser("init-run", help="create a durable versioned run workspace")
    init.add_argument("--slug", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--target", type=int, required=True)
    init.add_argument("--workspace-root", type=Path, default=WORKSPACE_ROOT)
    init.add_argument("--source-id", default=SOURCE_ID)
    init.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    init.add_argument("--source-profile", type=Path)
    init.set_defaults(func=command_init)

    inspect = sub.add_parser("inspection-plan", help="build an exact plan for local PhotoKit inspection")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    inspect.add_argument("--source-id", default=SOURCE_ID)
    inspect.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    inspect.add_argument("--source-profile", type=Path)
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
    plans.add_argument("--view-column", default="primary_view")
    plans.add_argument("--config", type=Path)
    plans.add_argument("--source-id", default=SOURCE_ID)
    plans.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    plans.add_argument("--source-profile", type=Path)
    plans.add_argument("--batch-size", type=int, default=500)
    plans.set_defaults(func=command_snapshot_plans)

    run = sub.add_parser("run-plan", help="launch a plan through the stable permissioned app bundle")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--run-state", type=Path)
    run.add_argument("--phase")
    run.set_defaults(func=command_run_plan)

    release = sub.add_parser("release-status", help="report the next incomplete resumable run phase")
    release.add_argument("--run-state", type=Path, required=True)
    release.set_defaults(func=command_release_status)
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
