from __future__ import annotations

import csv
import copy
import hashlib
import json
import random
import math
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
    allowed_statuses = {"active", "unsupported", "deferred", "empty-by-editorial-decision"}
    invalid_statuses = {
        str(view.get("status", "active")) for view in config["views"]
    } - allowed_statuses
    if invalid_statuses:
        raise ValueError(f"invalid view statuses: {', '.join(sorted(invalid_statuses))}")
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
        str(row.get("safety_status", "clear")).lower() in {"hold", "needs-review", "unavailable"}
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
                f"retrieval hypothesis {row['primary_view']}",
                f"visible context: {row.get('visible_context')}" if row.get("visible_context") else "",
                f"evidence confidence: {confidence}",
                "pre-existing named people" if split_values(row.get("persons")) else "",
                "prior favorite/edit attention" if attention_score(row) else "",
            ]
            if reason
        )

    by_view: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        by_view[row["primary_view"]].append(row)
    for rows in by_view.values():
        rows.sort(key=lambda row: float(row["score_total"]), reverse=True)

    selected: list[dict] = []
    selected_ids: set[str] = set()
    event_caps = {
        str(view): int(cap)
        for view, cap in config.get("event_cluster_caps", {}).items()
        if int(cap) > 0
    }
    for view in config["views"]:
        view_id = view["id"]
        if int(view["quota"]) <= 0:
            continue
        cluster_counts: Counter[str] = Counter()
        view_selected = 0
        for row in by_view[view_id]:
            cluster = str(row.get("event_cluster", "")).strip()
            cap = event_caps.get(view_id)
            if cap and cluster and cluster_counts[cluster] >= cap:
                continue
            if row["uuid"] not in selected_ids:
                selected.append(row)
                selected_ids.add(row["uuid"])
                view_selected += 1
                if cluster:
                    cluster_counts[cluster] += 1
            if view_selected == int(view["quota"]):
                break

    target = int(config["target_count"])
    if len(selected) < target:
        remainder = sorted(
            (row for row in eligible if row["uuid"] not in selected_ids),
            key=lambda row: float(row["score_total"]),
            reverse=True,
        )
        cluster_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for row in selected:
            cluster = str(row.get("event_cluster", "")).strip()
            if cluster:
                cluster_counts[row["primary_view"]][cluster] += 1
        for row in remainder:
            cluster = str(row.get("event_cluster", "")).strip()
            cap = event_caps.get(row["primary_view"])
            if cap and cluster and cluster_counts[row["primary_view"]][cluster] >= cap:
                continue
            selected.append(row)
            selected_ids.add(row["uuid"])
            if cluster:
                cluster_counts[row["primary_view"]][cluster] += 1
            if len(selected) == target:
                break

    if len(selected) < target:
        raise ValueError(
            f"candidate field cannot reach target {target} under configured event-cluster caps"
        )

    selected = selected[:target]

    def enforce_floor(predicate, required: int, reason: str) -> None:
        nonlocal selected, selected_ids
        current = sum(predicate(row) for row in selected)
        if current >= required:
            return
        candidates = sorted(
            (row for row in eligible if row["uuid"] not in selected_ids and predicate(row)),
            key=lambda row: float(row["score_total"]),
            reverse=True,
        )
        while current < required and candidates:
            incoming = candidates.pop(0)
            donors = sorted(
                (row for row in selected if not predicate(row)),
                key=lambda row: (
                    row["primary_view"] != incoming["primary_view"],
                    float(row["score_total"]),
                ),
            )
            if not donors:
                break
            outgoing = donors[0]
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
    exploratory_floor = math.ceil(target * float(config.get("exploratory_fraction", 0)))
    enforce_floor(
        lambda row: row.get("selection_tier") == "exploratory",
        exploratory_floor,
        "exploratory editor field",
    )
    outside_prior_floor = math.ceil(target * float(config.get("minimum_outside_prior_final_fraction", 0)))
    enforce_floor(
        lambda row: truthy(row.get("outside_prior")),
        outside_prior_floor,
        "outside prior corpus",
    )
    if sum(bool(split_values(row.get("persons"))) for row in selected) < named_floor:
        raise ValueError("candidate field cannot satisfy minimum_named_people_fraction")
    if sum(not bool(split_values(row.get("persons"))) for row in selected) < person_free_floor:
        raise ValueError("candidate field cannot satisfy minimum_person_free_fraction")
    if sum(row.get("selection_tier") == "exploratory" for row in selected) < exploratory_floor:
        raise ValueError("candidate field cannot satisfy exploratory_fraction")
    if sum(truthy(row.get("outside_prior")) for row in selected) < outside_prior_floor:
        raise ValueError("candidate field cannot satisfy minimum_outside_prior_final_fraction")
    selected.sort(key=lambda row: (row["primary_view"], -float(row["score_total"]), row["uuid"]))
    summary = {
        "inventory_count": len(inventory),
        "eligible_after_cluster_reduction": len(eligible),
        "hold_count": len(holds),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "outside_prior_count": sum(truthy(row.get("outside_prior")) for row in selected),
        "event_cluster_maxima": {
            view: max(
                Counter(
                    row.get("event_cluster")
                    for row in selected
                    if row["primary_view"] == view and row.get("event_cluster")
                ).values(),
                default=0,
            )
            for view in event_caps
        },
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
            sample.append(item)
    return sample


def make_final_holdout(
    master: list[dict[str, str]],
    sample_size: int,
    minimum_per_view: int,
    seed: int,
    excluded_ids: set[str] | None = None,
) -> list[dict]:
    """Draw a fresh, deterministic final holdout after the master is frozen.

    The estimate is a simple random sample of the untouched population. Extra
    rows may be added to meet a per-view review floor, but those rows are marked
    supplemental and excluded from the aggregate estimate. Rows used during
    tuning can be excluded explicitly so the final audit does not recycle its
    own training evidence.
    """
    excluded_ids = excluded_ids or set()
    eligible = [row for row in master if row["uuid"] not in excluded_ids]
    if not eligible:
        raise ValueError("no final-master rows remain after holdout exclusions")
    sample_size = min(max(1, sample_size), len(eligible))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        grouped[row.get("primary_view", "unknown")].append(row)
    rng = random.Random(seed)
    randomized = list(eligible)
    rng.shuffle(randomized)
    estimate = randomized[:sample_size]
    selected_ids = {row["uuid"] for row in estimate}
    supplemental: list[dict] = []
    estimate_counts = Counter(row.get("primary_view", "unknown") for row in estimate)
    for view, rows in sorted(grouped.items()):
        needed = max(0, min(minimum_per_view, len(rows)) - estimate_counts[view])
        if not needed:
            continue
        candidates = [row for row in rows if row["uuid"] not in selected_ids]
        rng.shuffle(candidates)
        for row in candidates[:needed]:
            supplemental.append(row)
            selected_ids.add(row["uuid"])

    sample: list[dict] = []
    for row, estimate_included in [
        *((row, True) for row in estimate),
        *((row, False) for row in supplemental),
    ]:
        view = row.get("primary_view", "unknown")
        item = dict(row)
        item["sample_role"] = (
            "final-holdout-estimate" if estimate_included else "final-holdout-supplemental"
        )
        item["estimate_included"] = str(estimate_included).lower()
        item["sample_seed"] = str(seed)
        item["population_count"] = str(len(eligible))
        item["full_master_count"] = str(len(master))
        item["view_population_count"] = str(len(grouped[view]))
        item["judgment"] = ""
        item["evaluation_note"] = ""
        sample.append(item)
    sample.sort(key=lambda row: (row.get("primary_view", ""), row["uuid"]))
    return sample


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        (proportion * (1 - proportion) + z * z / (4 * total)) / total
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def evaluate(feedback: list[dict[str, str]], config: dict) -> tuple[dict, bool]:
    allowed = {"fit", "reject", "uncertain"}
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in allowed]
    final_holdout = bool(feedback) and all(
        row.get("sample_role", "").startswith("final-holdout") for row in feedback
    )
    estimate_judged = (
        [row for row in judged if truthy(row.get("estimate_included"))]
        if final_holdout else judged
    )
    fit = sum(row["judgment"].strip().lower() == "fit" for row in estimate_judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in estimate_judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in estimate_judged)
    review_completion = len(judged) / len(feedback) if feedback else 0.0
    decisive_fit_rate = fit / (fit + reject) if fit + reject else 0.0
    configured_views = {
        view["id"] for view in config["views"]
        if int(view["quota"]) > 0 and view.get("status", "active") == "active"
    }
    sampled_views = {row.get("primary_view", "unknown") for row in judged}
    view_sampling_coverage = (
        len(configured_views & sampled_views) / len(configured_views)
        if configured_views else 1.0
    )
    decisive_count = fit + reject
    lower, upper = wilson_interval(fit, decisive_count)
    population_count = max(
        [int(row.get("population_count") or 0) for row in feedback] or [0]
    )
    full_master_count = max(
        [int(row.get("full_master_count") or 0) for row in feedback] or [0]
    )
    field_audit_rate = len(feedback) / full_master_count if full_master_count else None
    untouched_population_audit_rate = (
        len([row for row in feedback if truthy(row.get("estimate_included"))]) / population_count
        if population_count else None
    )
    by_view = {}
    for view in sorted({row.get("primary_view", "unknown") for row in feedback}):
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_fit = sum(row["judgment"].strip().lower() == "fit" for row in decisive)
        view_lower, view_upper = wilson_interval(view_fit, len(decisive))
        by_view[view] = {
            "judged": len(rows),
            "decisive_fit_rate": view_fit / len(decisive) if decisive else None,
            "wilson_95_lower": round(view_lower, 4) if decisive else None,
            "wilson_95_upper": round(view_upper, 4) if decisive else None,
        }
    passed = (
        review_completion >= float(config.get("minimum_eval_coverage", 0.8))
        and decisive_fit_rate >= float(config.get("minimum_eval_precision", 0.75))
        and view_sampling_coverage >= float(config.get("minimum_view_sampling_coverage", 1.0))
    )
    final_lower_bound = config.get("minimum_final_wilson_lower_bound")
    if final_holdout and final_lower_bound is not None:
        passed = passed and lower >= float(final_lower_bound)
    report = {
        "sample_count": len(feedback),
        "judged_count": len(judged),
        "estimation_judged_count": len(estimate_judged),
        "estimation_sample_count": len(
            [row for row in feedback if truthy(row.get("estimate_included"))]
        ) if final_holdout else len(feedback),
        "supplemental_sample_count": len(feedback) - len(
            [row for row in feedback if truthy(row.get("estimate_included"))]
        ) if final_holdout else 0,
        "fit": fit,
        "reject": reject,
        "uncertain": uncertain,
        "all_fit": sum(row["judgment"].strip().lower() == "fit" for row in judged),
        "all_reject": sum(row["judgment"].strip().lower() == "reject" for row in judged),
        "all_uncertain": sum(
            row["judgment"].strip().lower() == "uncertain" for row in judged
        ),
        "review_completion": round(review_completion, 4),
        "view_sampling_coverage": round(view_sampling_coverage, 4),
        "decisive_fit_rate": round(decisive_fit_rate, 4),
        "decisive_fit_wilson_95_lower": round(lower, 4),
        "decisive_fit_wilson_95_upper": round(upper, 4),
        "field_audit_rate": round(field_audit_rate, 4) if field_audit_rate is not None else None,
        "untouched_population_audit_rate": (
            round(untouched_population_audit_rate, 4)
            if untouched_population_audit_rate is not None else None
        ),
        "untouched_population_count": population_count or None,
        "full_master_count": full_master_count or None,
        "final_holdout": final_holdout,
        "minimum_final_wilson_lower_bound": final_lower_bound,
        "coverage": round(review_completion, 4),
        "precision": round(decisive_fit_rate, 4),
        "minimum_coverage": config.get("minimum_eval_coverage", 0.8),
        "minimum_precision": config.get("minimum_eval_precision", 0.75),
        "passed": passed,
        "by_view": by_view,
    }
    return report, passed


