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


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    quota_mode = config.get("quota_mode", "exact")
    if quota_mode not in {"exact", "flexible"}:
        raise ValueError("quota_mode must be exact or flexible")
    for view in config["views"]:
        if "quota" not in view and "target" not in view:
            raise ValueError(f"view {view['id']} requires quota or target")
        target = int(view.get("target", view.get("quota", 0)))
        minimum = int(view.get("minimum", 0))
        maximum = int(view.get("maximum", config["target_count"]))
        if not 0 <= minimum <= target <= maximum:
            raise ValueError(f"view {view['id']} requires minimum <= target <= maximum")
    if quota_mode == "exact" and sum(
        int(view.get("target", view.get("quota", 0))) for view in config["views"]
    ) != int(config["target_count"]):
        raise ValueError("view targets must sum to target_count in exact quota mode")
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


def visible_person_free(row: dict[str, str]) -> bool:
    visible = {value.casefold() for value in split_values(row.get("visible_context"))}
    visible_people = {"people", "person", "portrait", "crowd", "face"}
    for field in ("detected_face_count", "face_count"):
        if str(row.get(field, "")).strip():
            try:
                return int(float(row[field])) == 0 and not bool(visible & visible_people)
            except ValueError:
                return False
    if visible:
        return not bool(visible & visible_people)
    return not bool(split_values(row.get("persons")))


