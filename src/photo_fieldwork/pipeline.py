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

from .assignment import assign_views


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
    target = int(config["target_count"])
    named_fraction = float(config.get("minimum_named_people_fraction", 0))
    free_fraction = float(config.get("minimum_person_free_fraction", 0))
    if not 0 <= named_fraction <= 1 or not 0 <= free_fraction <= 1:
        raise ValueError("people fractions must be between 0 and 1")
    if named_fraction + free_fraction > 1:
        raise ValueError("named-people and person-free minimum fractions cannot sum above 1")
    config["minimum_named_people_count"] = math.ceil(target * named_fraction)
    config["minimum_person_free_count"] = math.ceil(target * free_fraction)
    for field in [
        "minimum_eval_precision",
        "minimum_eval_coverage",
        "minimum_view_eval_precision",
    ]:
        if field in config and not 0 <= float(config[field]) <= 1:
            raise ValueError(f"{field} must be between 0 and 1")
    if int(config.get("minimum_decisive_per_view", 1)) < 1:
        raise ValueError("minimum_decisive_per_view must be at least 1")
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
    return (
        str(row.get("safety_status", "clear")).lower() == "hold"
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


def choose_primary_view(row: dict[str, str], config: dict) -> str:
    configured = {view["id"] for view in config["views"]}
    candidates = [view for view in split_values(row.get("candidate_views")) if view in configured]
    return candidates[0] if candidates else config["unclassified_view"]


def rank_row(row: dict[str, str], config: dict) -> float:
    return attention_score(row) + evidence_score(row) + stable_noise(int(config["seed"]), row["uuid"])


def review_state_counts(rows: list[dict[str, str]], selected_count: int, held_count: int) -> dict[str, int]:
    """Report operational states without calling machine processing human review."""

    allowed = {"fit", "reject", "uncertain"}
    return {
        "catalog_indexed": len(rows),
        "candidate_retrieved": len(rows),
        "pixel_available": sum(truthy(row.get("pixel_available")) for row in rows),
        "preview_rendered": sum(truthy(row.get("preview_exported")) for row in rows),
        "automated_locally_classified": sum(
            bool(row.get("vision_labels_all")) or truthy(row.get("automated_classified"))
            for row in rows
        ),
        "editorially_sampled": sum(bool(row.get("round_id")) for row in rows),
        "editorially_judged": sum(row.get("judgment", "").strip().lower() in allowed for row in rows),
        "selected": selected_count,
        "held": held_count,
        "publication_cleared": sum(truthy(row.get("publication_cleared")) for row in rows),
    }


def select(inventory: list[dict[str, str]], config: dict) -> tuple[list[dict], list[dict], dict]:
    holds = [dict(row) for row in inventory if is_hold(row)]
    eligible = cluster_representatives([dict(row) for row in inventory if not is_hold(row)], config)
    for row in eligible:
        row["score_total"] = f"{rank_row(row, config):.6f}"
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_tier"] = "evidence" if confidence in {"high", "medium"} else "exploratory"
        row["selection_reason"] = "; ".join(
            reason
            for reason in [
                f"retrieval hypotheses {row.get('candidate_views') or config['unclassified_view']}",
                f"visible context: {row.get('visible_context')}" if row.get("visible_context") else "",
                f"evidence confidence: {confidence}",
                "pre-existing named people" if split_values(row.get("persons")) else "",
                "prior favorite/edit attention" if attention_score(row) else "",
            ]
            if reason
        )

    assignments, assignment_report = assign_views(
        eligible,
        config,
        lambda row: rank_row(row, config),
        lambda row: bool(split_values(row.get("persons"))),
    )
    selected = []
    for row in eligible:
        if row["uuid"] not in assignments:
            continue
        row["primary_view"] = assignments[row["uuid"]]
        row["selection_reason"] += f"; exact quota assignment: {row['primary_view']}"
        selected.append(row)

    selected.sort(key=lambda row: (row["primary_view"], -float(row["score_total"]), row["uuid"]))
    summary = {
        "inventory_count": len(inventory),
        "eligible_after_cluster_reduction": len(eligible),
        "hold_count": len(holds),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "person_free_count": sum(not bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "assignment": assignment_report,
        "review_state_scope": "input inventory rows only",
        "review_states": review_state_counts(inventory, len(selected), len(holds)),
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
            item["evaluation_note"] = ""
            item["visible_reason"] = ""
            item["error_category"] = ""
            item["editorial_safety_status"] = "clear"
            item["provenance_status"] = "hypothesis"
            item["reviewer_actor"] = ""
            item["reviewer_lens"] = ""
            item["round_id"] = ""
            sample.append(item)
    return sample


def evaluate(feedback: list[dict[str, str]], config: dict) -> tuple[dict, bool]:
    allowed = {"fit", "reject", "uncertain"}
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in allowed]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / len(feedback) if feedback else 0.0
    precision = fit / (fit + reject) if fit + reject else 0.0
    minimum_view_precision = float(config.get("minimum_view_eval_precision", 0.65))
    minimum_decisive = int(config.get("minimum_decisive_per_view", 3))
    configured_views = {
        str(view["id"]): view for view in config.get("views", []) if int(view.get("quota", 0)) > 0
    }
    sampled_views = {row.get("primary_view", "unknown") for row in feedback}
    by_view = {}
    failures = []
    for view in sorted(set(configured_views) | sampled_views):
        sample_rows = [row for row in feedback if row.get("primary_view", "unknown") == view]
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_precision = (
            sum(row["judgment"].strip().lower() == "fit" for row in decisive) / len(decisive)
            if decisive
            else None
        )
        threshold = float(configured_views.get(view, {}).get("minimum_eval_precision", minimum_view_precision))
        if len(decisive) < minimum_decisive:
            state = "insufficient-evidence"
            failures.append(f"view {view} has {len(decisive)} decisive judgments; requires {minimum_decisive}")
        elif view_precision is not None and view_precision < threshold:
            state = "fail"
            failures.append(f"view {view} precision {view_precision:.4f} is below {threshold:.4f}")
        else:
            state = "pass"
        by_view[view] = {
            "sample_count": len(sample_rows),
            "judged": len(rows),
            "decisive": len(decisive),
            "fit": sum(row["judgment"].strip().lower() == "fit" for row in decisive),
            "reject": sum(row["judgment"].strip().lower() == "reject" for row in decisive),
            "precision": round(view_precision, 4) if view_precision is not None else None,
            "minimum_precision": threshold,
            "minimum_decisive": minimum_decisive,
            "state": state,
        }

    safety_regressions = sum(
        row.get("editorial_safety_status", row.get("safety_status", "clear")).strip().lower() == "hold"
        and row.get("judgment", "").strip().lower() == "fit"
        for row in feedback
    )
    minimum_coverage = float(config.get("minimum_eval_coverage", 0.8))
    minimum_precision = float(config.get("minimum_eval_precision", 0.75))
    if coverage < minimum_coverage:
        failures.append(f"coverage {coverage:.4f} is below {minimum_coverage:.4f}")
    if precision < minimum_precision:
        failures.append(f"precision {precision:.4f} is below {minimum_precision:.4f}")
    if safety_regressions:
        failures.append(f"{safety_regressions} known safety regressions were marked fit")
    passed = not failures
    report = {
        "sample_count": len(feedback),
        "judged_count": len(judged),
        "fit": fit,
        "reject": reject,
        "uncertain": uncertain,
        "coverage": round(coverage, 4),
        "precision": round(precision, 4),
        "minimum_coverage": minimum_coverage,
        "minimum_precision": minimum_precision,
        "minimum_view_precision": minimum_view_precision,
        "minimum_decisive_per_view": minimum_decisive,
        "safety_regressions": safety_regressions,
        "passed": passed,
        "failures": failures,
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
    configured = {view["id"] for view in config["views"] if int(view["quota"]) > 0}
    represented = {row.get("primary_view") for row in master}
    missing_views = configured - represented
    if missing_views:
        errors.append(f"configured views absent from master: {', '.join(sorted(missing_views))}")
    expected_counts = {str(view["id"]): int(view["quota"]) for view in config["views"]}
    actual_counts = Counter(str(row.get("primary_view")) for row in master)
    quota_mismatches = {
        view: {"expected": count, "actual": actual_counts.get(view, 0)}
        for view, count in expected_counts.items()
        if actual_counts.get(view, 0) != count
    }
    if quota_mismatches:
        errors.append(f"view quota mismatches: {quota_mismatches}")
    named_count = sum(bool(split_values(row.get("persons"))) for row in master)
    free_count = len(master) - named_count
    named_required = int(config.get("minimum_named_people_count", 0))
    free_required = int(config.get("minimum_person_free_count", 0))
    if named_count < named_required:
        errors.append(f"named people floor not met: {named_count} < {named_required}")
    if free_count < free_required:
        errors.append(f"person-free floor not met: {free_count} < {free_required}")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "represented_views": sorted(represented),
        "view_counts": dict(sorted(actual_counts.items())),
        "quota_mismatches": quota_mismatches,
        "named_people_count": named_count,
        "minimum_named_people_count": named_required,
        "person_free_count": free_count,
        "minimum_person_free_count": free_required,
    }
    return errors, metrics


def build_catalog_plan(
    master: list[dict[str, str]],
    config: dict,
    plan_id: str,
    source_title: str,
    source_identifier: str,
) -> dict:
    """Build an adapter-neutral, membership-only catalog plan."""
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
        "schema_version": 1,
        "plan_id": plan_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source": {"title": source_title, "identifier": source_identifier},
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
