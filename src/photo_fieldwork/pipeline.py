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


CLEAR_SAFETY_STATES = {"clear"}
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
    for view in config["views"]:
        mode = str(view.get("evaluation_mode", "material"))
        if mode not in {"material", "sparse-hypothesis"}:
            raise ValueError(f"view {view['id']} has unknown evaluation_mode {mode}")
        if mode == "sparse-hypothesis" and not str(view.get("evaluation_waiver_reason", "")).strip():
            raise ValueError(
                f"view {view['id']} requires evaluation_waiver_reason for sparse-hypothesis mode"
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


def evaluation_sample_sha256(rows: Iterable[dict[str, str]]) -> str:
    payload = [
        {
            "uuid": str(row["uuid"]),
            "primary_view": str(row.get("primary_view") or ""),
            "proposal_id": str(row.get("proposal_id") or ""),
            "master_sha256": str(row.get("master_sha256") or ""),
            "sample_role": str(row.get("sample_role") or "fresh"),
            "expected_judgment": str(row.get("expected_judgment") or ""),
            "expected_safety_state": str(row.get("expected_safety_state") or ""),
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
    state = str(row.get("safety_state") or row.get("safety_status") or "unknown").strip().lower()
    attributed_editor_clearance = (
        state == "clear_for_editor_field"
        and bool(str(row.get("safety_clearance_actor", "")).strip())
        and str(row.get("safety_clearance_authority", "")).strip().lower() == "human-editor"
    )
    return (
        state not in CLEAR_SAFETY_STATES and not attributed_editor_clearance
        or truthy(row.get("hidden"))
        or truthy(row.get("missing"))
    )


def propagate_related_holds(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Propagate unresolved safety through duplicate and burst components.

    Event, person, place, and date relationships are intentionally excluded:
    they are retrieval context, not evidence that safety state is shared.
    """
    prepared = [dict(row) for row in rows]
    parent = list(range(len(prepared)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    first_by_relation: dict[tuple[str, str], int] = {}
    for index, row in enumerate(prepared):
        for field in (
            "perceptual_cluster_id",
            "duplicate_group",
            "duplicate_group_id",
            "burst_group",
        ):
            value = str(row.get(field, "")).strip()
            if not value:
                continue
            namespace = "burst" if field == "burst_group" else "duplicate"
            key = (namespace, value)
            if key in first_by_relation:
                union(index, first_by_relation[key])
            else:
                first_by_relation[key] = index

    held_roots = {find(index) for index, row in enumerate(prepared) if is_hold(row)}
    for index, row in enumerate(prepared):
        if find(index) not in held_roots or is_hold(row):
            continue
        row["safety_status"] = "automatic-hold"
        row["safety_propagated"] = "true"
        reason = str(row.get("safety_reason", "")).strip()
        propagation = "related duplicate or burst member is held"
        row["safety_reason"] = "; ".join(value for value in (reason, propagation) if value)
    return prepared


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


def candidate_views(row: dict[str, str], config: dict) -> list[str]:
    configured = {view["id"] for view in config["views"]}
    requested = split_values(row.get("candidate_views"))
    unknown = sorted(set(requested) - configured)
    if unknown:
        raise ValueError(
            f"inventory row {row.get('uuid', '<unknown>')} has unknown candidate view: "
            + ", ".join(unknown)
        )
    candidates = [view for view in requested if view in configured]
    return list(dict.fromkeys(candidates)) if candidates else [config["unclassified_view"]]


def rank_row(row: dict[str, str], config: dict) -> float:
    return attention_score(row) + evidence_score(row) + stable_noise(int(config["seed"]), row["uuid"])


def assignment_capacity_report(rows: list[dict[str, str]], config: dict) -> dict:
    views_by_asset = {row["uuid"]: set(candidate_views(row, config)) for row in rows}
    quotas = {view["id"]: int(view["quota"]) for view in config["views"] if int(view["quota"]) > 0}
    overlaps = Counter(";".join(sorted(views)) for views in views_by_asset.values())
    return {
        "eligible_asset_count": len(rows),
        "target_count": int(config["target_count"]),
        "by_view": {
            view_id: {
                "quota": quota,
                "eligible_assets": sum(view_id in views for views in views_by_asset.values()),
            }
            for view_id, quota in quotas.items()
        },
        "overlap_groups": dict(sorted(overlaps.items())),
    }


def exact_view_assignment(rows: list[dict[str, str]], config: dict) -> tuple[dict[str, str], dict]:
    """Jointly satisfy view quotas and global people-diversity floors."""
    quotas = {view["id"]: int(view["quota"]) for view in config["views"] if int(view["quota"]) > 0}
    view_ids = list(quotas)
    row_map = {row["uuid"]: row for row in rows}
    asset_ids = sorted(
        row_map,
        key=lambda uuid: (-rank_row(row_map[uuid], config), uuid),
    )
    target = int(config["target_count"])
    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
    if named_floor + person_free_floor > target:
        raise ValueError("named-people and person-free diversity floors exceed target_count")

    def solve(category_counts: dict[str, int] | None = None) -> tuple[dict[str, str], dict[str, int], int]:
        source = 0
        category_node = {"named": 1, "person_free": 2} if category_counts else {}
        asset_start = 3 if category_counts else 1
        asset_node = {uuid: index + asset_start for index, uuid in enumerate(asset_ids)}
        view_start = asset_start + len(asset_ids)
        view_node = {view_id: view_start + index for index, view_id in enumerate(view_ids)}
        sink = view_start + len(view_ids)
        graph: list[list[dict]] = [[] for _ in range(sink + 1)]

        def add_edge(start: int, stop: int, capacity: int) -> dict:
            forward = {"to": stop, "rev": len(graph[stop]), "cap": capacity}
            backward = {"to": start, "rev": len(graph[start]), "cap": 0}
            graph[start].append(forward)
            graph[stop].append(backward)
            return forward

        if category_counts:
            for category in ("named", "person_free"):
                add_edge(source, category_node[category], category_counts[category])
        assignment_edges: list[tuple[str, str, dict]] = []
        for uuid in asset_ids:
            row = row_map[uuid]
            if category_counts:
                category = "named" if split_values(row.get("persons")) else "person_free"
                add_edge(category_node[category], asset_node[uuid], 1)
            else:
                add_edge(source, asset_node[uuid], 1)
            for view_id in candidate_views(row, config):
                if view_id in quotas:
                    edge = add_edge(asset_node[uuid], view_node[view_id], 1)
                    assignment_edges.append((uuid, view_id, edge))
        sink_edges = {
            view_id: add_edge(view_node[view_id], sink, quotas[view_id])
            for view_id in view_ids
        }

        flow = 0
        while flow < target:
            levels = [-1] * len(graph)
            levels[source] = 0
            queue = [source]
            for node in queue:
                for edge in graph[node]:
                    if edge["cap"] > 0 and levels[edge["to"]] < 0:
                        levels[edge["to"]] = levels[node] + 1
                        queue.append(edge["to"])
            if levels[sink] < 0:
                break
            cursors = [0] * len(graph)

            def send(node: int, available: int) -> int:
                if node == sink:
                    return available
                while cursors[node] < len(graph[node]):
                    edge = graph[node][cursors[node]]
                    if edge["cap"] > 0 and levels[edge["to"]] == levels[node] + 1:
                        pushed = send(edge["to"], min(available, edge["cap"]))
                        if pushed:
                            edge["cap"] -= pushed
                            graph[edge["to"]][edge["rev"]]["cap"] += pushed
                            return pushed
                    cursors[node] += 1
                return 0

            while flow < target:
                pushed = send(source, target - flow)
                if not pushed:
                    break
                flow += pushed

        assignments = {
            uuid: view_id for uuid, view_id, edge in assignment_edges if edge["cap"] == 0
        }
        assigned_by_view = {
            view_id: quotas[view_id] - sink_edges[view_id]["cap"] for view_id in view_ids
        }
        return assignments, assigned_by_view, flow

    assignments, assigned_counts, flow = solve()
    selected_named = sum(bool(split_values(row_map[uuid].get("persons"))) for uuid in assignments)
    selected_person_free = len(assignments) - selected_named
    assignment_mode = "ranked-unconstrained"
    if flow == target and (selected_named < named_floor or selected_person_free < person_free_floor):
        required_named = named_floor if selected_named < named_floor else target - person_free_floor
        assignments, assigned_counts, flow = solve({
            "named": required_named,
            "person_free": target - required_named,
        })
        selected_named = sum(bool(split_values(row_map[uuid].get("persons"))) for uuid in assignments)
        selected_person_free = len(assignments) - selected_named
        assignment_mode = "minimum-diversity-floor-repair"

    report = assignment_capacity_report(rows, config)
    report["assigned_by_view"] = assigned_counts
    report["diversity"] = {
        "named_people_floor": named_floor,
        "person_free_floor": person_free_floor,
        "named_people_assigned": selected_named,
        "person_free_assigned": selected_person_free,
        "assignment_mode": assignment_mode,
    }
    report["deficits"] = {
        view_id: quotas[view_id] - assigned_counts[view_id]
        for view_id in view_ids
        if assigned_counts[view_id] != quotas[view_id]
    }
    diversity_passed = selected_named >= named_floor and selected_person_free >= person_free_floor
    report["status"] = (
        "PASS" if flow == target and not report["deficits"] and diversity_passed else "INFEASIBLE"
    )
    if report["status"] != "PASS":
        raise ValueError(
            "exact view quotas are infeasible; quotas were not changed: "
            + json.dumps(report, sort_keys=True)
        )
    return assignments, report


def select(inventory: list[dict[str, str]], config: dict) -> tuple[list[dict], list[dict], dict]:
    inventory_ids = [row.get("uuid", "") for row in inventory]
    duplicate_ids = [uuid for uuid, count in Counter(inventory_ids).items() if count > 1]
    if duplicate_ids:
        raise ValueError(f"duplicate inventory UUID: {sorted(duplicate_ids)[0]}")
    prepared = propagate_related_holds(inventory)
    holds = [dict(row) for row in prepared if is_hold(row)]
    eligible = cluster_representatives([dict(row) for row in prepared if not is_hold(row)], config)
    assignments, capacity = exact_view_assignment(eligible, config)
    row_map = {row["uuid"]: row for row in eligible}

    def decorate(source: dict[str, str], primary_view: str) -> dict[str, str]:
        row = dict(source)
        row["primary_view"] = primary_view
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
        return row

    selected = [decorate(row_map[uuid], view_id) for uuid, view_id in assignments.items()]
    target = int(config["target_count"])
    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
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
        "relational_hold_count": sum(truthy(row.get("safety_propagated")) for row in holds),
        "review_required_count": sum(
            str(row.get("safety_state") or row.get("safety_status") or "").strip().lower()
            in {"needs-review", "review_required"}
            for row in holds
        ),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "person_free_count": sum(not bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "capacity": capacity,
        "master_sha256": digest,
        "proposal_id": proposal_id,
    }
    return selected, holds, summary


def make_sample(
    master: list[dict[str, str]],
    per_view: int,
    seed: int,
    excluded_ids: set[str] | None = None,
    novel_only: bool = False,
    known_regressions: list[dict[str, str]] | None = None,
) -> list[dict]:
    if per_view < 1:
        raise ValueError("per_view must be at least 1")
    excluded = {str(uuid) for uuid in (excluded_ids or set())}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in master:
        grouped[row.get("primary_view", "unknown")].append(row)
    sample: list[dict] = []
    rng = random.Random(seed)
    for view, rows in sorted(grouped.items()):
        candidates = [row for row in rows if not novel_only or row["uuid"] not in excluded]
        needed = min(per_view, len(rows))
        if novel_only and len(candidates) < needed:
            raise ValueError(
                f"view {view} has {len(candidates)} novel rows but needs {needed}; "
                "expand the candidate field or lower the sample explicitly"
            )
        ordered = sorted(candidates, key=lambda row: float(row.get("score_total") or 0))
        if len(ordered) <= per_view:
            picks = ordered
        else:
            positions = {0, len(ordered) // 2, len(ordered) - 1}
            while len(positions) < per_view:
                positions.add(rng.randrange(len(ordered)))
            picks = [ordered[index] for index in sorted(positions)[:per_view]]
        for row in picks:
            item = dict(row)
            item["sample_role"] = "fresh"
            item["view_population"] = str(len(rows))
            item["sampling_reason"] = (
                "complete small view"
                if len(rows) <= per_view
                else "score boundaries plus deterministic random positions"
            )
            item["prior_review_overlap"] = "true" if row["uuid"] in excluded else "false"
            item["judgment"] = ""
            item["evaluation_note"] = ""
            sample.append(item)
    master_edges = {(row["uuid"], row.get("primary_view", "")): row for row in master}
    sampled_edges = {(row["uuid"], row.get("primary_view", "")) for row in sample}
    for regression in known_regressions or []:
        key = (regression.get("uuid", ""), regression.get("primary_view", ""))
        if key not in master_edges:
            raise ValueError(f"regression canary is not in the exact master: {key[0]}:{key[1]}")
        if key in sampled_edges:
            continue
        expected_judgment = str(regression.get("expected_judgment", "")).strip().lower()
        if expected_judgment not in JUDGMENTS:
            raise ValueError(f"regression canary {key[0]} requires expected_judgment")
        item = dict(master_edges[key])
        item["sample_role"] = "regression-canary"
        item["expected_judgment"] = expected_judgment
        item["expected_safety_state"] = str(
            regression.get("expected_safety_state") or "clear"
        ).strip().lower()
        item["view_population"] = str(sum(row.get("primary_view", "") == key[1] for row in master))
        item["sampling_reason"] = "known regression canary"
        item["prior_review_overlap"] = "true"
        item["judgment"] = ""
        item["evaluation_note"] = ""
        sample.append(item)
        sampled_edges.add(key)
    digest = evaluation_sample_sha256(sample)
    for item in sample:
        item["evaluation_sample_sha256"] = digest
    return sample


def evaluate(feedback: list[dict[str, str]], config: dict) -> tuple[dict, bool]:
    edges = [(row.get("uuid", ""), row.get("primary_view", "")) for row in feedback]
    duplicates = [edge for edge, count in Counter(edges).items() if count > 1]
    if duplicates:
        raise ValueError(f"duplicate evaluation edge: {duplicates[0][0]}:{duplicates[0][1]}")
    proposal_ids = {row.get("proposal_id", "").strip() for row in feedback}
    master_hashes = {row.get("master_sha256", "").strip() for row in feedback}
    sample_hashes = {row.get("evaluation_sample_sha256", "").strip() for row in feedback}
    if "" in proposal_ids or len(proposal_ids) != 1:
        raise ValueError("evaluation rows must share one non-empty proposal_id")
    if "" in master_hashes or len(master_hashes) != 1:
        raise ValueError("evaluation rows must share one non-empty master_sha256")
    if "" in sample_hashes or len(sample_hashes) != 1:
        raise ValueError("evaluation rows must share one non-empty evaluation_sample_sha256")
    if sample_hashes != {evaluation_sample_sha256(feedback)}:
        raise ValueError("evaluation sample membership does not match evaluation_sample_sha256")
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
    invalid_roles = sorted({
        str(row.get("sample_role") or "fresh").strip().lower()
        for row in feedback
        if str(row.get("sample_role") or "fresh").strip().lower()
        not in {"fresh", "regression-canary", "final-holdout"}
    })
    if invalid_roles:
        raise ValueError(f"unknown evaluation sample roles: {', '.join(invalid_roles)}")
    missing_reasons = [
        row.get("uuid", "")
        for row in feedback
        if row.get("judgment", "").strip().lower() in JUDGMENTS
        and not str(row.get("visible_reason") or row.get("evaluation_note") or "").strip()
    ]
    if missing_reasons:
        raise ValueError("every evaluation judgment requires a visible reason")
    canaries = [
        row for row in feedback
        if str(row.get("sample_role") or "fresh").strip().lower() == "regression-canary"
    ]
    fresh = [
        row for row in feedback
        if str(row.get("sample_role") or "fresh").strip().lower() != "regression-canary"
    ]
    judged = [row for row in fresh if row.get("judgment", "").strip().lower() in JUDGMENTS]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / len(fresh) if fresh else 0.0
    decisive_precision = fit / (fit + reject) if fit + reject else 0.0
    fit_rate = fit / len(judged) if judged else 0.0
    uncertainty_rate = uncertain / len(judged) if judged else 0.0
    safety_regressions = sum(is_hold(row) for row in fresh)
    canary_regressions = sum(
        row.get("judgment", "").strip().lower()
        != str(row.get("expected_judgment", "")).strip().lower()
        or str(row.get("safety_state") or row.get("safety_status") or "unknown").strip().lower()
        != str(row.get("expected_safety_state") or "clear").strip().lower()
        for row in canaries
    )
    by_view = {}
    configured_views = {view["id"]: view for view in config["views"] if int(view["quota"]) > 0}
    minimum_view_precision = float(config.get("minimum_view_eval_decisive_precision", 0.65))
    minimum_view_decisive = int(config.get("minimum_view_eval_decisive_count", 2))
    minimum_coverage = float(config.get("minimum_eval_coverage", 0.8))
    maximum_uncertainty = float(config.get("maximum_eval_uncertainty", 1.0))
    for view, view_config in sorted(configured_views.items()):
        sampled = [row for row in fresh if row.get("primary_view", "unknown") == view]
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_fit = sum(row["judgment"].strip().lower() == "fit" for row in rows)
        view_uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in rows)
        view_precision = (
            sum(row["judgment"].strip().lower() == "fit" for row in decisive) / len(decisive)
            if decisive
            else None
        )
        view_coverage = len(rows) / len(sampled) if sampled else 0.0
        view_uncertainty_rate = view_uncertain / len(rows) if rows else 0.0
        population = max((int(row.get("view_population") or 0) for row in sampled), default=int(view_config["quota"]))
        required_decisive = min(minimum_view_decisive, population)
        evaluation_mode = str(view_config.get("evaluation_mode", "material"))
        waiver_reason = str(view_config.get("evaluation_waiver_reason", "")).strip()
        if evaluation_mode == "sparse-hypothesis" and not waiver_reason:
            raise ValueError(f"view {view} requires evaluation_waiver_reason")
        failures = []
        if not sampled:
            failures.append("view not sampled")
        if view_coverage < minimum_coverage:
            failures.append("coverage below minimum")
        if view_uncertainty_rate > maximum_uncertainty:
            failures.append("uncertainty above maximum")
        if evaluation_mode == "material":
            if len(decisive) < required_decisive:
                failures.append("insufficient decisive judgments")
            if view_precision is None or view_precision < float(view_config.get("minimum_eval_decisive_precision", minimum_view_precision)):
                failures.append("decisive precision below minimum")
        gate_status = "FAIL" if failures else "WAIVED" if evaluation_mode == "sparse-hypothesis" else "PASS"
        by_view[view] = {
            "label": view_config.get("label", view),
            "evaluation_mode": evaluation_mode,
            "evaluation_waiver_reason": waiver_reason or None,
            "sampled": len(sampled),
            "judged": len(rows),
            "decisive": len(decisive),
            "required_decisive": required_decisive,
            "population": population,
            "coverage": round(view_coverage, 4),
            "decisive_precision": view_precision,
            "decisive_precision_interval_95": wilson_interval(view_fit, len(decisive)),
            "fit_rate": view_fit / len(rows) if rows else None,
            "fit_rate_interval_95": wilson_interval(view_fit, len(rows)),
            "uncertainty_rate": view_uncertainty_rate if rows else None,
            "passed": not failures,
            "gate_status": gate_status,
            "failure_reasons": failures,
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
    decisive_interval = wilson_interval(fit, fit + reject)
    minimum_lower_bound = config.get("minimum_eval_decisive_precision_lower_bound")
    passed = (
        coverage >= float(config.get("minimum_eval_coverage", 0.8))
        and decisive_precision >= minimum_precision
        and uncertainty_rate <= maximum_uncertainty
        and safety_regressions == 0
        and canary_regressions == 0
        and all(metrics["passed"] for metrics in by_view.values())
        and (
            minimum_lower_bound is None
            or (decisive_interval is not None and decisive_interval[0] >= float(minimum_lower_bound))
        )
    )
    report = {
        "schema_version": 2,
        "release_class": "editor-field",
        "proposal_id": next(iter(proposal_ids)),
        "master_sha256": next(iter(master_hashes)),
        "evaluation_sample_sha256": next(iter(sample_hashes)),
        "sample_count": len(feedback),
        "fresh_sample_count": len(fresh),
        "canary_count": len(canaries),
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
        "minimum_view_decisive_precision": minimum_view_precision,
        "minimum_view_decisive_count": minimum_view_decisive,
        "safety_regressions": safety_regressions,
        "canary_regressions": canary_regressions,
        "waivers": [
            {"view_id": view_id, "reason": metrics["evaluation_waiver_reason"]}
            for view_id, metrics in by_view.items()
            if metrics["gate_status"] == "WAIVED"
        ],
        "passed": passed,
        "by_view": by_view,
    }
    return report, passed


def audit_holdout_split(
    tuning_rows: list[dict[str, str]],
    holdout_rows: list[dict[str, str]],
) -> tuple[dict, bool]:
    """Detect exact and relationship-level leakage without reporting identifiers."""
    tuning_ids = [str(row.get("uuid", "")) for row in tuning_rows]
    holdout_ids = [str(row.get("uuid", "")) for row in holdout_rows]
    missing_uuid_count = sum(not value.strip() for value in tuning_ids + holdout_ids)
    duplicate_tuning = len(tuning_ids) - len(set(tuning_ids))
    duplicate_holdout = len(holdout_ids) - len(set(holdout_ids))
    uuid_overlap = set(tuning_ids) & set(holdout_ids)
    relationship_overlap: dict[str, int] = {}
    internal_relationship_duplicates: dict[str, int] = {}
    for field in (
        "perceptual_cluster_id",
        "duplicate_group",
        "duplicate_group_id",
        "burst_group",
    ):
        tuning_values = {str(row.get(field, "")).strip() for row in tuning_rows} - {""}
        holdout_values = {str(row.get(field, "")).strip() for row in holdout_rows} - {""}
        relationship_overlap[field] = len(tuning_values & holdout_values)
        holdout_counts = Counter(
            str(row.get(field, "")).strip()
            for row in holdout_rows
            if str(row.get(field, "")).strip()
        )
        internal_relationship_duplicates[field] = sum(
            count - 1 for count in holdout_counts.values() if count > 1
        )
    relationship_count = sum(relationship_overlap.values())
    internal_relationship_count = sum(internal_relationship_duplicates.values())
    passed = not (
        missing_uuid_count
        or duplicate_tuning
        or duplicate_holdout
        or uuid_overlap
        or relationship_count
        or internal_relationship_count
    )
    return {
        "schema_version": 1,
        "status": "PASS" if passed else "FAIL",
        "tuning_count": len(tuning_rows),
        "holdout_count": len(holdout_rows),
        "missing_uuid_count": missing_uuid_count,
        "duplicate_tuning_uuid_count": duplicate_tuning,
        "duplicate_holdout_uuid_count": duplicate_holdout,
        "uuid_overlap_count": len(uuid_overlap),
        "relationship_overlap_count": relationship_count,
        "relationship_overlap_by_type": relationship_overlap,
        "internal_relationship_duplicate_count": internal_relationship_count,
        "internal_relationship_duplicates_by_type": internal_relationship_duplicates,
    }, passed


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
    expected_view_counts = {view["id"]: int(view["quota"]) for view in config["views"]}
    actual_view_counts = Counter(row.get("primary_view") for row in master)
    mismatched_view_counts = {
        view_id: {"expected": expected, "actual": actual_view_counts.get(view_id, 0)}
        for view_id, expected in expected_view_counts.items()
        if actual_view_counts.get(view_id, 0) != expected
    }
    if mismatched_view_counts:
        errors.append(f"view quotas do not match: {json.dumps(mismatched_view_counts, sort_keys=True)}")
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
        "view_counts": dict(sorted(actual_view_counts.items())),
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
    if evaluation_report is None or not evaluation_report.get("passed"):
        raise ValueError("catalog plan requires a passing bound evaluation")
    if evaluation_report.get("master_sha256") != digest:
        raise ValueError("evaluation does not match the proposed master")
    if evaluation_report.get("proposal_id") != proposal_id:
        raise ValueError("evaluation proposal_id does not match the proposed master")
    if evaluation_report.get("release_class") != "editor-field":
        raise ValueError("catalog plan requires an editor-field evaluation release class")
    if not evaluation_report.get("evaluation_sample_sha256"):
        raise ValueError("catalog plan requires evaluation sample identity")
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
        "evaluation_sample_sha256": evaluation_report["evaluation_sample_sha256"],
        "release_class": "editor-field",
        "publication_clearance": False,
        "evaluation_waivers": evaluation_report.get("waivers", []),
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
