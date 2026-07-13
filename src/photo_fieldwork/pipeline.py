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


CLEAR_SAFETY_STATES = {"", "clear", "clear_for_editor_field"}
JUDGMENTS = {"fit", "reject", "uncertain"}


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
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


def master_sha256(rows: Iterable[dict[str, str]]) -> str:
    payload = [
        {
            "uuid": str(row["uuid"]),
            "primary_view": str(row.get("primary_view") or ""),
        }
        for row in rows
    ]
    payload.sort(key=lambda row: (row["primary_view"], row["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def wilson_interval(successes: int, total: int, z: float = 1.96) -> list[float] | None:
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1 + (z * z / total)
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total)
        / denominator
    )
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def is_hold(row: dict[str, str]) -> bool:
    state = str(row.get("safety_state") or row.get("safety_status") or "clear").strip().lower()
    return (
        state not in CLEAR_SAFETY_STATES
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
    for view in config["views"]:
        for row in by_view[view["id"]][: int(view["quota"])]:
            if row["uuid"] not in selected_ids:
                selected.append(row)
                selected_ids.add(row["uuid"])

    target = int(config["target_count"])
    if len(selected) < target:
        remainder = sorted(
            (row for row in eligible if row["uuid"] not in selected_ids),
            key=lambda row: float(row["score_total"]),
            reverse=True,
        )
        for row in remainder[: target - len(selected)]:
            selected.append(row)
            selected_ids.add(row["uuid"])

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
    if sum(bool(split_values(row.get("persons"))) for row in selected) < named_floor:
        raise ValueError("candidate field cannot satisfy minimum_named_people_fraction")
    if sum(not bool(split_values(row.get("persons"))) for row in selected) < person_free_floor:
        raise ValueError("candidate field cannot satisfy minimum_person_free_fraction")
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
        "review_required_count": sum(
            str(row.get("safety_state") or row.get("safety_status") or "").strip().lower()
            in {"needs-review", "review_required"}
            for row in holds
        ),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "master_sha256": digest,
        "proposal_id": proposal_id,
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
            item["view_population"] = str(len(rows))
            item["sampling_reason"] = (
                "complete small view"
                if len(rows) <= per_view
                else "score boundaries plus deterministic random positions"
            )
            item["judgment"] = ""
            item["evaluation_note"] = ""
            sample.append(item)
    return sample


def evaluate(feedback: list[dict[str, str]], config: dict) -> tuple[dict, bool]:
    proposal_ids = {row.get("proposal_id", "").strip() for row in feedback}
    master_hashes = {row.get("master_sha256", "").strip() for row in feedback}
    if "" in proposal_ids or len(proposal_ids) != 1:
        raise ValueError("evaluation rows must share one non-empty proposal_id")
    if "" in master_hashes or len(master_hashes) != 1:
        raise ValueError("evaluation rows must share one non-empty master_sha256")
    unknown = sorted(
        {
            row.get("judgment", "").strip().lower()
            for row in feedback
            if row.get("judgment", "").strip()
            and row.get("judgment", "").strip().lower() not in JUDGMENTS
        }
    )
    if unknown:
        raise ValueError(f"unknown evaluation judgments: {', '.join(unknown)}")
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in JUDGMENTS]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / len(feedback) if feedback else 0.0
    decisive_precision = fit / (fit + reject) if fit + reject else 0.0
    fit_rate = fit / len(judged) if judged else 0.0
    uncertainty_rate = uncertain / len(judged) if judged else 0.0
    by_view = {}
    for view in sorted({row.get("primary_view", "unknown") for row in feedback}):
        sampled = [row for row in feedback if row.get("primary_view", "unknown") == view]
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_fit = sum(row["judgment"].strip().lower() == "fit" for row in rows)
        view_uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in rows)
        by_view[view] = {
            "sampled": len(sampled),
            "judged": len(rows),
            "population": max((int(row.get("view_population") or 0) for row in sampled), default=0),
            "decisive_precision": (
                sum(row["judgment"].strip().lower() == "fit" for row in decisive) / len(decisive)
                if decisive
                else None
            ),
            "decisive_precision_interval_95": wilson_interval(view_fit, len(decisive)),
            "fit_rate": view_fit / len(rows) if rows else None,
            "fit_rate_interval_95": wilson_interval(view_fit, len(rows)),
            "uncertainty_rate": view_uncertain / len(rows) if rows else None,
        }

    weighted_fit = 0.0
    weighted_decisive_fit = 0.0
    weighted_total = 0.0
    weighted_decisive_total = 0.0
    for view, metrics in by_view.items():
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        if not rows:
            continue
        population = metrics["population"] or len(rows)
        weight = population / len(rows)
        for row in rows:
            judgment = row["judgment"].strip().lower()
            weighted_total += weight
            weighted_fit += weight if judgment == "fit" else 0.0
            if judgment in {"fit", "reject"}:
                weighted_decisive_total += weight
                weighted_decisive_fit += weight if judgment == "fit" else 0.0
    weighted_fit_rate = weighted_fit / weighted_total if weighted_total else 0.0
    weighted_decisive_precision = (
        weighted_decisive_fit / weighted_decisive_total if weighted_decisive_total else 0.0
    )

    minimum_precision = float(
        config.get("minimum_eval_decisive_precision", config.get("minimum_eval_precision", 0.75))
    )
    maximum_uncertainty = float(config.get("maximum_eval_uncertainty", 1.0))
    decisive_interval = wilson_interval(fit, fit + reject)
    minimum_lower_bound = config.get("minimum_eval_decisive_precision_lower_bound")
    passed = (
        coverage >= float(config.get("minimum_eval_coverage", 0.8))
        and decisive_precision >= minimum_precision
        and uncertainty_rate <= maximum_uncertainty
        and (
            minimum_lower_bound is None
            or (decisive_interval is not None and decisive_interval[0] >= float(minimum_lower_bound))
        )
    )
    report = {
        "schema_version": 2,
        "proposal_id": next(iter(proposal_ids)),
        "master_sha256": next(iter(master_hashes)),
        "sample_count": len(feedback),
        "judged_count": len(judged),
        "fit": fit,
        "reject": reject,
        "uncertain": uncertain,
        "coverage": round(coverage, 4),
        "decisive_precision": round(decisive_precision, 4),
        "decisive_precision_interval_95": decisive_interval,
        "fit_rate": round(fit_rate, 4),
        "fit_rate_interval_95": wilson_interval(fit, len(judged)),
        "uncertainty_rate": round(uncertainty_rate, 4),
        "population_weighted_fit_rate": round(weighted_fit_rate, 4),
        "population_weighted_decisive_precision": round(weighted_decisive_precision, 4),
        "precision": round(decisive_precision, 4),
        "minimum_coverage": config.get("minimum_eval_coverage", 0.8),
        "minimum_decisive_precision": minimum_precision,
        "minimum_decisive_precision_lower_bound": minimum_lower_bound,
        "maximum_uncertainty": maximum_uncertainty,
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
    unsafe_master = [row for row in master if is_hold(row)]
    if unsafe_master:
        errors.append(f"master contains {len(unsafe_master)} non-clear safety states")
    if any(not row.get("selection_reason") for row in master):
        errors.append("one or more selected rows lack a selection reason")
    digest = master_sha256(master)
    hashes = {row.get("master_sha256", "") for row in master}
    if hashes != {digest}:
        errors.append("master_sha256 is missing or does not match exact membership and views")
    proposal_ids = {row.get("proposal_id", "") for row in master}
    if proposal_ids != {f"pfp-{digest[:16]}"}:
        errors.append("proposal_id is missing or does not match master_sha256")
    configured = {view["id"] for view in config["views"] if int(view["quota"]) > 0}
    represented = {row.get("primary_view") for row in master}
    missing_views = configured - represented
    if missing_views:
        errors.append(f"configured views absent from master: {', '.join(sorted(missing_views))}")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "unsafe_master_count": len(unsafe_master),
        "master_sha256": digest,
        "proposal_id": f"pfp-{digest[:16]}",
        "represented_views": sorted(represented),
    }
    return errors, metrics


def build_catalog_plan(
    master: list[dict[str, str]],
    config: dict,
    plan_id: str,
    source_title: str,
    source_identifier: str,
    evaluation_report: dict | None = None,
) -> dict:
    """Build an adapter-neutral, membership-only catalog plan."""
    digest = master_sha256(master)
    proposal_id = f"pfp-{digest[:16]}"
    if evaluation_report is not None:
        if not evaluation_report.get("passed"):
            raise ValueError("catalog plan requires a passing evaluation")
        if evaluation_report.get("master_sha256") != digest:
            raise ValueError("evaluation does not match the proposed master")
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
        "proposal_id": proposal_id,
        "master_sha256": digest,
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
