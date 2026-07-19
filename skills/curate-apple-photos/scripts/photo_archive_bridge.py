#!/usr/bin/env python3
"""Bridge Photo Fieldwork manifests to the permissioned Jamie Photo Archive app."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from photo_fieldwork.contracts import (  # noqa: E402
    canonical_sha256,
    finalize_plan,
    identifier_set_sha256,
    load_source_manifest,
    plan_sha256,
    validate_plan,
)
from photo_fieldwork.pipeline import validate as validate_master  # noqa: E402


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
RUN_PHASES = (
    "brief",
    "retrieval",
    "local_inspection",
    "recursive_evaluation",
    "validation",
    "write_test",
    "production_commit",
    "independent_verification",
)
PHASE_STATUSES = {"pending", "running", "interrupted", "failed", "completed", "stale", "verified"}
HELPER_REVISION = "revision-B"


def load_profile(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    profile = json.loads(path.read_text(encoding="utf-8"))
    if int(profile.get("schema_version", 0)) != 1:
        raise ValueError("local profile schema_version must be 1")
    return profile


def profile_path(profile: dict[str, object], key: str, default: Path) -> Path:
    return Path(str(profile.get(key) or default)).expanduser()


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


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
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _last_event(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    previous_hash = None
    previous_revision = 0
    last = None
    for line in lines:
        event = json.loads(line)
        supplied_hash = event.get("event_sha256")
        payload = dict(event)
        payload.pop("event_sha256", None)
        if supplied_hash != canonical_sha256(payload):
            raise ValueError("run event ledger contains an invalid event hash")
        if int(event.get("previous_revision", -1)) != previous_revision:
            raise ValueError("run event ledger contains a revision gap")
        if int(event.get("revision", -1)) != previous_revision + 1:
            raise ValueError("run event ledger contains an invalid revision")
        if event.get("previous_event_sha256") != previous_hash:
            raise ValueError("run event ledger contains a broken hash chain")
        previous_hash = supplied_hash
        previous_revision = int(event["revision"])
        last = event
    return last


def update_run_state(
    workspace: Path,
    phase: str,
    status: str,
    *,
    expected_revision: int | None = None,
    actor: str = "photo_archive_bridge",
    **details: object,
) -> None:
    state_path = workspace / "run-state.json"
    if not state_path.exists():
        return
    lock_path = workspace / "run-state.lock"
    event_path = workspace / "run-events.jsonl"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        last_event = _last_event(event_path)
        state_revision = int(state.get("revision", 0))
        state_event = state.get("last_event_sha256")
        if last_event and int(last_event["revision"]) == state_revision + 1:
            if (
                int(last_event["previous_revision"]) == state_revision
                and last_event.get("previous_event_sha256") == state_event
            ):
                recovered = last_event.get("state_after")
                if not isinstance(recovered, dict):
                    raise ValueError("run event cannot recover interrupted state write")
                state = dict(recovered)
                state["last_event_sha256"] = last_event["event_sha256"]
                state_revision = int(state["revision"])
                state_event = last_event["event_sha256"]
                temporary = state_path.with_suffix(".json.tmp")
                dump_json(temporary, state)
                temporary.replace(state_path)
            else:
                raise ValueError("run event ledger diverges from durable state")
        elif last_event and last_event.get("event_sha256") != state_event:
            raise ValueError("run event ledger diverges from durable state")
        elif not last_event and state_event:
            raise ValueError("run state references a missing event ledger")
        if expected_revision is not None and expected_revision != state_revision:
            raise ValueError(
                f"stale run-state revision: expected {expected_revision}, found {state_revision}"
            )
        if phase not in state.get("phases", {}):
            raise ValueError(f"unknown run phase: {phase}")
        if status not in PHASE_STATUSES:
            raise ValueError(f"unknown phase status: {status}")
        state["phases"][phase] = status
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        records = state.setdefault("phase_records", {})
        previous = dict(records.get(phase, {}))
        attempts = int(previous.get("attempts", 0)) + (1 if status == "running" else 0)
        records[phase] = {
            **previous,
            "status": status,
            "updated_at": now,
            "attempts": attempts,
            **details,
        }
        phase_values = set(state["phases"].values())
        if "failed" in phase_values:
            state["status"] = "failed"
        elif "interrupted" in phase_values:
            state["status"] = "interrupted"
        elif all(value in {"completed", "verified"} for value in phase_values):
            state["status"] = "complete"
        else:
            state["status"] = "active"
        state["updated_at"] = now
        state["last_transition"] = {"phase": phase, "status": status, **details}
        state["next_actions"] = next_actions(state)
        state["revision"] = state_revision + 1
        state_after = dict(state)
        state_after.pop("last_event_sha256", None)
        event = {
            "schema_version": 1,
            "run_id": state.get("run_id"),
            "revision": state["revision"],
            "previous_revision": state_revision,
            "previous_event_sha256": state_event,
            "occurred_at": now,
            "actor": actor,
            "phase": phase,
            "status": status,
            "details": details,
            "state_after": state_after,
        }
        event["event_sha256"] = canonical_sha256(event)
        with event_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            ledger.flush()
            os.fsync(ledger.fileno())
        event_path.chmod(0o600)
        state["last_event_sha256"] = event["event_sha256"]
        temporary = state_path.with_suffix(".json.tmp")
        dump_json(temporary, state)
        temporary.replace(state_path)


def next_actions(state: dict[str, object]) -> list[str]:
    phases = state.get("phases", {})
    if not isinstance(phases, dict):
        return []
    for phase in RUN_PHASES:
        status = str(phases.get(phase, "pending"))
        if status in {"failed", "interrupted", "stale"}:
            return [f"resume or retry {phase}"]
        if status not in {"completed", "verified"}:
            return [f"complete {phase}"]
    return ["run completion-report generation"]


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
    app = profile_path(profile, "permissioned_app", APP)
    app_executable = app / "Contents/MacOS/JamiePhotoArchive"
    app_plist = app / "Contents/Info.plist"
    inventory_db = profile_path(profile, "inventory_db", args.inventory_db)
    photos_db = profile_path(profile, "photos_db", args.photos_db)
    workspace_root = profile_path(profile, "workspace_root", args.workspace_root)
    expected_bundle = str(profile.get("bundle_identifier") or BUNDLE_ID)
    checks = {
        "permissioned_app": app.is_dir(),
        "app_executable": app_executable.is_file() and os.access(app_executable, os.X_OK),
        "app_plist": app_plist.is_file(),
        "shared_inventory": inventory_db.exists(),
        "photos_database": photos_db.exists(),
        "workspace_root": workspace_root.is_dir(),
        "photo_fieldwork_cli": (REPOSITORY_ROOT / "bin" / "photo-fieldwork").is_file(),
    }
    try:
        import PIL  # noqa: F401
        checks["review_dependency_pillow"] = True
    except ImportError:
        checks["review_dependency_pillow"] = False
    bundle = None
    version = None
    revision = None
    capabilities = {}
    inventory_meta = {}
    if app_plist.is_file():
        with app_plist.open("rb") as handle:
            plist = plistlib.load(handle)
        bundle = plist.get("CFBundleIdentifier")
        version = plist.get("CFBundleShortVersionString")
        revision = plist.get("PhotoFieldworkRevision")
        checks["stable_bundle_identifier"] = bundle == expected_bundle
    if checks["app_executable"]:
        completed = subprocess.run(
            [str(app_executable), "--capabilities"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            try:
                capabilities = json.loads(completed.stdout)
            except json.JSONDecodeError:
                capabilities = {}
        checks["helper_inspection_schema"] = capabilities.get("inspection_plan_schema") == 2
        checks["helper_snapshot_schema"] = capabilities.get("snapshot_plan_schema") == 2
        checks["helper_network_boundary"] = capabilities.get("network_access_allowed") is False
        checks["helper_revision"] = capabilities.get("photo_fieldwork_revision") == HELPER_REVISION
    if inventory_db.exists():
        conn = sqlite3.connect(f"file:{inventory_db}?mode=ro&immutable=1", uri=True)
        inventory_meta = {}
        for key, value in conn.execute("SELECT key, value FROM meta"):
            try:
                inventory_meta[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                inventory_meta[key] = value
        conn.close()
        if args.source_manifest:
            source = load_source_manifest(args.source_manifest)
            inventory_identifier = inventory_meta.get("source_identifier") or inventory_meta.get("source_album_uuid")
            inventory_count = inventory_meta.get("source_count") or inventory_meta.get("source_album_count")
            checks["inventory_source_identifier"] = str(inventory_identifier) == base_identifier(str(source["source_identifier"])) or str(inventory_identifier) == str(source["source_identifier"])
            checks["inventory_source_count"] = int(inventory_count or 0) == int(source["observed_count"])
            checks["inventory_source_fingerprint"] = str(inventory_meta.get("source_fingerprint", "")) == str(source["source_fingerprint"])
        else:
            checks["inventory_source_identifier"] = inventory_meta.get("source_album_uuid") == base_identifier(SOURCE_ID)
            checks["inventory_source_count"] = int(inventory_meta.get("source_album_count", 0)) == SOURCE_COUNT
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "revision": revision,
        "capabilities": capabilities,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
        "source_manifest": str(args.source_manifest) if args.source_manifest else None,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    source = load_source_manifest(args.source_manifest)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    workspace_root = profile_path(profile, "workspace_root", args.workspace_root)
    root = (workspace_root / f"{args.version}-{safe_slug(args.slug)}-{stamp}").resolve()
    if root.exists():
        raise ValueError(f"workspace already exists: {root}")
    for name in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets", "scripts"):
        (root / name).mkdir(parents=True, exist_ok=False, mode=0o700)
    state = {
        "schema_version": 1,
        "run_id": root.name,
        "status": "initialized",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version": args.version,
        "target_count": args.target,
        "source_identifier": source["source_identifier"],
        "source_fingerprint": source["source_fingerprint"],
        "expected_source_count": source["observed_count"],
        "source_manifest": str(args.source_manifest.resolve()),
        "phases": {phase: "pending" for phase in RUN_PHASES},
        "phase_records": {},
        "revision": 0,
        "last_event_sha256": None,
    }
    state["next_actions"] = next_actions(state)
    dump_json(root / "run-state.json", state)
    (root / "README.md").write_text(
        f"# {args.version}: {args.slug}\n\n"
        f"- Target: {args.target:,} unique still photographs\n"
        f"- Immutable source identifier: `{source['source_identifier']}`\n"
        f"- Source fingerprint: `{source['source_fingerprint']}`\n"
        f"- Expected source count: {int(source['observed_count']):,}\n"
        "- Final publication edit performed: no\n"
        "- External image or metadata upload permitted: no\n",
        encoding="utf-8",
    )
    print(root)
    return 0


def command_inspection_plan(args: argparse.Namespace) -> int:
    rows = read_csv(args.input)
    source = load_source_manifest(args.source_manifest)
    identifiers = list(dict.fromkeys(local_identifier(row["uuid"]) for row in rows))
    if args.limit:
        identifiers = identifiers[: args.limit]
    root = args.workspace.resolve()
    plan = {
        "operation": "inspect-local-images",
        "schema_version": 2,
        "plan_id": args.plan_id,
        "required_helper_revision": HELPER_REVISION,
        "source": source,
        "source_fingerprint": source["source_fingerprint"],
        "safety_mode": "read-only-local-inspection-and-preview-export",
        "source_album_identifier": source["source_identifier"],
        "expected_source_count": source["observed_count"],
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
    plan = finalize_plan(plan)
    dump_json(args.output, plan)
    print(f"inspection_assets={len(identifiers)}")
    print(f"plan={args.output}")
    return 0


def folder_specs(version_title: str, include_version: bool, profile: dict[str, object] | None = None) -> list[dict]:
    profile = profile or {}
    folders = [
        {
            "key": "root",
            "title": "JAMIE PHOTO EDIT — 2026",
            "parent_key": None,
            "existing_identifier": str(profile.get("root_folder_identifier") or ROOT_FOLDER_ID),
        },
        {
            "key": "private",
            "title": "90 PRIVATE REVIEW — DO NOT SHARE",
            "parent_key": "root",
            "existing_identifier": str(profile.get("private_folder_identifier") or PRIVATE_FOLDER_ID),
        },
        {
            "key": "audit",
            "title": "99 WRITE TESTS / AUDIT",
            "parent_key": "root",
            "existing_identifier": str(profile.get("audit_folder_identifier") or AUDIT_FOLDER_ID),
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


def album(key: str, title: str, parent: str, uuids: list[str]) -> dict:
    identifiers = list(dict.fromkeys(local_identifier(value) for value in uuids))
    return {
        "key": key,
        "title": title,
        "parent_folder_key": parent,
        "existing_identifier": None,
        "asset_identifiers": identifiers,
    }


def snapshot_plan(args: argparse.Namespace, plan_id: str, folders: list[dict], albums: list[dict], receipt: str) -> dict:
    plan = {
        "operation": "snapshot-membership",
        "schema_version": 2,
        "plan_id": plan_id,
        "required_helper_revision": HELPER_REVISION,
        "proposal_id": args.proposal_id,
        "master_sha256": args.master_sha256,
        "hold_sha256": args.hold_sha256,
        "config_sha256": args.config_sha256,
        "source": args.source_manifest_data,
        "source_fingerprint": args.source_manifest_data["source_fingerprint"],
        "release_class": args.release_class,
        "evaluation": args.evaluation_report_data,
        "evaluation_report_sha256": canonical_sha256(args.evaluation_report_data),
        "validation": args.validation_report_data,
        "validation_report_sha256": canonical_sha256(args.validation_report_data),
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source_album_identifier": args.source_manifest_data["source_identifier"],
        "expected_source_count": args.source_manifest_data["observed_count"],
        "batch_size": args.batch_size,
        "log_path": str(args.workspace / "logs" / "jamie-photo-archive-app.log"),
        "receipt_path": str(args.workspace / "manifests" / receipt),
        "folders": folders,
        "albums": albums,
    }
    return finalize_plan(plan)


def command_snapshot_plans(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    source_manifest = load_source_manifest(args.source_manifest)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    config_digest = canonical_sha256(config)
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
    if any(
        row.get("assigned_view")
        and row.get("primary_view")
        and row["assigned_view"] != row["primary_view"]
        for row in master_rows
    ):
        raise ValueError("primary_view must match assigned_view before snapshot plan generation")
    digest = master_sha256(master_rows)
    hold_digest = identifier_set_sha256(hold_ids)
    proposal_id = f"pfp-{digest[:16]}"
    evaluation = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    if not evaluation.get("passed"):
        raise ValueError("snapshot plans require a passing final evaluation")
    if evaluation.get("master_sha256") != digest or evaluation.get("proposal_id") != proposal_id:
        raise ValueError("final evaluation does not match the master membership and assignments")
    if not evaluation.get("master_bound"):
        raise ValueError("snapshot plans require evaluation bound to the exact master")
    if not evaluation.get("source_bound") or evaluation.get("source_fingerprint") != source_manifest["source_fingerprint"]:
        raise ValueError("snapshot plans require evaluation bound to this source manifest")
    if evaluation.get("config_sha256") != config_digest:
        raise ValueError("snapshot plans require the exact evaluated configuration")
    release_class = str(evaluation.get("release_class") or "")
    if not release_class:
        raise ValueError("snapshot plans require a qualified release class")
    args.master_sha256 = digest
    args.hold_sha256 = hold_digest
    args.proposal_id = proposal_id
    args.release_class = release_class
    args.evaluation_report_data = evaluation
    args.source_manifest_data = source_manifest
    args.config_sha256 = config_digest

    by_view: dict[str, list[str]] = {}
    view_labels = {}
    view_labels = {str(view["id"]): str(view["label"]) for view in config.get("views", [])}
    eligible_states = {
        str(value).strip().lower()
        for value in config.get("eligible_safety_states", ["clear", "clear-automated", "cleared-human"])
    }
    unsafe = [
        row["uuid"]
        for row in master_rows
        if str(row.get("safety_status", "clear-automated")).strip().lower() not in eligible_states
    ]
    if unsafe:
        raise ValueError(f"snapshot master contains {len(unsafe)} ineligible safety states")
    validation_errors, validation_report = validate_master(master_rows, hold_rows, config)
    if validation_errors:
        raise ValueError("snapshot plans require a passing exact-master validation")
    args.validation_report_data = validation_report
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
        [album("write-test", test_title, "audit", test_ids)],
        f"{args.version}-write-test-receipt.json",
    )
    production_albums = [album("master", f"00 MASTER — {args.target:,}", "version", master_ids)]
    for view, values in sorted(by_view.items()):
        label = view_labels.get(view, "EDITOR VIEW")
        production_albums.append(album(f"view-{view}", f"{view} {label} — {len(values):,}", "version", values))
    if named:
        production_albums.append(album("named-people", f"90 PEOPLE / NAMED ASSOCIATIONS — {len(named):,}", "version", named))
    if uncertain:
        production_albums.append(album("uncertain", f"91 CONTEXT UNCERTAIN — EDITOR REVIEW — {len(uncertain):,}", "version", uncertain))
    if hold_ids:
        production_albums.append(album("holds", f"{args.version} — SAFETY HOLD — {len(hold_ids):,}", "private", hold_ids))
    production_albums.append(album("write-test", test_title, "audit", test_ids))
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
    update_run_state(
        args.workspace,
        "validation",
        "completed",
        proposal_id=proposal_id,
        master_sha256=digest,
        production_plan=str(production_path),
    )
    print(f"test_plan={test_path}")
    print(f"production_plan={production_path}")
    print(f"production_albums={len(production_albums)}")
    print(f"production_memberships={sum(len(item['asset_identifiers']) for item in production_albums)}")
    return 0


def command_run_plan(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    app = profile_path(profile, "permissioned_app", APP)
    plan_path = args.plan.resolve()
    plan = validate_plan(json.loads(plan_path.read_text(encoding="utf-8")))
    receipt_path = Path(plan["receipt_path"])
    workspace = plan_path.parent.parent
    operation = str(plan.get("operation", ""))
    if operation == "inspect-local-images":
        phase = "local_inspection"
    elif "write-test" in str(plan.get("plan_id", "")):
        phase = "write_test"
    else:
        phase = "production_commit"
    if not app.is_dir():
        raise ValueError(f"permissioned app not found: {app}")
    before = receipt_path.stat().st_mtime_ns if receipt_path.exists() else None
    command = ["/usr/bin/open", "-W", "-n", str(app), "--args", "--plan", str(plan_path)]
    print("launching permissioned helper; this may run for a long time", flush=True)
    update_run_state(workspace, phase, "running", plan=str(plan_path))
    try:
        completed = subprocess.run(command, check=False)
    except KeyboardInterrupt:
        update_run_state(workspace, phase, "interrupted", plan=str(plan_path))
        raise ValueError("helper run was interrupted; use resume after checking status")
    if completed.returncode:
        update_run_state(workspace, phase, "failed", exit_code=completed.returncode)
        raise ValueError(f"helper launcher failed with exit code {completed.returncode}")
    if not receipt_path.exists():
        update_run_state(workspace, phase, "failed", reason="helper finished without receipt")
        raise ValueError(f"helper finished without receipt: {receipt_path}")
    after = receipt_path.stat().st_mtime_ns
    if before is not None and before == after:
        update_run_state(workspace, phase, "failed", reason="receipt was not refreshed")
        raise ValueError(f"receipt was not refreshed: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validate_receipt(plan, receipt)
    update_run_state(
        workspace,
        phase,
        "completed",
        receipt=str(receipt_path),
        plan=str(plan_path),
        plan_id=plan.get("plan_id"),
        plan_sha256=plan.get("plan_sha256"),
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


def command_status(args: argparse.Namespace) -> int:
    state_path = args.workspace / "run-state.json"
    if not state_path.exists():
        raise ValueError(f"run state not found: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["next_actions"] = next_actions(state)
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


def validate_receipt(plan: dict[str, object], receipt: dict[str, object]) -> None:
    if int(receipt.get("schema_version", 0)) != 2:
        raise ValueError("receipt schema_version must be 2")
    for field in ("plan_id", "plan_sha256", "source_fingerprint"):
        if receipt.get(field) != plan.get(field):
            raise ValueError(f"receipt {field} does not match plan")
    if receipt.get("helper_revision") != plan.get("required_helper_revision"):
        raise ValueError("receipt helper_revision does not match plan requirement")
    if int(receipt.get("source_count", -1)) != int(plan["expected_source_count"]):
        raise ValueError("receipt source_count does not match plan")
    if plan.get("operation") == "snapshot-membership":
        for field in ("proposal_id", "master_sha256", "hold_sha256", "config_sha256", "release_class"):
            if receipt.get(field) != plan.get(field):
                raise ValueError(f"receipt {field} does not match plan")
        expected = {
            str(item["key"]): (str(item["title"]), len(item["asset_identifiers"]))
            for item in plan.get("albums", [])
        }
        actual = {
            str(item["key"]): (str(item["title"]), int(item["count"]))
            for item in receipt.get("albums", [])
        }
        if actual != expected:
            raise ValueError("receipt album keys, titles, or counts do not match plan")
    elif int(receipt.get("completed_count", -1)) != len(plan.get("asset_identifiers", [])):
        raise ValueError("inspection receipt completed_count does not match plan")


def command_resume(args: argparse.Namespace) -> int:
    state_path = args.workspace / "run-state.json"
    if not state_path.exists():
        raise ValueError(f"run state not found: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    records = state.get("phase_records", {})
    for phase in RUN_PHASES:
        record = records.get(phase, {}) if isinstance(records, dict) else {}
        if str(record.get("status")) in {"running", "interrupted", "failed", "stale"} and record.get("plan"):
            return command_run_plan(argparse.Namespace(plan=Path(str(record["plan"])), profile=args.profile))
    raise ValueError("no resumable plan found in run state")


def command_mark_phase(args: argparse.Namespace) -> int:
    details = {}
    if args.artifact:
        details["artifacts"] = [str(path.resolve()) for path in args.artifact]
    update_run_state(
        args.workspace,
        args.phase,
        args.status,
        expected_revision=args.expected_revision,
        actor="operator",
        **details,
    )
    return command_status(argparse.Namespace(workspace=args.workspace))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.add_argument("--profile", type=Path)
    doctor.add_argument("--source-manifest", type=Path)
    doctor.add_argument("--inventory-db", type=Path, default=INVENTORY_DB)
    doctor.add_argument("--photos-db", type=Path, default=PHOTOS_DB)
    doctor.add_argument("--workspace-root", type=Path, default=WORKSPACE_ROOT)
    doctor.set_defaults(func=command_doctor)

    init = sub.add_parser("init-run", help="create a durable versioned run workspace")
    init.add_argument("--slug", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--target", type=int, required=True)
    init.add_argument("--source-manifest", type=Path, required=True)
    init.add_argument("--profile", type=Path)
    init.add_argument("--workspace-root", type=Path, default=WORKSPACE_ROOT)
    init.set_defaults(func=command_init)

    inspect = sub.add_parser("inspection-plan", help="build an exact plan for local PhotoKit inspection")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--workspace", type=Path, required=True)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    inspect.add_argument("--source-manifest", type=Path, required=True)
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
    plans.add_argument("--config", type=Path, required=True)
    plans.add_argument("--evaluation-report", type=Path, required=True)
    plans.add_argument("--source-manifest", type=Path, required=True)
    plans.add_argument("--profile", type=Path)
    plans.add_argument("--batch-size", type=int, default=500)
    plans.set_defaults(func=command_snapshot_plans)

    run = sub.add_parser("run-plan", help="launch a plan through the stable permissioned app bundle")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--profile", type=Path)
    run.set_defaults(func=command_run_plan)

    status = sub.add_parser("status", help="show the durable state of a versioned run")
    status.add_argument("--workspace", type=Path, required=True)
    status.set_defaults(func=command_status)

    resume = sub.add_parser("resume", help="resume the interrupted or failed plan recorded in run state")
    resume.add_argument("--workspace", type=Path, required=True)
    resume.add_argument("--profile", type=Path)
    resume.set_defaults(func=command_resume)

    mark = sub.add_parser("mark-phase", help="atomically record a non-app workflow phase")
    mark.add_argument("--workspace", type=Path, required=True)
    mark.add_argument("--phase", choices=RUN_PHASES, required=True)
    mark.add_argument("--status", choices=sorted(PHASE_STATUSES), required=True)
    mark.add_argument("--artifact", type=Path, action="append")
    mark.add_argument("--expected-revision", type=int)
    mark.set_defaults(func=command_mark_phase)
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
