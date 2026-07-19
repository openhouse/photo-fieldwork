#!/usr/bin/env python3
"""Bridge Photo Fieldwork manifests to a profile-selected permissioned Photos app."""

from __future__ import annotations

import argparse
import csv
import json
import os
import plistlib
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from photo_fieldwork.pipeline import content_sha256, master_sha256


DEFAULT_PROFILE = Path(
    os.environ.get("PHOTO_FIELDWORK_PROFILE", "~/.config/photo-fieldwork/profile.json")
).expanduser()


def load_profile(path: Path | None) -> dict:
    profile_path = (path or DEFAULT_PROFILE).expanduser()
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(
            f"machine profile not found: {profile_path}; copy config/machine-profile.example.json"
        ) from error
    if profile.get("schema_version") != 1:
        raise ValueError("machine profile requires schema_version 1")
    default_source = profile.get("default_source")
    if default_source not in profile.get("sources", {}):
        raise ValueError("machine profile default_source is not configured")
    return profile


def source_values(args: argparse.Namespace, profile: dict) -> tuple[str, int]:
    key = args.source_key or profile["default_source"]
    try:
        source = profile["sources"][key]
    except KeyError as error:
        raise ValueError(f"unknown profile source: {key}") from error
    identifier = args.source_id or source["identifier"]
    count = args.source_count if args.source_count is not None else source.get("expected_count")
    if count is None:
        raise ValueError(f"profile source {key} requires an expected_count for this operation")
    return str(identifier), int(count)


def profile_path(profile: dict, key: str) -> Path:
    value = profile.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"machine profile requires {key}")
    return Path(value).expanduser()


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


