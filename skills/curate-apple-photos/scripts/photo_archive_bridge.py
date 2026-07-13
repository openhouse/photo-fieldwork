#!/usr/bin/env python3
"""Bridge Photo Fieldwork manifests to the permissioned Jamie Photo Archive app."""

from __future__ import annotations

import argparse
import csv
import json
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


APP = Path("/Applications/Photo Fieldwork Helper.app")
APP_EXECUTABLE = APP / "Contents/MacOS/JamiePhotoArchive"
APP_PLIST = APP / "Contents/Info.plist"
BUNDLE_ID = "example.photo-fieldwork-helper"
WORKSPACE_ROOT = Path.home() / "Documents/Photo-Fieldwork"
INVENTORY_DB = WORKSPACE_ROOT / "shared/wide-corpus.sqlite"
PHOTOS_DB = Path.home() / "Pictures/Photos Library.photoslibrary/database/Photos.sqlite"
SOURCE_ID = "visible-library-stills://v1"
SOURCE_COUNT = None
ROOT_FOLDER_ID = "REPLACE-WITH-PRIVATE-PROFILE"
PRIVATE_FOLDER_ID = "REPLACE-WITH-PRIVATE-PROFILE"
AUDIT_FOLDER_ID = "REPLACE-WITH-PRIVATE-PROFILE"


def default_profile() -> dict:
    return {
        "schema_version": 1,
        "workspace_root": str(WORKSPACE_ROOT),
        "photo_fieldwork_cli": str(Path(__file__).resolve().parents[3] / "bin/photo-fieldwork"),
        "inventory_database": str(INVENTORY_DB),
        "photos_database": str(PHOTOS_DB),
        "app": {
            "path": str(APP),
            "bundle_identifier": BUNDLE_ID,
            "executable": "JamiePhotoArchive",
        },
        "source": {
            "identifier": SOURCE_ID,
            "expected_count": None,
            "title": "Visible Apple Photos library - still photographs",
        },
        "protected_folders": {
            "root": {
                "title": "PHOTO FIELDWORK",
                "identifier": ROOT_FOLDER_ID,
            },
            "private": {
                "title": "PRIVATE REVIEW - DO NOT SHARE",
                "identifier": PRIVATE_FOLDER_ID,
            },
            "audit": {
                "title": "WRITE TESTS / AUDIT",
                "identifier": AUDIT_FOLDER_ID,
            },
        },
    }


def load_profile(path: Path | None) -> dict:
    if path is None:
        raise ValueError("--profile is required for live Apple Photos operations")
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile.get("schema_version") != 1:
        raise ValueError("profile schema_version must be 1")
    required = {"workspace_root", "source"}
    missing = required - set(profile)
    if missing:
        raise ValueError(f"profile missing: {', '.join(sorted(missing))}")
    return profile


def source_values(args: argparse.Namespace, profile: dict) -> tuple[str, int]:
    identifier = args.source_id or profile["source"]["identifier"]
    count = args.source_count
    if count is None:
        count = profile["source"].get("expected_count")
    if count is None:
        raise ValueError("source count must be frozen before building an inspection or write plan")
    return str(identifier), int(count)


