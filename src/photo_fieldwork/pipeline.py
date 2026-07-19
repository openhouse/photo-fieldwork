from __future__ import annotations

import csv
import copy
import hashlib
import heapq
import json
import random
import math
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from .integrity import content_sha256, master_sha256, relation_leakage_report


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
    for key in (
        "exploratory_fraction",
        "minimum_eval_precision",
        "minimum_eval_coverage",
        "minimum_view_sampling_coverage",
        "minimum_view_precision",
        "minimum_named_people_fraction",
        "minimum_person_free_fraction",
        "minimum_outside_prior_final_fraction",
    ):
        value = float(config.get(key, 0))
        if not 0 <= value <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
    if int(config.get("minimum_view_decisions", 1)) < 1:
        raise ValueError("minimum_view_decisions must be positive")
    unknown_cap_views = set(config.get("event_cluster_caps", {})) - set(view_ids)
    if unknown_cap_views:
        raise ValueError(
            "event_cluster_caps name unknown views: "
            + ", ".join(sorted(unknown_cap_views))
        )
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
    return candidate_view_ids(row, config)[0]


def candidate_view_ids(row: dict[str, str], config: dict) -> list[str]:
    configured = {view["id"] for view in config["views"]}
    candidates = [view for view in split_values(row.get("candidate_views")) if view in configured]
    return list(dict.fromkeys(candidates)) or [config["unclassified_view"]]


def rank_row(row: dict[str, str], config: dict) -> float:
    return attention_score(row) + evidence_score(row) + stable_noise(int(config["seed"]), row["uuid"])


