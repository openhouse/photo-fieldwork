from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping


RELEASE_CLASSES = {"editor-field-verified", "publication-ready"}
SOURCE_MANIFEST_FIELDS = {
    "schema_version",
    "source_adapter",
    "source_identifier",
    "predicate_version",
    "observed_count",
    "membership_sha256",
    "source_fingerprint",
}


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_identifier(value: object) -> str:
    return str(value).strip().split("/", 1)[0]


def identifier_set_sha256(values: Iterable[object]) -> str:
    digest = hashlib.sha256()
    for value in sorted({base_identifier(item) for item in values}):
        if not value:
            raise ValueError("identifier sets cannot contain empty values")
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def rows_membership_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    return identifier_set_sha256(row["uuid"] for row in rows)


def master_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    assignments = [
        {
            "uuid": base_identifier(row["uuid"]),
            "primary_view": str(row.get("primary_view", "")).strip(),
        }
        for row in rows
    ]
    assignments.sort(key=lambda row: (row["primary_view"], row["uuid"]))
    return canonical_sha256(assignments)


def sample_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    sample = [
        {
            "uuid": base_identifier(row["uuid"]),
            "primary_view": str(row.get("primary_view", "")).strip(),
            "sample_kind": str(row.get("sample_kind", "final-holdout")).strip(),
            "round_id": str(row.get("round_id", "")).strip(),
        }
        for row in rows
    ]
    sample.sort(key=lambda row: (row["sample_kind"], row["primary_view"], row["uuid"], row["round_id"]))
    return canonical_sha256(sample)


def source_fingerprint_payload(manifest: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": int(manifest["schema_version"]),
        "source_adapter": str(manifest["source_adapter"]),
        "source_identifier": str(manifest["source_identifier"]),
        "predicate_version": str(manifest["predicate_version"]),
        "observed_count": int(manifest["observed_count"]),
        "membership_sha256": str(manifest["membership_sha256"]),
        "library_fingerprint": str(manifest.get("library_fingerprint", "")),
    }


def build_source_manifest(
    rows: Iterable[Mapping[str, object]],
    *,
    source_adapter: str,
    source_identifier: str,
    predicate_version: str,
    library_fingerprint: str = "",
) -> dict[str, object]:
    rows = list(rows)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_adapter": source_adapter,
        "source_identifier": source_identifier,
        "predicate_version": predicate_version,
        "observed_count": len(rows),
        "membership_sha256": rows_membership_sha256(rows),
        "library_fingerprint": library_fingerprint,
        "artifact_sensitivity": "private-operational",
    }
    manifest["source_fingerprint"] = canonical_sha256(source_fingerprint_payload(manifest))
    return manifest


def validate_source_manifest(manifest: Mapping[str, object]) -> dict[str, object]:
    missing = SOURCE_MANIFEST_FIELDS - set(manifest)
    if missing:
        raise ValueError(f"source manifest missing fields: {', '.join(sorted(missing))}")
    if int(manifest["schema_version"]) != 1:
        raise ValueError("source manifest schema_version must be 1")
    if int(manifest["observed_count"]) < 1:
        raise ValueError("source manifest observed_count must be positive")
    membership = str(manifest["membership_sha256"])
    if len(membership) != 64:
        raise ValueError("source manifest membership_sha256 must be a SHA-256 digest")
    expected = canonical_sha256(source_fingerprint_payload(manifest))
    if str(manifest["source_fingerprint"]) != expected:
        raise ValueError("source manifest fingerprint does not match its contents")
    return dict(manifest)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _require_binding(report: Mapping[str, object], expected: Mapping[str, object], label: str) -> None:
    for field, value in expected.items():
        if report.get(field) != value:
            raise ValueError(f"{label} {field} does not match the release candidate")