def meta_value(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


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


def command_doctor(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    app = Path(profile.get("app", {}).get("path", APP))
    app_executable = app / "Contents/MacOS" / profile.get("app", {}).get(
        "executable", "JamiePhotoArchive"
    )
    app_plist = app / "Contents/Info.plist"
    bundle_id = profile.get("app", {}).get("bundle_identifier", BUNDLE_ID)
    inventory_db = Path(profile.get("inventory_database", INVENTORY_DB))
    photos_db = Path(profile.get("photos_database", PHOTOS_DB))
    workspace_root = Path(profile["workspace_root"])
    cli_path = Path(profile.get("photo_fieldwork_cli", ""))
    source_id = str(profile["source"]["identifier"])
    expected_count = profile["source"].get("expected_count")
    checks = {
        "permissioned_app": app.is_dir(),
        "app_executable": app_executable.is_file() and os.access(app_executable, os.X_OK),
        "app_plist": app_plist.is_file(),
        "shared_inventory": inventory_db.exists(),
        "photos_database": photos_db.exists(),
        "workspace_root": workspace_root.is_dir(),
        "photo_fieldwork_cli": cli_path.is_file(),
    }
    bundle = None
    version = None
    inventory_meta = {}
    if app_plist.is_file():
        with app_plist.open("rb") as handle:
            plist = plistlib.load(handle)
        bundle = plist.get("CFBundleIdentifier")
        version = plist.get("CFBundleShortVersionString")
        checks["stable_bundle_identifier"] = bundle == bundle_id
    if inventory_db.exists():
        conn = sqlite3.connect(f"file:{inventory_db}?mode=ro&immutable=1", uri=True)
        inventory_meta = {key: meta_value(value) for key, value in conn.execute("SELECT key, value FROM meta")}
        conn.close()
        inventory_source = inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid")
        inventory_count = inventory_meta.get("source_count") or inventory_meta.get("source_album_count")
        checks["inventory_source_identifier"] = inventory_source in {
            source_id,
            base_identifier(source_id),
        }
        checks["inventory_source_count"] = (
            expected_count is None or int(inventory_count or 0) == int(expected_count)
        )
    if photos_db.exists():
        conn = sqlite3.connect(f"file:{photos_db}?mode=ro&immutable=1", uri=True)
        conn.execute("PRAGMA query_only=ON")
        required_tables = {"ZASSET", "ZGENERICALBUM", "Z_30ASSETS"}
        present_tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        conn.close()
        checks["photos_schema_compatible"] = required_tables <= present_tables
    live_receipt = None
    if args.live and all(checks.values()):
        with tempfile.TemporaryDirectory(prefix="photo-fieldwork-preflight-") as temporary:
            root = Path(temporary)
            plan_path = root / "preflight-plan.json"
            receipt_path = root / "preflight-receipt.json"
            plan = {
                "operation": "preflight-read-only",
                "schema_version": 1,
                "plan_id": "photo-fieldwork-live-doctor",
                "source_album_identifier": source_id,
                "expected_source_count": expected_count,
                "sample_asset_identifier": args.sample_asset_id,
                "receipt_path": str(receipt_path),
                "network_access_allowed": False,
            }
            dump_json(plan_path, plan)
            completed = subprocess.run(
                ["/usr/bin/open", "-W", "-n", str(app), "--args", "--plan", str(plan_path)],
                check=False,
            )
            checks["live_helper_launch"] = completed.returncode == 0
            checks["live_preflight_receipt"] = receipt_path.exists()
            if receipt_path.exists():
                live_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                checks["live_preflight"] = live_receipt.get("status") == "PASS"
                checks["live_bundle_identity"] = (
                    live_receipt.get("helper_bundle_identifier") == bundle_id
                )
                capabilities = set(live_receipt.get("capabilities", []))
                checks["live_capability_handshake"] = {
                    "preflight-read-only",
                    "inspect-local-images",
                    "snapshot-membership",
                } <= capabilities
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
        "live_preflight": live_receipt,
        "mutation_performed": False,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init_profile(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite private profile: {output}")
    profile = {
        "$schema": str(args.schema.resolve()) if args.schema else None,
        "schema_version": 1,
        "workspace_root": str(args.workspace_root.resolve()),
        "photo_fieldwork_cli": str(args.cli.resolve()),
        "inventory_database": str(args.inventory.resolve()),
        "photos_database": str(args.photos_db.resolve()),
        "app": {
            "path": str(args.app.resolve()),
            "bundle_identifier": args.bundle_identifier,
            "executable": args.executable,
        },
        "source": {
            "identifier": args.source_id,
            "expected_count": args.source_count,
            "title": args.source_title,
        },
        "protected_folders": {
            "root": {"title": args.root_title, "identifier": args.root_id},
            "private": {"title": args.private_title, "identifier": args.private_id},
            "audit": {"title": args.audit_title, "identifier": args.audit_id},
        },
    }
    if profile["$schema"] is None:
        profile.pop("$schema")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dump_json(output, profile)
    output.chmod(0o600)
    print(output)
    return 0


def command_init(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    source_id, source_count = source_values(args, profile)
    workspace_root = args.workspace_root or Path(profile["workspace_root"])
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    root = (workspace_root / f"{args.version}-{safe_slug(args.slug)}-{stamp}").resolve()
    if root.exists():
        raise ValueError(f"workspace already exists: {root}")
    for name in (
        "inventory",
        "manifests",
        "reports",
        "logs",
        "previews",
        "contact-sheets",
        "scripts",
        "review",
        "final",
    ):
        (root / name).mkdir(parents=True, exist_ok=False, mode=0o700)
    root.chmod(0o700)
    state = {
        "schema_version": 2,
        "run_id": root.name,
        "status": "initialized",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": args.version,
        "target_count": args.target,
        "source": {"identifier": source_id, "expected_count": source_count},
        "tool": {"name": "photo-fieldwork bridge", "version": 2},
        "phases": {
            phase: {"status": "pending", "attempts": []}
            for phase in (
                "brief",
                "source",
                "retrieval",
                "inspection",
                "evaluation",
                "final_freeze",
                "validation",
                "write_test",
                "production_commit",
                "independent_verification",
            )
        },
    }
    dump_json(root / "run-state.json", state)
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
    profile = load_profile(args.profile)
    source_id, source_count = source_values(args, profile)
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


def folder_specs(version_title: str, include_version: bool, profile: dict | None = None) -> list[dict]:
    profile = profile or default_profile()
    protected = profile.get("protected_folders", {})
    root_spec = protected.get("root", {})
    private_spec = protected.get("private", {})
    audit_spec = protected.get("audit", {})
    folders = [
        {
            "key": "root",
            "title": root_spec.get("title", "JAMIE PHOTO EDIT — 2026"),
            "parent_key": None,
            "existing_identifier": root_spec.get("identifier", ROOT_FOLDER_ID),
        },
        {
            "key": "private",
            "title": private_spec.get("title", "90 PRIVATE REVIEW — DO NOT SHARE"),
            "parent_key": "root",
            "existing_identifier": private_spec.get("identifier", PRIVATE_FOLDER_ID),
        },
        {
            "key": "audit",
            "title": audit_spec.get("title", "99 WRITE TESTS / AUDIT"),
            "parent_key": "root",
            "existing_identifier": audit_spec.get("identifier", AUDIT_FOLDER_ID),
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
    profile = load_profile(args.profile)
    source_id, source_count = source_values(args, profile)
    return {
        "operation": "snapshot-membership",
        "schema_version": 1,
        "plan_id": plan_id,
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": source_id,
        "expected_source_count": source_count,
        "batch_size": args.batch_size,
        "writer_contract": {
            "allowed_backends": ["photokit", "applescript"],
            "backend_selection_must_be_explicit": True,
            "independent_verification_required": True,
            "source_verification_required_before_write": True,
        },
        "log_path": str(args.workspace / "logs" / "jamie-photo-archive-app.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
    }


def command_snapshot_plans(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
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
    profile = load_profile(args.profile)
    app = Path(profile.get("app", {}).get("path", APP))
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
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
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    init_profile = sub.add_parser("init-profile", help="create a private local profile")
    init_profile.add_argument("--output", type=Path, required=True)
    init_profile.add_argument("--schema", type=Path)
    init_profile.add_argument("--workspace-root", type=Path, required=True)
    init_profile.add_argument("--cli", type=Path, required=True)
    init_profile.add_argument("--inventory", type=Path, required=True)
    init_profile.add_argument("--photos-db", type=Path, required=True)
    init_profile.add_argument("--app", type=Path, required=True)
    init_profile.add_argument("--bundle-identifier", required=True)
    init_profile.add_argument("--executable", required=True)
    init_profile.add_argument("--source-id", required=True)
    init_profile.add_argument("--source-count", type=int)
    init_profile.add_argument("--source-title", required=True)
    init_profile.add_argument("--root-title", required=True)
    init_profile.add_argument("--root-id", required=True)
    init_profile.add_argument("--private-title", required=True)
    init_profile.add_argument("--private-id", required=True)
    init_profile.add_argument("--audit-title", required=True)
    init_profile.add_argument("--audit-id", required=True)
    init_profile.set_defaults(func=command_init_profile)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.add_argument("--profile", type=Path)
    doctor.add_argument("--live", action="store_true", help="launch the helper for a read-only capability probe")
    doctor.add_argument("--sample-asset-id")
    doctor.set_defaults(func=command_doctor)

    init = sub.add_parser("init-run", help="create a durable versioned run workspace")
    init.add_argument("--slug", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--target", type=int, required=True)
    init.add_argument("--profile", type=Path)
    init.add_argument("--workspace-root", type=Path)
    init.add_argument("--source-id")
    init.add_argument("--source-count", type=int)
    init.set_defaults(func=command_init)

    inspect = sub.add_parser("inspection-plan", help="build an exact plan for local PhotoKit inspection")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    inspect.add_argument("--profile", type=Path)
    inspect.add_argument("--source-id")
    inspect.add_argument("--source-count", type=int)
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
    plans.add_argument("--profile", type=Path)
    plans.add_argument("--source-id")
    plans.add_argument("--source-count", type=int)
    plans.add_argument("--batch-size", type=int, default=500)
    plans.set_defaults(func=command_snapshot_plans)

    run = sub.add_parser("run-plan", help="launch a plan through the stable permissioned app bundle")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--profile", type=Path)
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