def effective_final_config(intent_config: dict, master: list[dict[str, str]]) -> dict:
    """Record the field that survived evaluation without erasing original intent."""
    config = copy.deepcopy(intent_config)
    counts = Counter(row.get("primary_view", "") for row in master)
    for view in config["views"]:
        view["intent_quota"] = int(view["quota"])
        actual = counts.get(view["id"], 0)
        view["quota"] = actual
        if actual == 0 and view.get("status", "active") == "active":
            view["status"] = "unsupported"
        else:
            view.setdefault("status", "active")
    config["target_count"] = len(master)
    config["enforce_view_quotas"] = True
    config["derived_from_frozen_master"] = True
    return config


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
    unsafe_master = [row for row in master if is_hold(row)]
    if unsafe_master:
        errors.append(f"master contains {len(unsafe_master)} non-clear safety rows")
    configured = {
        view["id"] for view in config["views"]
        if int(view["quota"]) > 0 and view.get("status", "active") == "active"
    }
    represented = {row.get("primary_view") for row in master}
    missing_views = configured - represented
    if missing_views:
        errors.append(f"configured views absent from master: {', '.join(sorted(missing_views))}")
    actual_counts = Counter(row.get("primary_view") for row in master)
    expected_counts = {view["id"]: int(view["quota"]) for view in config["views"]}
    if config.get("enforce_view_quotas"):
        mismatches = {
            view: {"expected": expected, "actual": actual_counts.get(view, 0)}
            for view, expected in expected_counts.items()
            if actual_counts.get(view, 0) != expected
        }
        if mismatches:
            errors.append(
                "view quota mismatch: "
                + ", ".join(
                    f"{view} expected {values['expected']} actual {values['actual']}"
                    for view, values in sorted(mismatches.items())
                )
            )
    event_cap_violations = {}
    for view, cap in config.get("event_cluster_caps", {}).items():
        counts = Counter(
            row.get("event_cluster")
            for row in master
            if row.get("primary_view") == view and row.get("event_cluster")
        )
        violations = {cluster: count for cluster, count in counts.items() if count > int(cap)}
        if violations:
            event_cap_violations[view] = violations
    if event_cap_violations:
        errors.append("one or more event clusters exceed configured view caps")

    allowed_publication = {"", "not-reviewed", "candidate", "cleared-for-specific-use", "published"}
    allowed_rights = {"", "owner-verified", "third-party", "unknown"}
    allowed_consent = {"", "cleared-for-use", "ask", "declined", "not-applicable", "unknown"}
    allowed_claim = {"", "visible-only", "provenance-backed", "caption-review"}
    invalid_publication_rows = sum(
        row.get("publication_status", "") not in allowed_publication
        or row.get("rights_status", "") not in allowed_rights
        or row.get("consent_status", "") not in allowed_consent
        or row.get("claim_status", "") not in allowed_claim
        for row in master
    )
    if invalid_publication_rows:
        errors.append(f"master contains {invalid_publication_rows} invalid publication-readiness states")

    required_outside = math.ceil(
        len(master) * float(config.get("minimum_outside_prior_final_fraction", 0))
    )
    outside_count = sum(truthy(row.get("outside_prior")) for row in master)
    if outside_count < required_outside:
        errors.append(f"outside-prior final floor failed: {outside_count} < {required_outside}")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "represented_views": sorted(represented),
        "view_counts": dict(sorted(actual_counts.items())),
        "configured_view_counts": expected_counts,
        "outside_prior_count": outside_count,
        "required_outside_prior_count": required_outside,
        "event_cap_violations": event_cap_violations,
        "invalid_publication_state_rows": invalid_publication_rows,
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