def person_free(row: dict[str, str], config: dict) -> bool:
    mode = config.get("person_free_mode", "no_named_association")
    if mode == "visible":
        return visible_person_free(row)
    if mode != "no_named_association":
        raise ValueError("person_free_mode must be visible or no_named_association")
    return not bool(split_values(row.get("persons")))


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
    event_limit = int(config.get("event_limit", len(unburst) or 1))
    event_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    unevented: list[dict[str, str]] = []
    for row in unburst:
        event = row.get("event_cluster", "").strip()
        (event_groups[event] if event else unevented).append(row)
    for group in event_groups.values():
        unevented.extend(sorted(group, key=cluster_rank, reverse=True)[:event_limit])
    return unevented


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
        view_target = int(view.get("target", view.get("quota", 0)))
        for row in by_view[view["id"]][:view_target]:
            if row["uuid"] not in selected_ids:
                selected.append(row)
                selected_ids.add(row["uuid"])

    target = int(config["target_count"])
    if len(selected) < target:
        view_specs = {view["id"]: view for view in config["views"]}
        selected_counts = Counter(row["primary_view"] for row in selected)
        remainder = sorted(
            (row for row in eligible if row["uuid"] not in selected_ids),
            key=lambda row: float(row["score_total"]),
            reverse=True,
        )
        for row in remainder:
            spec = view_specs[row["primary_view"]]
            maximum = int(spec.get("maximum", target))
            if config.get("quota_mode", "exact") == "exact":
                maximum = int(spec.get("target", spec.get("quota", 0)))
            if selected_counts[row["primary_view"]] >= maximum:
                continue
            selected.append(row)
            selected_ids.add(row["uuid"])
            selected_counts[row["primary_view"]] += 1
            if len(selected) == target:
                break

    selected = selected[:target]

    enforced_constraints: list[tuple[object, int, str]] = []

    def enforce_floor(predicate, required: int, reason: str) -> None:
        nonlocal selected, selected_ids
        current = sum(predicate(row) for row in selected)
        if current >= required:
            enforced_constraints.append((predicate, required, reason))
            return
        candidates = sorted(
            (row for row in eligible if row["uuid"] not in selected_ids and predicate(row)),
            key=lambda row: float(row["score_total"]),
            reverse=True,
        )
        while current < required and candidates:
            incoming = candidates.pop(0)
            donors = []
            for row in selected:
                if predicate(row):
                    continue
                if config.get("quota_mode", "exact") == "exact" and row["primary_view"] != incoming["primary_view"]:
                    continue
                preserves_prior = all(
                    sum(prior(candidate) for candidate in selected)
                    - int(bool(prior(row)))
                    + int(bool(prior(incoming)))
                    >= minimum
                    for prior, minimum, _ in enforced_constraints
                )
                if preserves_prior:
                    donors.append(row)
            donors = sorted(
                donors,
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
        enforced_constraints.append((predicate, required, reason))

    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
    exploratory_floor = math.ceil(target * float(config.get("exploratory_fraction", 0)))
    enforce_floor(lambda row: bool(split_values(row.get("persons"))), named_floor, "named relationships")
    enforce_floor(lambda row: person_free(row, config), person_free_floor, "person-free material context")
    enforce_floor(
        lambda row: str(row.get("evidence_confidence", "unknown")).lower() in {"low", "unknown", ""},
        exploratory_floor,
        "exploratory field",
    )
    if sum(bool(split_values(row.get("persons"))) for row in selected) < named_floor:
        raise ValueError("candidate field cannot satisfy minimum_named_people_fraction")
    if sum(person_free(row, config) for row in selected) < person_free_floor:
        raise ValueError("candidate field cannot satisfy minimum_person_free_fraction")
    if sum(
        str(row.get("evidence_confidence", "unknown")).lower() in {"low", "unknown", ""}
        for row in selected
    ) < exploratory_floor:
        raise ValueError("candidate field cannot satisfy exploratory_fraction")
    if len(selected) != target:
        raise ValueError(f"candidate field can select only {len(selected)} of {target} rows within view bounds")

    final_view_counts = Counter(row["primary_view"] for row in selected)
    for view in config["views"]:
        view_id = view["id"]
        view_target = int(view.get("target", view.get("quota", 0)))
        minimum = view_target if config.get("quota_mode", "exact") == "exact" else int(view.get("minimum", 0))
        maximum = view_target if config.get("quota_mode", "exact") == "exact" else int(view.get("maximum", target))
        if not minimum <= final_view_counts[view_id] <= maximum:
            raise ValueError(
                f"view {view_id} selected {final_view_counts[view_id]}; required {minimum}...{maximum}"
            )
    selected.sort(key=lambda row: (row["primary_view"], -float(row["score_total"]), row["uuid"]))
    view_counts = Counter(row["primary_view"] for row in selected)
    view_targets = {
        view["id"]: int(view.get("target", view.get("quota", 0)))
        for view in config["views"]
    }
    summary = {
        "inventory_count": len(inventory),
        "eligible_after_cluster_reduction": len(eligible),
        "hold_count": len(holds),
        "selected_count": len(selected),
        "view_counts": dict(sorted(view_counts.items())),
        "view_targets": view_targets,
        "view_target_deltas": {
            view: view_counts.get(view, 0) - target_count
            for view, target_count in view_targets.items()
        },
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "person_free_count": sum(person_free(row, config) for row in selected),
        "person_free_mode": config.get("person_free_mode", "no_named_association"),
        "exploratory_count": sum(
            str(row.get("evidence_confidence", "unknown")).lower() in {"low", "unknown", ""}
            for row in selected
        ),
        "confidence_uncertain_count": sum(
            row.get("evidence_confidence", "unknown") in {"low", "unknown", ""}
            for row in selected
        ),
    }
    # Retain the legacy field for downstream manifests while making its semantics explicit.
    summary["uncertain_count"] = summary["confidence_uncertain_count"]
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


def evaluate(feedback: list[dict[str, str]], config: dict) -> tuple[dict, bool]:
    allowed = {"fit", "reject", "uncertain"}
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in allowed]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / len(feedback) if feedback else 0.0
    precision = fit / (fit + reject) if fit + reject else 0.0
    by_view = {}
    for view in sorted({row.get("primary_view", "unknown") for row in feedback}):
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        by_view[view] = {
            "judged": len(rows),
            "precision": sum(row["judgment"].strip().lower() == "fit" for row in decisive) / len(decisive) if decisive else None,
        }
    minimum_per_view = float(config.get("minimum_per_view_precision", 0.65))
    view_config = {view["id"]: view for view in config["views"]}
    per_view_failures = []
    per_view_waivers = []
    for view, result in by_view.items():
        value = result["precision"]
        spec = view_config.get(view, {})
        threshold = float(spec.get("minimum_precision", minimum_per_view))
        material = bool(spec.get("material", True))
        hypothesis = bool(spec.get("hypothesis", False)) or "editor hypothesis" in str(spec.get("label", "")).casefold()
        if value is not None and material and value < threshold:
            if hypothesis:
                per_view_waivers.append({"view": view, "precision": value, "threshold": threshold, "reason": "editor hypothesis"})
            else:
                per_view_failures.append({"view": view, "precision": value, "threshold": threshold})
    passed = (
        coverage >= float(config.get("minimum_eval_coverage", 0.8))
        and precision >= float(config.get("minimum_eval_precision", 0.75))
        and not per_view_failures
    )
    report = {
        "sample_count": len(feedback),
        "judged_count": len(judged),
        "fit": fit,
        "reject": reject,
        "uncertain": uncertain,
        "coverage": round(coverage, 4),
        "precision": round(precision, 4),
        "minimum_coverage": config.get("minimum_eval_coverage", 0.8),
        "minimum_precision": config.get("minimum_eval_precision", 0.75),
        "minimum_per_view_precision": minimum_per_view,
        "per_view_failures": per_view_failures,
        "per_view_waivers": per_view_waivers,
        "passed": passed,
        "by_view": by_view,
    }
    return report, passed


