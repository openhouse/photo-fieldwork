from __future__ import annotations

import csv
import hashlib
import json
import random
import math
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


JUDGMENTS = {"fit", "reject", "uncertain"}
ASSIGNMENT_STATUSES = {"assigned", "unclassified", "sparse-hypothesis"}


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 2:
        raise ValueError("config schema_version must be 2")
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
    named_fraction = float(config.get("minimum_named_people_fraction", 0))
    person_free_fraction = float(config.get("minimum_person_free_fraction", 0))
    if named_fraction + person_free_fraction > 1:
        raise ValueError("named-people and person-free minimum fractions cannot sum above 1")
    invalid_modes = {
        str(view.get("evaluation_mode", "material"))
        for view in config["views"]
        if str(view.get("evaluation_mode", "material")) not in {"material", "sparse-hypothesis"}
    }
    if invalid_modes:
        raise ValueError(f"invalid view evaluation modes: {', '.join(sorted(invalid_modes))}")
    return config


def read_csv(path: Path, allow_empty: bool = False) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        rows = list(reader)
    if not rows:
        if allow_empty and {"uuid", "filename"}.issubset(fields):
            return []
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


def master_sha256(rows: Iterable[dict[str, str]]) -> str:
    """Hash exact membership and reviewed editorial assignment."""
    payload = [
        {
            "uuid": str(row["uuid"]).split("/", 1)[0],
            "assigned_view": str(row.get("assigned_view") or row.get("primary_view") or ""),
        }
        for row in rows
    ]
    payload.sort(key=lambda row: (row["assigned_view"], row["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def uuid_sha256(rows: Iterable[dict[str, str]]) -> str:
    identifiers = sorted({str(row["uuid"]).split("/", 1)[0] for row in rows})
    return hashlib.sha256(("\n".join(identifiers) + "\n").encode()).hexdigest()


def is_hold(row: dict[str, str]) -> bool:
    safety = str(row.get("safety_status", "clear")).strip().lower()
    return (
        safety.startswith("hold")
        or safety in {"unavailable", "review-required", "needs-review", "unknown"}
        or truthy(row.get("hidden"))
        or truthy(row.get("missing"))
    )


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
        group = (
            row.get("perceptual_cluster_id", "").strip()
            or row.get("duplicate_group", "").strip()
            or row.get("duplicate_group_id", "").strip()
        )
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


def choose_primary_view(row: dict[str, str], config: dict) -> str:
    configured = {view["id"] for view in config["views"]}
    assigned = str(row.get("assigned_view", "")).strip()
    if not assigned:
        raise ValueError(
            f"inventory row {row.get('uuid', '<unknown>')} lacks assigned_view; "
            "candidate_views are retrieval hypotheses, not editorial assignments"
        )
    if assigned not in configured:
        raise ValueError(f"inventory row {row.get('uuid', '<unknown>')} has unknown assigned_view {assigned}")
    status = str(row.get("assignment_status", "assigned")).strip() or "assigned"
    if status not in ASSIGNMENT_STATUSES:
        raise ValueError(f"inventory row {row.get('uuid', '<unknown>')} has invalid assignment_status {status}")
    return assigned


def rank_row(row: dict[str, str], config: dict) -> float:
    return attention_score(row) + evidence_score(row) + stable_noise(int(config["seed"]), row["uuid"])


def select(inventory: list[dict[str, str]], config: dict) -> tuple[list[dict], list[dict], dict]:
    holds = [dict(row) for row in inventory if is_hold(row)]
    eligible = cluster_representatives([dict(row) for row in inventory if not is_hold(row)], config)
    for row in eligible:
        row["primary_view"] = choose_primary_view(row, config)
        row["score_total"] = f"{rank_row(row, config):.6f}"
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_tier"] = "evidence" if confidence in {"high", "medium"} else "exploratory"
        row["selection_reason"] = "; ".join(
            reason
            for reason in [
                f"editorial assignment {row['primary_view']}",
                f"assignment: {row.get('assignment_reason')}" if row.get("assignment_reason") else "",
                f"retrieval hypotheses: {row.get('candidate_views')}" if row.get("candidate_views") else "",
                f"visible context: {row.get('visible_context')}" if row.get("visible_context") else "",
                f"evidence confidence: {confidence}",
                "pre-existing named people" if split_values(row.get("persons")) else "",
                "prior favorite/edit attention" if attention_score(row) else "",
                f"retrieval channels: {row.get('retrieval_channels')}" if row.get("retrieval_channels") else "",
            ]
            if reason
        )

    by_view: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        by_view[row["primary_view"]].append(row)
    for rows in by_view.values():
        rows.sort(key=lambda row: float(row["score_total"]), reverse=True)

    quotas = {str(view["id"]): int(view["quota"]) for view in config["views"]}
    deficits = {
        view: {"quota": quota, "eligible": len(by_view.get(view, [])), "deficit": quota - len(by_view.get(view, []))}
        for view, quota in quotas.items()
        if len(by_view.get(view, [])) < quota
    }
    if deficits:
        raise ValueError(
            "unable to satisfy exact reviewed view quotas; "
            f"deficits={json.dumps(deficits, sort_keys=True)}"
        )

    selected: list[dict] = []
    selected_ids: set[str] = set()
    for view_id, quota in quotas.items():
        for row in by_view[view_id][:quota]:
            selected.append(row)
            selected_ids.add(row["uuid"])

    target = int(config["target_count"])

    def enforce_floor(predicate, required: int, reason: str) -> None:
        nonlocal selected, selected_ids
        current = sum(predicate(row) for row in selected)
        while current < required:
            options = []
            for incoming in eligible:
                if incoming["uuid"] in selected_ids or not predicate(incoming):
                    continue
                donors = [
                    row for row in selected
                    if row["primary_view"] == incoming["primary_view"] and not predicate(row)
                ]
                if not donors:
                    continue
                outgoing = min(donors, key=lambda row: (float(row["score_total"]), row["uuid"]))
                score_loss = float(outgoing["score_total"]) - float(incoming["score_total"])
                options.append((score_loss, incoming["uuid"], outgoing["uuid"], incoming, outgoing))
            if not options:
                break
            _, _, _, incoming, outgoing = min(options, key=lambda item: item[:3])
            selected.remove(outgoing)
            selected_ids.remove(outgoing["uuid"])
            incoming["selection_reason"] += f"; diversity floor: {reason}"
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
    final_view_counts = Counter(row["primary_view"] for row in selected)
    quota_mismatches = {
        view: {"expected": quota, "actual": final_view_counts.get(view, 0)}
        for view, quota in quotas.items()
        if final_view_counts.get(view, 0) != quota
    }
    if quota_mismatches:
        raise ValueError(
            "selection changed exact reviewed view quotas; "
            f"mismatches={json.dumps(quota_mismatches, sort_keys=True)}"
        )
    selected.sort(key=lambda row: (row["primary_view"], -float(row["score_total"]), row["uuid"]))
    digest = master_sha256(selected)
    proposal_id = f"pfp-{digest[:16]}"
    for row in selected:
        row["master_sha256"] = digest
        row["proposal_id"] = proposal_id
    summary = {
        "inventory_count": len(inventory),
        "eligible_after_cluster_reduction": len(eligible),
        "hold_count": len(holds),
        "selected_count": len(selected),
        "assignment_method": "reviewed-exclusive-exact-quota",
        "view_quotas": quotas,
        "view_counts": dict(sorted(final_view_counts.items())),
        "quota_deficits": {},
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "master_sha256": digest,
        "proposal_id": proposal_id,
    }
    return selected, holds, summary


def make_sample(
    master: list[dict[str, str]],
    per_view: int,
    seed: int,
    views: set[str] | None = None,
    round_id: str = "round-01",
) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in master:
        grouped[row.get("primary_view", "unknown")].append(row)
    sample: list[dict] = []
    rng = random.Random(seed)
    for view, rows in sorted(grouped.items()):
        if views is not None and view not in views:
            continue
        ordered = sorted(rows, key=lambda row: float(row.get("score_total") or 0))
        if len(ordered) <= per_view:
            picks = ordered
        else:
            if per_view == 1:
                positions = {len(ordered) // 2}
            elif per_view == 2:
                positions = {0, len(ordered) - 1}
            else:
                positions = {0, len(ordered) // 2, len(ordered) - 1}
            while len(positions) < per_view:
                positions.add(rng.randrange(len(ordered)))
            picks = [ordered[index] for index in sorted(positions)[:per_view]]
        for row in picks:
            item = dict(row)
            item["view_selected_count"] = str(len(rows))
            item["sampling_reason"] = (
                "full view audit" if len(rows) <= per_view
                else "score boundary and deterministic random stratum sample"
            )
            item["judgment"] = ""
            item["visible_reason"] = ""
            item["evaluation_safety_state"] = ""
            item["error_category"] = ""
            item["round_id"] = round_id
            item["reviewer_lens"] = ""
            sample.append(item)
    return sample


def evaluate(
    feedback: list[dict[str, str]],
    config: dict,
    master: list[dict[str, str]] | None = None,
) -> tuple[dict, bool]:
    proposal_ids = {row.get("proposal_id", "").strip() for row in feedback}
    master_hashes = {row.get("master_sha256", "").strip() for row in feedback}
    if "" in proposal_ids or len(proposal_ids) != 1:
        raise ValueError("evaluation rows must share one non-empty proposal_id")
    if "" in master_hashes or len(master_hashes) != 1:
        raise ValueError("evaluation rows must share one non-empty master_sha256")
    unknown = sorted({
        row.get("judgment", "").strip().lower()
        for row in feedback
        if row.get("judgment", "").strip()
        and row.get("judgment", "").strip().lower() not in JUDGMENTS
    })
    if unknown:
        raise ValueError(f"unknown evaluation judgments: {', '.join(unknown)}")
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in JUDGMENTS]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / len(feedback) if feedback else 0.0
    precision = fit / (fit + reject) if fit + reject else 0.0
    missing_reasons = sum(
        not str(row.get("visible_reason") or row.get("evaluation_note") or "").strip()
        for row in judged
    )
    missing_safety_states = sum(
        not str(row.get("evaluation_safety_state", "")).strip()
        for row in judged
    )
    missing_error_categories = sum(
        row["judgment"].strip().lower() in {"reject", "uncertain"}
        and not row.get("error_category", "").strip()
        for row in judged
    )
    safety_regressions = sum(
        str(row.get("evaluation_safety_state", "")).strip().lower()
        in {
            "hold", "hold-automated", "hold-human-sensitive", "unavailable",
            "review-required", "needs-review", "unknown",
        }
        for row in judged
    )
    by_view = {}
    failed_views = []
    configured_views = {
        str(view["id"]): view for view in config["views"] if int(view.get("quota", 0)) > 0
    }
    default_view_precision = float(
        config.get(
            "minimum_view_eval_precision",
            config.get("minimum_eval_precision_per_view", config.get("minimum_eval_precision", 0.75)),
        )
    )
    default_decisive = int(config.get("minimum_view_eval_sample", config.get("minimum_decisive_per_view", 1)))
    maximum_uncertainty = float(
        config.get("maximum_eval_uncertainty", config.get("maximum_eval_uncertainty_per_view", 1.0))
    )
    view_ids = set(configured_views) | {row.get("primary_view", "unknown") for row in feedback}
    for view in sorted(view_ids):
        all_rows = [row for row in feedback if row.get("primary_view", "unknown") == view]
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_config = configured_views.get(view, {})
        minimum_precision = float(view_config.get("minimum_eval_precision", default_view_precision))
        selected_count = max(
            [int(row.get("view_selected_count") or 0) for row in all_rows]
            or [int(view_config.get("quota", 0))]
        )
        minimum_decisive = min(
            int(view_config.get("minimum_decisive_samples", default_decisive)),
            selected_count,
        )
        evaluation_mode = str(view_config.get("evaluation_mode", "material"))
        view_precision = (
            sum(row["judgment"].strip().lower() == "fit" for row in decisive) / len(decisive)
            if decisive
            else None
        )
        uncertainty_fraction = (
            sum(row["judgment"].strip().lower() == "uncertain" for row in rows) / len(rows)
            if rows
            else 1.0
        )
        view_coverage = len(rows) / len(all_rows) if all_rows else 0.0
        failure_reasons = []
        if not all_rows:
            failure_reasons.append("view not sampled")
        if view_coverage < float(config.get("minimum_eval_coverage", 0.8)):
            failure_reasons.append("coverage below minimum")
        if uncertainty_fraction > maximum_uncertainty:
            failure_reasons.append("uncertainty above maximum")
        if evaluation_mode == "material":
            if len(decisive) < minimum_decisive:
                failure_reasons.append("insufficient decisive judgments")
            if view_precision is None or view_precision < minimum_precision:
                failure_reasons.append("precision below minimum")
        view_passed = not failure_reasons
        if not view_passed:
            failed_views.append(view)
        by_view[view] = {
            "judged": len(rows),
            "decisive": len(decisive),
            "fit": sum(row["judgment"].strip().lower() == "fit" for row in decisive),
            "reject": sum(row["judgment"].strip().lower() == "reject" for row in decisive),
            "uncertain": sum(row["judgment"].strip().lower() == "uncertain" for row in rows),
            "coverage": round(view_coverage, 4),
            "precision": round(view_precision, 4) if view_precision is not None else None,
            "uncertainty_fraction": round(uncertainty_fraction, 4),
            "minimum_decisive": minimum_decisive,
            "minimum_precision": minimum_precision if evaluation_mode == "material" else None,
            "maximum_uncertainty": maximum_uncertainty,
            "evaluation_mode": evaluation_mode,
            "passed": view_passed,
            "failure_reasons": failure_reasons,
        }
    reported_selected_total = sum(
        max(
            [int(row.get("view_selected_count") or 0) for row in feedback if row.get("primary_view") == view]
            or [0]
        )
        for view in configured_views
    )
    audited_uuid_hash = uuid_sha256(feedback)
    full_master_audit = False
    selected_total = reported_selected_total
    if master is not None:
        selected_total = len(master)
        if master_sha256(master) != next(iter(master_hashes)):
            raise ValueError("evaluation master file does not match feedback master_sha256")
        full_master_audit = (
            {row["uuid"].split("/", 1)[0] for row in feedback}
            == {row["uuid"].split("/", 1)[0] for row in master}
            and len(feedback) == len(master)
            and uuid_sha256(master) == audited_uuid_hash
        )
    passed = (
        coverage >= float(config.get("minimum_eval_coverage", 0.8))
        and precision >= float(config.get("minimum_eval_precision", 0.75))
        and not failed_views
        and missing_reasons == 0
        and missing_safety_states == 0
        and missing_error_categories == 0
        and safety_regressions == 0
    )
    report = {
        "schema_version": 3,
        "proposal_id": next(iter(proposal_ids)),
        "master_sha256": next(iter(master_hashes)),
        "full_master_audit": full_master_audit,
        "selected_master_count": selected_total,
        "audited_uuid_sha256": audited_uuid_hash,
        "sample_count": len(feedback),
        "judged_count": len(judged),
        "fit": fit,
        "reject": reject,
        "uncertain": uncertain,
        "coverage": round(coverage, 4),
        "precision": round(precision, 4),
        "minimum_coverage": config.get("minimum_eval_coverage", 0.8),
        "minimum_precision": config.get("minimum_eval_precision", 0.75),
        "missing_visible_reasons": missing_reasons,
        "missing_safety_states": missing_safety_states,
        "missing_error_categories": missing_error_categories,
        "safety_regressions": safety_regressions,
        "failed_views": failed_views,
        "passed": passed,
        "by_view": by_view,
    }
    return report, passed


def validate_feedback(feedback: list[dict[str, str]]) -> dict:
    required = {
        "uuid", "proposal_id", "master_sha256", "judgment", "visible_reason",
        "evaluation_safety_state", "error_category",
    }
    missing = required - set(feedback[0]) if feedback else required
    if missing:
        raise ValueError(f"feedback missing required columns: {', '.join(sorted(missing))}")
    seen: dict[str, str] = {}
    proposal_ids: set[str] = set()
    master_hashes: set[str] = set()
    for row in feedback:
        uuid = row["uuid"].strip()
        judgment = row["judgment"].strip().lower()
        if not uuid:
            raise ValueError("feedback contains an empty uuid")
        if judgment not in JUDGMENTS:
            raise ValueError(f"feedback row {uuid} has invalid judgment {judgment or '<empty>'}")
        if not row["visible_reason"].strip():
            raise ValueError(f"feedback row {uuid} lacks visible_reason")
        if not row["evaluation_safety_state"].strip():
            raise ValueError(f"feedback row {uuid} lacks evaluation_safety_state")
        if judgment in {"reject", "uncertain"} and not row["error_category"].strip():
            raise ValueError(f"feedback row {uuid} lacks error_category")
        if uuid in seen and seen[uuid] != judgment:
            raise ValueError(f"feedback contains conflicting judgments for {uuid}")
        seen[uuid] = judgment
        proposal_ids.add(row["proposal_id"].strip())
        master_hashes.add(row["master_sha256"].strip())
    if "" in proposal_ids or len(proposal_ids) != 1:
        raise ValueError("feedback must name one non-empty proposal_id")
    if "" in master_hashes or len(master_hashes) != 1:
        raise ValueError("feedback must name one non-empty master_sha256")
    return {
        "schema_version": 2,
        "row_count": len(feedback),
        "unique_uuid_count": len(seen),
        "proposal_id": next(iter(proposal_ids)),
        "master_sha256": next(iter(master_hashes)),
        "judgment_counts": dict(sorted(Counter(seen.values()).items())),
        "status": "PASS",
    }


def apply_feedback(sample: list[dict[str, str]], feedback: list[dict[str, str]]) -> list[dict[str, str]]:
    summary = validate_feedback(feedback)
    sample_proposals = {row.get("proposal_id", "").strip() for row in sample}
    sample_hashes = {row.get("master_sha256", "").strip() for row in sample}
    if sample_proposals != {summary["proposal_id"]}:
        raise ValueError("feedback proposal_id does not match the evaluation sample")
    if sample_hashes != {summary["master_sha256"]}:
        raise ValueError("feedback master_sha256 does not match the evaluation sample")
    updates: dict[str, dict[str, str]] = {}
    for row in feedback:
        uuid = row["uuid"].strip()
        if uuid not in updates:
            updates[uuid] = row
    unknown = set(updates) - {row["uuid"] for row in sample}
    if unknown:
        raise ValueError(f"feedback contains {len(unknown)} UUIDs outside the evaluation sample")
    merged = []
    fields = [
        "judgment", "visible_reason", "evaluation_safety_state", "error_category",
        "round_id", "reviewer_lens", "evaluator", "judged_at",
    ]
    for row in sample:
        item = dict(row)
        if update := updates.get(row["uuid"]):
            for field in fields:
                item[field] = update.get(field, "").strip()
            item["judgment"] = item["judgment"].lower()
        merged.append(item)
    return merged


def validate(master: list[dict[str, str]], holds: list[dict[str, str]], config: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    ids = [row["uuid"] for row in master]
    base_ids = [identifier.split("/", 1)[0] for identifier in ids]
    hold_ids = {row["uuid"] for row in holds}
    if len(master) != int(config["target_count"]):
        errors.append(f"expected {config['target_count']} selected rows, found {len(master)}")
    if len(ids) != len(set(ids)):
        errors.append("master contains duplicate UUIDs")
    if len(base_ids) != len(set(base_ids)):
        errors.append("master contains duplicate canonical asset UUIDs")
    overlap = set(ids) & hold_ids
    if overlap:
        errors.append(f"master overlaps safety holds by {len(overlap)} rows")
    unsafe_master = [row["uuid"] for row in master if is_hold(row)]
    if unsafe_master:
        errors.append(f"master contains {len(unsafe_master)} rows with unsafe state")
    if any(not row.get("selection_reason") for row in master):
        errors.append("one or more selected rows lack a selection reason")
    if any(not row.get("assigned_view") for row in master):
        errors.append("one or more selected rows lack assigned_view")
    expected_hash = master_sha256(master)
    hashes = {row.get("master_sha256", "") for row in master}
    if hashes != {expected_hash}:
        errors.append("master_sha256 is missing or does not match exact membership and assignments")
    expected_proposal = f"pfp-{expected_hash[:16]}"
    if {row.get("proposal_id", "") for row in master} != {expected_proposal}:
        errors.append("proposal_id is missing or does not match master_sha256")
    quotas = {str(view["id"]): int(view["quota"]) for view in config["views"]}
    view_counts = Counter(str(row.get("primary_view", "")) for row in master)
    quota_mismatches = {
        view: {"expected": quota, "actual": view_counts.get(view, 0)}
        for view, quota in quotas.items()
        if view_counts.get(view, 0) != quota
    }
    if quota_mismatches:
        errors.append(f"exact view quota mismatch: {json.dumps(quota_mismatches, sort_keys=True)}")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "unsafe_master_rows": len(unsafe_master),
        "view_quotas": quotas,
        "view_counts": dict(sorted(view_counts.items())),
        "quota_mismatches": quota_mismatches,
        "master_sha256": expected_hash,
        "proposal_id": expected_proposal,
    }
    return errors, metrics


def build_catalog_plan(
    master: list[dict[str, str]],
    config: dict,
    plan_id: str,
    source_title: str,
    source_identifier: str,
    evaluation_report: dict,
    source_manifest: dict | None = None,
) -> dict:
    """Build an adapter-neutral, membership-only catalog plan."""
    digest = master_sha256(master)
    proposal_id = f"pfp-{digest[:16]}"
    canonical_ids = [str(row["uuid"]).split("/", 1)[0] for row in master]
    if len(canonical_ids) != len(set(canonical_ids)):
        raise ValueError("catalog plan master contains duplicate canonical asset UUIDs")
    if not evaluation_report.get("full_master_audit"):
        raise ValueError("catalog plan requires a full audit of the frozen master")
    if not evaluation_report.get("passed"):
        raise ValueError("catalog plan requires a passing final evaluation")
    if evaluation_report.get("master_sha256") != digest:
        raise ValueError("evaluated master hash does not match the proposed catalog plan")
    if evaluation_report.get("proposal_id") != proposal_id:
        raise ValueError("evaluated proposal_id does not match the proposed catalog plan")
    if evaluation_report.get("audited_uuid_sha256") != uuid_sha256(master):
        raise ValueError("evaluated UUID set does not match the proposed catalog plan")
    source = {"title": source_title, "identifier": source_identifier}
    if source_manifest is not None:
        if source_manifest.get("identifier") != source_identifier:
            raise ValueError("source manifest identifier does not match requested plan source")
        if int(source_manifest.get("snapshot_count", 0)) < 1:
            raise ValueError("source manifest requires a positive snapshot_count")
        if source_manifest.get("kind") != "synthetic" and not source_manifest.get("source_fingerprint"):
            raise ValueError("non-synthetic catalog plans require a source membership fingerprint")
        source.update({
            key: source_manifest.get(key)
            for key in (
                "kind", "predicate_version", "snapshot_count", "source_fingerprint",
                "artifact_sensitivity", "generated_at",
            )
            if source_manifest.get(key) is not None
        })
    config_digest = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    view_labels = {view["id"]: view["label"] for view in config["views"]}
    albums = [
        {
            "key": "master",
            "title": f"00 MASTER - {len(master):,}",
            "asset_ids": [row["uuid"] for row in master],
        }
    ]
    for view_id in sorted({row["primary_view"] for row in master}):
        asset_ids = [row["uuid"] for row in master if row["primary_view"] == view_id]
        albums.append(
            {
                "key": f"view-{view_id}",
                "title": f"{view_id} {view_labels.get(view_id, 'Unlabeled View')} - {len(asset_ids):,}",
                "asset_ids": asset_ids,
            }
        )
    return {
        "schema_version": 2,
        "plan_id": plan_id,
        "proposal_id": proposal_id,
        "master_sha256": digest,
        "audited_uuid_sha256": uuid_sha256(master),
        "config_sha256": config_digest,
        "evaluation": {
            "proposal_id": proposal_id,
            "master_sha256": digest,
            "passed": True,
            "full_master_audit": True,
            "audited_uuid_sha256": uuid_sha256(master),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source": source,
        "release_class": "editor-field",
        "publication_clearance": False,
        "expected_master_count": len(master),
        "write_test_count": min(10, len(master)),
        "albums": albums,
        "required_verification": [
            "exact album counts",
            "no missing asset IDs",
            "no unexpected asset IDs",
            "no members outside source corpus",
            "no safety-hold overlap",
            "source membership unchanged",
        ],
    }