def build_release_candidate(
    *,
    master: list[Mapping[str, object]],
    holds: list[Mapping[str, object]],
    sample: list[Mapping[str, object]],
    config: Mapping[str, object],
    source_manifest: Mapping[str, object],
    source_rows: list[Mapping[str, object]],
    evaluation_report: Mapping[str, object],
    validation_report: Mapping[str, object],
    split_audit_report: Mapping[str, object],
    release_class: str = "editor-field-verified",
) -> dict[str, object]:
    if release_class not in RELEASE_CLASSES:
        raise ValueError(f"unknown release class: {release_class}")
    if release_class == "publication-ready":
        raise ValueError("publication-ready requires a separate destination-specific clearance workflow")
    source = validate_source_manifest(source_manifest)
    if int(source["observed_count"]) != len(source_rows):
        raise ValueError("source inventory count does not match its manifest")
    if source["membership_sha256"] != rows_membership_sha256(source_rows):
        raise ValueError("source inventory membership does not match its manifest")
    master_ids = [base_identifier(row["uuid"]) for row in master]
    hold_ids = [base_identifier(row["uuid"]) for row in holds]
    if len(master_ids) != len(set(master_ids)):
        raise ValueError("release master contains duplicate identifiers")
    overlap = set(master_ids) & set(hold_ids)
    if overlap:
        raise ValueError(f"release master overlaps HOLD by {len(overlap)} identifiers")
    outside_source = set(master_ids) - {base_identifier(row["uuid"]) for row in source_rows}
    if outside_source:
        raise ValueError(f"release master contains {len(outside_source)} identifiers outside the frozen source")
    master_digest = master_sha256(master)
    sample_digest = sample_sha256(sample)
    config_digest = canonical_sha256(config)
    proposal_id = f"pfp-{master_digest[:16]}"
    expected = {
        "proposal_id": proposal_id,
        "master_sha256": master_digest,
        "evaluation_sample_sha256": sample_digest,
        "config_sha256": config_digest,
        "source_fingerprint": source["source_fingerprint"],
    }
    if evaluation_report.get("passed") is not True:
        raise ValueError("release candidate requires a passing final evaluation")
    if evaluation_report.get("evaluation_scope") != "final-holdout":
        raise ValueError("release candidate requires an untouched final-holdout evaluation")
    if evaluation_report.get("candidate_bound") is not True:
        raise ValueError("release candidate requires evaluation bound to the exact candidate")
    _require_binding(evaluation_report, expected, "evaluation report")
    if validation_report.get("status") != "PASS":
        raise ValueError("release candidate requires passing final validation")
    _require_binding(
        validation_report,
        {
            "proposal_id": proposal_id,
            "master_sha256": master_digest,
            "config_sha256": config_digest,
        },
        "validation report",
    )
    if split_audit_report.get("status") != "PASS":
        raise ValueError("release candidate requires a contamination-free evaluation split audit")
    final_rows = [row for row in sample if str(row.get("sample_kind", "final-holdout")) != "canary"]
    canary_rows = [row for row in sample if str(row.get("sample_kind", "")) == "canary"]
    split_membership = split_audit_report.get("membership_sha256", {})
    if split_membership.get("final_holdout") != rows_membership_sha256(final_rows):
        raise ValueError("evaluation split audit does not match the final-holdout sample")
    if split_membership.get("canaries") != rows_membership_sha256(canary_rows):
        raise ValueError("evaluation split audit does not match the regression canaries")
    payload: dict[str, object] = {
        "schema_version": 1,
        "release_class": release_class,
        "publication_clearance": False,
        "proposal_id": proposal_id,
        "source_fingerprint": source["source_fingerprint"],
        "source_membership_sha256": source["membership_sha256"],
        "config_sha256": config_digest,
        "master_sha256": master_digest,
        "hold_sha256": identifier_set_sha256(hold_ids),
        "evaluation_sample_sha256": sample_digest,
        "evaluation_report_sha256": canonical_sha256(evaluation_report),
        "validation_report_sha256": canonical_sha256(validation_report),
        "evaluation_split_sha256": str(split_audit_report.get("split_sha256", "")),
        "evaluation_split_report_sha256": canonical_sha256(split_audit_report),
        "master_count": len(master_ids),
        "hold_count": len(set(hold_ids)),
    }
    digest = canonical_sha256(payload)
    payload["release_candidate_sha256"] = digest
    payload["candidate_id"] = f"pfc-{digest[:20]}"
    return payload


def validate_release_candidate(candidate: Mapping[str, object]) -> dict[str, object]:
    required = {
        "schema_version",
        "release_class",
        "publication_clearance",
        "proposal_id",
        "source_fingerprint",
        "source_membership_sha256",
        "config_sha256",
        "master_sha256",
        "hold_sha256",
        "evaluation_sample_sha256",
        "evaluation_report_sha256",
        "validation_report_sha256",
        "evaluation_split_sha256",
        "evaluation_split_report_sha256",
        "master_count",
        "hold_count",
        "release_candidate_sha256",
        "candidate_id",
    }
    missing = required - set(candidate)
    if missing:
        raise ValueError(f"release candidate missing fields: {', '.join(sorted(missing))}")
    payload = dict(candidate)
    observed_digest = str(payload.pop("release_candidate_sha256"))
    observed_id = str(payload.pop("candidate_id"))
    expected_digest = canonical_sha256(payload)
    if observed_digest != expected_digest or observed_id != f"pfc-{expected_digest[:20]}":
        raise ValueError("release candidate identity does not match its contents")
    if candidate["release_class"] not in RELEASE_CLASSES:
        raise ValueError("release candidate has an unknown release class")
    if candidate["release_class"] == "editor-field-verified" and candidate["publication_clearance"] is not False:
        raise ValueError("editor-field release candidates cannot assert publication clearance")
    return dict(candidate)