def command_doctor(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    app = Path(profile["helper"]["app_path"]).expanduser()
    executable_directory = app / "Contents/MacOS"
    app_executables = [
        path for path in executable_directory.iterdir()
        if path.is_file() and os.access(path, os.X_OK)
    ] if executable_directory.is_dir() else []
    app_plist = app / "Contents/Info.plist"
    bundle_id = profile["helper"]["bundle_id"]
    workspace_root = profile_path(profile, "workspace_root")
    photos_db = profile_path(profile, "photos_database")
    source_key = args.source_key or profile["default_source"]
    source = profile["sources"][source_key]
    inventory_db = Path(source["inventory_db"]).expanduser() if source.get("inventory_db") else None
    source_id, source_count = source_values(args, profile)
    checks = {
        "permissioned_app": app.is_dir(),
        "app_executable": len(app_executables) == 1,
        "app_plist": app_plist.is_file(),
        "shared_inventory": bool(inventory_db and inventory_db.exists()),
        "photos_database": photos_db.exists(),
        "workspace_root": workspace_root.is_dir(),
        "writer_adapter_configured": profile.get("default_writer_adapter", "photokit") in {"photokit", "applescript"},
    }
    if profile.get("default_writer_adapter") == "applescript":
        script_value = profile.get("applescript_writer")
        checks["applescript_writer_exists"] = bool(
            script_value and Path(script_value).expanduser().is_file()
        )
    bundle = None
    version = None
    inventory_meta = {}
    if app_plist.is_file():
        with app_plist.open("rb") as handle:
            plist = plistlib.load(handle)
        bundle = plist.get("CFBundleIdentifier")
        version = plist.get("CFBundleShortVersionString")
        checks["stable_bundle_identifier"] = bundle == bundle_id
    if inventory_db and inventory_db.exists():
        conn = sqlite3.connect(f"file:{inventory_db}?mode=ro&immutable=1", uri=True)
        inventory_meta = {}
        for key, value in conn.execute("SELECT key, value FROM meta"):
            try:
                inventory_meta[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                inventory_meta[key] = value
        conn.close()
        inventory_identifier = inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid")
        inventory_count = inventory_meta.get("source_count") or inventory_meta.get("source_album_count")
        checks["inventory_source_identifier"] = inventory_identifier in {source_id, base_identifier(source_id)}
        checks["inventory_source_count"] = int(inventory_count or 0) == source_count
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
        "profile": profile.get("name"),
        "source_key": source_key,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    source_id, source_count = source_values(args, profile)
    workspace_root = args.workspace_root or profile_path(profile, "workspace_root")
    try:
        from photo_fieldwork.runstate import init_run
    except ImportError as error:
        raise ValueError("install the photo-fieldwork package before initializing a run") from error
    root = init_run(
        workspace_root,
        args.version,
        args.slug,
        args.target,
        source_id,
        source_count,
        args.code_commit,
        args.parent_run,
    )
    print(root)
    return 0


def command_probe(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    source_id, source_count = source_values(args, profile)
    app = Path(profile["helper"]["app_path"]).expanduser()
    workspace = profile_path(profile, "workspace_root") / ".photo-fieldwork" / "probes"
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    plan_path = workspace / f"probe-{stamp}.json"
    receipt_path = workspace / f"probe-{stamp}-receipt.json"
    dump_json(
        plan_path,
        {
            "operation": "probe-photos-access",
            "schema_version": 1,
            "plan_id": f"photos-access-probe-{stamp}",
            "source_album_identifier": source_id,
            "expected_source_count": source_count,
            "receipt_path": str(receipt_path),
            "network_access_allowed": False,
        },
    )
    if not app.is_dir():
        raise ValueError(f"permissioned app not found: {app}")
    completed = subprocess.run(
        ["/usr/bin/open", "-W", "-n", str(app), "--args", "--plan", str(plan_path)],
        check=False,
    )
    if completed.returncode or not receipt_path.exists():
        raise ValueError("operational Photos authorization probe failed")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("helper_capability_version", 0) < 2:
        raise ValueError("installed helper does not support capability version 2")
    print(json.dumps(receipt, indent=2))
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
        "log_path": str(root / "logs" / "photo-fieldwork-helper.log"),
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


def folder_specs(version_title: str, include_version: bool, profile: dict) -> list[dict]:
    protected = profile["protected_folders"]
    folders = [
        {
            "key": "root",
            "title": protected["root"]["title"],
            "parent_key": None,
            "existing_identifier": protected["root"]["identifier"],
        },
        {
            "key": "private",
            "title": protected["private"]["title"],
            "parent_key": "root",
            "existing_identifier": protected["private"]["identifier"],
        },
        {
            "key": "audit",
            "title": protected["audit"]["title"],
            "parent_key": "root",
            "existing_identifier": protected["audit"]["identifier"],
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


def release_binding(
    release_plan_path: Path,
    master_rows: list[dict[str, str]],
    source_id: str,
    source_count: int,
) -> dict:
    plan = json.loads(release_plan_path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 2:
        raise ValueError("release plan requires schema_version 2")
    if plan.get("plan_sha256") != content_sha256(plan):
        raise ValueError("release plan content does not match plan_sha256")
    digest = master_sha256(master_rows)
    if plan.get("master_sha256") != digest:
        raise ValueError("release plan master identity does not match the bridge master")
    proposal_id = f"pfp-{digest[:16]}"
    if plan.get("proposal_id") != proposal_id:
        raise ValueError("release plan proposal identity does not match the bridge master")
    evaluation = plan.get("evaluation", {})
    if (
        evaluation.get("passed") is not True
        or evaluation.get("final_field_audit") is not True
        or evaluation.get("proposal_id") != proposal_id
        or evaluation.get("master_sha256") != digest
    ):
        raise ValueError("release plan evaluation binding is invalid")
    validation = plan.get("validation", {})
    if (
        validation.get("status") != "PASS"
        or validation.get("proposal_id") != proposal_id
        or validation.get("master_sha256") != digest
    ):
        raise ValueError("release plan validation binding is invalid")
    for label, value in (
        ("source membership", plan.get("source", {}).get("membership_sha256", "")),
        ("evaluation report", evaluation.get("report_sha256", "")),
        ("validation report", validation.get("report_sha256", "")),
    ):
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.casefold()):
            raise ValueError(f"release plan {label} SHA-256 is invalid")
    if plan.get("source", {}).get("identifier") != source_id:
        raise ValueError("release plan source identifier does not match the bridge source")
    if plan.get("source", {}).get("count") != source_count:
        raise ValueError("release plan source count does not match the bridge source")
    if plan.get("expected_master_count") != len(master_rows):
        raise ValueError("release plan master count does not match the bridge master")
    master_album = next(
        (album for album in plan.get("albums", []) if album.get("key") == "master"),
        None,
    )
    expected_ids = sorted(base_identifier(row["uuid"]) for row in master_rows)
    planned_ids = sorted(
        base_identifier(value)
        for value in (master_album or {}).get("asset_ids", [])
    )
    if planned_ids != expected_ids:
        raise ValueError("release plan master album does not match the bridge master")
    return {
        "release_plan_id": plan["plan_id"],
        "release_plan_sha256": plan["plan_sha256"],
        "proposal_id": proposal_id,
        "master_sha256": plan["master_sha256"],
        "source_membership_sha256": plan["source"]["membership_sha256"],
        "evaluation_report_sha256": evaluation["report_sha256"],
        "validation_report_sha256": validation["report_sha256"],
    }


def snapshot_plan(
    args: argparse.Namespace,
    plan_id: str,
    folders: list[dict],
    albums: list[dict],
    receipt: str,
    source_id: str,
    source_count: int,
    binding: dict,
) -> dict:
    return {
        "operation": "snapshot-membership",
        "schema_version": 1,
        "plan_id": plan_id,
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": source_id,
        "expected_source_count": source_count,
        "release_binding": binding,
        "batch_size": args.batch_size,
        "log_path": str(args.workspace / "logs" / "photo-fieldwork-helper.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
    }


def command_snapshot_plans(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    source_id, source_count = source_values(args, profile)
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
    binding = release_binding(args.release_plan, master_rows, source_id, source_count)

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
        source_id,
        source_count,
        binding,
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
        source_id,
        source_count,
        binding,
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
    app = Path(profile["helper"]["app_path"]).expanduser()
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    receipt_path = Path(plan["receipt_path"])
    adapter = args.adapter or profile.get("default_writer_adapter", "photokit")
    before = receipt_path.stat().st_mtime_ns if receipt_path.exists() else None
    if adapter == "photokit":
        if not app.is_dir():
            raise ValueError(f"permissioned app not found: {app}")
        command = ["/usr/bin/open", "-W", "-n", str(app), "--args", "--plan", str(plan_path)]
    elif adapter == "applescript":
        script_value = profile.get("applescript_writer")
        if not script_value:
            raise ValueError("applescript adapter selected without applescript_writer in profile")
        script = Path(script_value).expanduser()
        if not script.is_file():
            raise ValueError(f"AppleScript writer not found: {script}")
        command = ["/usr/bin/osascript", str(script), str(plan_path)]
    else:
        raise ValueError(f"unsupported writer adapter: {adapter}")
    print(f"launching {adapter} writer adapter; this may run for a long time", flush=True)
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

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.add_argument("--profile", type=Path)
    doctor.add_argument("--source-key")
    doctor.add_argument("--source-id")
    doctor.add_argument("--source-count", type=int)
    doctor.set_defaults(func=command_doctor)

    probe = sub.add_parser("probe", help="run a read-only operational Photos authorization probe")
    probe.add_argument("--profile", type=Path)
    probe.add_argument("--source-key")
    probe.add_argument("--source-id")
    probe.add_argument("--source-count", type=int)
    probe.set_defaults(func=command_probe)

    init = sub.add_parser("init-run", help="create a durable versioned run workspace")
    init.add_argument("--slug", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--target", type=int, required=True)
    init.add_argument("--profile", type=Path)
    init.add_argument("--workspace-root", type=Path)
    init.add_argument("--source-key")
    init.add_argument("--source-id")
    init.add_argument("--source-count", type=int)
    init.add_argument("--code-commit")
    init.add_argument("--parent-run")
    init.set_defaults(func=command_init)

    inspect = sub.add_parser("inspection-plan", help="build an exact plan for local PhotoKit inspection")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    inspect.add_argument("--profile", type=Path)
    inspect.add_argument("--source-key")
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
    plans.add_argument("--source-key")
    plans.add_argument("--source-id")
    plans.add_argument("--source-count", type=int)
    plans.add_argument("--release-plan", type=Path, required=True)
    plans.add_argument("--batch-size", type=int, default=500)
    plans.set_defaults(func=command_snapshot_plans)

    run = sub.add_parser("run-plan", help="launch a plan through the stable permissioned app bundle")
    run.add_argument("--profile", type=Path)
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--adapter", choices=("photokit", "applescript"))
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
