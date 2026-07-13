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
from datetime import datetime
from pathlib import Path


DEFAULT_PROFILE = Path(
    os.environ.get(
        "PHOTO_FIELDWORK_PROFILE",
        "~/.config/photo-fieldwork/apple-photos.json",
    )
).expanduser()
RUN_PHASES = [
    "brief",
    "retrieval",
    "local_inspection",
    "recursive_evaluation",
    "validation",
    "write_test",
    "production_commit",
    "independent_verification",
]


def load_profile(path: Path) -> dict:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ValueError(f"machine profile must not be a symlink: {expanded}")
    resolved = expanded.resolve()
    if not resolved.is_file():
        raise ValueError(
            f"machine profile not found: {resolved}; copy references/machine-profile.example.json "
            "outside the repository and fill it with local values"
        )
    if resolved.stat().st_mode & 0o077:
        raise ValueError(f"machine profile must be a non-symlink with mode 0600: {resolved}")
    profile = json.loads(resolved.read_text(encoding="utf-8"))
    required = {
        "app_path",
        "app_executable",
        "bundle_id",
        "workspace_root",
        "inventory_db",
        "photos_db",
        "photo_fieldwork_cli",
        "default_source",
        "folders",
    }
    missing = required - set(profile)
    if missing:
        raise ValueError(f"machine profile missing: {', '.join(sorted(missing))}")
    source = profile["default_source"]
    if not source.get("identifier") or int(source.get("expected_count", 0)) < 1:
        raise ValueError("default_source requires identifier and positive expected_count")
    digest = source.get("identifier_sha256")
    if digest is not None and not re.fullmatch(r"[a-f0-9]{64}", str(digest)):
        raise ValueError("default_source.identifier_sha256 must be null or lowercase SHA-256")
    if set(profile["folders"]) != {"root", "private", "audit"}:
        raise ValueError("folders must define exactly root, private, and audit")
    return profile


def profile_path(profile: dict, key: str) -> Path:
    return Path(str(profile[key])).expanduser().resolve()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def safe_workspace_file(workspace: Path, value: Path) -> Path:
    candidate = value.expanduser().absolute()
    current = candidate
    while current != workspace and workspace in current.parents:
        if current.is_symlink():
            raise ValueError(f"artifact path contains a symlink: {value}")
        current = current.parent
    resolved = candidate.resolve()
    if workspace not in resolved.parents or not resolved.is_file():
        raise ValueError(f"artifact must be a file inside the run workspace: {value}")
    return resolved


def dump_json(path: Path, value: object) -> None:
    secure_directory(path.parent)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def secure_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def secure_text(path: Path, value: str) -> None:
    secure_directory(path.parent)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


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