def validate(
    master: list[dict[str, str]],
    holds: list[dict[str, str]],
    config: dict,
    *,
    evaluation_report: dict | None = None,
    candidate_summary: dict | None = None,
) -> tuple[list[str], dict]:
    errors: list[str] = []
    gates: list[dict] = []

    def gate(name: str, passed: bool, detail: object, *, waived: bool = False) -> None:
        status = "WAIVED" if waived else ("PASS" if passed else "FAIL")
        gates.append({"name": name, "status": status, "detail": detail})
        if status == "FAIL":
            errors.append(f"{name}: {detail}")

    ids = [row["uuid"] for row in master]
    hold_ids = {row["uuid"] for row in holds}
    gate("target", len(master) == int(config["target_count"]), f"expected {config['target_count']}, found {len(master)}")
    gate("uniqueness", len(ids) == len(set(ids)), f"{len(ids) - len(set(ids))} duplicate UUIDs")
    overlap = set(ids) & hold_ids
    gate("safety-disjoint", not overlap, f"master/HOLD overlap: {len(overlap)}")
    missing_reasons = sum(not row.get("selection_reason") for row in master)
    gate("selection-reasons", missing_reasons == 0, f"rows without reasons: {missing_reasons}")
    configured = {
        view["id"] for view in config["views"]
        if int(view.get("minimum", view.get("target", view.get("quota", 0)))) > 0
    }
    represented = {row.get("primary_view") for row in master}
    missing_views = configured - represented
    gate("view-coverage", not missing_views, f"missing views: {', '.join(sorted(missing_views)) or 'none'}")

    if config.get("require_still_only"):
        invalid_media = []
        for row in master:
            media = str(row.get("media_type", row.get("kind", ""))).casefold()
            is_photo = truthy(row.get("is_photo")) if "is_photo" in row else media in {"photo", "still", "image", "0"}
            if not is_photo:
                invalid_media.append(row["uuid"])
        gate("still-only", not invalid_media, f"non-still or unknown rows: {len(invalid_media)}")
    else:
        gate("still-only", True, "not required by configuration", waived=True)

    if config.get("require_pixel_available"):
        unavailable = [row["uuid"] for row in master if not truthy(row.get("pixel_available"))]
        gate("pixels-local", not unavailable, f"unavailable rows: {len(unavailable)}")
    else:
        gate("pixels-local", True, "not required by configuration", waived=True)

    if config.get("require_preview_exported"):
        missing_previews = [row["uuid"] for row in master if not truthy(row.get("preview_exported"))]
        gate("previews-exported", not missing_previews, f"missing previews: {len(missing_previews)}")
    else:
        gate("previews-exported", True, "not required by configuration", waived=True)

    unresolved = [row["uuid"] for row in master if str(row.get("safety_status", "clear")).casefold() in {"hold", "needs-review", "unavailable"}]
    gate("needs-review-resolved", not unresolved, f"unresolved safety rows: {len(unresolved)}")

    named_count = sum(bool(split_values(row.get("persons"))) for row in master)
    named_required = math.ceil(len(master) * float(config.get("minimum_named_people_fraction", 0)))
    gate("named-associations", named_count >= named_required, f"found {named_count}, required {named_required}")
    person_free_count = sum(person_free(row, config) for row in master)
    person_free_required = math.ceil(len(master) * float(config.get("minimum_person_free_fraction", 0)))
    gate("person-free", person_free_count >= person_free_required, f"found {person_free_count}, required {person_free_required}; mode={config.get('person_free_mode', 'no_named_association')}")

    if candidate_summary is not None and "outside_prior_fraction" in candidate_summary:
        actual = float(candidate_summary["outside_prior_fraction"])
        required = float(config.get("minimum_outside_prior_fraction", 0))
        gate("fresh-candidate-share", actual >= required, f"found {actual:.4f}, required {required:.4f}")
    elif float(config.get("minimum_outside_prior_fraction", 0)) > 0:
        gate("fresh-candidate-share", False, "candidate summary with outside_prior_fraction is required")
    else:
        gate("fresh-candidate-share", True, "not required by configuration", waived=True)

    if evaluation_report is not None:
        gate("evaluation-overall", bool(evaluation_report.get("passed")), f"precision={evaluation_report.get('precision')}, coverage={evaluation_report.get('coverage')}")
        failures = evaluation_report.get("per_view_failures", [])
        gate("evaluation-per-view", not failures, failures or "all material views passed or were explicitly waived")
    else:
        gate("evaluation-overall", True, "evaluation report not supplied", waived=True)
        gate("evaluation-per-view", True, "evaluation report not supplied", waived=True)

    hypothesis_errors = []
    by_id = {view["id"]: view for view in config["views"]}
    for view_id in represented:
        spec = by_id.get(view_id, {})
        if spec.get("hypothesis") and "editor hypothesis" not in str(spec.get("label", "")).casefold():
            hypothesis_errors.append(view_id)
    gate("hypothesis-labeling", not hypothesis_errors, f"unlabeled hypothesis views: {', '.join(sorted(hypothesis_errors)) or 'none'}")

    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "represented_views": sorted(represented),
        "named_people_count": named_count,
        "person_free_count": person_free_count,
        "gates": gates,
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
