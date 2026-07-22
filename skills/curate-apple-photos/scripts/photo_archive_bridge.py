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
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from compare_receipts import require_plan_match, require_receipt


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
    "write_test_verification",
    "production_commit",
    "production_rerun",
    "idempotence_verification",
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
    workspace_parent = profile.get("workspace_parent")
    if workspace_parent is not None and (
        not workspace_parent.get("title") or not workspace_parent.get("identifier")
    ):
        raise ValueError("workspace_parent requires an existing title and identifier")
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


def structured_artifact(path: Path) -> object | None:
    try:
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".jsonl":
            return [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as handle:
                return list(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return None


def plan_matches_release(
    plan: dict, state: dict, expected_plan_id: str, plan_sha256: str
) -> bool:
    """Require a write plan to carry the exact validated release candidate."""
    release = state.get("release_binding", {})
    evaluation = plan.get("evaluation", {})
    validation = plan.get("validation", {})
    plan_key = "write_test" if expected_plan_id.endswith("-write-test") else "production"
    return bool(
        release
        and state.get("write_plan_sha256", {}).get(plan_key) == plan_sha256
        and plan.get("plan_id") == expected_plan_id
        and plan.get("source_album_identifier") == state.get("source_album_identifier")
        and plan.get("expected_source_count") == state.get("expected_source_count")
        and plan.get("source_identifier_sha256") == state.get("source_identifier_sha256")
        and evaluation.get("passed") is True
        and evaluation.get("proposal_id") == release.get("proposal_id")
        and evaluation.get("master_sha256") == release.get("master_sha256")
        and evaluation.get("feedback_sha256") == release.get("feedback_sha256")
        and evaluation.get("config_sha256") == release.get("config_sha256")
        and evaluation.get("sample_sha256") == release.get("sample_sha256")
        and validation.get("status") == "PASS"
        and validation.get("master_sha256") == release.get("master_sha256")
        and validation.get("safety_sha256") == release.get("safety_sha256")
        and isinstance(plan.get("albums"), list)
        and bool(plan["albums"])
    )


def write_evidence_matches(phase: str, paths: list[Path], state: dict) -> bool:
    """Bind a write receipt to the exact release plan and run state."""
    suffix = "write-test" if phase == "write_test" else "production"
    expected_plan_id = f"{state.get('version', '')}-{suffix}"
    if not expected_plan_id:
        return False
    artifacts = [(path, structured_artifact(path)) for path in paths]
    plans = [
        (path, data)
        for path, data in artifacts
        if isinstance(data, dict)
        and {"plan_id", "expected_source_count", "evaluation", "validation", "albums"} <= set(data)
    ]
    receipts = [
        data
        for _, data in artifacts
        if isinstance(data, dict)
        and {"plan_id", "source_count", "execution_fingerprint", "albums"} <= set(data)
    ]
    for plan_path, plan in plans:
        plan_digest = file_sha256(plan_path)
        if not plan_matches_release(plan, state, expected_plan_id, plan_digest):
            continue
        for receipt in receipts:
            fingerprint = receipt.get("execution_fingerprint", {})
            receipt_path = next(
                path
                for path, data in artifacts
                if data is receipt
            )
            phase_launch = state.get("launch_bindings", {}).get(phase, {})
            try:
                require_receipt(receipt)
                require_plan_match(
                    receipt,
                    plan,
                    plan_digest,
                    state.get("helper_binding", {}).get("app_bundle_identifier"),
                    state.get("helper_binding", {}).get("app_binary_sha256"),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if (
                receipt.get("plan_id") == expected_plan_id
                and receipt.get("source_album_identifier") == state.get("source_album_identifier")
                and receipt.get("source_count") == state.get("expected_source_count")
                and receipt.get("source_identifier_sha256") == state.get("source_identifier_sha256")
                and fingerprint.get("plan_sha256") == plan_digest
                and re.fullmatch(r"[a-f0-9]{64}", str(fingerprint.get("app_binary_sha256", "")))
                and re.fullmatch(
                    r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)+",
                    str(fingerprint.get("app_bundle_identifier", "")),
                )
                and receipt.get("completed_at")
                and receipt.get("execution_nonce") == phase_launch.get("execution_nonce")
                and isinstance(receipt.get("albums"), list)
                and receipt["albums"]
            ):
                if phase == "production_rerun":
                    first = state.get("production_binding", {})
                    if (
                        file_sha256(receipt_path) == first.get("first_receipt_sha256")
                        or receipt.get("completed_at") == first.get("first_completed_at")
                    ):
                        continue
                return True
    return False


def verification_evidence_matches(phase: str, paths: list[Path], state: dict) -> bool:
    if phase == "write_test_verification":
        expected_plan_id = f"{state.get('version', '')}-write-test"
        binding = state.get("write_test_binding", {})
        expected_receipt = binding.get("receipt_sha256")
    else:
        expected_plan_id = f"{state.get('version', '')}-production"
        binding = state.get("production_binding", {})
        expected_receipt = binding.get("second_receipt_sha256")
    for path in paths:
        data = structured_artifact(path)
        if (
            isinstance(data, dict)
            and data.get("status") == "PASS"
            and data.get("verification_kind") == "wal-aware-live-snapshot"
            and data.get("plan_id") == expected_plan_id
            and data.get("plan_sha256") == binding.get("plan_sha256")
            and data.get("receipt_sha256") == expected_receipt
            and data.get("source_album_identifier") == state.get("source_album_identifier")
            and data.get("source_count") == state.get("expected_source_count")
            and data.get("source_identifier_sha256") == state.get("source_identifier_sha256")
        ):
            return True
    return False


def idempotence_evidence_matches(paths: list[Path], state: dict) -> bool:
    binding = state.get("production_binding", {})
    for path in paths:
        data = structured_artifact(path)
        if (
            isinstance(data, dict)
            and data.get("status") == "PASS"
            and data.get("verification_kind") == "wal-aware-live-snapshot"
            and data.get("plan_id") == f"{state.get('version', '')}-production"
            and data.get("plan_sha256") == binding.get("plan_sha256")
            and data.get("first_receipt_sha256") == binding.get("first_receipt_sha256")
            and data.get("second_receipt_sha256") == binding.get("second_receipt_sha256")
            and data.get("source_album_identifier") == state.get("source_album_identifier")
            and data.get("source_identifier_sha256") == state.get("source_identifier_sha256")
        ):
            return True
    return False


def phase_evidence_matches(phase: str, paths: list[Path], state: dict | None = None) -> bool:
    """Recognize one minimally meaningful artifact for a completed phase."""
    state = state or {}
    if phase in {"write_test", "production_commit", "production_rerun"}:
        return write_evidence_matches(phase, paths, state)
    if phase in {"write_test_verification", "independent_verification"}:
        return verification_evidence_matches(phase, paths, state)
    if phase == "idempotence_verification":
        return idempotence_evidence_matches(paths, state)
    sha256 = re.compile(r"[a-f0-9]{64}")
    for path in paths:
        if path.stat().st_size < 1:
            continue
        data = structured_artifact(path)
        if phase == "brief" and path.suffix.lower() in {".md", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="replace").strip().lower()
            if len(text.split()) >= 8 and sum(term in text for term in ("target", "source", "safety", "brief")) >= 2:
                return True
        elif phase == "retrieval" and isinstance(data, list) and data:
            if all(isinstance(row, dict) and (row.get("uuid") or row.get("asset_identifier")) for row in data):
                return True
        elif phase == "local_inspection" and isinstance(data, list) and data:
            evidence_fields = {"labels", "ocr_text", "safety_flags", "visible_observation", "preview_exported"}
            if all(
                isinstance(row, dict)
                and (row.get("uuid") or row.get("asset_identifier"))
                and evidence_fields.intersection(row)
                for row in data
            ):
                return True
        elif phase == "recursive_evaluation" and isinstance(data, dict):
            required = {
                "passed",
                "proposal_id",
                "master_sha256",
                "feedback_sha256",
                "config_sha256",
                "sample_sha256",
            }
            if (
                required <= set(data)
                and data["passed"] is True
                and re.fullmatch(r"pfp-[a-f0-9]{16}", str(data["proposal_id"]))
                and sha256.fullmatch(str(data["master_sha256"]))
                and sha256.fullmatch(str(data["feedback_sha256"]))
                and sha256.fullmatch(str(data["config_sha256"]))
                and sha256.fullmatch(str(data["sample_sha256"]))
                and (
                    not state.get("release_binding")
                    or all(
                        data.get(field) == state["release_binding"].get(field)
                        for field in (
                            "proposal_id",
                            "master_sha256",
                            "feedback_sha256",
                            "config_sha256",
                            "sample_sha256",
                        )
                    )
                )
            ):
                return True
        elif phase == "validation" and isinstance(data, dict):
            required = {"status", "errors", "master_sha256", "safety_sha256"}
            if (
                required <= set(data)
                and data["status"] == "PASS"
                and data["errors"] == []
                and sha256.fullmatch(str(data["master_sha256"]))
                and sha256.fullmatch(str(data["safety_sha256"]))
                and data["master_sha256"] == state.get("release_binding", {}).get("master_sha256")
                and (
                    not state.get("release_binding", {}).get("safety_sha256")
                    or data["safety_sha256"] == state["release_binding"]["safety_sha256"]
                )
            ):
                return True
    return False


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
            **(
                {"config_sha256": str(row["config_sha256"])}
                if row.get("config_sha256")
                else {}
            ),
        }
        for row in rows
    ]
    payload.sort(key=lambda row: (row["assigned_view"], row["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "photo-field"


def wait_for_fresh_receipt(
    receipt_path: Path,
    *,
    before_mtime_ns: int | None,
    execution_nonce: str,
    timeout_seconds: float,
    stderr_path: Path | None = None,
    poll_interval_seconds: float = 0.25,
) -> dict:
    """Wait for the app, not LaunchServices, to finish the governed operation."""
    if timeout_seconds <= 0:
        raise ValueError("receipt timeout must be positive")
    deadline = time.monotonic() + timeout_seconds
    last_problem = "receipt has not appeared"
    while True:
        if receipt_path.is_file():
            current_mtime_ns = receipt_path.stat().st_mtime_ns
            if before_mtime_ns is None or current_mtime_ns != before_mtime_ns:
                try:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    last_problem = "receipt is not yet readable JSON"
                else:
                    if receipt.get("execution_nonce") == execution_nonce:
                        return receipt
                    last_problem = "receipt does not carry the current launch nonce"
            else:
                last_problem = "receipt has not been refreshed"

        if stderr_path is not None and stderr_path.is_file() and stderr_path.stat().st_size:
            detail = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
            if detail:
                raise ValueError(f"permissioned helper failed before a fresh receipt: {detail}")

        if time.monotonic() >= deadline:
            raise ValueError(
                f"timed out after {timeout_seconds:g}s waiting for a fresh helper receipt; "
                f"{last_problem}: {receipt_path}"
            )
        time.sleep(poll_interval_seconds)


def launch_permissioned_helper(
    *,
    app: Path,
    plan_path: Path,
    receipt_path: Path,
    execution_nonce: str,
    before_mtime_ns: int | None,
    timeout_seconds: float,
) -> dict:
    command = [
        "/usr/bin/open", "-W", "-n", str(app),
        "--args", "--plan", str(plan_path),
        "--launch-nonce", execution_nonce,
    ]
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise ValueError(f"helper launcher failed with exit code {completed.returncode}")
    return wait_for_fresh_receipt(
        receipt_path,
        before_mtime_ns=before_mtime_ns,
        execution_nonce=execution_nonce,
        timeout_seconds=timeout_seconds,
    )


def authorization_plan(profile: dict, workspace: Path, plan_id: str) -> dict:
    source = profile["default_source"]
    return {
        "operation": "inspect-local-images",
        "schema_version": 1,
        "plan_id": plan_id,
        "safety_mode": "read-only-local-inspection-and-preview-export",
        "source_album_identifier": str(source["identifier"]),
        "expected_source_count": int(source["expected_count"]),
        "source_identifier_sha256": source.get("identifier_sha256"),
        "asset_identifiers": [],
        "output_jsonl_path": str(workspace / "authorization-check.jsonl"),
        "receipt_path": str(workspace / "authorization-receipt.json"),
        "log_path": str(workspace / "authorization-helper.log"),
        "preview_directory": str(workspace / "previews-disabled"),
        "target_long_edge": 256,
        "export_previews": False,
        "ocr_all": False,
        "classify_all": False,
        "detect_faces": False,
        "network_access_allowed": False,
    }


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
    live_receipt = None
    live_workspace = None
    if args.live:
        live_workspace = (
            workspace_root
            / ".authorization-checks"
            / f"{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}"
        )
        secure_directory(live_workspace)
        plan_path = live_workspace / "authorization-plan.json"
        plan = authorization_plan(profile, live_workspace, f"authorization-{secrets.token_hex(8)}")
        dump_json(plan_path, plan)
        receipt_path = Path(plan["receipt_path"])
        execution_nonce = secrets.token_hex(16)
        live_receipt = launch_permissioned_helper(
            app=app,
            plan_path=plan_path,
            receipt_path=receipt_path,
            execution_nonce=execution_nonce,
            before_mtime_ns=None,
            timeout_seconds=args.receipt_timeout_seconds,
        )
        live_receipt["execution_fingerprint"] = {
            "app_bundle_identifier": profile["bundle_id"],
            "app_binary_sha256": file_sha256(executable),
            "plan_sha256": file_sha256(plan_path),
        }
        dump_json(receipt_path, live_receipt)
        checks["live_photo_authorization"] = (
            live_receipt.get("execution_nonce") == execution_nonce
            and live_receipt.get("requested_count") == 0
            and live_receipt.get("completed_count") == 0
            and live_receipt.get("network_access_allowed") is False
            and live_receipt.get("external_uploads_performed") is False
        )
        checks["live_source_contract"] = (
            live_receipt.get("source_album_identifier") == default_source["identifier"]
            and live_receipt.get("source_count") == int(default_source["expected_count"])
            and (
                not default_source.get("identifier_sha256")
                or live_receipt.get("source_identifier_sha256")
                == default_source["identifier_sha256"]
            )
        )
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "bundle_id": bundle,
        "version": version,
        "app_binary_sha256": file_sha256(executable) if executable.is_file() else None,
        "inventory_generated_at": inventory_meta.get("generated_at"),
        "inventory_source_count": inventory_meta.get("source_count") or inventory_meta.get("source_album_count"),
        "profile": str(args.profile.expanduser().resolve()),
        "live_authorization_workspace": str(live_workspace) if live_workspace else None,
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
    artifacts = state.get("artifacts", {})
    completed_phases = []
    seen_phase_artifacts = set()
    encountered_pending = False
    for phase in RUN_PHASES:
        phase_record = state.get("phases", {}).get(phase, {})
        completed = phase_record.get("status") == "completed"
        if not completed:
            encountered_pending = True
            continue
        completed_phases.append(phase)
        if encountered_pending:
            issues.append(f"completed phase follows an incomplete phase: {phase}")
        phase_artifacts = phase_record.get("artifacts")
        if not isinstance(phase_artifacts, list) or not phase_artifacts:
            issues.append(f"completed phase has no evidence artifacts: {phase}")
            continue
        for relative in phase_artifacts:
            if relative in seen_phase_artifacts:
                issues.append(f"artifact is reused across completed phases: {relative}")
            seen_phase_artifacts.add(relative)
            if relative not in artifacts:
                issues.append(f"phase references an unrecorded artifact: {relative}")
    for relative, record in artifacts.items():
        try:
            path = safe_workspace_file(workspace, workspace / relative)
        except ValueError:
            issues.append(f"missing or unsafe artifact: {relative}")
            continue
        if path.stat().st_size < 1:
            issues.append(f"artifact is empty: {relative}")
        if path.stat().st_size != int(record["bytes"]) or file_sha256(path) != record["sha256"]:
            issues.append(f"artifact changed after phase completion: {relative}")
    for phase in completed_phases:
        relative_paths = state["phases"][phase].get("artifacts", [])
        paths = []
        for relative in relative_paths:
            try:
                paths.append(safe_workspace_file(workspace, workspace / relative))
            except ValueError:
                continue
        if paths and not phase_evidence_matches(phase, paths, state):
            issues.append(f"completed phase lacks recognizable evidence: {phase}")
    state["artifact_integrity"] = (
        "FAIL" if issues else "PASS" if completed_phases else "NOT-STARTED"
    )
    state["artifact_integrity_issues"] = issues
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0 if not issues else 2


def command_advance(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    state_path = workspace / "run-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if args.phase not in RUN_PHASES:
        raise ValueError(f"unknown run phase: {args.phase}")
    if args.phase in {
        "write_test_verification",
        "idempotence_verification",
        "independent_verification",
    } and not getattr(args, "_verified_by_command", False):
        raise ValueError("verification phases must be completed with verify-phase")
    phase_index = RUN_PHASES.index(args.phase)
    incomplete = [
        phase
        for phase in RUN_PHASES[:phase_index]
        if state["phases"].get(phase, {}).get("status") != "completed"
    ]
    if incomplete:
        raise ValueError(f"cannot complete {args.phase}; earlier phases pending: {', '.join(incomplete)}")
    if not args.artifact:
        raise ValueError(f"cannot complete {args.phase} without evidence artifacts")
    records = []
    recorded = set(state.get("artifacts", {}))
    seen = set()
    for value in args.artifact:
        path = safe_workspace_file(workspace, value)
        if path.stat().st_size < 1:
            raise ValueError(f"evidence artifact must be non-empty: {path}")
        relative = str(path.relative_to(workspace))
        if relative in seen or relative in recorded:
            raise ValueError(f"artifact must be unique to this phase: {relative}")
        seen.add(relative)
        records.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    artifact_paths = [workspace / record["path"] for record in records]
    if not phase_evidence_matches(args.phase, artifact_paths, state):
        raise ValueError(f"cannot complete {args.phase} without recognizable phase evidence")
    if args.phase == "recursive_evaluation":
        report = next(
            data
            for data in (structured_artifact(path) for path in artifact_paths)
            if isinstance(data, dict) and data.get("passed") is True
        )
        state["release_binding"] = {
            field: report[field]
            for field in (
                "proposal_id",
                "master_sha256",
                "feedback_sha256",
                "config_sha256",
                "sample_sha256",
            )
        }
    elif args.phase == "validation":
        report = next(
            data
            for data in (structured_artifact(path) for path in artifact_paths)
            if isinstance(data, dict) and data.get("status") == "PASS"
        )
        state["release_binding"]["safety_sha256"] = report["safety_sha256"]
    elif args.phase in {"write_test", "production_commit", "production_rerun"}:
        structured = [(path, structured_artifact(path)) for path in artifact_paths]
        plan_path, plan = next(
            (path, data)
            for path, data in structured
            if isinstance(data, dict) and "expected_source_count" in data
        )
        receipt_path, receipt = next(
            (path, data)
            for path, data in structured
            if isinstance(data, dict) and "source_count" in data
        )
        binding = {
            "plan_id": plan["plan_id"],
            "plan_sha256": file_sha256(plan_path),
            "receipt_sha256": file_sha256(receipt_path),
            "completed_at": receipt["completed_at"],
            "execution_nonce": receipt["execution_nonce"],
        }
        if args.phase == "write_test":
            state["write_test_binding"] = binding
        elif args.phase == "production_commit":
            state["production_binding"] = {
                "plan_id": binding["plan_id"],
                "plan_sha256": binding["plan_sha256"],
                "first_receipt_sha256": binding["receipt_sha256"],
                "first_completed_at": binding["completed_at"],
                "first_execution_nonce": binding["execution_nonce"],
            }
        else:
            state["production_binding"].update(
                {
                    "second_receipt_sha256": binding["receipt_sha256"],
                    "second_completed_at": binding["completed_at"],
                    "second_execution_nonce": binding["execution_nonce"],
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
    workspace_parent = profile.get("workspace_parent")
    folders = [
        {
            "key": "root",
            "title": protected["root"]["title"],
            "parent_key": "workspace_parent" if workspace_parent else None,
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
    if workspace_parent:
        folders.insert(
            0,
            {
                "key": "workspace_parent",
                "title": workspace_parent["title"],
                "parent_key": None,
                "existing_identifier": workspace_parent["identifier"],
            },
        )
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
            "feedback_sha256": args.feedback_sha256,
            "config_sha256": args.config_sha256,
            "sample_sha256": args.sample_sha256,
            "passed": True,
        },
        "validation": {
            "status": "PASS",
            "master_sha256": args.master_sha256,
            "safety_sha256": args.safety_sha256,
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
    core_plan_path = args.workspace / "manifests" / f"{args.version}-core-catalog-plan.json"
    cli = profile_path(args.profile_data, "photo_fieldwork_cli")
    command = [
        str(cli),
        "plan",
        "--master", str(args.master),
        "--holds", str(args.holds),
        "--feedback", str(args.feedback),
        "--config", str(args.config),
        "--evaluation-report", str(args.evaluation_report),
        "--validation-report", str(args.validation_report),
        "--plan-id", f"{args.version}-core",
        "--source-title", "Frozen Apple Photos source",
        "--source-identifier", source_id,
        "--source-count", str(source_count),
        "--source-sha256", str(source_sha256),
        "--output", str(core_plan_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown core planner failure"
        raise ValueError(f"snapshot plans require an exact passing release bundle: {detail}")
    core_plan = json.loads(core_plan_path.read_text(encoding="utf-8"))
    digest = master_sha256(master_rows)
    proposal_id = f"pfp-{digest[:16]}"
    if core_plan.get("master_sha256") != digest or core_plan.get("proposal_id") != proposal_id:
        raise ValueError("core catalog plan does not match exact master membership and assignments")
    args.master_sha256 = digest
    args.proposal_id = proposal_id
    args.feedback_sha256 = core_plan["evaluation"]["feedback_sha256"]
    args.config_sha256 = core_plan["evaluation"]["config_sha256"]
    args.sample_sha256 = core_plan["evaluation"]["sample_sha256"]
    args.safety_sha256 = core_plan["validation"]["safety_sha256"]

    state_path = args.workspace / "run-state.json"
    if not state_path.is_file():
        raise ValueError("snapshot plans require an initialized run-state.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("phases", {}).get("validation", {}).get("status") != "completed":
        raise ValueError("snapshot plans require completed validation")
    expected_release = {
        "proposal_id": args.proposal_id,
        "master_sha256": args.master_sha256,
        "feedback_sha256": args.feedback_sha256,
        "config_sha256": args.config_sha256,
        "sample_sha256": args.sample_sha256,
        "safety_sha256": args.safety_sha256,
    }
    if state.get("release_binding") != expected_release:
        raise ValueError("snapshot plans do not match the run's validated release binding")

    by_view: dict[str, list[str]] = {}
    view_labels = {}
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
    state["write_plan_sha256"] = {
        "write_test": file_sha256(test_path),
        "production": file_sha256(production_path),
    }
    state["helper_binding"] = {
        "app_bundle_identifier": args.profile_data["bundle_id"],
        "app_binary_sha256": file_sha256(profile_path(args.profile_data, "app_executable")),
    }
    dump_json(state_path, state)
    print(f"test_plan={test_path}")
    print(f"production_plan={production_path}")
    print(f"production_albums={len(production_albums)}")
    print(f"production_memberships={sum(len(item['asset_identifiers']) for item in production_albums)}")
    return 0


def command_run_plan(args: argparse.Namespace) -> int:
    app = profile_path(args.profile_data, "app_path")
    workspace = args.workspace.resolve()
    state = json.loads((workspace / "run-state.json").read_text(encoding="utf-8"))
    plan_path = safe_workspace_file(workspace, args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    receipt_path = Path(plan["receipt_path"]).resolve()
    if workspace not in receipt_path.parents:
        raise ValueError("receipt path must remain inside the run workspace")
    version = str(state.get("version", ""))
    if plan.get("source_album_identifier") != state.get("source_album_identifier"):
        raise ValueError("write plan source does not match run state")
    if plan.get("source_identifier_sha256") != state.get("source_identifier_sha256"):
        raise ValueError("write plan source digest does not match run state")
    if plan.get("expected_source_count") != state.get("expected_source_count"):
        raise ValueError("write plan source count does not match run state")
    if plan.get("operation") == "inspect-local-images":
        required_phase = "retrieval"
        pending_phase = "local_inspection"
    elif plan.get("plan_id") == f"{version}-write-test":
        required_phase = "validation"
        pending_phase = "write_test"
    elif plan.get("plan_id") == f"{version}-production":
        if state["phases"].get("production_commit", {}).get("status") != "completed":
            required_phase = "write_test_verification"
            pending_phase = "production_commit"
        else:
            required_phase = "production_commit"
            pending_phase = "production_rerun"
    else:
        raise ValueError("write plan ID does not match the run version")
    if plan.get("operation") != "inspect-local-images" and not plan_matches_release(
        plan, state, str(plan["plan_id"]), file_sha256(plan_path)
    ):
        raise ValueError("write plan does not match the exact validated release candidate")
    if state["phases"].get(required_phase, {}).get("status") != "completed":
        raise ValueError(f"cannot run plan before completed phase: {required_phase}")
    if state["phases"].get(pending_phase, {}).get("status") == "completed":
        raise ValueError(f"write phase is already completed: {pending_phase}")
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
    execution_nonce = secrets.token_hex(16)
    state.setdefault("launch_bindings", {})[pending_phase] = {
        "execution_nonce": execution_nonce,
        "plan_sha256": file_sha256(plan_path),
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    dump_json(workspace / "run-state.json", state)
    print(
        "launching permissioned helper; completion requires its fresh nonce-bound receipt",
        flush=True,
    )
    receipt = launch_permissioned_helper(
        app=app,
        plan_path=plan_path,
        receipt_path=receipt_path,
        execution_nonce=execution_nonce,
        before_mtime_ns=before,
        timeout_seconds=args.receipt_timeout_seconds,
    )
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


def command_verify_phase(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    plan = safe_workspace_file(workspace, args.plan)
    report = args.report.expanduser().absolute().resolve()
    if workspace not in report.parents:
        raise ValueError("verification report must remain inside the run workspace")
    secure_directory(report.parent)
    scripts = Path(__file__).resolve().parent
    common = [
        "--plan", str(plan),
        "--app-binary", str(profile_path(args.profile_data, "app_executable")),
        "--bundle-id", str(args.profile_data["bundle_id"]),
        "--photos-db", str(profile_path(args.profile_data, "photos_db")),
        "--report", str(report),
    ]
    if args.phase == "idempotence_verification":
        if args.first_receipt is None or args.second_receipt is None:
            raise ValueError("idempotence verification requires first and second receipts")
        first = safe_workspace_file(workspace, args.first_receipt)
        second = safe_workspace_file(workspace, args.second_receipt)
        command = [
            sys.executable,
            str(scripts / "compare_receipts.py"),
            "--first", str(first),
            "--second", str(second),
            *common,
        ]
    else:
        if args.receipt is None:
            raise ValueError("catalog verification requires a receipt")
        receipt = safe_workspace_file(workspace, args.receipt)
        command = [
            sys.executable,
            str(scripts / "verify_photos_commit.py"),
            "--receipt", str(receipt),
            "--plan", str(plan),
            "--photos-db", str(profile_path(args.profile_data, "photos_db")),
            "--report", str(report),
        ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "verification failed"
        raise ValueError(detail)
    machine_report = report.with_suffix(".json")
    if not machine_report.is_file():
        raise ValueError("verifier did not emit machine-readable evidence")
    return command_advance(
        argparse.Namespace(
            workspace=workspace,
            phase=args.phase,
            artifact=[machine_report],
            _verified_by_command=True,
        )
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the local integration without mutating Photos")
    doctor.add_argument(
        "--live",
        action="store_true",
        help="launch a zero-image, read-only PhotoKit authorization and source check",
    )
    doctor.add_argument(
        "--receipt-timeout-seconds",
        type=float,
        default=600,
        help="maximum wait for the live authorization receipt (default: 600)",
    )
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
    plans.add_argument("--config", type=Path, required=True)
    plans.add_argument("--feedback", type=Path, required=True)
    plans.add_argument("--evaluation-report", type=Path, required=True)
    plans.add_argument("--validation-report", type=Path, required=True)
    plans.add_argument("--source-id")
    plans.add_argument("--source-count", type=int)
    plans.add_argument("--source-sha256")
    plans.add_argument("--batch-size", type=int, default=500)
    plans.set_defaults(func=command_snapshot_plans)

    run = sub.add_parser("run-plan", help="launch a plan through the stable permissioned app bundle")
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument(
        "--receipt-timeout-seconds",
        type=float,
        default=21600,
        help="maximum wait after launch for the app's fresh receipt (default: 21600)",
    )
    run.set_defaults(func=command_run_plan)

    verify_phase = sub.add_parser(
        "verify-phase", help="run live verification and advance its governed phase"
    )
    verify_phase.add_argument("--workspace", type=Path, required=True)
    verify_phase.add_argument(
        "--phase",
        choices=[
            "write_test_verification",
            "idempotence_verification",
            "independent_verification",
        ],
        required=True,
    )
    verify_phase.add_argument("--plan", type=Path, required=True)
    verify_phase.add_argument("--receipt", type=Path)
    verify_phase.add_argument("--first-receipt", type=Path)
    verify_phase.add_argument("--second-receipt", type=Path)
    verify_phase.add_argument("--report", type=Path, required=True)
    verify_phase.set_defaults(func=command_verify_phase)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command in {
            "doctor", "init-run", "inspection-plan", "snapshot-plans", "run-plan", "verify-phase"
        }:
            args.profile_data = load_profile(args.profile)
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