def master_sha256(rows: list[dict[str, str]]) -> str:
    payload = [
        {
            "uuid": str(row["uuid"]),
            "assigned_view": str(row.get("assigned_view") or row.get("primary_view") or ""),
        }
        for row in rows
    ]
    payload.sort(key=lambda row: (row["assigned_view"], row["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "photo-field"


def command_doctor(args: argparse.Namespace) -> int:
    profile = args.profile_data
    app = profile_path(profile, "app_path")
    executable = profile_path(profile, "app_executable")
    plist_path = app / "Contents/Info.plist"
    inventory_db = profile_path(profile, "inventory_db")
    photos_db = profile_path(profile, "photos_db")
    workspace_root = profile_path(profile, "workspace_root")
    cli = profile_path(profile, "photo_fieldwork_cli")
    default_source = profile["default_source"]
    checks = {
        "permissioned_app": app.is_dir(),
        "app_executable": executable.is_file() and os.access(executable, os.X_OK),
        "app_plist": plist_path.is_file(),
        "shared_inventory": inventory_db.exists(),
        "photos_database": photos_db.exists(),
        "workspace_root": workspace_root.is_dir(),
        "photo_fieldwork_cli": cli.is_file(),
        "workspace_private": workspace_root.is_dir() and workspace_root.stat().st_mode & 0o077 == 0,
    }
    bundle = None
    version = None
    inventory_meta = {}
    if plist_path.is_file():
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
        bundle = plist.get("CFBundleIdentifier")
        version = plist.get("CFBundleShortVersionString")
        checks["stable_bundle_identifier"] = bundle == profile["bundle_id"]
    if inventory_db.exists():
        conn = sqlite3.connect(f"file:{inventory_db}?mode=ro&immutable=1", uri=True)
        def decode_meta(value: str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        inventory_meta = {key: decode_meta(value) for key, value in conn.execute("SELECT key, value FROM meta")}
        conn.close()
        actual_identifier = inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid")
        expected_identifier = str(default_source["identifier"])
        checks["inventory_source_identifier"] = (
            actual_identifier == expected_identifier
            or actual_identifier == base_identifier(expected_identifier)
        )
        actual_count = inventory_meta.get("source_count") or inventory_meta.get("source_album_count")
        checks["inventory_source_count"] = int(actual_count or 0) == int(default_source["expected_count"])
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "app_binary_sha256": file_sha256(executable) if executable.is_file() else None,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
        "profile": str(args.profile.expanduser().resolve()),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    profile = args.profile_data
    workspace_root = args.workspace_root or profile_path(profile, "workspace_root")
    source_id = args.source_id or str(profile["default_source"]["identifier"])
    source_count = args.source_count if args.source_count is not None else int(profile["default_source"]["expected_count"])
    source_sha256 = getattr(args, "source_sha256", None) or profile["default_source"].get("identifier_sha256")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    root = (workspace_root / f"{args.version}-{safe_slug(args.slug)}-{stamp}").resolve()
    if root.exists():
        raise ValueError(f"workspace already exists: {root}")
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    root.chmod(0o700)
    for name in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets", "scripts"):
        directory = root / name
        directory.mkdir(mode=0o700, exist_ok=False)
        directory.chmod(0o700)
    state = {
        "schema_version": 2,
        "run_id": root.name,
        "status": "initialized",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": args.version,
        "target_count": args.target,
        "source_album_identifier": source_id,
        "expected_source_count": source_count,
        "source_identifier_sha256": source_sha256,
        "phases": {phase: {"status": "pending"} for phase in RUN_PHASES},
        "artifacts": {},
    }
    dump_json(root / "run-state.json", state)
    secure_text(
        root / "README.md",
        f"# {args.version}: {args.slug}\n\n"
        f"- Target: {args.target:,} unique still photographs\n"
        f"- Immutable source identifier: `{source_id}`\n"
        f"- Expected source count: {source_count:,}\n"
        f"- Source identifier digest: `{source_sha256 or 'not yet frozen'}`\n"
        "- Final publication edit performed: no\n"
        "- External image or metadata upload permitted: no\n",
    )
    print(root)
    return 0


def command_status(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    state_path = workspace / "run-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    issues = []
    for relative, record in state.get("artifacts", {}).items():
        try:
            path = safe_workspace_file(workspace, workspace / relative)
        except ValueError:
            issues.append(f"missing or unsafe artifact: {relative}")
            continue
        if path.stat().st_size != int(record["bytes"]) or file_sha256(path) != record["sha256"]:
            issues.append(f"artifact changed after phase completion: {relative}")
    state["artifact_integrity"] = "PASS" if not issues else "FAIL"
    state["artifact_integrity_issues"] = issues
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0 if not issues else 2


def command_advance(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    state_path = workspace / "run-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if args.phase not in RUN_PHASES:
        raise ValueError(f"unknown run phase: {args.phase}")
    phase_index = RUN_PHASES.index(args.phase)
    incomplete = [
        phase
        for phase in RUN_PHASES[:phase_index]
        if state["phases"].get(phase, {}).get("status") != "completed"
    ]
    if incomplete:
        raise ValueError(f"cannot complete {args.phase}; earlier phases pending: {', '.join(incomplete)}")
    records = []
    for value in args.artifact:
        path = safe_workspace_file(workspace, value)
        records.append(
            {
                "path": str(path.relative_to(workspace)),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    completed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    state["phases"][args.phase] = {
        "status": "completed",
        "completed_at": completed_at,
        "artifacts": [record["path"] for record in records],
    }
    for record in records:
        state.setdefault("artifacts", {})[record["path"]] = record
    state["status"] = (
        "completed" if args.phase == RUN_PHASES[-1] else f"in-progress:{RUN_PHASES[phase_index + 1]}"
    )
    dump_json(state_path, state)
    print(f"completed_phase={args.phase}")
    print(f"next_phase={RUN_PHASES[phase_index + 1] if phase_index + 1 < len(RUN_PHASES) else 'none'}")
    return 0


def command_inspection_plan(args: argparse.Namespace) -> int:
    source_id = args.source_id or str(args.profile_data["default_source"]["identifier"])
    source_count = (
        args.source_count
        if args.source_count is not None
        else int(args.profile_data["default_source"]["expected_count"])
    )
    source_sha256 = args.source_sha256 or args.profile_data["default_source"].get("identifier_sha256")
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
        "source_identifier_sha256": source_sha256,
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


def folder_specs(profile: dict, version_title: str, include_version: bool) -> list[dict]:
    protected = profile["folders"]
    folders = [
        {
            "key": "root",
            "title": protected["root"]["title"],
            "parent_key": None,
            "existing_identifier": protected["root"].get("identifier"),
        },
        {
            "key": "private",
            "title": protected["private"]["title"],
            "parent_key": "root",
            "existing_identifier": protected["private"].get("identifier"),
        },
        {
            "key": "audit",
            "title": protected["audit"]["title"],
            "parent_key": "root",
            "existing_identifier": protected["audit"].get("identifier"),
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


def album(title: str, parent: str, uuids: list[str], safety_role: str = "editor") -> dict:
    identifiers = list(dict.fromkeys(local_identifier(value) for value in uuids))
    return {
        "title": title,
        "parent_folder_key": parent,
        "existing_identifier": None,
        "asset_identifiers": identifiers,
        "safety_role": safety_role,
    }


def snapshot_plan(args: argparse.Namespace, plan_id: str, folders: list[dict], albums: list[dict], receipt: str) -> dict:
    return {
        "operation": "snapshot-membership",
        "schema_version": 1,
        "plan_id": plan_id,
        "proposal_id": args.proposal_id,
        "master_sha256": args.master_sha256,
        "evaluation": {
            "proposal_id": args.proposal_id,
            "master_sha256": args.master_sha256,
            "passed": True,
        },
        "hold_asset_identifiers": args.hold_ids,
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": args.source_id,
        "expected_source_count": args.source_count,
        "source_identifier_sha256": args.source_sha256,
        "batch_size": args.batch_size,
        "log_path": str(args.workspace / "logs" / "jamie-photo-archive-app.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
    }


def command_snapshot_plans(args: argparse.Namespace) -> int:
    source_id = args.source_id or str(args.profile_data["default_source"]["identifier"])
    source_count = (
        args.source_count
        if args.source_count is not None
        else int(args.profile_data["default_source"]["expected_count"])
    )
    source_sha256 = args.source_sha256 or args.profile_data["default_source"].get("identifier_sha256")
    args.source_id = source_id
    args.source_count = source_count
    args.source_sha256 = source_sha256
    master_rows = read_csv(args.master)
    hold_rows = read_csv(args.holds)
    master_ids = [base_identifier(row["uuid"]) for row in master_rows]
    hold_ids = [base_identifier(row["uuid"]) for row in hold_rows]
    args.hold_ids = [local_identifier(value) for value in hold_ids]
    if len(master_ids) != args.target or len(set(master_ids)) != args.target:
        raise ValueError(f"master must contain exactly {args.target} unique IDs")
    overlap = set(master_ids) & set(hold_ids)
    if overlap:
        raise ValueError(f"master overlaps HOLD by {len(overlap)} IDs")
    if not all(row.get("selection_reason") or row.get("selection_reasons") or row.get("editorial_reasons") for row in master_rows):
        raise ValueError("every master row must have a selection reason")
    digest = master_sha256(master_rows)
    proposal_id = f"pfp-{digest[:16]}"
    evaluation = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    if not evaluation.get("passed"):
        raise ValueError("snapshot plans require a passing final evaluation")
    if evaluation.get("master_sha256") != digest or evaluation.get("proposal_id") != proposal_id:
        raise ValueError("final evaluation does not match exact master membership and assignments")
    args.master_sha256 = digest
    args.proposal_id = proposal_id

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
        folder_specs(args.profile_data, args.folder_title, include_version=False),
        [album(test_title, "audit", test_ids, safety_role="audit")],
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
        production_albums.append(
            album(
                f"{args.version} — AUTOMATED SAFETY HOLD — {len(hold_ids):,}",
                "private",
                hold_ids,
                safety_role="hold",
            )
        )
    production_albums.append(album(test_title, "audit", test_ids, safety_role="audit"))
    production = snapshot_plan(
        args,
        f"{args.version}-production",
        folder_specs(args.profile_data, args.folder_title, include_version=True),
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
    app = profile_path(args.profile_data, "app_path")
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    receipt_path = Path(plan["receipt_path"])
    if not app.is_dir():
        raise ValueError(f"permissioned app not found: {app}")
    before = receipt_path.stat().st_mtime_ns if receipt_path.exists() else None
    preserved = None
    if receipt_path.exists():
        history = receipt_path.parent / "receipt-history"
        secure_directory(history)
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        preserved = history / f"{receipt_path.stem}-{stamp}{receipt_path.suffix}"
        shutil.copy2(receipt_path, preserved)
        preserved.chmod(0o600)
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
    receipt["execution_fingerprint"] = {
        "app_bundle_identifier": args.profile_data["bundle_id"],
        "app_binary_sha256": file_sha256(profile_path(args.profile_data, "app_executable")),
        "plan_sha256": file_sha256(plan_path),
    }
    dump_json(receipt_path, receipt)
    if preserved:
        print(f"preserved_receipt={preserved}")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.set_defaults(func=command_doctor)

    init = sub.add_parser("init-run", help="create a durable versioned run workspace")
    init.add_argument("--slug", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--target", type=int, required=True)
    init.add_argument("--workspace-root", type=Path)
    init.add_argument("--source-id")
    init.add_argument("--source-count", type=int)
    init.add_argument("--source-sha256")
    init.set_defaults(func=command_init)

    status = sub.add_parser("status", help="show durable run state and artifact ledger")
    status.add_argument("--workspace", type=Path, required=True)
    status.set_defaults(func=command_status)

    advance = sub.add_parser("advance", help="complete one ordered run phase with hashed artifacts")
    advance.add_argument("--workspace", type=Path, required=True)
    advance.add_argument("--phase", choices=RUN_PHASES, required=True)
    advance.add_argument("--artifact", type=Path, action="append", default=[])
    advance.set_defaults(func=command_advance)

    inspect = sub.add_parser("inspection-plan", help="build an exact plan for local PhotoKit inspection")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    inspect.add_argument("--source-id")
    inspect.add_argument("--source-count", type=int)
    inspect.add_argument("--source-sha256")
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
    plans.add_argument("--source-id")
    plans.add_argument("--source-count", type=int)
    plans.add_argument("--source-sha256")
    plans.add_argument("--batch-size", type=int, default=500)
    plans.set_defaults(func=command_snapshot_plans)

    run = sub.add_parser("run-plan", help="launch a plan through the stable permissioned app bundle")
    run.add_argument("--plan", type=Path, required=True)
    run.set_defaults(func=command_run_plan)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command in {"doctor", "init-run", "inspection-plan", "snapshot-plans", "run-plan"}:
            args.profile_data = load_profile(args.profile)
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
