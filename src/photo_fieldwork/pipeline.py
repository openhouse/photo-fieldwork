from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from . import __version__
from .feedback import JUDGMENTS, sample_fingerprint, validate_feedback
from .integrity import verify_evaluation_seal
from .release import REQUIRED_HELPER_CAPABILITIES, validate_helper_profile
from .safety import may_enter_general_master, normalize_safety_state


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
    if int(config.get("minimum_decisive_per_view", 0)) < 0:
        raise ValueError("minimum_decisive_per_view cannot be negative")
    target = int(config["target_count"])
    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
    if named_floor + person_free_floor > target:
        raise ValueError("named-people and person-free floors cannot both fit within target_count")
    fractions = [
        "minimum_eval_precision",
        "minimum_eval_coverage",
        "maximum_eval_uncertainty",
        "minimum_view_precision",
        "maximum_view_uncertainty",
        "minimum_named_people_fraction",
        "minimum_person_free_fraction",
    ]
    for key in fractions:
        if key in config and not 0 <= float(config[key]) <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
    uncertainty_views = set(config.get("uncertainty_views", []))
    unknown_uncertainty = uncertainty_views - set(view_ids)
    if unknown_uncertainty:
        raise ValueError(f"uncertainty_views are not configured: {', '.join(sorted(unknown_uncertainty))}")
    return config


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"no rows found in {path}")
    required = {"uuid", "filename"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"missing required columns: {', '.join(sorted(missing))}")
    return rows


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str] | None = None) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def split_values(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def stable_noise(seed: int, uuid: str) -> float:
    digest = hashlib.sha256(f"{seed}:{uuid}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def is_hold(row: dict[str, str]) -> bool:
    return not may_enter_general_master(row.get("safety_status", "clear")) or truthy(row.get("hidden")) or truthy(
        row.get("missing")
    )


def partition_safety_rows(inventory: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Conservatively propagate unresolved safety states across related images."""
    unresolved_duplicates = {
        row.get("duplicate_group", "").strip()
        for row in inventory
        if is_hold(row) and row.get("duplicate_group", "").strip()
    }
    unresolved_bursts = {
        row.get("burst_group", "").strip()
        for row in inventory
        if is_hold(row) and row.get("burst_group", "").strip()
    }
    eligible = []
    holds = []
    for source_row in inventory:
        row = dict(source_row)
        related_by = []
        if row.get("duplicate_group", "").strip() in unresolved_duplicates:
            related_by.append("duplicate_group")
        if row.get("burst_group", "").strip() in unresolved_bursts:
            related_by.append("burst_group")
        if is_hold(row) or related_by:
            if may_enter_general_master(row.get("safety_status", "clear_automated")):
                row["safety_status"] = "hold_automated"
            else:
                row["safety_status"] = normalize_safety_state(row.get("safety_status"))
            if truthy(row.get("hidden")) or truthy(row.get("missing")):
                row["safety_status"] = "hold_automated"
            if related_by and not is_hold(source_row):
                existing = str(row.get("safety_reason", "")).strip()
                reason = f"unresolved safety state in related {', '.join(related_by)}"
                row["safety_reason"] = "; ".join(part for part in (existing, reason) if part)
                row["safety_propagated_by"] = ";".join(related_by)
            holds.append(row)
        else:
            eligible.append(row)
    return eligible, holds


def attention_score(row: dict[str, str]) -> float:
    favorite = truthy(row.get("favorite"))
    edited = truthy(row.get("edited"))
    if favorite and edited:
        return 12.0
    if favorite:
        return 7.0
    if edited:
        return 5.0
    return 0.0


def evidence_score(row: dict[str, str]) -> float:
    confidence = str(row.get("evidence_confidence", "unknown")).lower()
    score = {"high": 12.0, "medium": 6.0, "low": 2.0, "unknown": 0.0}.get(confidence, 0.0)
    if split_values(row.get("persons")):
        score += 4.0
    if row.get("visible_context"):
        score += 3.0
    return score


def cluster_representatives(rows: list[dict[str, str]], config: dict) -> list[dict[str, str]]:
    """Reduce exact duplicates and bursts before quota selection.

    Aesthetic score is intentionally considered only inside an existing cluster.
    It never ranks unrelated photographs.
    """
    seed = int(config["seed"])
    exact_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    singles: list[dict[str, str]] = []
    for row in rows:
        group = row.get("duplicate_group", "").strip()
        (exact_groups[group] if group else singles).append(row)

    def cluster_rank(row: dict[str, str]) -> tuple:
        try:
            aesthetic = float(row.get("aesthetic_score") or 0)
        except ValueError:
            aesthetic = 0.0
        return (
            truthy(row.get("favorite")) and truthy(row.get("edited")),
            truthy(row.get("favorite")),
            truthy(row.get("edited")),
            aesthetic,
            stable_noise(seed, row["uuid"]),
        )

    reduced = singles + [max(group, key=cluster_rank) for group in exact_groups.values()]
    burst_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    unburst: list[dict[str, str]] = []
    for row in reduced:
        group = row.get("burst_group", "").strip()
        (burst_groups[group] if group else unburst).append(row)
    limit = int(config.get("burst_limit", 2))
    for group in burst_groups.values():
        unburst.extend(sorted(group, key=cluster_rank, reverse=True)[:limit])
    return unburst


def candidate_view_scores(row: dict[str, str], config: dict) -> dict[str, float]:
    configured = {view["id"] for view in config["views"]}
    scores: dict[str, float] = {}
    raw = str(row.get("candidate_view_scores", "")).strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid candidate_view_scores for {row['uuid']}: {error}") from error
        if not isinstance(parsed, dict):
            raise ValueError(f"candidate_view_scores must be an object for {row['uuid']}")
        for view, score in parsed.items():
            if str(view) in configured:
                scores[str(view)] = float(score)
    for view in split_values(row.get("candidate_views")):
        if view in configured:
            scores.setdefault(view, 0.0)
    if not scores:
        scores[config["unclassified_view"]] = 0.0
    return scores


def ordered_candidate_views(row: dict[str, str], config: dict) -> list[str]:
    scores = candidate_view_scores(row, config)
    return sorted(scores, key=lambda view: (-scores[view], view))


def choose_primary_view(row: dict[str, str], config: dict) -> str:
    return ordered_candidate_views(row, config)[0]


def rank_row(row: dict[str, str], config: dict) -> float:
    return attention_score(row) + evidence_score(row) + stable_noise(int(config["seed"]), row["uuid"])


def assign_exact_quotas(rows: list[dict], config: dict) -> tuple[list[dict], dict[str, int]]:
    """Assign one primary view per photograph with deterministic augmenting paths."""
    quotas = {view["id"]: int(view["quota"]) for view in config["views"]}
    assigned: dict[str, list[dict]] = {view: [] for view in quotas}
    row_assignment: dict[str, str] = {}

    def try_assign(row: dict, seen_rows: set[str], seen_views: set[str]) -> bool:
        for view in ordered_candidate_views(row, config):
            if quotas[view] == 0 or view in seen_views:
                continue
            if len(assigned[view]) < quotas[view]:
                assigned[view].append(row)
                row_assignment[row["uuid"]] = view
                return True
            donors = sorted(assigned[view], key=lambda item: (rank_row(item, config), item["uuid"]))
            for donor in donors:
                if donor["uuid"] in seen_rows:
                    continue
                assigned[view].remove(donor)
                row_assignment.pop(donor["uuid"], None)
                if try_assign(donor, seen_rows | {donor["uuid"]}, seen_views | {view}):
                    assigned[view].append(row)
                    row_assignment[row["uuid"]] = view
                    return True
                assigned[view].append(donor)
                row_assignment[donor["uuid"]] = view
        return False

    ordered = sorted(rows, key=lambda row: (-rank_row(row, config), len(ordered_candidate_views(row, config)), row["uuid"]))
    target = int(config["target_count"])
    for row in ordered:
        if len(row_assignment) == target:
            break
        try_assign(row, {row["uuid"]}, set())

    shortfalls = {view: quota - len(assigned[view]) for view, quota in quotas.items() if len(assigned[view]) != quota}
    if shortfalls:
        capacity = Counter(view for row in rows for view in ordered_candidate_views(row, config))
        detail = ", ".join(
            f"{view}: short {amount}, candidates {capacity[view]}, quota {quotas[view]}"
            for view, amount in sorted(shortfalls.items())
        )
        raise ValueError(f"candidate field cannot satisfy exact view quotas ({detail})")

    selected = []
    for view in quotas:
        for row in assigned[view]:
            item = dict(row)
            item["primary_view"] = view
            item["secondary_views"] = ";".join(candidate for candidate in ordered_candidate_views(row, config) if candidate != view)
            selected.append(item)
    return selected, {view: len(assigned[view]) for view in quotas}


def select(inventory: list[dict[str, str]], config: dict) -> tuple[list[dict], list[dict], dict]:
    eligible_rows, holds = partition_safety_rows(inventory)
    eligible = cluster_representatives(eligible_rows, config)
    for row in eligible:
        row["safety_status"] = normalize_safety_state(row.get("safety_status"))
        row["score_total"] = f"{rank_row(row, config):.6f}"
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_tier"] = "evidence" if confidence in {"high", "medium"} else "exploratory"

    selected, _ = assign_exact_quotas(eligible, config)
    for row in selected:
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_reason"] = "; ".join(
            reason
            for reason in [
                f"retrieval hypothesis {row['primary_view']}",
                f"visible context: {row.get('visible_context')}" if row.get("visible_context") else "",
                f"evidence confidence: {confidence}",
                "pre-existing named people" if split_values(row.get("persons")) else "",
                "prior favorite/edit attention" if attention_score(row) else "",
            ]
            if reason
        )

    target = int(config["target_count"])
    selected_ids = {row["uuid"] for row in selected}

    def enforce_floor(predicate, required: int, reason: str) -> None:
        nonlocal selected, selected_ids
        current = sum(predicate(row) for row in selected)
        if current >= required:
            return
        candidates = sorted(
            (dict(row) for row in eligible if row["uuid"] not in selected_ids and predicate(row)),
            key=lambda row: float(row["score_total"]),
            reverse=True,
        )
        while current < required and candidates:
            incoming = candidates.pop(0)
            allowed_views = set(ordered_candidate_views(incoming, config))
            donors = sorted(
                (row for row in selected if not predicate(row) and row["primary_view"] in allowed_views),
                key=lambda row: (float(row["score_total"]), row["uuid"]),
            )
            if not donors:
                continue
            outgoing = donors[0]
            incoming["primary_view"] = outgoing["primary_view"]
            incoming["secondary_views"] = ";".join(
                view for view in ordered_candidate_views(incoming, config) if view != incoming["primary_view"]
            )
            confidence = str(incoming.get("evidence_confidence", "unknown")).lower()
            incoming["selection_reason"] = "; ".join(
                reason
                for reason in [
                    f"retrieval hypothesis {incoming['primary_view']}",
                    f"visible context: {incoming.get('visible_context')}" if incoming.get("visible_context") else "",
                    f"evidence confidence: {confidence}",
                    "pre-existing named people" if split_values(incoming.get("persons")) else "",
                    "prior favorite/edit attention" if attention_score(incoming) else "",
                    f"diversity floor: {reason}",
                ]
                if reason
            )
            selected.remove(outgoing)
            selected_ids.remove(outgoing["uuid"])
            selected.append(incoming)
            selected_ids.add(incoming["uuid"])
            current += 1

    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
    enforce_floor(lambda row: bool(split_values(row.get("persons"))), named_floor, "named relationships")
    enforce_floor(lambda row: not bool(split_values(row.get("persons"))), person_free_floor, "person-free material context")
    if sum(bool(split_values(row.get("persons"))) for row in selected) < named_floor:
        raise ValueError("candidate field cannot satisfy minimum_named_people_fraction")
    if sum(not bool(split_values(row.get("persons"))) for row in selected) < person_free_floor:
        raise ValueError("candidate field cannot satisfy minimum_person_free_fraction")
    selected.sort(key=lambda row: (row["primary_view"], -float(row["score_total"]), row["uuid"]))
    summary = {
        "inventory_count": len(inventory),
        "eligible_after_cluster_reduction": len(eligible),
        "hold_count": len(holds),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
    }
    return selected, holds, summary


def make_sample(master: list[dict[str, str]], per_view: int, seed: int) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in master:
        grouped[row.get("primary_view", "unknown")].append(row)
    sample: list[dict] = []
    rng = random.Random(seed)
    for view, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: float(row.get("score_total") or 0))
        if len(ordered) <= per_view:
            picks = ordered
        else:
            positions = {0, len(ordered) // 2, len(ordered) - 1}
            while len(positions) < per_view:
                positions.add(rng.randrange(len(ordered)))
            picks = [ordered[index] for index in sorted(positions)[:per_view]]
        for row in picks:
            item = dict(row)
            item["judgment"] = ""
            item["visible_reason"] = ""
            item["safety_status"] = normalize_safety_state(item.get("safety_status"))
            item["error_category"] = ""
            item["round_id"] = ""
            item["reviewer_lens"] = ""
            sample.append(item)
    fingerprint = sample_fingerprint(sample)
    for item in sample:
        item["sample_hash"] = fingerprint
    return sample


def evaluate(feedback: list[dict[str, str]], config: dict) -> tuple[dict, bool]:
    unknown = sorted(
        {str(row.get("judgment", "")).strip().lower() for row in feedback}
        - JUDGMENTS
        - {""}
    )
    if unknown:
        raise ValueError(f"unknown evaluation judgments: {', '.join(unknown)}")
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in JUDGMENTS]
    if judged:
        validate_feedback(feedback, judged, require_complete=False)

    def metrics(rows: list[dict], total: int) -> dict:
        fit = sum(row["judgment"].strip().lower() == "fit" for row in rows)
        reject = sum(row["judgment"].strip().lower() == "reject" for row in rows)
        uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in rows)
        decisive = fit + reject
        judged_count = len(rows)
        return {
            "sample_count": total,
            "judged_count": judged_count,
            "decisive_count": decisive,
            "fit_count": fit,
            "reject_count": reject,
            "uncertain_count": uncertain,
            "coverage": round(judged_count / total, 4) if total else 0.0,
            "decisive_precision": round(fit / decisive, 4) if decisive else None,
            "fit_rate": round(fit / judged_count, 4) if judged_count else 0.0,
            "reject_rate": round(reject / judged_count, 4) if judged_count else 0.0,
            "uncertainty_rate": round(uncertain / judged_count, 4) if judged_count else 0.0,
        }

    overall = metrics(judged, len(feedback))
    by_view = {}
    for view in sorted({row.get("primary_view", "unknown") for row in feedback}):
        sampled = [row for row in feedback if row.get("primary_view", "unknown") == view]
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        by_view[view] = metrics(rows, len(sampled))

    gates = {
        "minimum_coverage": float(config.get("minimum_eval_coverage", 0.8)),
        "minimum_decisive_precision": float(config.get("minimum_eval_precision", 0.75)),
        "maximum_uncertainty_rate": float(config.get("maximum_eval_uncertainty", 1.0)),
        "minimum_decisive_per_view": int(config.get("minimum_decisive_per_view", 0)),
        "minimum_view_decisive_precision": float(config.get("minimum_view_precision", 0.0)),
        "maximum_view_uncertainty_rate": float(config.get("maximum_view_uncertainty", 1.0)),
    }
    failures = []
    if overall["coverage"] < gates["minimum_coverage"]:
        failures.append("overall coverage below minimum")
    if overall["decisive_precision"] is None or overall["decisive_precision"] < gates["minimum_decisive_precision"]:
        failures.append("overall decisive precision below minimum")
    if overall["uncertainty_rate"] > gates["maximum_uncertainty_rate"]:
        failures.append("overall uncertainty rate above maximum")
    uncertainty_views = set(config.get("uncertainty_views", []))
    material_views = {view["id"] for view in config["views"] if int(view["quota"]) > 0} - uncertainty_views
    for view in sorted(material_views):
        values = by_view.get(view)
        if not values or values["sample_count"] == 0:
            failures.append(f"view {view} was not sampled")
            continue
        if values["decisive_count"] < gates["minimum_decisive_per_view"]:
            failures.append(f"view {view} has too few decisive judgments")
        precision = values["decisive_precision"]
        if precision is None or precision < gates["minimum_view_decisive_precision"]:
            failures.append(f"view {view} decisive precision below minimum")
        if values["uncertainty_rate"] > gates["maximum_view_uncertainty_rate"]:
            failures.append(f"view {view} uncertainty rate above maximum")

    passed = not failures
    report = {
        **overall,
        "metric_definitions": {
            "coverage": "judged_count / sample_count",
            "decisive_precision": "fit_count / (fit_count + reject_count)",
            "fit_rate": "fit_count / judged_count",
            "reject_rate": "reject_count / judged_count",
            "uncertainty_rate": "uncertain_count / judged_count",
        },
        "gates": gates,
        "gate_failures": failures,
        "passed": passed,
        "by_view": by_view,
    }
    return report, passed


def validate(master: list[dict[str, str]], holds: list[dict[str, str]], config: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    ids = [row["uuid"] for row in master]
    hold_ids = {row["uuid"] for row in holds}
    if len(master) != int(config["target_count"]):
        errors.append(f"expected {config['target_count']} selected rows, found {len(master)}")
    if len(ids) != len(set(ids)):
        errors.append("master contains duplicate UUIDs")
    overlap = set(ids) & hold_ids
    if overlap:
        errors.append(f"master overlaps safety holds by {len(overlap)} rows")
    if any(not row.get("selection_reason") for row in master):
        errors.append("one or more selected rows lack a selection reason")
    unsafe = [row["uuid"] for row in master if not may_enter_general_master(row.get("safety_status"))]
    if unsafe:
        errors.append(f"master contains {len(unsafe)} rows outside allowed safety states")
    expected_counts = {view["id"]: int(view["quota"]) for view in config["views"]}
    view_counts = Counter(row.get("primary_view") for row in master)
    quota_errors = {
        view: {"expected": quota, "actual": view_counts.get(view, 0)}
        for view, quota in expected_counts.items()
        if view_counts.get(view, 0) != quota
    }
    unknown_views = sorted(set(view_counts) - set(expected_counts))
    if quota_errors:
        errors.append(f"view quotas differ: {json.dumps(quota_errors, sort_keys=True)}")
    if unknown_views:
        errors.append(f"master contains unknown views: {', '.join(unknown_views)}")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "view_counts": dict(sorted(view_counts.items(), key=lambda item: str(item[0]))),
        "expected_view_counts": expected_counts,
        "quota_errors": quota_errors,
        "unsafe_master_count": len(unsafe),
    }
    return errors, metrics


def build_catalog_plan(
    master: list[dict[str, str]],
    config: dict,
    plan_id: str,
    source_title: str,
    source_identifier: str,
    source_profile: dict | None = None,
    holds: list[dict] | None = None,
    evaluation_seal: dict | None = None,
    evaluation_report: dict | None = None,
    helper_profile: dict | None = None,
) -> dict:
    """Build an adapter-neutral, membership-only catalog plan."""
    view_labels = {view["id"]: view["label"] for view in config["views"]}
    folders = [
        {
            "key": "root",
            "title": str(config.get("catalog_root_title", "Photo Fieldwork")),
            "parent_key": None,
        },
        {
            "key": "version",
            "title": str(config.get("catalog_version_title", plan_id)),
            "parent_key": "root",
        },
        {
            "key": "private",
            "title": str(config.get("catalog_private_title", f"{plan_id} - PRIVATE")),
            "parent_key": "root",
        },
    ]
    albums = [
        {
            "key": "master",
            "role": "editor-master",
            "visibility": "private-editor",
            "parent_folder_key": "version",
            "title": f"00 MASTER - {len(master):,}",
            "asset_identifiers": [row["uuid"] for row in master],
        }
    ]
    for view_id in sorted({row["primary_view"] for row in master}):
        asset_ids = [row["uuid"] for row in master if row["primary_view"] == view_id]
        albums.append(
            {
                "key": f"view-{view_id}",
                "role": "editor-view",
                "visibility": "private-editor",
                "parent_folder_key": "version",
                "title": f"{view_id} {view_labels.get(view_id, 'Unlabeled View')} - {len(asset_ids):,}",
                "asset_identifiers": asset_ids,
            }
        )
    if holds:
        albums.append(
            {
                "key": "safety-hold",
                "role": "safety-hold",
                "visibility": "restricted-private",
                "parent_folder_key": "private",
                "title": f"AUTOMATED SAFETY HOLD - {len(holds):,}",
                "asset_identifiers": [row["uuid"] for row in holds],
            }
        )
    source = source_profile or {
        "schema_version": 1,
        "id": source_identifier,
        "kind": "catalog-album",
        "scope": source_title,
        "actual_count": None,
        "fingerprint": None,
    }
    required_verification = [
        "master equals reviewed master manifest",
        "exact album membership",
        "all secondary editor views are subsets of master",
        "safety hold is disjoint from editor master",
    ]
    if source.get("fingerprint"):
        required_verification.extend(
            [
                "all planned assets belong to the exact source fingerprint",
                "source fingerprint is unchanged",
            ]
        )
    else:
        required_verification.append("legacy source identifier and count are unchanged")
    candidate_binding = None
    if evaluation_seal is not None:
        if evaluation_report is None:
            raise ValueError("evaluation report is required with an evaluation seal")
        seal_errors = verify_evaluation_seal(evaluation_seal, master, config, evaluation_report)
        if seal_errors:
            raise ValueError(f"evaluation seal does not authorize this plan: {'; '.join(seal_errors)}")
        candidate_binding = {
            "evaluation_seal_fingerprint": evaluation_seal["seal_fingerprint"],
            "master_fingerprint": evaluation_seal["master_fingerprint"],
            "config_fingerprint": evaluation_seal["config_fingerprint"],
            "evaluation_report_fingerprint": evaluation_seal["evaluation_report_fingerprint"],
        }
        required_verification.append("catalog plan matches the passing evaluation seal")
    helper_requirement = None
    if helper_profile is not None:
        helper_errors = validate_helper_profile(helper_profile, REQUIRED_HELPER_CAPABILITIES, 2)
        if helper_errors:
            raise ValueError(f"helper profile cannot execute this plan: {'; '.join(helper_errors)}")
        helper_requirement = {
            "bundle_identifier": helper_profile["bundle_identifier"],
            "binary_sha256": helper_profile["binary_sha256"],
            "required_capabilities": list(REQUIRED_HELPER_CAPABILITIES),
            "plan_schema_version": 2,
        }
        required_verification.append("execution receipt matches the authorized helper and exact plan digest")
    return {
        "schema_version": 2,
        "tool_version": __version__,
        "plan_id": plan_id,
        "release_class": "editor-field",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source": source,
        "candidate_binding": candidate_binding,
        "helper_requirement": helper_requirement,
        "expected_master_count": len(master),
        "write_test_count": min(10, len(master)),
        "folders": folders,
        "albums": albums,
        "required_verification": required_verification,
    }
