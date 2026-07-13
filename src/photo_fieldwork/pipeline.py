from __future__ import annotations

import csv
import hashlib
import json
import random
import math
from datetime import datetime, timezone
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


JUDGMENTS = {"fit", "reject", "uncertain"}
ASSIGNMENT_STATUSES = {"assigned", "unclassified", "sparse-hypothesis"}


def ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def write_private_text(path: Path, value: str) -> None:
    ensure_private_directory(path.parent)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {"seed", "target_count", "unclassified_view", "views"}
    missing = required - set(config)
    if missing:
        raise ValueError(f"config missing required fields: {', '.join(sorted(missing))}")
    if not isinstance(config["views"], list) or not config["views"]:
        raise ValueError("config views must be a non-empty list")
    for index, view in enumerate(config["views"]):
        missing_view = {"id", "label", "quota"} - set(view)
        if missing_view:
            raise ValueError(
                f"view {index} missing required fields: {', '.join(sorted(missing_view))}"
            )
        if int(view["quota"]) < 0:
            raise ValueError(f"view {view['id']} quota must be non-negative")
    if int(config["target_count"]) < 1:
        raise ValueError("target_count must be positive")
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
    valid_modes = {"material", "sparse-hypothesis"}
    invalid_modes = {
        str(view.get("evaluation_mode", "material"))
        for view in config["views"]
        if str(view.get("evaluation_mode", "material")) not in valid_modes
    }
    if invalid_modes:
        raise ValueError(f"invalid view evaluation modes: {', '.join(sorted(invalid_modes))}")
    for field in (
        "minimum_eval_precision",
        "minimum_eval_coverage",
        "minimum_view_eval_precision",
        "maximum_eval_uncertainty",
        "minimum_named_people_fraction",
        "minimum_person_free_fraction",
    ):
        value = float(config.get(field, 0))
        if not 0 <= value <= 1:
            raise ValueError(f"{field} must be between 0 and 1")
    if int(config.get("minimum_view_eval_sample", 2)) < 1:
        raise ValueError("minimum_view_eval_sample must be at least 1")
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
    ensure_private_directory(path.parent)
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
    path.chmod(0o600)


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def split_values(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def stable_noise(seed: int, uuid: str) -> float:
    digest = hashlib.sha256(f"{seed}:{uuid}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def master_sha256(rows: Iterable[dict[str, str]]) -> str:
    """Hash the exact membership and editorial assignment written to Photos."""
    payload = [
        {
            "uuid": str(row["uuid"]),
            "assigned_view": str(row.get("assigned_view") or row.get("primary_view") or ""),
        }
        for row in rows
    ]
    payload.sort(key=lambda row: (row["assigned_view"], row["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_hold(row: dict[str, str]) -> bool:
    return (
        str(row.get("safety_status", "clear")).lower()
        in {"hold", "automatic-hold", "human-needs-review", "unavailable"}
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
    observation = row.get("visible_observation") or row.get("visible_context")
    if observation and row.get("observation_source") in {"human", "reviewer", "delegated-editorial-inference"}:
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


@dataclass
class _FlowEdge:
    target: int
    reverse: int
    capacity: int
    original_capacity: int


def _add_flow_edge(graph: list[list[_FlowEdge]], source: int, target: int, capacity: int) -> None:
    graph[source].append(_FlowEdge(target, len(graph[target]), capacity, capacity))
    graph[target].append(_FlowEdge(source, len(graph[source]) - 1, 0, 0))


def _maximum_flow(graph: list[list[_FlowEdge]], source: int, sink: int) -> int:
    flow = 0
    while True:
        level = [-1] * len(graph)
        level[source] = 0
        queue = [source]
        for node in queue:
            for edge in graph[node]:
                if edge.capacity and level[edge.target] < 0:
                    level[edge.target] = level[node] + 1
                    queue.append(edge.target)
        if level[sink] < 0:
            return flow
        cursor = [0] * len(graph)

        def send(node: int, available: int) -> int:
            if node == sink:
                return available
            while cursor[node] < len(graph[node]):
                edge = graph[node][cursor[node]]
                if edge.capacity and level[edge.target] == level[node] + 1:
                    pushed = send(edge.target, min(available, edge.capacity))
                    if pushed:
                        edge.capacity -= pushed
                        graph[edge.target][edge.reverse].capacity += pushed
                        return pushed
                cursor[node] += 1
            return 0

        while pushed := send(source, 1 << 30):
            flow += pushed


def assign_candidates(rows: list[dict[str, str]], config: dict) -> list[dict[str, str]]:
    """Select and assign exact view quotas from retrieval hypotheses.

    This deterministic maximum-flow step keeps retrieval hypotheses distinct
    from the editorial assignment later frozen into the proposal manifest.
    """
    views = [view for view in config["views"] if int(view["quota"]) > 0]
    configured = {view["id"] for view in views}
    unclassified = config["unclassified_view"]

    def candidates(row: dict[str, str]) -> list[str]:
        values = [value for value in split_values(row.get("candidate_views")) if value in configured]
        if unclassified in configured and unclassified not in values:
            values.append(unclassified)
        return values or ([unclassified] if unclassified in configured else [])

    availability = Counter(view for row in rows for view in set(candidates(row)))
    ordered_rows = sorted(rows, key=lambda row: (-float(row["score_total"]), row["uuid"]))
    source = 0
    asset_offset = 1
    view_offset = asset_offset + len(ordered_rows)
    sink = view_offset + len(views)
    graph: list[list[_FlowEdge]] = [[] for _ in range(sink + 1)]
    view_nodes = {view["id"]: view_offset + index for index, view in enumerate(views)}
    node_views = {node: view for view, node in view_nodes.items()}
    quota_by_view = {view["id"]: int(view["quota"]) for view in views}
    scarcity = {
        view["id"]: availability[view["id"]] / max(1, int(view["quota"]))
        for view in views
    }

    for index, row in enumerate(ordered_rows):
        node = asset_offset + index
        _add_flow_edge(graph, source, node, 1)
        original_order = {view: position for position, view in enumerate(candidates(row))}
        ordered_views = sorted(
            candidates(row),
            key=lambda view: (
                view == unclassified,
                original_order[view],
                scarcity.get(view, float("inf")),
                view,
            ),
        )
        for view in ordered_views:
            _add_flow_edge(graph, node, view_nodes[view], 1)
    for view in views:
        _add_flow_edge(graph, view_nodes[view["id"]], sink, int(view["quota"]))

    target = int(config["target_count"])
    achieved = _maximum_flow(graph, source, sink)
    if achieved != target:
        detail = ", ".join(
            f"{view['id']} eligible={availability[view['id']]} quota={view['quota']}"
            for view in views
        )
        raise ValueError(f"view quotas are infeasible: assigned {achieved} of {target}; {detail}")

    assigned = []
    for index, row in enumerate(ordered_rows):
        node = asset_offset + index
        view = next(
            (
                node_views[edge.target]
                for edge in graph[node]
                if edge.target in node_views and edge.original_capacity == 1 and edge.capacity == 0
            ),
            None,
        )
        if view is None:
            continue
        item = dict(row)
        item["assigned_view"] = view
        item["assignment_status"] = "unclassified" if view == unclassified else "assigned"
        item["assignment_reason"] = (
            "deterministic quota assignment from retrieval hypotheses; "
            f"view availability {availability[view]} for quota "
            f"{quota_by_view[view]}"
        )
        assigned.append(item)
    return assigned


def select(inventory: list[dict[str, str]], config: dict) -> tuple[list[dict], list[dict], dict]:
    holds = [dict(row) for row in inventory if is_hold(row)]
    candidate_pool = cluster_representatives([dict(row) for row in inventory if not is_hold(row)], config)
    for row in candidate_pool:
        row["score_total"] = f"{rank_row(row, config):.6f}"
    assignment_presence = [bool(str(row.get("assigned_view", "")).strip()) for row in candidate_pool]
    if any(assignment_presence) and not all(assignment_presence):
        raise ValueError("inventory cannot mix assigned and unassigned eligible rows")
    automatic_assignment = not any(assignment_presence)
    eligible = assign_candidates(candidate_pool, config) if automatic_assignment else candidate_pool
    for row in eligible:
        row["primary_view"] = choose_primary_view(row, config)
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_tier"] = "evidence" if confidence in {"high", "medium"} else "exploratory"
        row["selection_reason"] = "; ".join(
            reason
            for reason in [
                f"editorial assignment {row['primary_view']}",
                f"assignment: {row.get('assignment_reason')}" if row.get("assignment_reason") else "",
                f"retrieval hypotheses: {row.get('candidate_views')}" if row.get("candidate_views") else "",
                f"visible observation: {row.get('visible_observation')}" if row.get("visible_observation") else "",
                f"machine-visible signals: {row.get('machine_visible_signals')}" if row.get("machine_visible_signals") else "",
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
    replacement_pool = [row for row in candidate_pool if row["uuid"] not in selected_ids]

    def enforce_floor(predicate, required: int, reason: str) -> None:
        nonlocal selected, selected_ids
        current = sum(predicate(row) for row in selected)
        if current >= required:
            return
        candidates = sorted(
            (row for row in replacement_pool if row["uuid"] not in selected_ids and predicate(row)),
            key=lambda row: float(row["score_total"]),
            reverse=True,
        )
        while current < required and candidates:
            incoming = candidates.pop(0)
            allowed = set(split_values(incoming.get("candidate_views")))
            donors = sorted(
                (
                    row for row in selected
                    if not predicate(row)
                    and (
                        row["primary_view"] in allowed
                        or row["primary_view"] == config["unclassified_view"]
                    )
                ),
                key=lambda row: (float(row["score_total"]), row["uuid"]),
            )
            if not donors:
                continue
            outgoing = donors[0]
            selected.remove(outgoing)
            selected_ids.remove(outgoing["uuid"])
            incoming = dict(incoming)
            incoming["assigned_view"] = outgoing["primary_view"]
            incoming["primary_view"] = outgoing["primary_view"]
            incoming["assignment_status"] = (
                "unclassified" if incoming["primary_view"] == config["unclassified_view"] else "assigned"
            )
            incoming["assignment_reason"] = f"deterministic same-view replacement for {reason}"
            confidence = str(incoming.get("evidence_confidence", "unknown")).lower()
            incoming["selection_tier"] = "evidence" if confidence in {"high", "medium"} else "exploratory"
            incoming["selection_reason"] = (
                f"editorial assignment {incoming['primary_view']}; diversity floor: {reason}"
            )
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
    expected_view_counts = {
        view["id"]: int(view["quota"])
        for view in config["views"]
        if int(view["quota"]) > 0
    }
    actual_view_counts = Counter(row["primary_view"] for row in selected)
    if dict(sorted(actual_view_counts.items())) != dict(sorted(expected_view_counts.items())):
        raise ValueError(
            "selected view counts do not match configured quotas; provide complete explicit assignments "
            "or remove them and use deterministic constrained assignment"
        )
    selected.sort(key=lambda row: (row["primary_view"], -float(row["score_total"]), row["uuid"]))
    digest = master_sha256(selected)
    proposal_id = f"pfp-{digest[:16]}"
    for row in selected:
        row["master_sha256"] = digest
        row["proposal_id"] = proposal_id
        row["provenance_status"] = row.get("provenance_status") or "retrieval-only"
        row["publication_state"] = row.get("publication_state") or "publication-review-required"
    summary = {
        "inventory_count": len(inventory),
        "eligible_after_cluster_reduction": len(candidate_pool),
        "hold_count": len(holds),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "master_sha256": digest,
        "proposal_id": proposal_id,
        "assignment_method": (
            "deterministic-constrained-maximum-flow" if automatic_assignment else "explicit-assigned-view"
        ),
    }
    return selected, holds, summary


def make_sample(
    master: list[dict[str, str]],
    per_view: int,
    seed: int,
    round_id: str = "round-01",
) -> list[dict]:
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
            item["view_selected_count"] = str(len(rows))
            item["sampling_reason"] = (
                "full sparse view" if len(rows) <= per_view else "score boundary and deterministic random stratum sample"
            )
            item["judgment"] = ""
            item["evaluation_note"] = ""
            item["visible_reason"] = ""
            item["error_category"] = ""
            item["round_id"] = round_id
            item["reviewer_lens"] = ""
            sample.append(item)
    return sample


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)


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
            if row.get("judgment", "").strip() and row.get("judgment", "").strip().lower() not in JUDGMENTS
        }
    )
    if unknown:
        raise ValueError(f"unknown evaluation judgments: {', '.join(unknown)}")
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in JUDGMENTS]
    missing_visible_reason_count = sum(not row.get("visible_reason", "").strip() for row in judged)
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / len(feedback) if feedback else 0.0
    precision = fit / (fit + reject) if fit + reject else 0.0
    by_view = {}
    minimum_view_precision = float(config.get("minimum_view_eval_precision", 0.65))
    minimum_view_sample = int(config.get("minimum_view_eval_sample", 2))
    maximum_uncertainty = float(config.get("maximum_eval_uncertainty", 0.25))
    minimum_coverage = float(config.get("minimum_eval_coverage", 0.8))
    views_by_id = {str(view["id"]): view for view in config["views"] if int(view["quota"]) > 0}
    for view_id, view in sorted(views_by_id.items()):
        sampled = [row for row in feedback if row.get("primary_view", "unknown") == view_id]
        rows = [row for row in judged if row.get("primary_view", "unknown") == view_id]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_fit = sum(row["judgment"].strip().lower() == "fit" for row in decisive)
        view_precision = view_fit / len(decisive) if decisive else None
        wilson_low, wilson_high = wilson_interval(view_fit, len(decisive))
        view_coverage = len(rows) / len(sampled) if sampled else 0.0
        uncertainty_rate = (
            sum(row["judgment"].strip().lower() == "uncertain" for row in rows) / len(rows)
            if rows else 0.0
        )
        selected_count = max(
            [int(row.get("view_selected_count") or 0) for row in sampled] or [int(view["quota"])]
        )
        required_decisive = min(minimum_view_sample, selected_count)
        mode = str(view.get("evaluation_mode", "material"))
        precision_gate = float(view.get("minimum_eval_precision", minimum_view_precision))
        reasons = []
        if not sampled:
            reasons.append("view not sampled")
        if view_coverage < minimum_coverage:
            reasons.append("coverage below minimum")
        if uncertainty_rate > maximum_uncertainty:
            reasons.append("uncertainty above maximum")
        if mode == "material":
            if len(decisive) < required_decisive:
                reasons.append("insufficient decisive judgments")
            if view_precision is None or view_precision < precision_gate:
                reasons.append("precision below minimum")
        by_view[view_id] = {
            "label": view.get("label", view_id),
            "evaluation_mode": mode,
            "sampled": len(sampled),
            "judged": len(rows),
            "decisive": len(decisive),
            "fit": view_fit,
            "reject": len(decisive) - view_fit,
            "required_decisive": required_decisive,
            "coverage": round(view_coverage, 4),
            "precision": round(view_precision, 4) if view_precision is not None else None,
            "wilson_95_low": wilson_low,
            "wilson_95_high": wilson_high,
            "minimum_precision": precision_gate if mode == "material" else None,
            "uncertainty_rate": round(uncertainty_rate, 4),
            "maximum_uncertainty": maximum_uncertainty,
            "passed": not reasons,
            "failure_reasons": reasons,
        }
    passed = (
        coverage >= minimum_coverage
        and precision >= float(config.get("minimum_eval_precision", 0.75))
        and all(result["passed"] for result in by_view.values())
        and missing_visible_reason_count == 0
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
        "precision": round(precision, 4),
        "minimum_coverage": minimum_coverage,
        "minimum_precision": config.get("minimum_eval_precision", 0.75),
        "minimum_view_precision": minimum_view_precision,
        "minimum_view_sample": minimum_view_sample,
        "maximum_uncertainty": maximum_uncertainty,
        "missing_visible_reason_count": missing_visible_reason_count,
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
    if any(not row.get("assigned_view") for row in master):
        errors.append("one or more selected rows lack assigned_view")
    hashes = {row.get("master_sha256", "") for row in master}
    expected_hash = master_sha256(master)
    if hashes != {expected_hash}:
        errors.append("master_sha256 is missing or does not match exact membership and assignments")
    proposal_ids = {row.get("proposal_id", "") for row in master}
    if proposal_ids != {f"pfp-{expected_hash[:16]}"}:
        errors.append("proposal_id is missing or does not match master_sha256")
    configured = {view["id"] for view in config["views"] if int(view["quota"]) > 0}
    represented = {row.get("primary_view") for row in master}
    missing_views = configured - represented
    if missing_views:
        errors.append(f"configured views absent from master: {', '.join(sorted(missing_views))}")
    actual_view_counts = Counter(row.get("primary_view") for row in master)
    expected_view_counts = {
        view["id"]: int(view["quota"])
        for view in config["views"]
        if int(view["quota"]) > 0
    }
    if dict(sorted(actual_view_counts.items())) != dict(sorted(expected_view_counts.items())):
        errors.append("master view counts do not match configured quotas")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "represented_views": sorted(represented),
        "view_counts": dict(sorted(actual_view_counts.items())),
        "master_sha256": expected_hash,
        "proposal_id": f"pfp-{expected_hash[:16]}",
    }
    return errors, metrics


def build_catalog_plan(
    master: list[dict[str, str]],
    config: dict,
    plan_id: str,
    source_title: str,
    source_identifier: str,
    evaluation_report: dict,
) -> dict:
    """Build an adapter-neutral, membership-only catalog plan."""
    digest = master_sha256(master)
    proposal_id = f"pfp-{digest[:16]}"
    if not evaluation_report.get("passed"):
        raise ValueError("catalog plan requires a passing final evaluation")
    if evaluation_report.get("master_sha256") != digest:
        raise ValueError("evaluated master hash does not match the proposed catalog plan")
    if evaluation_report.get("proposal_id") != proposal_id:
        raise ValueError("evaluated proposal_id does not match the proposed catalog plan")
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
        "evaluation": {
            "proposal_id": evaluation_report["proposal_id"],
            "master_sha256": evaluation_report["master_sha256"],
            "passed": True,
        },
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
