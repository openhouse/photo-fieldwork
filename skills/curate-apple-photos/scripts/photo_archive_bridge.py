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
import secrets
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from photo_fieldwork.integrity import canonical_json_fingerprint  # noqa: E402
from photo_fieldwork.release import REQUIRED_HELPER_CAPABILITIES, validate_helper_profile  # noqa: E402
from photo_fieldwork.state import initialize_run  # noqa: E402


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


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


def installed_helper_profile(bundle: str | None) -> dict:
    return {
        "schema_version": 1,
        "bundle_identifier": bundle,
        "binary_sha256": file_sha256(APP_EXECUTABLE) if APP_EXECUTABLE.is_file() else None,
        "capabilities": list(REQUIRED_HELPER_CAPABILITIES),
        "supported_plan_schema_versions": [2],
    }


def command_doctor(args: argparse.Namespace) -> int:
    checks = {
        "permissioned_app": APP.is_dir(),
        "app_executable": APP_EXECUTABLE.is_file() and os.access(APP_EXECUTABLE, os.X_OK),
        "app_plist": APP_PLIST.is_file(),
        "shared_inventory": INVENTORY_DB.exists(),
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
        checks["helper_contract_version"] = version == "3.0"
    if INVENTORY_DB.exists():
        conn = sqlite3.connect(f"file:{INVENTORY_DB}?mode=ro&immutable=1", uri=True)
        inventory_meta = {key: json.loads(value) for key, value in conn.execute("SELECT key, value FROM meta")}
        conn.close()
        checks["inventory_source_identifier"] = inventory_meta.get("source_album_uuid") == base_identifier(SOURCE_ID)
        checks["inventory_source_count"] = int(inventory_meta.get("source_album_count", 0)) == SOURCE_COUNT
    helper_profile = installed_helper_profile(bundle)
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_count": inventory_meta.get("source_album_count"),
        "helper_profile": helper_profile,
    }
    if args.helper_profile_output:
        if report["status"] != "PASS":
            raise ValueError("cannot write a helper profile while doctor checks are failing")
        dump_json(args.helper_profile_output, helper_profile)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    root = (args.workspace_root / f"{args.version}-{safe_slug(args.slug)}-{stamp}").resolve()
    if root.exists():
        raise ValueError(f"workspace already exists: {root}")
    for name in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets", "scripts"):
        (root / name).mkdir(parents=True, exist_ok=False)
    initialize_run(
        root,
        run_id=root.name,
        phases=[
            "brief",
            "retrieval",
            "local_inspection",
            "recursive_evaluation",
            "validation",
            "write_test",
            "production_commit",
            "independent_verification",
        ],
        metadata={
            "version": args.version,
            "target_count": args.target,
            "source_album_identifier": args.source_id,
            "expected_source_count": args.source_count,
        },
    )
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


def album(
    title: str,
    parent: str,
    uuids: list[str],
    *,
    key: str,
    role: str,
    visibility: str,
) -> dict:
    identifiers = list(dict.fromkeys(local_identifier(value) for value in uuids))
    return {
        "key": key,
        "role": role,
        "visibility": visibility,
        "title": title,
        "parent_folder_key": parent,
        "existing_identifier": None,
        "asset_identifiers": identifiers,
    }


