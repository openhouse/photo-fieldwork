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

from source_contract import SourceSpec, fallback_source, load_source, write_source


APP = Path(os.environ.get("PHOTO_FIELDWORK_APP", "/Applications/Jamie Photo Archive.app"))
APP_EXECUTABLE = APP / "Contents/MacOS/JamiePhotoArchive"
APP_PLIST = APP / "Contents/Info.plist"
BUNDLE_ID = "art.jamieburkart.jamiephotoarchive"
WORKSPACE_ROOT = Path(
    os.environ.get("PHOTO_FIELDWORK_WORKSPACE_ROOT", "/Users/jburkart/Documents/Jamie-Photo-Archive-2026")
)
INVENTORY_DB = Path(
    os.environ.get("PHOTO_FIELDWORK_INVENTORY", str(WORKSPACE_ROOT / "shared/wide-corpus.sqlite"))
)
PHOTOS_DB = Path(
    os.environ.get(
        "PHOTO_FIELDWORK_PHOTOS_DB",
        "/Volumes/apple-photos-8tb-external-ssd/Photos Library.photoslibrary/database/Photos.sqlite",
    )
)
SOURCE_ID = "360ED78F-FB05-490A-8FFD-F3CB951D0D0A/L0/040"
SOURCE_COUNT = 124_484
ROOT_FOLDER_ID = "92BBCF49-B077-478D-B9EE-DD94FAAFEAB5/L0/020"
PRIVATE_FOLDER_ID = "1095845F-B6FA-41D0-8A22-D156C3071631/L0/020"
AUDIT_FOLDER_ID = "7F9EB400-C06D-412C-9443-300A2C47CCE7/L0/020"


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def artifact_record(path: Path, workspace: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        recorded_path = str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        recorded_path = str(path.resolve())
    return {
        "path": recorded_path,
        "sha256": digest,
        "bytes": path.stat().st_size,
    }


def master_sha256(rows: list[dict[str, str]]) -> str:
    payload = [
        {
            "uuid": base_identifier(row["uuid"]),
            "assigned_view": str(row.get("assigned_view") or row.get("primary_view") or ""),
        }
        for row in rows
    ]
    payload.sort(key=lambda row: (row["assigned_view"], row["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def uuid_sha256(rows: list[dict[str, str]]) -> str:
    identifiers = sorted({base_identifier(row["uuid"]) for row in rows})
    return hashlib.sha256(("\n".join(identifiers) + "\n").encode()).hexdigest()


def update_run_phase(
    workspace: Path,
    phase: str,
    status: str,
    artifacts: list[Path] | None = None,
    **details: object,
) -> None:
    path = workspace / "run-state.json"
    if not path.exists():
        return
    state = json.loads(path.read_text(encoding="utf-8"))
    if phase not in state.get("phases", {}):
        raise ValueError(f"unknown run phase: {phase}")
    records = [artifact_record(item, workspace) for item in artifacts or []]
    state["phases"][phase] = {
        "status": status,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifacts": records,
        **details,
    }
    state["status"] = "active" if status != "blocked" else "attention-required"
    state["last_transition"] = {"phase": phase, "status": status}
    temporary = path.with_suffix(".json.tmp")
    dump_json(temporary, state)
    temporary.replace(path)


def local_identifier(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("empty asset identifier")
    return value if value.endswith("/L0/001") else f"{value.split('/', 1)[0]}/L0/001"


def base_identifier(value: str) -> str:
    return value.split("/", 1)[0]


def read_csv(path: Path, allow_empty: bool = False) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        rows = list(reader)
    if allow_empty and not rows and "uuid" in fields:
        return []
    if not rows or "uuid" not in rows[0]:
        raise ValueError(f"CSV requires uuid rows: {path}")
    return rows


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "photo-field"


def resolve_source(args: argparse.Namespace) -> SourceSpec:
    manifest = getattr(args, "source_manifest", None)
    if manifest:
        return load_source(manifest)
    return fallback_source(
        getattr(args, "source_id", SOURCE_ID),
        int(getattr(args, "source_count", SOURCE_COUNT)),
        getattr(args, "source_title", "Apple Photos source"),
    )


def decode_meta(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def helper_capabilities() -> dict:
    completed = subprocess.run(
        [str(APP_EXECUTABLE), "--capabilities"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "helper capability probe failed")
    return json.loads(completed.stdout)


def command_doctor(args: argparse.Namespace) -> int:
    source = resolve_source(args)
    inventory_db = Path(source.inventory_path) if source.inventory_path else INVENTORY_DB
    checks = {
        "permissioned_app": APP.is_dir(),
        "app_executable": APP_EXECUTABLE.is_file() and os.access(APP_EXECUTABLE, os.X_OK),
        "app_plist": APP_PLIST.is_file(),
        "source_inventory": inventory_db.exists(),
        "photos_database": PHOTOS_DB.exists(),
        "workspace_root": WORKSPACE_ROOT.is_dir(),
        "photo_fieldwork_cli": Path(
            "/Volumes/16TB_SSD/Sites/photo-fieldwork/bin/photo-fieldwork"
        ).is_file(),
    }
    bundle = None
    version = None
    inventory_meta = {}
    capabilities = {}
    if APP_PLIST.is_file():
        with APP_PLIST.open("rb") as handle:
            plist = plistlib.load(handle)
        bundle = plist.get("CFBundleIdentifier")
        version = plist.get("CFBundleShortVersionString")
        checks["stable_bundle_identifier"] = bundle == BUNDLE_ID
    if APP_EXECUTABLE.is_file() and os.access(APP_EXECUTABLE, os.X_OK):
        try:
            capabilities = helper_capabilities()
            checks["helper_schema_v2"] = 2 in capabilities.get("supported_plan_schema_versions", [])
            checks["helper_source_kind"] = source.kind in capabilities.get("supported_source_kinds", [])
        except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired):
            checks["helper_capabilities"] = False
    if inventory_db.exists():
        conn = sqlite3.connect(f"file:{inventory_db}?mode=ro&immutable=1", uri=True)
        inventory_meta = {key: decode_meta(value) for key, value in conn.execute("SELECT key, value FROM meta")}
        conn.close()
        inventory_identifier = inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid")
        inventory_count = inventory_meta.get("source_count") or inventory_meta.get("source_album_count")
        checks["inventory_source_identifier"] = str(inventory_identifier) in {
            source.identifier,
            base_identifier(source.identifier),
        }
        checks["inventory_source_count"] = int(inventory_count or 0) == source.snapshot_count
        if source.source_fingerprint:
            checks["inventory_source_fingerprint"] = (
                inventory_meta.get("source_fingerprint") == source.source_fingerprint
            )
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "capabilities": capabilities,
        "source": source.to_dict(),
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    source = resolve_source(args)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    root = (args.workspace_root / f"{args.version}-{safe_slug(args.slug)}-{stamp}").resolve()
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
        "source": source.to_dict(),
        "source_album_identifier": source.identifier,
        "expected_source_count": source.snapshot_count,
        "phases": {
            phase: {"status": "pending", "artifacts": []}
            for phase in (
                "initialize", "retrieve", "inspect", "select", "evaluate", "validate",
                "test-write", "production-write", "verify",
            )
        },
    }
    source_path = root / "source.json"
    readme_path = root / "README.md"
    write_source(source_path, source)
    readme_path.write_text(
        f"# {args.version}: {args.slug}\n\n"
        f"- Target: {args.target:,} unique still photographs\n"
        f"- Immutable source identifier: `{source.identifier}`\n"
        f"- Expected source count: {source.snapshot_count:,}\n"
        "- Final publication edit performed: no\n"
        "- External image or metadata upload permitted: no\n",
        encoding="utf-8",
    )
    state["phases"]["initialize"] = {
        "status": "complete",
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifacts": [artifact_record(source_path, root), artifact_record(readme_path, root)],
    }
    dump_json(root / "run-state.json", state)
    print(root)
    return 0


def command_inspection_plan(args: argparse.Namespace) -> int:
    source = resolve_source(args)
    rows = read_csv(args.input)
    identifiers = list(dict.fromkeys(local_identifier(row["uuid"]) for row in rows))
    if args.limit:
        identifiers = identifiers[: args.limit]
    root = args.workspace.resolve()
    plan = {
        "operation": "inspect-local-images",
        "schema_version": 2,
        "plan_id": args.plan_id,
        "safety_mode": "read-only-local-inspection-and-preview-export",
        "source_album_identifier": source.identifier,
        "source_kind": source.kind,
        "source_title": source.title,
        "source_predicate_version": source.predicate_version,
        "expected_source_count": source.snapshot_count,
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


def snapshot_plan(args: argparse.Namespace, plan_id: str, folders: list[dict], albums: list[dict], receipt: str) -> dict:
    source = resolve_source(args)
    return {
        "operation": "snapshot-membership",
        "schema_version": 2,
        "plan_id": plan_id,
        "proposal_id": args.proposal_id,
        "master_sha256": args.master_sha256,
        "audited_uuid_sha256": args.audited_uuid_sha256,
        "config_sha256": args.config_sha256,
        "evaluation": {
            "proposal_id": args.proposal_id,
            "master_sha256": args.master_sha256,
            "passed": True,
            "full_master_audit": True,
            "audited_uuid_sha256": args.audited_uuid_sha256,
        },
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": source.identifier,
        "source_kind": source.kind,
        "source_title": source.title,
        "source_predicate_version": source.predicate_version,
        "source_fingerprint": source.source_fingerprint,
        "expected_source_count": source.snapshot_count,
        "batch_size": args.batch_size,
        "log_path": str(args.workspace / "logs" / "jamie-photo-archive-app.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
    }


def command_snapshot_plans(args: argparse.Namespace) -> int:
    master_rows = read_csv(args.master)
    hold_rows = read_csv(args.holds, allow_empty=True)
    master_ids = [base_identifier(row["uuid"]) for row in master_rows]
    hold_ids = [base_identifier(row["uuid"]) for row in hold_rows]
    if len(master_ids) != args.target or len(set(master_ids)) != args.target:
        raise ValueError(f"master must contain exactly {args.target} unique IDs")
    overlap = set(master_ids) & set(hold_ids)
    if overlap:
        raise ValueError(f"master overlaps HOLD by {len(overlap)} IDs")
    if not all(row.get("selection_reason") or row.get("selection_reasons") or row.get("editorial_reasons") for row in master_rows):
        raise ValueError("every master row must have a selection reason")
    if not all(row.get("assigned_view") or row.get("primary_view") for row in master_rows):
        raise ValueError("every master row must have a reviewed assignment")
    digest = master_sha256(master_rows)
    proposal_id = f"pfp-{digest[:16]}"
    evaluation = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    if not evaluation.get("passed") or not evaluation.get("full_master_audit"):
        raise ValueError("snapshot plans require a passing full-master evaluation")
    if evaluation.get("master_sha256") != digest or evaluation.get("proposal_id") != proposal_id:
        raise ValueError("final evaluation does not match master membership and assignments")
    audited_uuid_hash = uuid_sha256(master_rows)
    if evaluation.get("audited_uuid_sha256") != audited_uuid_hash:
        raise ValueError("final evaluation does not match the master UUID set")
    args.master_sha256 = digest
    args.proposal_id = proposal_id
    args.audited_uuid_sha256 = audited_uuid_hash

    by_view: dict[str, list[str]] = {}
    view_labels = {}
    args.config_sha256 = None
    if args.config:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        view_labels = {str(view["id"]): str(view["label"]) for view in config.get("views", [])}
        args.config_sha256 = hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
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
    update_run_phase(
        args.workspace,
        "validate",
        "complete",
        artifacts=[args.master, args.holds, args.evaluation_report, test_path, production_path],
        proposal_id=proposal_id,
        master_sha256=digest,
    )
    print(f"test_plan={test_path}")
    print(f"production_plan={production_path}")
    print(f"production_albums={len(production_albums)}")
    print(f"production_memberships={sum(len(item['asset_identifiers']) for item in production_albums)}")
    return 0


def receipt_identity_errors(plan: dict, receipt: dict) -> list[str]:
    errors = []
    for field in ("plan_id", "source_album_identifier"):
        if plan.get(field) != receipt.get(field):
            errors.append(f"receipt {field} does not match launched plan")
    if int(plan.get("schema_version", 0)) != int(receipt.get("plan_schema_version", -1)):
        errors.append("receipt plan_schema_version does not match launched plan")
    if int(plan.get("expected_source_count", 0)) != int(receipt.get("source_count", -1)):
        errors.append("receipt source_count does not match launched plan")
    for field in ("execution_nonce", "reviewed_plan_sha256"):
        if not plan.get(field) or plan.get(field) != receipt.get(field):
            errors.append(f"receipt {field} does not match launched plan")
    if plan.get("operation") == "snapshot-membership":
        for field in (
            "proposal_id", "master_sha256", "audited_uuid_sha256",
            "source_fingerprint", "safety_mode",
        ):
            if plan.get(field) != receipt.get(field):
                errors.append(f"receipt {field} does not match launched plan")
        expected = {item["title"]: len(item["asset_identifiers"]) for item in plan.get("albums", [])}
        received = receipt.get("albums", [])
        received_titles = [str(item.get("title", "")) for item in received]
        if len(received_titles) != len(set(received_titles)):
            errors.append("receipt contains duplicate album titles")
        if set(received_titles) != set(expected):
            errors.append("receipt album titles do not match launched plan")
        for item in received:
            title = str(item.get("title", ""))
            if title in expected and int(item.get("count", -1)) != expected[title]:
                errors.append(f"receipt count for {title} does not match launched plan")
    return errors


def command_run_plan(args: argparse.Namespace) -> int:
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    receipt_path = Path(plan["receipt_path"])
    if not APP.is_dir():
        raise ValueError(f"permissioned app not found: {APP}")
    capabilities = helper_capabilities()
    if int(plan.get("schema_version", 0)) not in capabilities.get("supported_plan_schema_versions", []):
        raise ValueError("permissioned helper does not support this plan schema")
    source_kind = plan.get("source_kind", "album")
    if source_kind not in capabilities.get("supported_source_kinds", []):
        raise ValueError(f"permissioned helper does not support source kind {source_kind}")
    if capabilities.get("receipt_execution_binding") is not True:
        raise ValueError("permissioned helper does not support receipt execution binding")
    before = receipt_path.stat().st_mtime_ns if receipt_path.exists() else None
    operation = str(plan.get("operation", ""))
    if operation == "inspect-local-images":
        phase = "inspect"
    elif "write-test" in str(plan.get("plan_id", "")):
        phase = "test-write"
    else:
        phase = "production-write"
    workspace = (
        Path(plan["output_jsonl_path"]).parent.parent
        if operation == "inspect-local-images"
        else plan_path.parent.parent
    )
    execution_nonce = secrets.token_hex(16)
    launch_plan = {
        **plan,
        "execution_nonce": execution_nonce,
        "reviewed_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
    }
    launch_plan_path = workspace / "logs" / f"{plan.get('plan_id', 'plan')}-launch-{execution_nonce}.json"
    dump_json(launch_plan_path, launch_plan)
    command = ["/usr/bin/open", "-W", "-n", str(APP), "--args", "--plan", str(launch_plan_path)]
    print("launching permissioned helper; this may run for a long time", flush=True)
    update_run_phase(workspace, phase, "in-progress", artifacts=[plan_path, launch_plan_path])
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        update_run_phase(workspace, phase, "blocked", artifacts=[plan_path], exit_code=completed.returncode)
        raise ValueError(f"helper launcher failed with exit code {completed.returncode}")
    if not receipt_path.exists():
        update_run_phase(workspace, phase, "blocked", artifacts=[plan_path], reason="missing receipt")
        raise ValueError(f"helper finished without receipt: {receipt_path}")
    after = receipt_path.stat().st_mtime_ns
    if before is not None and before == after:
        update_run_phase(workspace, phase, "blocked", artifacts=[plan_path, receipt_path], reason="stale receipt")
        raise ValueError(f"receipt was not refreshed: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    identity_errors = receipt_identity_errors(launch_plan, receipt)
    if identity_errors:
        update_run_phase(
            workspace,
            phase,
            "blocked",
            artifacts=[plan_path, launch_plan_path, receipt_path],
            reason="; ".join(identity_errors),
        )
        raise ValueError("helper receipt identity mismatch: " + "; ".join(identity_errors))
    if plan.get("operation") == "inspect-local-images" and plan.get("export_previews"):
        root = Path(plan["output_jsonl_path"]).parent.parent
        invalid_output = root / "manifests" / f"{plan['plan_id']}-invalid-previews.csv"
        report_output = root / "reports" / f"{plan['plan_id']}-preview-verification.json"
        verifier = Path(__file__).with_name("verify_preview_exports.py")
        verified = subprocess.run(
            [
                sys.executable,
                str(verifier),
                "--inspection",
                plan["output_jsonl_path"],
                "--previews",
                plan["preview_directory"],
                "--invalid-output",
                str(invalid_output),
                "--report",
                str(report_output),
            ],
            check=False,
        )
        if verified.returncode:
            update_run_phase(root, phase, "blocked", artifacts=[plan_path, receipt_path, invalid_output, report_output])
            raise ValueError(
                f"preview integrity failed; inspect {invalid_output} and retry those assets"
            )
        phase_artifacts = [
            plan_path, launch_plan_path, receipt_path,
            Path(plan["output_jsonl_path"]), report_output,
        ]
    else:
        phase_artifacts = [plan_path, launch_plan_path, receipt_path]
    update_run_phase(
        workspace,
        phase,
        "complete",
        artifacts=phase_artifacts,
        plan_id=plan.get("plan_id"),
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


def add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--source-id", default=SOURCE_ID)
    parser.add_argument("--source-count", type=int, default=SOURCE_COUNT)
    parser.add_argument("--source-title", default="Apple Photos source")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    add_source_arguments(doctor)
    doctor.set_defaults(func=command_doctor)

    init = sub.add_parser("init-run", help="create a durable versioned run workspace")
    init.add_argument("--slug", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--target", type=int, required=True)
    init.add_argument("--workspace-root", type=Path, default=WORKSPACE_ROOT)
    add_source_arguments(init)
    init.set_defaults(func=command_init)

    inspect = sub.add_parser("inspection-plan", help="build an exact plan for local PhotoKit inspection")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    add_source_arguments(inspect)
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
    plans.add_argument("--evaluation-report", type=Path, required=True)
    add_source_arguments(plans)
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
