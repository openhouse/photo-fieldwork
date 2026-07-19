from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .pipeline import master_sha256, read_csv, uuid_sha256


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _artifact(path: Path, root: Path) -> dict:
    resolved = path.resolve()
    try:
        recorded_path = str(resolved.relative_to(root.resolve()))
    except ValueError:
        recorded_path = str(resolved)
    return {"path": recorded_path, "bytes": resolved.stat().st_size, "sha256": file_sha256(resolved)}


def _canonical_sha256(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _plan_source(plan: dict) -> dict:
    nested = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    return {
        "identifier": plan.get("source_album_identifier") or nested.get("identifier"),
        "kind": plan.get("source_kind") or nested.get("kind"),
        "predicate_version": plan.get("source_predicate_version") or nested.get("predicate_version"),
        "snapshot_count": plan.get("expected_source_count") or nested.get("snapshot_count"),
        "source_fingerprint": plan.get("source_fingerprint") or nested.get("source_fingerprint"),
    }


def _master_album_ids(plan: dict) -> list[str]:
    matches = []
    for album in plan.get("albums", []):
        key = str(album.get("key", "")).lower()
        title = str(album.get("title", "")).upper()
        if key == "master" or title.startswith("00 MASTER"):
            matches.append(album.get("asset_ids") or album.get("asset_identifiers") or [])
    if len(matches) != 1:
        raise ValueError("catalog plan must contain exactly one master album")
    return [str(value).split("/", 1)[0] for value in matches[0]]


def build_release_seal(
    *,
    source_path: Path,
    config_path: Path,
    master_path: Path,
    evaluation_path: Path,
    validation_path: Path,
    plan_path: Path,
    output_path: Path,
) -> dict:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    master = read_csv(master_path)
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    source_kind = str(source.get("kind", ""))
    source_identifier = str(source.get("identifier", ""))
    source_fingerprint = str(source.get("source_fingerprint", ""))
    source_count = int(source.get("snapshot_count", 0))
    if not source_identifier or source_count < 1:
        raise ValueError("release source requires an identifier and positive snapshot_count")
    if source_kind != "synthetic" and not re.fullmatch(r"[0-9a-f]{64}", source_fingerprint):
        raise ValueError("non-synthetic release source requires an exact membership fingerprint")

    digest = master_sha256(master)
    proposal_id = f"pfp-{digest[:16]}"
    audited_ids = uuid_sha256(master)
    if not evaluation.get("passed") or not evaluation.get("full_master_audit"):
        raise ValueError("release seal requires a passing full-master evaluation")
    if (
        evaluation.get("proposal_id") != proposal_id
        or evaluation.get("master_sha256") != digest
        or evaluation.get("audited_uuid_sha256") != audited_ids
    ):
        raise ValueError("evaluation does not match the exact master candidate")
    if validation.get("status") != "PASS":
        raise ValueError("release seal requires passing validation")
    if validation.get("proposal_id") != proposal_id or validation.get("master_sha256") != digest:
        raise ValueError("validation does not match the exact master candidate")
    if validation.get("quota_mismatches"):
        raise ValueError("validation contains unresolved exact-quota mismatches")
    if plan.get("proposal_id") != proposal_id or plan.get("master_sha256") != digest:
        raise ValueError("catalog plan does not match the exact master candidate")
    if plan.get("audited_uuid_sha256") != audited_ids:
        raise ValueError("catalog plan does not match the audited master UUID set")
    if plan.get("safety_mode") != "create-folders-albums-and-add-membership-only":
        raise ValueError("catalog plan exceeds the membership-only mutation boundary")
    if sorted(_master_album_ids(plan)) != sorted(str(row["uuid"]).split("/", 1)[0] for row in master):
        raise ValueError("catalog plan master album membership does not match the master candidate")

    planned_source = _plan_source(plan)
    if planned_source["identifier"] != source_identifier:
        raise ValueError("catalog plan source identifier does not match the frozen source")
    if planned_source["snapshot_count"] is not None and int(planned_source["snapshot_count"]) != source_count:
        raise ValueError("catalog plan source count does not match the frozen source")
    if source_fingerprint and planned_source["source_fingerprint"] != source_fingerprint:
        raise ValueError("catalog plan source fingerprint does not match the frozen source")
    if planned_source["kind"] and planned_source["kind"] != source_kind:
        raise ValueError("catalog plan source kind does not match the frozen source")
    if (
        planned_source["predicate_version"]
        and planned_source["predicate_version"] != source.get("predicate_version")
    ):
        raise ValueError("catalog plan source predicate does not match the frozen source")
    config_contract_sha256 = _canonical_sha256(config)
    if plan.get("config_sha256") != config_contract_sha256:
        raise ValueError("catalog plan configuration hash does not match the frozen configuration")

    paths = {
        "source": source_path,
        "config": config_path,
        "master": master_path,
        "evaluation": evaluation_path,
        "validation": validation_path,
        "plan": plan_path,
    }
    artifacts = {name: _artifact(path, output_path.parent) for name, path in paths.items()}
    identity = {
        "release_class": "editor-field",
        "source": {
            "kind": source_kind,
            "identifier": source_identifier,
            "snapshot_count": source_count,
            "predicate_version": source.get("predicate_version"),
            "source_fingerprint": source_fingerprint or None,
        },
        "config_sha256": artifacts["config"]["sha256"],
        "proposal_id": proposal_id,
        "master_sha256": digest,
        "audited_uuid_sha256": audited_ids,
        "evaluation_sha256": artifacts["evaluation"]["sha256"],
        "validation_sha256": artifacts["validation"]["sha256"],
        "plan_sha256": artifacts["plan"]["sha256"],
    }
    seal = {
        "schema_version": 1,
        "status": "SEALED_FOR_WRITE_TEST",
        "release_identity": identity,
        "release_identity_sha256": _canonical_sha256(identity),
        "artifacts": artifacts,
        "write_authority": {
            "test_write": True,
            "production_write": False,
            "requires_passing_test_receipt": True,
            "requires_independent_test_verification": True,
        },
        "publication": {
            "publication_clearance": False,
            "rights_status": "unresolved",
            "consent_status": "unresolved",
            "claim_status": "unresolved",
            "context_status": "unresolved",
        },
    }
    return seal


def write_release_seal(path: Path, seal: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")


def audit_release_seal(path: Path) -> dict:
    seal = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    resolved_artifacts: dict[str, Path] = {}
    identity = seal.get("release_identity", {})
    if seal.get("release_identity_sha256") != _canonical_sha256(identity):
        errors.append("release identity hash mismatch")
    for name, artifact in seal.get("artifacts", {}).items():
        artifact_path = Path(str(artifact.get("path", "")))
        if not artifact_path.is_absolute():
            artifact_path = path.parent / artifact_path
        resolved_artifacts[name] = artifact_path
        if not artifact_path.is_file():
            errors.append(f"{name}: missing artifact")
            continue
        if artifact_path.stat().st_size != int(artifact.get("bytes", -1)):
            errors.append(f"{name}: byte-size drift")
        if file_sha256(artifact_path) != artifact.get("sha256"):
            errors.append(f"{name}: content digest drift")
    if seal.get("publication", {}).get("publication_clearance") is not False:
        errors.append("editor-field release seal cannot grant publication clearance")
    required = {"source", "config", "master", "evaluation", "validation", "plan"}
    if set(resolved_artifacts) != required:
        errors.append("release seal artifact set is incomplete or unexpected")
    elif all(artifact.is_file() for artifact in resolved_artifacts.values()):
        try:
            rebuilt = build_release_seal(
                source_path=resolved_artifacts["source"],
                config_path=resolved_artifacts["config"],
                master_path=resolved_artifacts["master"],
                evaluation_path=resolved_artifacts["evaluation"],
                validation_path=resolved_artifacts["validation"],
                plan_path=resolved_artifacts["plan"],
                output_path=path,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"release contract validation failed: {error}")
        else:
            if rebuilt["release_identity"] != seal.get("release_identity"):
                errors.append("release identity does not match current artifact contracts")
            if rebuilt["write_authority"] != seal.get("write_authority"):
                errors.append("write authority differs from the bounded release contract")
            if rebuilt["publication"] != seal.get("publication"):
                errors.append("publication state differs from the default-closed contract")
    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "release_identity_sha256": seal.get("release_identity_sha256"),
        "artifact_count": len(seal.get("artifacts", {})),
        "errors": errors,
    }