def plan_sha256(plan: Mapping[str, object]) -> str:
    payload = dict(plan)
    payload.pop("plan_sha256", None)
    return canonical_sha256(payload)


def finalize_plan(plan: Mapping[str, object]) -> dict[str, object]:
    result = dict(plan)
    result["plan_sha256"] = plan_sha256(result)
    return result


def validate_plan(plan: Mapping[str, object]) -> dict[str, object]:
    if int(plan.get("schema_version", 0)) != 2:
        raise ValueError("catalog plan schema_version must be 2")
    if plan.get("safety_mode") != "create-folders-albums-and-add-membership-only":
        raise ValueError("catalog plan requests an unsupported mutation boundary")
    if str(plan.get("plan_sha256", "")) != plan_sha256(plan):
        raise ValueError("catalog plan digest does not match its contents")
    candidate_value = plan.get("release_candidate")
    if not isinstance(candidate_value, Mapping):
        raise ValueError("catalog plan requires an embedded release candidate")
    candidate = validate_release_candidate(candidate_value)
    if plan.get("candidate_id") != candidate["candidate_id"]:
        raise ValueError("catalog plan candidate_id does not match its release candidate")
    if plan.get("source_membership_sha256") != candidate["source_membership_sha256"]:
        raise ValueError("catalog plan source membership does not match its release candidate")
    source_value = plan.get("source")
    if not isinstance(source_value, Mapping):
        raise ValueError("catalog plan requires its frozen source manifest")
    source = validate_source_manifest(source_value)
    if source["source_fingerprint"] != candidate["source_fingerprint"]:
        raise ValueError("catalog plan source fingerprint does not match its release candidate")
    if source["membership_sha256"] != candidate["source_membership_sha256"]:
        raise ValueError("catalog plan frozen source membership does not match its release candidate")

    albums_value = plan.get("albums")
    if not isinstance(albums_value, list):
        raise ValueError("catalog plan albums must be a list")
    album_keys: set[str] = set()
    master_ids: list[str] | None = None
    assigned_rows: list[dict[str, str]] = []
    assigned_ids: list[str] = []
    for album in albums_value:
        if not isinstance(album, Mapping):
            raise ValueError("catalog plan albums must be objects")
        key = str(album.get("key", "")).strip()
        identifiers = album.get("asset_identifiers")
        if not key or key in album_keys or not isinstance(identifiers, list):
            raise ValueError("catalog plan album keys must be unique and contain identifier lists")
        album_keys.add(key)
        normalized = [base_identifier(value) for value in identifiers]
        if any(not value for value in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError(f"catalog plan album {key} contains empty or duplicate identifiers")
        if key == "master":
            master_ids = normalized
        elif key.startswith("view-") and key.removeprefix("view-"):
            view = key.removeprefix("view-")
            assigned_ids.extend(normalized)
            assigned_rows.extend({"uuid": value, "primary_view": view} for value in normalized)
        else:
            raise ValueError(f"catalog plan contains unsupported album key: {key}")
    if master_ids is None:
        raise ValueError("catalog plan requires exactly one master album")
    if len(assigned_ids) != len(set(assigned_ids)):
        raise ValueError("catalog plan assigns one or more identifiers to multiple views")
    if set(assigned_ids) != set(master_ids):
        raise ValueError("catalog plan view memberships do not exactly partition the master")
    if len(master_ids) != int(candidate["master_count"]):
        raise ValueError("catalog plan master count does not match its release candidate")
    if master_sha256(assigned_rows) != candidate["master_sha256"]:
        raise ValueError("catalog plan memberships or view assignments do not match its release candidate")
    if int(plan.get("expected_master_count", -1)) != len(master_ids):
        raise ValueError("catalog plan expected_master_count does not match its master album")
    if int(plan.get("expected_hold_count", -1)) != int(candidate["hold_count"]):
        raise ValueError("catalog plan expected_hold_count does not match its release candidate")
    return dict(plan)