def snapshot_plan(args: argparse.Namespace, plan_id: str, folders: list[dict], albums: list[dict], receipt: str) -> dict:
    source = (
        json.loads(args.source_profile.read_text(encoding="utf-8"))
        if getattr(args, "source_profile", None)
        else {
            "schema_version": 1,
            "id": args.source_id,
            "kind": "photos-album",
            "scope": "configured immutable source album",
            "actual_count": args.source_count,
            "fingerprint": None,
        }
    )
    if getattr(args, "source_profile", None):
        if int(source["actual_count"]) != int(args.source_count):
            raise ValueError(
                f"source profile count {source['actual_count']} does not match adapter source count {args.source_count}"
            )
        if source.get("catalog_identifier") and source["catalog_identifier"] != args.source_id:
            raise ValueError("source profile catalog_identifier does not match --source-id")
    source["catalog_identifier"] = args.source_id
    return {
        "operation": "snapshot-membership",
        "schema_version": 2,
        "plan_id": plan_id,
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": args.source_id,
        "expected_source_count": args.source_count,
        "source": source,
        "release_candidate": args.release_candidate,
        "helper_requirement": args.helper_requirement,
        "batch_size": args.batch_size,
        "log_path": str(args.workspace / "logs" / "jamie-photo-archive-app.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
    }


def command_snapshot_plans(args: argparse.Namespace) -> int:
    master_rows = read_csv(args.master)
    hold_rows = read_csv(args.holds)
    master_ids = [base_identifier(row["uuid"]) for row in master_rows]
    hold_ids = [base_identifier(row["uuid"]) for row in hold_rows]
    catalog_plan = json.loads(args.catalog_plan.read_text(encoding="utf-8"))
    catalog_master = next(
        (album for album in catalog_plan.get("albums", []) if album.get("role") == "editor-master"),
        None,
    )
    if catalog_master is None:
        raise ValueError("catalog plan lacks an editor-master album")
    if set(base_identifier(value) for value in catalog_master.get("asset_identifiers", [])) != set(master_ids):
        raise ValueError("catalog plan editor master differs from the supplied master")
    if not catalog_plan.get("candidate_binding"):
        raise ValueError("catalog plan lacks a passing candidate binding")
    if not catalog_plan.get("helper_requirement"):
        raise ValueError("catalog plan lacks an authorized helper requirement")
    if catalog_plan.get("release_class") != "editor-field":
        raise ValueError("catalog plan is not an editor-field release")
    args.release_candidate = {
        "catalog_plan_id": catalog_plan.get("plan_id"),
        "catalog_plan_fingerprint": canonical_json_fingerprint(catalog_plan),
        "candidate_binding": catalog_plan["candidate_binding"],
        "release_class": catalog_plan["release_class"],
    }
    args.helper_requirement = catalog_plan["helper_requirement"]
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
        [
            album(
                test_title,
                "audit",
                test_ids,
                key="write-test",
                role="write-test",
                visibility="restricted-private",
            )
        ],
        f"{args.version}-write-test-receipt.json",
    )
    production_albums = [
        album(
            f"00 MASTER — {args.target:,}",
            "version",
            master_ids,
            key="master",
            role="editor-master",
            visibility="private-editor",
        )
    ]
    for view, values in sorted(by_view.items()):
        label = view_labels.get(view, "EDITOR VIEW")
        production_albums.append(
            album(
                f"{view} {label} — {len(values):,}",
                "version",
                values,
                key=f"view-{view}",
                role="editor-view",
                visibility="private-editor",
            )
        )
    if named:
        production_albums.append(
            album(
                f"90 PEOPLE / NAMED ASSOCIATIONS — {len(named):,}",
                "version",
                named,
                key="people-context",
                role="people-context",
                visibility="private-editor",
            )
        )
    if uncertain:
        production_albums.append(
            album(
                f"91 CONTEXT UNCERTAIN — EDITOR REVIEW — {len(uncertain):,}",
                "version",
                uncertain,
                key="uncertainty",
                role="uncertainty",
                visibility="private-editor",
            )
        )
    if hold_ids:
        production_albums.append(
            album(
                f"{args.version} — AUTOMATED SAFETY HOLD — {len(hold_ids):,}",
                "private",
                hold_ids,
                key="safety-hold",
                role="safety-hold",
                visibility="restricted-private",
            )
        )
    production_albums.append(
        album(
            test_title,
            "audit",
            test_ids,
            key="write-test",
            role="write-test",
            visibility="restricted-private",
        )
    )
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
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    receipt_path = Path(plan["receipt_path"])
    if not APP.is_dir():
        raise ValueError(f"permissioned app not found: {APP}")
    with APP_PLIST.open("rb") as handle:
        bundle = plistlib.load(handle).get("CFBundleIdentifier")
    helper_profile = installed_helper_profile(bundle)
    profile_errors = validate_helper_profile(helper_profile)
    if profile_errors:
        raise ValueError(f"installed helper is incompatible: {'; '.join(profile_errors)}")
    if plan.get("operation") == "snapshot-membership":
        requirement = plan.get("helper_requirement") or {}
        if not plan.get("release_candidate"):
            raise ValueError("snapshot plan lacks an authorized release candidate")
        if helper_profile["bundle_identifier"] != requirement.get("bundle_identifier"):
            raise ValueError("installed helper bundle differs from the authorized plan")
        if helper_profile["binary_sha256"] != requirement.get("binary_sha256"):
            raise ValueError("installed helper binary differs from the authorized plan")
        missing = set(requirement.get("required_capabilities", [])) - set(helper_profile["capabilities"])
        if missing:
            raise ValueError(f"installed helper lacks authorized capabilities: {', '.join(sorted(missing))}")
    nonce = secrets.token_hex(16)
    plan_file_sha256 = file_sha256(plan_path)
    before = receipt_path.stat().st_mtime_ns if receipt_path.exists() else None
    command = [
        "/usr/bin/open",
        "-W",
        "-n",
        str(APP),
        "--args",
        "--plan",
        str(plan_path),
        "--launch-nonce",
        nonce,
    ]
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
    if receipt.get("execution_nonce") != nonce:
        raise ValueError("helper receipt does not match the bridge launch nonce")
    if receipt.get("plan_file_sha256") != plan_file_sha256:
        raise ValueError("helper receipt does not match the launched plan bytes")
    if receipt.get("source_id") != plan.get("source_album_identifier"):
        raise ValueError("helper observed a different source album than the plan")
    expected_source_count = (plan.get("source") or {}).get(
        "actual_count", plan.get("expected_source_count")
    )
    if int(receipt.get("source_count", -1)) != int(expected_source_count):
        raise ValueError("helper observed a different source count than the plan")
    if file_sha256(APP_EXECUTABLE) != helper_profile["binary_sha256"]:
        raise ValueError("helper binary changed during execution")
    source = plan.get("source") or {}
    receipt.update(
        {
            "schema_version": 1,
            "plan_fingerprint": canonical_json_fingerprint(plan),
            "source_id": source.get("id", plan.get("source_album_identifier")),
            "source_fingerprint": source.get("fingerprint"),
            "helper": {
                "bundle_identifier": helper_profile["bundle_identifier"],
                "binary_sha256": helper_profile["binary_sha256"],
            },
        }
    )
    dump_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.add_argument("--helper-profile-output", type=Path)
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
    plans.add_argument("--catalog-plan", type=Path, required=True)
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