def assign_exact_quotas(rows: list[dict[str, str]], config: dict) -> tuple[dict[str, str], dict]:
    """Assign overlapping view hypotheses jointly under exact quotas and event caps."""
    active_views = [
        view
        for view in config["views"]
        if int(view["quota"]) > 0 and view.get("status", "active") == "active"
    ]
    quotas = {view["id"]: int(view["quota"]) for view in active_views}
    target = int(config["target_count"])
    if sum(quotas.values()) != target:
        raise ValueError("active view quotas must sum to target_count")

    row_map = {row["uuid"]: row for row in rows}
    candidates = {
        uuid: [view for view in candidate_view_ids(row, config) if view in quotas]
        for uuid, row in row_map.items()
    }
    candidates = {uuid: views for uuid, views in candidates.items() if views}
    eligible_by_view = {
        view: sum(view in supported for supported in candidates.values())
        for view in quotas
    }
    overlaps = Counter(";".join(sorted(views)) for views in candidates.values())
    event_caps = {
        str(view): int(cap)
        for view, cap in config.get("event_cluster_caps", {}).items()
        if int(cap) > 0
    }

    def edge_benefit(uuid: str, view: str, views: list[str]) -> int:
        preference = views.index(view)
        return (
            int(rank_row(row_map[uuid], config) * 1_000_000)
            + (len(views) - preference) * 1_000
            + int(stable_noise(int(config["seed"]), f"{uuid}:{view}") * 999)
        )

    # An edge ranked below the top T edges for an uncapped view cannot occur in
    # an optimal T-asset assignment: at most T-1 better assets can be selected
    # elsewhere, leaving a better unselected replacement. Capped views retain
    # their full graph because the group constraint invalidates that dominance
    # argument. Diversity-floor candidates remain available to the joint repair.
    original_edge_count = sum(len(views) for views in candidates.values())
    retained_edges: set[tuple[str, str]] = set()
    for view in quotas:
        view_edges = [
            (edge_benefit(uuid, view, views), uuid)
            for uuid, views in candidates.items()
            if view in views
        ]
        view_edges.sort(key=lambda item: (-item[0], item[1]))
        limit = len(view_edges) if view in event_caps else min(target, len(view_edges))
        retained_edges.update((uuid, view) for _, uuid in view_edges[:limit])
    candidates = {
        uuid: [view for view in views if (uuid, view) in retained_edges]
        for uuid, views in candidates.items()
    }
    candidates = {uuid: views for uuid, views in candidates.items() if views}

    source = 0
    view_nodes = {view: index + 1 for index, view in enumerate(quotas)}
    group_keys: dict[tuple[str, str], str] = {}
    for uuid, views in candidates.items():
        cluster = str(row_map[uuid].get("event_cluster", "")).strip()
        for view in views:
            group_keys[(view, uuid)] = cluster or f"asset:{uuid}"
    unique_groups = sorted({(view, key) for (view, _), key in group_keys.items()})
    group_start = 1 + len(view_nodes)
    group_nodes = {
        key: group_start + index for index, key in enumerate(unique_groups)
    }
    asset_start = group_start + len(group_nodes)
    asset_nodes = {
        uuid: asset_start + index for index, uuid in enumerate(sorted(candidates))
    }
    sink = asset_start + len(asset_nodes)
    graph: list[list[dict[str, int]]] = [[] for _ in range(sink + 1)]

    def add_edge(start: int, stop: int, capacity: int, cost: int = 0) -> dict[str, int]:
        forward = {
            "to": stop,
            "rev": len(graph[stop]),
            "cap": capacity,
            "cost": cost,
        }
        backward = {
            "to": start,
            "rev": len(graph[start]),
            "cap": 0,
            "cost": -cost,
        }
        graph[start].append(forward)
        graph[stop].append(backward)
        return forward

    source_edges = {
        view: add_edge(source, node, quotas[view])
        for view, node in view_nodes.items()
    }
    ranked_edges = []
    for uuid, views in candidates.items():
        original_views = candidate_view_ids(row_map[uuid], config)
        for view in views:
            benefit = edge_benefit(uuid, view, original_views)
            ranked_edges.append((view, group_keys[(view, uuid)], benefit, uuid))
    group_priority: dict[tuple[str, str], int] = {}
    for view, group, benefit, _ in ranked_edges:
        key = (view, group)
        group_priority[key] = min(
            -benefit,
            group_priority.get(key, -benefit),
        )
    group_members: Counter[tuple[str, str]] = Counter(
        (view, group_keys[(view, uuid)])
        for uuid, views in candidates.items()
        for view in views
    )
    for view, group in sorted(
        unique_groups,
        key=lambda key: (key[0], group_priority[key], key[1]),
    ):
        node = group_nodes[(view, group)]
        cap = group_members[(view, group)]
        if not group.startswith("asset:") and view in event_caps:
            cap = min(cap, event_caps[view])
        add_edge(view_nodes[view], node, cap)

    assignment_edges: list[tuple[str, str, int, dict[str, int]]] = []
    maximum_benefit = max((benefit for _, _, benefit, _ in ranked_edges), default=0)
    for view, group, benefit, uuid in sorted(
        ranked_edges,
        key=lambda item: (item[0], item[1], -item[2], item[3]),
    ):
        edge = add_edge(
            group_nodes[(view, group)],
            asset_nodes[uuid],
            1,
            maximum_benefit - benefit,
        )
        assignment_edges.append((uuid, view, benefit, edge))
    for node in asset_nodes.values():
        add_edge(node, sink, 1)

    flow = 0
    total_cost = 0
    potentials = [0] * len(graph)
    while flow < target:
        distances = [float("inf")] * len(graph)
        previous: list[tuple[int, int] | None] = [None] * len(graph)
        distances[source] = 0
        queue: list[tuple[int, int]] = [(0, source)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            for edge_index, edge in enumerate(graph[node]):
                if edge["cap"] <= 0:
                    continue
                candidate = distance + edge["cost"] + potentials[node] - potentials[edge["to"]]
                if candidate < distances[edge["to"]]:
                    distances[edge["to"]] = candidate
                    previous[edge["to"]] = (node, edge_index)
                    heapq.heappush(queue, (candidate, edge["to"]))
        if previous[sink] is None:
            break
        for node, distance in enumerate(distances):
            if distance != float("inf"):
                potentials[node] += int(distance)
        amount = target - flow
        node = sink
        while node != source:
            parent, edge_index = previous[node] or (-1, -1)
            amount = min(amount, graph[parent][edge_index]["cap"])
            node = parent
        node = sink
        path_cost = 0
        while node != source:
            parent, edge_index = previous[node] or (-1, -1)
            edge = graph[parent][edge_index]
            path_cost += edge["cost"]
            edge["cap"] -= amount
            graph[node][edge["rev"]]["cap"] += amount
            node = parent
        flow += amount
        total_cost += amount * path_cost

    assigned_by_view = {
        view: quotas[view] - source_edges[view]["cap"] for view in quotas
    }
    deficits = {
        view: quotas[view] - assigned_by_view[view]
        for view in quotas
        if assigned_by_view[view] != quotas[view]
    }
    report = {
        "status": "PASS" if flow == target and not deficits else "INFEASIBLE",
        "target_count": target,
        "eligible_asset_count": len(candidates),
        "eligible_by_view": eligible_by_view,
        "assigned_by_view": assigned_by_view,
        "deficits": deficits,
        "overlap_groups": dict(sorted(overlaps.items())),
        "event_cluster_caps": event_caps,
        "input_assignment_edge_count": original_edge_count,
        "solver_assignment_edge_count": len(ranked_edges),
        "dominance_pruning": "top-target-per-uncapped-view",
        "assignment_objective": "maximum-total-deterministic-benefit",
        "assignment_cost": total_cost,
        "quotas_changed": False,
    }
    if report["status"] != "PASS":
        raise ValueError(f"exact view quota deficit: {json.dumps(report, sort_keys=True)}")
    chosen_edges = [item for item in assignment_edges if item[3]["cap"] == 0]
    assignments = {uuid: view for uuid, view, _, _ in chosen_edges}
    report["assignment_benefit"] = sum(benefit for _, _, benefit, _ in chosen_edges)
    if len(assignments) != target:
        raise ValueError("capacity solver produced a non-unique assignment")
    return assignments, report


def repair_diversity_floors(
    assignments: dict[str, str],
    rows: list[dict[str, str]],
    config: dict,
    floor_specs: list[tuple[str, int, object]],
) -> tuple[dict[str, str], dict]:
    """Backtrack alternating assignment paths until all diversity floors hold."""
    row_map = {row["uuid"]: row for row in rows}
    event_caps = {
        str(view): int(cap)
        for view, cap in config.get("event_cluster_caps", {}).items()
        if int(cap) > 0
    }
    active_views = {
        view["id"]
        for view in config["views"]
        if int(view["quota"]) > 0 and view.get("status", "active") == "active"
    }

    def count(state: dict[str, str], predicate) -> int:
        return sum(predicate(row_map[uuid]) for uuid in state)

    def caps_hold(state: dict[str, str]) -> bool:
        counts: Counter[tuple[str, str]] = Counter()
        for uuid, view in state.items():
            cluster = str(row_map[uuid].get("event_cluster", "")).strip()
            if cluster:
                counts[(view, cluster)] += 1
        return all(
            amount <= event_caps.get(view, amount)
            for (view, _), amount in counts.items()
        )

    def variants(
        state: dict[str, str],
        incoming_uuid: str,
    ) -> Iterable[dict[str, str]]:
        def place(
            current: dict[str, str],
            floating_uuid: str,
            previous_view: str | None,
            visited_assets: frozenset[str],
            visited_views: frozenset[str],
        ) -> Iterable[dict[str, str]]:
            supported = [
                view
                for view in candidate_view_ids(row_map[floating_uuid], config)
                if view in active_views and view != previous_view and view not in visited_views
            ]
            for view in supported:
                donors = sorted(
                    (uuid for uuid, assigned in current.items() if assigned == view),
                    key=lambda uuid: (float(row_map[uuid]["score_total"]), uuid),
                )
                for donor_uuid in donors:
                    if donor_uuid in visited_assets:
                        continue
                    proposal = dict(current)
                    del proposal[donor_uuid]
                    proposal[floating_uuid] = view
                    if not caps_hold(proposal):
                        continue
                    yield proposal
                    yield from place(
                        proposal,
                        donor_uuid,
                        view,
                        visited_assets | {donor_uuid},
                        visited_views | {view},
                    )

        yield from place(
            state,
            incoming_uuid,
            None,
            frozenset({incoming_uuid}),
            frozenset(),
        )

    visited_states: set[tuple[int, tuple[tuple[str, str], ...]]] = set()

    def satisfy(state: dict[str, str], floor_index: int) -> dict[str, str] | None:
        key = (floor_index, tuple(sorted(state.items())))
        if key in visited_states:
            return None
        visited_states.add(key)
        if floor_index == len(floor_specs):
            return state
        reason, required, predicate = floor_specs[floor_index]
        current = count(state, predicate)
        if current >= required:
            result = satisfy(state, floor_index + 1)
            if result is not None or required == 0:
                return result
            # A later floor may require a different representative of this
            # already-satisfied floor. Explore those substitutions before
            # declaring the joint system infeasible.
            alternatives = sorted(
                (
                    row
                    for row in rows
                    if row["uuid"] not in state and predicate(row)
                ),
                key=lambda row: (-float(row["score_total"]), row["uuid"]),
            )
            for incoming in alternatives:
                for proposal in variants(state, incoming["uuid"]):
                    if count(proposal, predicate) < required:
                        continue
                    result = satisfy(proposal, floor_index + 1)
                    if result is not None:
                        return result
            return None
        candidates = sorted(
            (
                row
                for row in rows
                if row["uuid"] not in state and predicate(row)
            ),
            key=lambda row: (-float(row["score_total"]), row["uuid"]),
        )
        for incoming in candidates:
            for proposal in variants(state, incoming["uuid"]):
                if count(proposal, predicate) <= current:
                    continue
                if any(
                    count(proposal, prior_predicate) < prior_required
                    for _, prior_required, prior_predicate in floor_specs[:floor_index]
                ):
                    continue
                result = satisfy(proposal, floor_index)
                if result is not None:
                    return result
        return None

    repaired = satisfy(dict(assignments), 0)
    if repaired is None:
        deficits = {
            reason: max(0, required - count(assignments, predicate))
            for reason, required, predicate in floor_specs
        }
        raise ValueError(
            "candidate field cannot jointly satisfy diversity floors: "
            + json.dumps(deficits, sort_keys=True)
        )
    counts = {
        reason: count(repaired, predicate)
        for reason, _, predicate in floor_specs
    }
    return repaired, {
        "status": "PASS",
        "method": "deterministic-alternating-path-backtracking",
        "requirements": {reason: required for reason, required, _ in floor_specs},
        "counts": counts,
        "membership_replacements": len(set(repaired) - set(assignments)),
        "view_reassignments": sum(
            assignments.get(uuid) != view
            for uuid, view in repaired.items()
            if uuid in assignments
        ),
    }


def select(inventory: list[dict[str, str]], config: dict) -> tuple[list[dict], list[dict], dict]:
    holds = [dict(row) for row in inventory if is_hold(row)]
    eligible = cluster_representatives([dict(row) for row in inventory if not is_hold(row)], config)
    for row in eligible:
        row["primary_view"] = choose_primary_view(row, config)
        row["score_total"] = f"{rank_row(row, config):.6f}"
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_tier"] = "evidence" if confidence in {"high", "medium"} else "exploratory"

    def explain(row: dict[str, str]) -> str:
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        return "; ".join(
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

    assignments, capacity = assign_exact_quotas(eligible, config)
    target = int(config["target_count"])
    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
    exploratory_floor = math.ceil(target * float(config.get("exploratory_fraction", 0)))
    outside_prior_floor = math.ceil(target * float(config.get("minimum_outside_prior_final_fraction", 0)))
    floor_specs = [
        ("named relationships", named_floor, lambda row: bool(split_values(row.get("persons")))),
        ("person-free material context", person_free_floor, lambda row: not bool(split_values(row.get("persons")))),
        ("exploratory editor field", exploratory_floor, lambda row: row.get("selection_tier") == "exploratory"),
        ("outside prior corpus", outside_prior_floor, lambda row: truthy(row.get("outside_prior"))),
    ]
    initial_assignments = dict(assignments)
    assignments, diversity = repair_diversity_floors(
        assignments,
        eligible,
        config,
        floor_specs,
    )
    original_ids = set(initial_assignments)
    selected: list[dict] = []
    for row in eligible:
        assigned_view = assignments.get(row["uuid"])
        if not assigned_view:
            continue
        row["primary_view"] = assigned_view
        row["selection_reason"] = explain(row)
        if row["uuid"] not in original_ids:
            row["selection_reason"] += "; joint diversity-floor repair"
        selected.append(row)
    selected.sort(key=lambda row: (row["primary_view"], -float(row["score_total"]), row["uuid"]))
    digest = master_sha256(selected)
    proposal_id = f"pfp-{digest[:16]}"
    for row in selected:
        row["master_sha256"] = digest
        row["proposal_id"] = proposal_id
    event_caps = {
        str(view): int(cap)
        for view, cap in config.get("event_cluster_caps", {}).items()
        if int(cap) > 0
    }
    summary = {
        "inventory_count": len(inventory),
        "eligible_after_cluster_reduction": len(eligible),
        "hold_count": len(holds),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "outside_prior_count": sum(truthy(row.get("outside_prior")) for row in selected),
        "capacity": capacity,
        "diversity_floors": diversity,
        "master_sha256": digest,
        "proposal_id": proposal_id,
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
    prior_rows: list[dict[str, str]] | None = None,
) -> list[dict]:
    """Draw a fresh, deterministic final holdout after the master is frozen.

    The estimate is a simple random sample of the untouched population. Extra
    rows may be added to meet a per-view review floor, but those rows are marked
    supplemental and excluded from the aggregate estimate. Rows used during
    tuning can be excluded explicitly so the final audit does not recycle its
    own training evidence.
    """
    excluded_ids = excluded_ids or set()
    prior_rows = prior_rows or []
    relational_report = relation_leakage_report(master, prior_rows)
    relationally_excluded = {
        item["sample_uuid"] for item in relational_report["collisions"]
    }
    eligible = [
        row
        for row in master
        if row["uuid"] not in excluded_ids and row["uuid"] not in relationally_excluded
    ]
    if not eligible:
        raise ValueError("no final-master rows remain after holdout exclusions")
    digest = master_sha256(master)
    proposal_id = f"pfp-{digest[:16]}"
    embedded_digests = {
        row.get("master_sha256", "").strip()
        for row in master
        if row.get("master_sha256", "").strip()
    }
    embedded_proposals = {
        row.get("proposal_id", "").strip()
        for row in master
        if row.get("proposal_id", "").strip()
    }
    if embedded_digests and embedded_digests != {digest}:
        raise ValueError("frozen master rows do not share the recomputed master identity")
    if embedded_proposals and embedded_proposals != {proposal_id}:
        raise ValueError("frozen master rows do not share the recomputed proposal identity")
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
        item["master_sha256"] = digest
        item["proposal_id"] = proposal_id
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


def evaluate(
    feedback: list[dict[str, str]],
    config: dict,
    leakage_report: dict | None = None,
) -> tuple[dict, bool]:
    allowed = {"fit", "reject", "uncertain"}
    edges = [
        (row.get("uuid", "").strip(), row.get("primary_view", "").strip())
        for row in feedback
    ]
    if len(edges) != len(set(edges)):
        raise ValueError("evaluation contains duplicate image-view judgments")
    identity_present = any(
        row.get("master_sha256", "").strip() or row.get("proposal_id", "").strip()
        for row in feedback
    )
    if identity_present and any(
        not row.get("master_sha256", "").strip()
        or not row.get("proposal_id", "").strip()
        for row in feedback
    ):
        raise ValueError("evaluation identity must be present on every feedback row")
    master_digests = {
        row.get("master_sha256", "").strip()
        for row in feedback
        if row.get("master_sha256", "").strip()
    }
    proposal_ids = {
        row.get("proposal_id", "").strip()
        for row in feedback
        if row.get("proposal_id", "").strip()
    }
    if len(master_digests) > 1 or len(proposal_ids) > 1:
        raise ValueError("evaluation feedback mixes more than one release candidate")

    canaries = [
        row for row in feedback if row.get("sample_role", "") == "regression-canary"
    ]
    fresh_feedback = [row for row in feedback if row not in canaries]
    judged = [
        row
        for row in fresh_feedback
        if row.get("judgment", "").strip().lower() in allowed
    ]
    final_holdout = bool(fresh_feedback) and all(
        row.get("sample_role", "").startswith("final-holdout") for row in fresh_feedback
    )
    relation_clean = bool(
        final_holdout
        and leakage_report
        and leakage_report.get("status") == "PASS"
        and not leakage_report.get("collisions")
    )
    estimate_judged = (
        [row for row in judged if truthy(row.get("estimate_included"))]
        if final_holdout else judged
    )
    fit = sum(row["judgment"].strip().lower() == "fit" for row in estimate_judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in estimate_judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in estimate_judged)
    review_completion = len(judged) / len(fresh_feedback) if fresh_feedback else 0.0
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
        [int(row.get("population_count") or 0) for row in fresh_feedback] or [0]
    )
    full_master_count = max(
        [int(row.get("full_master_count") or 0) for row in fresh_feedback] or [0]
    )
    field_audit_rate = len(fresh_feedback) / full_master_count if full_master_count else None
    untouched_population_audit_rate = (
        len([row for row in fresh_feedback if truthy(row.get("estimate_included"))])
        / population_count
        if population_count else None
    )
    by_view = {}
    minimum_view_decisions = int(config.get("minimum_view_decisions", 1))
    minimum_view_precision = float(config.get("minimum_view_precision", 0.0))
    for view in sorted(configured_views | {row.get("primary_view", "unknown") for row in fresh_feedback}):
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_fit = sum(row["judgment"].strip().lower() == "fit" for row in decisive)
        view_lower, view_upper = wilson_interval(view_fit, len(decisive))
        view_rate = view_fit / len(decisive) if decisive else None
        by_view[view] = {
            "judged": len(rows),
            "decisive": len(decisive),
            "decisive_fit_rate": view_rate,
            "wilson_95_lower": round(view_lower, 4) if decisive else None,
            "wilson_95_upper": round(view_upper, 4) if decisive else None,
            "passed": (
                len(decisive) >= minimum_view_decisions
                and view_rate is not None
                and view_rate >= minimum_view_precision
            ),
        }
    canary_judgments = [
        row.get("judgment", "").strip().lower() for row in canaries
    ]
    canary_regressions = sum(judgment != "fit" for judgment in canary_judgments)
    passed = (
        review_completion >= float(config.get("minimum_eval_coverage", 0.8))
        and decisive_fit_rate >= float(config.get("minimum_eval_precision", 0.75))
        and view_sampling_coverage >= float(config.get("minimum_view_sampling_coverage", 1.0))
        and all(by_view[view]["passed"] for view in configured_views)
        and canary_regressions == 0
    )
    final_lower_bound = config.get("minimum_final_wilson_lower_bound")
    if final_holdout and final_lower_bound is not None:
        passed = passed and lower >= float(final_lower_bound)
    if final_holdout and leakage_report is not None:
        passed = passed and relation_clean
    report = {
        "config_sha256": content_sha256(config),
        "proposal_id": next(iter(proposal_ids), None),
        "master_sha256": next(iter(master_digests), None),
        "sample_count": len(fresh_feedback),
        "regression_canary_count": len(canaries),
        "regression_canary_failures": canary_regressions,
        "judged_count": len(judged),
        "estimation_judged_count": len(estimate_judged),
        "estimation_sample_count": len(
            [row for row in fresh_feedback if truthy(row.get("estimate_included"))]
        ) if final_holdout else len(fresh_feedback),
        "supplemental_sample_count": len(fresh_feedback) - len(
            [row for row in fresh_feedback if truthy(row.get("estimate_included"))]
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
        "relation_clean_holdout": relation_clean,
        "leakage_report_sha256": (
            content_sha256(leakage_report) if leakage_report is not None else None
        ),
        "minimum_final_wilson_lower_bound": final_lower_bound,
        "minimum_view_decisions": minimum_view_decisions,
        "minimum_view_precision": minimum_view_precision,
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


def unsupported_view_gap_report(config: dict) -> dict:
    gaps = [
        {
            "view_id": view["id"],
            "label": view["label"],
            "intent_quota": int(view.get("intent_quota", view.get("quota", 0))),
            "effective_quota": int(view.get("quota", 0)),
            "status": view.get("status", "active"),
            "interpretation": "No selected row supported this view at final freeze.",
        }
        for view in config["views"]
        if view.get("status") in {"unsupported", "empty-by-editorial-decision"}
    ]
    return {
        "unsupported_views": gaps,
        "claim_boundary": (
            "A gap means qualifying evidence was not recovered in this run; "
            "it is not evidence that no relevant photograph exists."
        ),
        "production_album_policy": "omit unsupported and deliberately empty view albums",
    }


def validate(master: list[dict[str, str]], holds: list[dict[str, str]], config: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    ids = [row["uuid"] for row in master]
    try:
        digest = master_sha256(master)
    except ValueError as error:
        digest = None
        errors.append(str(error))
    proposal_id = f"pfp-{digest[:16]}" if digest else None
    embedded_digests = {
        row.get("master_sha256", "") for row in master if row.get("master_sha256", "")
    }
    embedded_proposals = {
        row.get("proposal_id", "") for row in master if row.get("proposal_id", "")
    }
    if digest and embedded_digests and embedded_digests != {digest}:
        errors.append("master identity does not match exact membership and assignments")
    if proposal_id and embedded_proposals and embedded_proposals != {proposal_id}:
        errors.append("proposal identity does not match the recomputed master identity")
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
        "config_sha256": content_sha256(config),
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
        "master_sha256": digest,
        "proposal_id": proposal_id,
    }
    return errors, metrics


def build_catalog_plan(
    master: list[dict[str, str]],
    config: dict,
    plan_id: str,
    source_title: str,
    source_identifier: str,
    *,
    source_count: int,
    source_membership_sha256: str,
    evaluation_report: dict,
    validation_report: dict,
    run_lock: dict | None,
    run_lock_sha256: str | None,
    release_class: str = "editor-field",
) -> dict:
    """Build a content-addressed plan bound to one evaluated release candidate."""
    if release_class not in {"synthetic-practice", "editor-field"}:
        raise ValueError("release_class must be synthetic-practice or editor-field")
    digest = master_sha256(master)
    proposal_id = f"pfp-{digest[:16]}"
    config_sha256 = content_sha256(config)
    if not evaluation_report.get("passed"):
        raise ValueError("catalog plan requires a passing evaluation")
    if evaluation_report.get("master_sha256") != digest:
        raise ValueError("evaluated master identity does not match the catalog plan")
    if evaluation_report.get("proposal_id") != proposal_id:
        raise ValueError("evaluated proposal identity does not match the catalog plan")
    if evaluation_report.get("config_sha256") != config_sha256:
        raise ValueError("evaluation config identity does not match the catalog plan")
    if release_class == "editor-field" and not evaluation_report.get("final_holdout"):
        raise ValueError("editor-field catalog plan requires a passing final holdout")
    if release_class == "editor-field":
        if not evaluation_report.get("relation_clean_holdout"):
            raise ValueError("editor-field catalog plan requires relation-clean holdout evidence")
        leakage_digest = evaluation_report.get("leakage_report_sha256")
        if not isinstance(leakage_digest, str) or len(leakage_digest) != 64:
            raise ValueError("editor-field catalog plan requires a holdout leakage-report digest")
    if validation_report.get("status") != "PASS":
        raise ValueError("catalog plan requires a passing validation report")
    if validation_report.get("master_sha256") != digest:
        raise ValueError("validated master identity does not match the catalog plan")
    if validation_report.get("proposal_id") != proposal_id:
        raise ValueError("validated proposal identity does not match the catalog plan")
    if validation_report.get("config_sha256") != config_sha256:
        raise ValueError("validation config identity does not match the catalog plan")
    if source_count < len(master):
        raise ValueError("source count cannot be smaller than the master")
    normalized_source_digest = source_membership_sha256.strip().lower()
    if len(normalized_source_digest) != 64 or any(
        character not in "0123456789abcdef" for character in normalized_source_digest
    ):
        raise ValueError("source membership SHA-256 must be 64 hexadecimal characters")
    if release_class == "editor-field":
        if not run_lock or not run_lock_sha256:
            raise ValueError("editor-field catalog plan requires a verified run lock")
        locked_artifacts = run_lock.get("artifacts", {})
        if not {"master", "effective_config", "replay_validation"} <= set(locked_artifacts):
            raise ValueError("run lock does not bind the required final artifacts")
        locked_source = run_lock.get("source", {})
        if locked_source != {
            "identifier": source_identifier,
            "expected_count": source_count,
            "membership_sha256": normalized_source_digest,
        }:
            raise ValueError("catalog plan source identity does not match the frozen run lock")
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
    plan = {
        "schema_version": 2,
        "plan_id": plan_id,
        "proposal_id": proposal_id,
        "master_sha256": digest,
        "config_sha256": config_sha256,
        "release_class": release_class,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source": {
            "title": source_title,
            "identifier": source_identifier,
            "count": source_count,
            "membership_sha256": normalized_source_digest,
        },
        "evaluation": {
            "passed": True,
            "final_holdout": bool(evaluation_report.get("final_holdout")),
            "relation_clean_holdout": bool(
                evaluation_report.get("relation_clean_holdout")
            ),
            "leakage_report_sha256": evaluation_report.get(
                "leakage_report_sha256"
            ),
            "report_sha256": content_sha256(evaluation_report),
        },
        "validation": {
            "status": "PASS",
            "report_sha256": content_sha256(validation_report),
        },
        "run_lock_sha256": run_lock_sha256,
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
            "writer receipt plan digest matches",
            "fresh read-only topology and membership verification",
        ],
    }
    plan["plan_sha256"] = content_sha256(plan, "plan_sha256")
    return plan
