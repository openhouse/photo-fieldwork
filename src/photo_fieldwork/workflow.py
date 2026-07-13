from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import canonical_asset_id, read_json, stable_digest, truthy, verify_plan_digest, write_json
from .pipeline import select


RAW_OCR_FIELDS = {"ocr_text", "recognized_text", "recognized_lines", "text_lines"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"expected object at {path}:{number}")
        rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_inspection_ledger(batch_manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if int(batch_manifest.get("schema_version", 0)) != 1:
        raise ValueError("unsupported inspection batch manifest schema_version")
    ledger: dict[str, dict[str, Any]] = {}
    duplicate_keys = 0
    refreshed = 0
    for batch in batch_manifest.get("batches") or []:
        inspection_path = Path(batch["inspection_jsonl"])
        preview_directory = Path(batch["preview_directory"]) if batch.get("preview_directory") else None
        policy = {
            "helper_version": str(batch.get("helper_version") or "unknown"),
            "target_long_edge": int(batch.get("target_long_edge") or 0),
            "classifier_policy": str(batch.get("classifier_policy") or "unknown"),
            "safety_ruleset_version": str(batch.get("safety_ruleset_version") or "unknown"),
            "source_fingerprint": str(batch.get("source_fingerprint") or "unknown"),
        }
        for row in read_jsonl(inspection_path):
            present_raw = RAW_OCR_FIELDS & row.keys()
            if present_raw:
                raise ValueError(f"raw OCR fields are prohibited: {', '.join(sorted(present_raw))}")
            identifier = row.get("asset_identifier") or row.get("uuid")
            uuid = canonical_asset_id(identifier)
            inspection_key = stable_digest({"uuid": uuid, **policy})
            entry = dict(row)
            entry["uuid"] = uuid
            entry["inspection_key"] = inspection_key
            entry["inspection_policy"] = policy
            if preview_directory and truthy(row.get("preview_exported")):
                preview_path = preview_directory / f"{str(identifier).replace('/', '_')}.jpg"
                if not preview_path.exists():
                    fallback = preview_directory / f"{uuid}.jpg"
                    preview_path = fallback if fallback.exists() else preview_path
                entry["preview_path"] = str(preview_path)
                entry["preview_sha256"] = _file_digest(preview_path) if preview_path.exists() else ""
                entry["preview_valid"] = preview_path.exists()
            existing = ledger.get(uuid)
            if existing and existing.get("inspection_key") == inspection_key:
                duplicate_keys += 1
                continue
            if existing:
                refreshed += 1
            ledger[uuid] = entry
    entries = [ledger[uuid] for uuid in sorted(ledger)]
    report: dict[str, Any] = {
        "unique_assets": len(entries),
        "reused_identical_inspections": duplicate_keys,
        "refreshed_inspections": refreshed,
        "pixel_available": sum(truthy(row.get("pixel_available")) for row in entries),
        "preview_valid": sum(bool(row.get("preview_valid")) for row in entries),
        "invalid_previews": sum(
            truthy(row.get("preview_exported")) and not bool(row.get("preview_valid"))
            for row in entries
        ),
        "pixel_unavailable": sum(not truthy(row.get("pixel_available")) for row in entries),
        "raw_ocr_persisted": False,
    }
    report["status"] = "PASS" if report["invalid_previews"] == 0 else "FAIL"
    return entries, report


def duplicate_audit(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for row in rows:
        uuid = canonical_asset_id(row["uuid"])
        if row.get("preview_sha256"):
            groups[("preview-sha256", row["preview_sha256"])].append(uuid)
        elif row.get("perceptual_hash"):
            groups[("perceptual-hash", row["perceptual_hash"])].append(uuid)
        else:
            file_signature = (
                row.get("filename", "").casefold(),
                row.get("width", ""),
                row.get("height", ""),
                row.get("original_file_size", ""),
            )
            if all(file_signature):
                groups[("file-signature", *file_signature)].append(uuid)
    audit = []
    cluster_number = 0
    for signature, ids in sorted(groups.items()):
        unique_ids = sorted(set(ids))
        if len(unique_ids) < 2:
            continue
        cluster_number += 1
        cluster_id = f"duplicate-{cluster_number:04d}"
        for uuid in unique_ids:
            audit.append(
                {
                    "uuid": uuid,
                    "duplicate_cluster": cluster_id,
                    "match_method": signature[0],
                    "review_status": "pending",
                }
            )
    report = {
        "duplicate_clusters": cluster_number,
        "assets_requiring_duplicate_review": len(audit),
        "unresolved": len(audit),
    }
    return audit, report


def apply_feedback(
    previous_master: list[dict[str, str]],
    candidates: list[dict[str, str]],
    feedback: list[dict[str, str]],
    config: dict[str, Any],
) -> tuple[list[dict], list[dict], list[dict[str, Any]], list[dict[str, str]]]:
    previous = {canonical_asset_id(row["uuid"]): row for row in previous_master}
    rejected: set[str] = set()
    safety_decisions: dict[str, str] = {}
    decisions: list[dict[str, Any]] = []
    decided_at = datetime.now(timezone.utc).isoformat()
    for row in feedback:
        uuid = canonical_asset_id(row["uuid"])
        judgment = str(row.get("judgment") or "").strip().lower()
        safety = str(row.get("safety_status") or "clear").strip().lower()
        if judgment == "reject":
            rejected.add(uuid)
        if safety in {"hold", "needs-review"}:
            safety_decisions[uuid] = safety
        if judgment or safety != "clear":
            decisions.append(
                {
                    "uuid": uuid,
                    "judgment": judgment,
                    "safety_status": safety,
                    "visible_reason": row.get("visible_reason") or row.get("evaluation_note") or "",
                    "error_category": row.get("error_category") or "",
                    "round_id": row.get("round_id") or "",
                    "reviewer_lens": row.get("reviewer_lens") or "",
                    "decided_at": decided_at,
                }
            )
    eligible = []
    for original in candidates:
        row = dict(original)
        uuid = canonical_asset_id(row["uuid"])
        row["uuid"] = uuid
        if uuid in rejected:
            continue
        if uuid in safety_decisions:
            row["safety_status"] = safety_decisions[uuid]
            row["safety_reason"] = row.get("safety_reason") or "visual review safety decision"
        eligible.append(row)
    next_master, holds, _ = select(eligible, config)
    replacement_review = []
    for row in next_master:
        uuid = canonical_asset_id(row["uuid"])
        old = previous.get(uuid)
        change = ""
        if old is None:
            change = "newly-admitted-replacement"
        elif old.get("primary_view") != row.get("primary_view"):
            change = "reassigned-view"
        if change:
            row["replacement_review_status"] = "pending"
            replacement_review.append(
                {
                    "uuid": uuid,
                    "change": change,
                    "previous_view": old.get("primary_view", "") if old else "",
                    "new_view": row.get("primary_view", ""),
                    "review_status": "pending",
                    "visible_reason": "",
                }
            )
    return next_master, holds, decisions, replacement_review


def lint_catalog_plan(
    plan: dict[str, Any],
    master: list[dict[str, str]],
    holds: list[dict[str, str]],
    config: dict[str, Any],
    *,
    inspected_ids: set[str] | None = None,
    source_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    master_ids = [canonical_asset_id(row["uuid"]) for row in master]
    hold_ids = {canonical_asset_id(row["uuid"]) for row in holds}
    if len(master_ids) != int(config["target_count"]):
        errors.append("master count differs from configured target")
    if len(master_ids) != len(set(master_ids)):
        errors.append("master contains duplicate UUIDs")
    if set(master_ids) & hold_ids:
        errors.append("master overlaps HOLD")
    if inspected_ids is not None:
        missing_inspections = set(master_ids) - {canonical_asset_id(value) for value in inspected_ids}
        if missing_inspections:
            errors.append(f"master has {len(missing_inspections)} assets without accepted inspection")
    pending_replacements = sum(
        str(row.get("replacement_review_status") or "").lower() == "pending" for row in master
    )
    if pending_replacements:
        errors.append(f"master has {pending_replacements} pending replacement reviews")
    if plan.get("safety_mode") != "create-folders-albums-and-add-membership-only":
        errors.append("plan safety_mode is not membership-only")
    if not verify_plan_digest(plan):
        errors.append("plan digest is missing or does not match")
    if source_profile:
        if str(plan.get("source_album_identifier") or plan.get("source", {}).get("identifier")) != str(source_profile["id"]):
            errors.append("plan source identifier differs from source profile")
        expected = plan.get("expected_source_count")
        if expected is None:
            errors.append("plan does not declare the source count")
        elif int(expected) != int(source_profile["expected_count"]):
            errors.append("plan source count differs from source profile")
        plan_fingerprint = plan.get("source_profile_fingerprint") or plan.get("source", {}).get("profile_fingerprint")
        if plan_fingerprint and source_profile.get("fingerprint") and plan_fingerprint != source_profile["fingerprint"]:
            errors.append("plan source fingerprint differs from source profile")
    plan_ids: list[str] = []
    albums = plan.get("albums") or []
    titles = [str(album.get("title") or "") for album in albums]
    if len(titles) != len(set(titles)):
        errors.append("plan contains duplicate album titles")
    folders = plan.get("folders") or []
    folder_keys = {str(folder.get("key") or "") for folder in folders}
    folder_titles = [str(folder.get("title") or "") for folder in folders]
    if len(folder_titles) != len(set(folder_titles)):
        errors.append("plan contains duplicate folder titles")
    for album in albums:
        parent = album.get("parent_folder_key")
        if parent and parent not in folder_keys:
            errors.append(f"album parent folder is absent: {parent}")
    if source_profile:
        protected = set(source_profile.get("protected_identifiers") or [])
        targeted = {str(folder.get("existing_identifier") or "") for folder in folders}
        overlap = (protected & targeted) - {""}
        if overlap:
            errors.append(f"plan targets {len(overlap)} protected prior identifiers")
    for album in albums:
        values = album.get("asset_identifiers") or album.get("asset_ids") or []
        plan_ids.extend(canonical_asset_id(value) for value in values)
    allowed = set(master_ids) | hold_ids
    outside_manifests = set(plan_ids) - allowed
    if outside_manifests:
        errors.append(f"plan has {len(outside_manifests)} memberships outside master and HOLD")
    master_albums = [album for album in albums if str(album.get("title") or "").startswith("00 MASTER") or album.get("key") == "master"]
    if len(master_albums) != 1:
        errors.append("plan must contain exactly one master album")
    elif {
        canonical_asset_id(value)
        for value in (master_albums[0].get("asset_identifiers") or master_albums[0].get("asset_ids") or [])
    } != set(master_ids):
        errors.append("master album membership differs from master manifest")
    unsigned = dict(plan)
    unsigned.pop("plan_digest", None)
    digest = stable_digest(unsigned)
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "plan_digest": digest,
        "master_count": len(master_ids),
        "hold_count": len(hold_ids),
        "album_count": len(albums),
        "membership_count": len(plan_ids),
    }


def transition_run_state(
    path: Path, phase: str, status: str, evidence: str | None = None
) -> dict[str, Any]:
    allowed = {"pending", "in_progress", "completed", "blocked"}
    if status not in allowed:
        raise ValueError(f"unsupported phase status: {status}")
    state = read_json(path)
    phases = state.get("phases") or {}
    if phase not in phases:
        raise ValueError(f"unknown run phase: {phase}")
    previous = phases[phase]
    if previous == "completed" and status != "completed":
        raise ValueError(f"completed phase cannot move backward: {phase}")
    phases[phase] = status
    state["phases"] = phases
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    history = state.setdefault("history", [])
    history.append(
        {
            "phase": phase,
            "from": previous,
            "to": status,
            "evidence": evidence or "",
            "at": state["updated_at"],
        }
    )
    state["status"] = "complete" if phases and all(value == "completed" for value in phases.values()) else "active"
    write_json(path, state)
    return state


def completion_report(run: Path) -> tuple[dict[str, Any], str]:
    state_path = run / "run-state.json"
    state = read_json(state_path) if state_path.exists() else {}
    artifacts: dict[str, Any] = {}
    patterns = {
        "selection": "reports/*selection-summary.json",
        "evaluations": "reports/*evaluation*.json",
        "validation": "reports/*validation*.json",
        "inspection": "reports/*inspection*.json",
        "duplicate_audit": "reports/*duplicate*.json",
        "plan_lint": "reports/*plan-lint*.json",
        "receipts": "manifests/*receipt*.json",
        "idempotence": "manifests/*idempotence*.json",
        "verification": "reports/*verification*.json",
    }
    for key, pattern in patterns.items():
        values = []
        for path in sorted(run.glob(pattern)):
            try:
                values.append({"path": str(path.relative_to(run)), "data": read_json(path)})
            except (OSError, ValueError, json.JSONDecodeError):
                values.append({"path": str(path.relative_to(run)), "error": "unreadable JSON artifact"})
        artifacts[key] = values
    selection_data = artifacts["selection"][-1].get("data", {}) if artifacts["selection"] else {}
    validation_data = artifacts["validation"][-1].get("data", {}) if artifacts["validation"] else {}
    evaluation_rounds = [
        {
            "path": item["path"],
            "precision": item.get("data", {}).get("precision"),
            "coverage": item.get("data", {}).get("coverage"),
            "passed": item.get("data", {}).get("passed"),
            "failed_views": item.get("data", {}).get("failed_views", []),
        }
        for item in artifacts["evaluations"]
    ]
    receipt_summaries = [
        {
            "path": item["path"],
            "plan_id": item.get("data", {}).get("plan_id"),
            "source_count": item.get("data", {}).get("source_count"),
            "completed_count": item.get("data", {}).get("completed_count"),
            "pixel_available_count": item.get("data", {}).get("pixel_available_count"),
            "external_uploads_performed": item.get("data", {}).get("external_uploads_performed"),
            "album_count": len(item.get("data", {}).get("albums", [])),
        }
        for item in artifacts["receipts"]
    ]
    report = {
        "run_id": state.get("run_id", run.name),
        "status": state.get("status", "unknown"),
        "source": state.get("source", {}),
        "target_count": state.get("target_count"),
        "phases": state.get("phases", {}),
        "metrics": {
            "candidate_inventory_count": selection_data.get("inventory_count"),
            "master_count": validation_data.get("master_count") or selection_data.get("selected_count"),
            "unique_count": validation_data.get("unique_count"),
            "hold_count": validation_data.get("hold_count") or selection_data.get("hold_count"),
            "view_counts": validation_data.get("view_counts") or selection_data.get("view_counts", {}),
            "assets_with_named_people_associations": validation_data.get("assets_with_named_people_associations") or selection_data.get("assets_with_named_people_associations") or selection_data.get("named_people_count"),
        },
        "evaluation_rounds": evaluation_rounds,
        "receipt_summaries": receipt_summaries,
        "artifacts": artifacts,
        "publication_clearance": "not_assessed",
        "editor_field_not_final_publication_edit": True,
    }
    lines = [f"# Completion report: {report['run_id']}", ""]
    lines.append(f"- **Run status:** {report['status']}")
    lines.append(f"- **Target count:** {report['target_count']}")
    lines.append("- **Publication clearance:** not assessed")
    lines.append("- **Final publication edit:** no")
    lines.extend(["", "## Exact metrics", ""])
    for key, value in report["metrics"].items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines.extend(["", "## Evaluation rounds", ""])
    for round_report in evaluation_rounds:
        lines.append(
            f"- `{round_report['path']}`: precision={round_report['precision']}, "
            f"coverage={round_report['coverage']}, passed={round_report['passed']}"
        )
    lines.extend(["", "## Phases", ""])
    lines.extend(f"- `{key}`: {value}" for key, value in report["phases"].items())
    lines.extend(["", "## Authoritative artifacts", ""])
    for key, values in artifacts.items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {len(values)}")
        for value in values:
            lines.append(f"  - `{value['path']}`")
    lines.extend(
        [
            "",
            "This report describes an editor-ready field. Album membership is not publication permission.",
        ]
    )
    return report, "\n".join(lines) + "\n"
