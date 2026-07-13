from __future__ import annotations

import csv
import heapq
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


JUDGMENTS = {"fit", "reject", "uncertain"}
EDGE_STATUSES = {"eligible", "reject", "uncertain", "needs-review", "hold"}
SAFETY_STATUSES = {"clear", "needs-review", "hold"}
ASSIGNMENT_STATUSES = {"assigned", "unclassified", "sparse-hypothesis", "uncertain"}


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
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
    return config


def read_csv(
    path: Path,
    required: set[str] | None = None,
    allow_empty: bool = False,
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = set(reader.fieldnames or [])
    if not rows and not allow_empty:
        raise ValueError(f"no rows found in {path}")
    required = required if required is not None else {"uuid", "filename"}
    missing = required - columns
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


def canonical_id(value: object) -> str:
    """Normalize Photos-style identifiers before equality and safety checks."""
    identifier = str(value or "").strip()
    if not identifier:
        raise ValueError("empty asset identifier")
    return identifier.split("/", 1)[0]


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def stable_noise(seed: int, uuid: str) -> float:
    digest = hashlib.sha256(f"{seed}:{uuid}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def master_sha256(rows: Iterable[dict[str, str]]) -> str:
    """Hash the exact membership and editorial assignment written to Photos."""
    payload = [
        {
            "uuid": canonical_id(row["uuid"]),
            "assigned_view": str(row.get("assigned_view") or row.get("primary_view") or ""),
        }
        for row in rows
    ]
    payload.sort(key=lambda row: (row["assigned_view"], row["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_hold(row: dict[str, str]) -> bool:
    safety_status = str(row.get("safety_status", "clear")).strip().lower() or "clear"
    if safety_status not in SAFETY_STATUSES:
        raise ValueError(f"row {row.get('uuid', '<unknown>')} has invalid safety_status {safety_status}")
    return (
        safety_status in {"needs-review", "hold"}
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


def candidate_view_evidence(inventory: list[dict[str, str]], config: dict) -> list[dict[str, str]]:
    """Migrate legacy row-level retrieval hints into explicit image-view edges."""
    configured = {str(view["id"]) for view in config["views"]}
    unclassified = str(config["unclassified_view"])
    edges: dict[tuple[str, str], dict[str, str]] = {}
    for source in inventory:
        uuid = canonical_id(source["uuid"])
        assigned = str(source.get("assigned_view", "")).strip()
        candidates = [view for view in split_values(source.get("candidate_views")) if view in configured]
        if assigned:
            if assigned not in configured:
                raise ValueError(f"inventory row {uuid} has unknown assigned_view {assigned}")
            candidates.insert(0, assigned)
        if not candidates:
            candidates = [unclassified]
        elif unclassified not in candidates:
            candidates.append(unclassified)
        for rank, view_id in enumerate(dict.fromkeys(candidates)):
            direct = assigned == view_id or truthy(source.get("direct_provenance"))
            edge = {
                "uuid": uuid,
                "view_id": view_id,
                "retrieval_score": str(number(source.get("retrieval_score"), max(0.0, 1.0 - rank * 0.1))),
                "direct_provenance": "true" if direct else "false",
                "visible_fit_score": str(number(source.get("visible_fit_score"))),
                "evidence_terms": str(source.get("visible_context", "")),
                "confidence": str(source.get("evidence_confidence", "unknown")).strip().lower() or "unknown",
                "status": str(source.get("edge_status", "eligible")).strip().lower() or "eligible",
                "round_id": str(source.get("round_id", "")),
                "reason": str(source.get("assignment_reason", "")).strip()
                or ("explicit editorial assignment" if assigned == view_id else "retrieval hypothesis"),
            }
            if edge["status"] not in EDGE_STATUSES:
                raise ValueError(f"image-view edge {uuid}:{view_id} has invalid status {edge['status']}")
            edges[(uuid, view_id)] = edge
    return list(edges.values())


def normalize_evidence_edges(edges: list[dict[str, str]], config: dict) -> list[dict[str, str]]:
    configured = {str(view["id"]) for view in config["views"]}
    normalized: dict[tuple[str, str], dict[str, str]] = {}
    for source in edges:
        uuid = canonical_id(source.get("uuid"))
        view_id = str(source.get("view_id", "")).strip()
        status = str(source.get("status", "eligible")).strip().lower() or "eligible"
        if view_id not in configured:
            raise ValueError(f"image-view edge {uuid} has unknown view_id {view_id or '<empty>'}")
        if status not in EDGE_STATUSES:
            raise ValueError(f"image-view edge {uuid}:{view_id} has invalid status {status}")
        item = dict(source)
        item.update(
            {
                "uuid": uuid,
                "view_id": view_id,
                "retrieval_score": str(number(source.get("retrieval_score"))),
                "direct_provenance": "true" if truthy(source.get("direct_provenance")) else "false",
                "visible_fit_score": str(number(source.get("visible_fit_score"))),
                "evidence_terms": str(source.get("evidence_terms", "")),
                "confidence": str(source.get("confidence", "unknown")).strip().lower() or "unknown",
                "status": status,
                "round_id": str(source.get("round_id", "")),
                "reason": str(source.get("reason", "")),
            }
        )
        normalized[(uuid, view_id)] = item
    return list(normalized.values())


def apply_feedback_to_evidence(
    inventory: list[dict[str, str]],
    edges: list[dict[str, str]],
    feedback: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Apply cumulative review to the relevant edge and to asset-level safety."""
    rows = [dict(row, uuid=canonical_id(row["uuid"])) for row in inventory]
    edge_map = {(canonical_id(edge["uuid"]), str(edge["view_id"])): dict(edge) for edge in edges}
    safety_updates: dict[str, tuple[str, dict[str, str]]] = {}
    for review in feedback:
        uuid = canonical_id(review.get("uuid"))
        view_id = str(review.get("view_id") or review.get("primary_view") or "").strip()
        judgment = str(review.get("judgment", "")).strip().lower()
        safety = str(review.get("safety_status", "")).strip().lower()
        if judgment not in JUDGMENTS:
            raise ValueError(f"feedback row {uuid} has invalid judgment {judgment or '<empty>'}")
        if safety and safety not in SAFETY_STATUSES:
            raise ValueError(f"feedback row {uuid} has invalid safety_status {safety}")
        if view_id:
            key = (uuid, view_id)
            if key not in edge_map:
                raise ValueError(f"feedback references unknown image-view edge {uuid}:{view_id}")
            edge = edge_map[key]
            edge["status"] = {"fit": "eligible", "reject": "reject", "uncertain": "uncertain"}[judgment]
            if judgment == "uncertain":
                edge["confidence"] = "low"
            edge["round_id"] = str(review.get("round_id", edge.get("round_id", "")))
            reason = str(review.get("visible_reason") or review.get("evaluation_note") or "").strip()
            if reason:
                edge["reason"] = reason
            edge["feedback_error_category"] = str(review.get("error_category", ""))
            edge["reviewer_lens"] = str(review.get("reviewer_lens", ""))
        if safety:
            safety_updates[uuid] = (safety, review)
    for row in rows:
        update = safety_updates.get(row["uuid"])
        if update:
            safety, review = update
            current = str(row.get("safety_status", "clear")).strip().lower() or "clear"
            if current == "hold" and safety != "hold":
                raise ValueError(f"feedback cannot clear permanent HOLD asset {row['uuid']}")
            if current == "needs-review" and safety == "clear":
                reviewer = str(review.get("reviewer_lens") or review.get("evaluator") or "").strip()
                if not truthy(review.get("safety_clearance")) or not reviewer:
                    raise ValueError(
                        f"feedback cannot clear protected asset {row['uuid']} without "
                        "safety_clearance=true and an identified reviewer"
                    )
            row["safety_status"] = safety
            row["safety_reason"] = str(review.get("safety_reason") or review.get("visible_reason") or "")
            row["feedback_round"] = str(review.get("round_id", ""))
    return rows, list(edge_map.values())


def edge_benefit(row: dict[str, str], edge: dict[str, str], config: dict) -> int:
    confidence = {"high": 3, "medium": 2, "low": 1, "unknown": 0}.get(
        str(edge.get("confidence", "unknown")).lower(), 0
    )
    direct = 1 if truthy(edge.get("direct_provenance")) else 0
    visible = max(0.0, min(1.0, number(edge.get("visible_fit_score"))))
    retrieval = max(0.0, min(100.0, number(edge.get("retrieval_score"))))
    attention = attention_score(row)
    tie = int(stable_noise(int(config["seed"]), f"{row['uuid']}:{edge['view_id']}") * 999)
    return direct * 400_000 + int(visible * 120_000) + confidence * 35_000 + int(attention * 2_000) + int(retrieval * 100) + tie


def assignment_capacity_report(
    rows: list[dict[str, str]], edges: list[dict[str, str]], config: dict
) -> dict:
    allowed_ids = {row["uuid"] for row in rows if not is_hold(row)}
    positive_views = {str(view["id"]) for view in config["views"] if int(view["quota"]) > 0}
    eligible = [
        edge for edge in edges
        if edge["uuid"] in allowed_ids
        and edge["view_id"] in positive_views
        and edge.get("status", "eligible") in {"eligible", "uncertain"}
    ]
    views_by_asset: dict[str, set[str]] = defaultdict(set)
    for edge in eligible:
        views_by_asset[edge["uuid"]].add(edge["view_id"])
    overlaps = Counter(";".join(sorted(views)) for views in views_by_asset.values())
    return {
        "eligible_asset_count": len(views_by_asset),
        "target_count": int(config["target_count"]),
        "by_view": {
            str(view["id"]): {
                "quota": int(view["quota"]),
                "eligible_assets": sum(str(view["id"]) in views for views in views_by_asset.values()),
            }
            for view in config["views"]
        },
        "overlap_groups": dict(sorted(overlaps.items())),
    }


def constrained_assignment(
    rows: list[dict[str, str]], edges: list[dict[str, str]], config: dict
) -> tuple[dict[str, dict[str, str]], dict]:
    """Solve exact view quotas as a deterministic minimum-cost bipartite flow."""
    row_map = {row["uuid"]: row for row in rows if not is_hold(row)}
    view_ids = [str(view["id"]) for view in config["views"] if int(view["quota"]) > 0]
    positive_views = set(view_ids)
    eligible = [
        edge for edge in edges
        if edge["uuid"] in row_map
        and edge["view_id"] in positive_views
        and edge.get("status", "eligible") in {"eligible", "uncertain"}
    ]
    report = assignment_capacity_report(rows, edges, config)
    asset_ids = sorted({edge["uuid"] for edge in eligible})
    source = 0
    view_node = {view_id: index + 1 for index, view_id in enumerate(view_ids)}
    asset_start = 1 + len(view_ids)
    asset_node = {uuid: asset_start + index for index, uuid in enumerate(asset_ids)}
    sink = asset_start + len(asset_ids)
    graph: list[list[dict]] = [[] for _ in range(sink + 1)]

    def add_edge(start: int, stop: int, capacity: int, cost: int) -> dict:
        forward = {"to": stop, "rev": len(graph[stop]), "cap": capacity, "cost": cost}
        backward = {"to": start, "rev": len(graph[start]), "cap": 0, "cost": -cost}
        graph[start].append(forward)
        graph[stop].append(backward)
        return forward

    source_edges = {}
    quotas = {str(view["id"]): int(view["quota"]) for view in config["views"]}
    for view_id in view_ids:
        source_edges[view_id] = add_edge(source, view_node[view_id], quotas[view_id], 0)
    edge_refs: list[tuple[dict[str, str], dict]] = []
    for edge in sorted(eligible, key=lambda item: (item["view_id"], item["uuid"])):
        benefit = edge_benefit(row_map[edge["uuid"]], edge, config)
        ref = add_edge(view_node[edge["view_id"]], asset_node[edge["uuid"]], 1, max(0, 1_000_000 - benefit))
        edge_refs.append((edge, ref))
    for uuid in asset_ids:
        add_edge(asset_node[uuid], sink, 1, 0)

    target = int(config["target_count"])
    flow = 0
    potentials = [0] * len(graph)
    infinity = 10**30
    while flow < target:
        distances = [infinity] * len(graph)
        previous: list[tuple[int, int] | None] = [None] * len(graph)
        distances[source] = 0
        queue = [(0, source)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            for index, edge in enumerate(graph[node]):
                if edge["cap"] <= 0:
                    continue
                candidate = distance + edge["cost"] + potentials[node] - potentials[edge["to"]]
                if candidate < distances[edge["to"]]:
                    distances[edge["to"]] = candidate
                    previous[edge["to"]] = (node, index)
                    heapq.heappush(queue, (candidate, edge["to"]))
        if previous[sink] is None:
            break
        for node, distance in enumerate(distances):
            if distance < infinity:
                potentials[node] += distance
        node = sink
        while node != source:
            parent, index = previous[node]  # type: ignore[misc]
            edge = graph[parent][index]
            edge["cap"] -= 1
            graph[node][edge["rev"]]["cap"] += 1
            node = parent
        flow += 1

    assigned_counts = {view_id: quotas[view_id] - source_edges[view_id]["cap"] for view_id in view_ids}
    report["assigned_by_view"] = assigned_counts
    report["deficits"] = {
        view_id: quotas[view_id] - assigned_counts[view_id]
        for view_id in view_ids
        if assigned_counts[view_id] != quotas[view_id]
    }
    report["status"] = "PASS" if flow == target and not report["deficits"] else "INFEASIBLE"
    if report["status"] != "PASS":
        report["recommendation"] = "Review the reported deficits and overlap groups; add eligible evidence or explicitly revise quotas. Quotas were not changed."
        raise ValueError(f"exact view quotas are infeasible: {json.dumps(report, sort_keys=True)}")
    assignments = {edge["uuid"]: edge for edge, ref in edge_refs if ref["cap"] == 0}
    return assignments, report


def select(
    inventory: list[dict[str, str]],
    config: dict,
    evidence_edges: list[dict[str, str]] | None = None,
    feedback: list[dict[str, str]] | None = None,
) -> tuple[list[dict], list[dict], dict]:
    normalized_inventory = [dict(row, uuid=canonical_id(row["uuid"])) for row in inventory]
    edges = normalize_evidence_edges(
        evidence_edges if evidence_edges is not None else candidate_view_evidence(normalized_inventory, config), config
    )
    if feedback:
        normalized_inventory, edges = apply_feedback_to_evidence(normalized_inventory, edges, feedback)
    holds = [dict(row) for row in normalized_inventory if is_hold(row)]
    eligible = cluster_representatives([dict(row) for row in normalized_inventory if not is_hold(row)], config)
    eligible_ids = {row["uuid"] for row in eligible}
    edges = [edge for edge in edges if edge["uuid"] in eligible_ids]
    assignments, capacity = constrained_assignment(eligible, edges, config)
    row_map = {row["uuid"]: row for row in eligible}
    edges_by_asset: dict[str, list[dict[str, str]]] = defaultdict(list)
    for edge in edges:
        if edge.get("status", "eligible") in {"eligible", "uncertain"}:
            edges_by_asset[edge["uuid"]].append(edge)

    def decorate(row: dict[str, str], edge: dict[str, str]) -> dict[str, str]:
        item = dict(row)
        view_id = edge["view_id"]
        confidence = str(edge.get("confidence", "unknown")).lower()
        alternatives = sorted(candidate["view_id"] for candidate in edges_by_asset[row["uuid"]] if candidate["view_id"] != view_id)
        score = edge_benefit(row, edge, config)
        item.update(
            {
                "assigned_view": view_id,
                "primary_view": view_id,
                "assignment_status": "uncertain" if edge.get("status") == "uncertain" else "unclassified" if view_id == config["unclassified_view"] else "assigned",
                "assignment_reason": str(edge.get("reason", "")) or "eligible image-view evidence",
                "assignment_alternatives": ";".join(alternatives),
                "edge_status": str(edge.get("status", "eligible")),
                "direct_provenance": "true" if truthy(edge.get("direct_provenance")) else "false",
                "visible_fit_score": str(number(edge.get("visible_fit_score"))),
                "retrieval_score": str(number(edge.get("retrieval_score"))),
                "evidence_terms": str(edge.get("evidence_terms", "")),
                "feedback_round": str(edge.get("round_id", "")),
                "evidence_confidence": "low" if edge.get("status") == "uncertain" else confidence,
                "score_total": f"{score:.6f}",
                "selection_tier": "evidence" if confidence in {"high", "medium"} and edge.get("status") != "uncertain" else "exploratory",
                "selection_provenance": json.dumps(
                    {
                        "view_id": view_id,
                        "direct_provenance": truthy(edge.get("direct_provenance")),
                        "visible_fit_score": number(edge.get("visible_fit_score")),
                        "retrieval_score": number(edge.get("retrieval_score")),
                        "confidence": "low" if edge.get("status") == "uncertain" else confidence,
                        "edge_status": edge.get("status", "eligible"),
                        "round_id": edge.get("round_id", ""),
                        "alternatives": alternatives,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
        item["selection_reason"] = "; ".join(
            reason
            for reason in [
                f"eligible evidence edge for {view_id}",
                item["assignment_reason"],
                f"visible context: {item.get('visible_context')}" if item.get("visible_context") else "",
                f"evidence confidence: {item['evidence_confidence']}",
                "direct provenance" if truthy(edge.get("direct_provenance")) else "",
                "pre-existing named people" if split_values(item.get("persons")) else "",
                "prior favorite/edit attention" if attention_score(item) else "",
            ]
            if reason
        )
        return item

    selected = [decorate(row_map[uuid], edge) for uuid, edge in assignments.items()]
    selected_ids = {row["uuid"] for row in selected}
    target = int(config["target_count"])

    def enforce_floor(predicate, required: int, reason: str) -> None:
        nonlocal selected, selected_ids
        while sum(predicate(row) for row in selected) < required:
            choices = []
            for uuid, row in row_map.items():
                if uuid in selected_ids or not predicate(row):
                    continue
                for edge in edges_by_asset[uuid]:
                    donors = [candidate for candidate in selected if candidate["primary_view"] == edge["view_id"] and not predicate(candidate)]
                    if donors:
                        choices.append((edge_benefit(row, edge, config), uuid, edge, min(donors, key=lambda item: float(item["score_total"]))))
            if not choices:
                raise ValueError(f"candidate field cannot satisfy diversity floor: {reason}")
            _, uuid, edge, outgoing = max(choices, key=lambda choice: (choice[0], choice[1]))
            incoming = decorate(row_map[uuid], edge)
            incoming["selection_reason"] += f"; diversity floor: {reason}"
            selected.remove(outgoing)
            selected_ids.remove(outgoing["uuid"])
            selected.append(incoming)
            selected_ids.add(uuid)

    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
    enforce_floor(lambda row: bool(split_values(row.get("persons"))), named_floor, "named relationships")
    enforce_floor(lambda row: not bool(split_values(row.get("persons"))), person_free_floor, "person-free material context")
    selected.sort(key=lambda row: (row["primary_view"], -float(row["score_total"]), row["uuid"]))
    digest = master_sha256(selected)
    proposal_id = f"pfp-{digest[:16]}"
    for row in selected:
        row["master_sha256"] = digest
        row["proposal_id"] = proposal_id
    summary = {
        "inventory_count": len(inventory),
        "evidence_edge_count": len(edges),
        "eligible_after_cluster_reduction": len(eligible),
        "hold_count": len(holds),
        "needs_review_count": sum(str(row.get("safety_status", "")).lower() == "needs-review" for row in holds),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "uncertain_count": sum(row.get("assignment_status") == "uncertain" for row in selected),
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
    excluded = {canonical_id(value) for value in (excluded_ids or set())}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in master:
        grouped[row.get("primary_view", "unknown")].append(row)
    sample: list[dict] = []
    rng = random.Random(seed)
    for view, rows in sorted(grouped.items()):
        candidates = [row for row in rows if not novel_only or canonical_id(row["uuid"]) not in excluded]
        if novel_only and len(candidates) < min(per_view, len(rows)):
            raise ValueError(
                f"view {view} has {len(candidates)} novel rows but needs {min(per_view, len(rows))}; "
                "expand the proposal or lower the requested sample explicitly"
            )
        ordered = sorted(candidates, key=lambda row: float(row.get("score_total") or 0))
        if len(ordered) <= per_view:
            picks = ordered
        else:
            if per_view == 1:
                anchors = [len(ordered) // 2]
            elif per_view == 2:
                anchors = [0, len(ordered) - 1]
            elif per_view == 3:
                anchors = [0, len(ordered) // 2, len(ordered) - 1]
            else:
                anchors = [0, len(ordered) // 4, len(ordered) // 2, (3 * len(ordered)) // 4, len(ordered) - 1]
            positions = set(anchors[:per_view])
            while len(positions) < per_view:
                positions.add(rng.randrange(len(ordered)))
            picks = [ordered[index] for index in sorted(positions)[:per_view]]
        for row in picks:
            item = dict(row)
            item["view_selected_count"] = str(len(rows))
            item["sampling_reason"] = (
                "full sparse view" if len(ordered) <= per_view else "score quantiles and deterministic random stratum sample"
            )
            item["prior_review_overlap"] = "true" if canonical_id(row["uuid"]) in excluded else "false"
            item["judgment"] = ""
            item["evaluation_note"] = ""
            sample.append(item)
    existing = {(canonical_id(row["uuid"]), row.get("primary_view", "")) for row in sample}
    for regression in known_regressions or []:
        key = (canonical_id(regression["uuid"]), regression.get("primary_view", ""))
        if novel_only and key[0] in excluded:
            raise ValueError("known-regression injection cannot reuse an ID in a --novel-only sample")
        if key in existing:
            continue
        item = dict(regression)
        item["sampling_reason"] = "known regression injection"
        item["prior_review_overlap"] = "true" if key[0] in excluded else "false"
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
            if row.get("judgment", "").strip() and row.get("judgment", "").strip().lower() not in JUDGMENTS
        }
    )
    if unknown:
        raise ValueError(f"unknown evaluation judgments: {', '.join(unknown)}")
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in JUDGMENTS]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    safety_regressions = sum(
        str(row.get("safety_status", "clear")).strip().lower() in {"needs-review", "hold"}
        for row in feedback
    )
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
        view_precision = (
            sum(row["judgment"].strip().lower() == "fit" for row in decisive) / len(decisive)
            if decisive else None
        )
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
            "required_decisive": required_decisive,
            "coverage": round(view_coverage, 4),
            "precision": round(view_precision, 4) if view_precision is not None else None,
            "minimum_precision": precision_gate if mode == "material" else None,
            "uncertainty_rate": round(uncertainty_rate, 4),
            "maximum_uncertainty": maximum_uncertainty,
            "passed": not reasons,
            "failure_reasons": reasons,
        }
    passed = (
        coverage >= minimum_coverage
        and precision >= float(config.get("minimum_eval_precision", 0.75))
        and safety_regressions == 0
        and all(result["passed"] for result in by_view.values())
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
        "safety_regressions": safety_regressions,
        "failure_categories": dict(
            sorted(Counter(row.get("error_category", "unclassified") or "unclassified" for row in judged).items())
        ),
        "passed": passed,
        "by_view": by_view,
    }
    return report, passed


def validate_feedback(feedback: list[dict[str, str]]) -> dict:
    required = {"uuid", "proposal_id", "master_sha256", "judgment"}
    missing = required - set(feedback[0]) if feedback else required
    if missing:
        raise ValueError(f"feedback missing required columns: {', '.join(sorted(missing))}")
    seen: dict[tuple[str, str, str], str] = {}
    proposal_ids: set[str] = set()
    master_hashes: set[str] = set()
    for row in feedback:
        uuid = canonical_id(row["uuid"])
        view_id = str(row.get("view_id") or row.get("primary_view") or "").strip()
        round_id = str(row.get("round_id") or row.get("judged_at") or "current").strip()
        judgment = row["judgment"].strip().lower()
        if not uuid:
            raise ValueError("feedback contains an empty uuid")
        if judgment not in JUDGMENTS:
            raise ValueError(f"feedback row {uuid} has invalid judgment {judgment or '<empty>'}")
        key = (uuid, view_id, round_id)
        if key in seen and seen[key] != judgment:
            raise ValueError(f"feedback contains conflicting judgments for {uuid}:{view_id or '<no-view>'}")
        seen[key] = judgment
        proposal_ids.add(row["proposal_id"].strip())
        master_hashes.add(row["master_sha256"].strip())
    if "" in proposal_ids or len(proposal_ids) != 1:
        raise ValueError("feedback must name one non-empty proposal_id")
    if "" in master_hashes or len(master_hashes) != 1:
        raise ValueError("feedback must name one non-empty master_sha256")
    return {
        "schema_version": 1,
        "row_count": len(feedback),
        "unique_edge_count": len({(uuid, view_id) for uuid, view_id, _ in seen}),
        "unique_uuid_count": len({uuid for uuid, _, _ in seen}),
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
    updates: dict[tuple[str, str], dict[str, str]] = {}
    for row in feedback:
        key = (canonical_id(row["uuid"]), str(row.get("view_id") or row.get("primary_view") or "").strip())
        updates[key] = row
    sample_ids = {(canonical_id(row["uuid"]), str(row.get("primary_view") or "").strip()) for row in sample}
    unknown = set(updates) - sample_ids
    if unknown:
        raise ValueError(f"feedback contains {len(unknown)} UUIDs outside the evaluation sample")
    merged = []
    for row in sample:
        item = dict(row)
        key = (canonical_id(row["uuid"]), str(row.get("primary_view") or "").strip())
        update = updates.get(key)
        if update:
            item["judgment"] = update["judgment"].strip().lower()
            item["evaluation_note"] = update.get("evaluation_note", "").strip()
            item["judgment_reason"] = update.get("judgment_reason", "").strip()
            item["evaluator"] = update.get("evaluator", "").strip()
            item["judged_at"] = update.get("judged_at", "").strip()
            item["visible_reason"] = update.get("visible_reason", "").strip()
            if update.get("safety_status", "").strip():
                item["safety_status"] = update["safety_status"].strip()
            item["error_category"] = update.get("error_category", "").strip()
            item["round_id"] = update.get("round_id", "").strip()
            item["reviewer_lens"] = update.get("reviewer_lens", "").strip()
        merged.append(item)
    return merged


def validate(
    master: list[dict[str, str]],
    holds: list[dict[str, str]],
    config: dict,
    feedback: list[dict[str, str]] | None = None,
) -> tuple[list[str], dict]:
    errors: list[str] = []
    ids = [canonical_id(row["uuid"]) for row in master]
    hold_ids = {canonical_id(row["uuid"]) for row in holds}
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
    protected = [row for row in master if str(row.get("safety_status", "clear")).lower() in {"needs-review", "hold"}]
    if protected:
        errors.append(f"master contains {len(protected)} protected safety rows")
    hashes = {row.get("master_sha256", "") for row in master}
    expected_hash = master_sha256(master)
    if hashes != {expected_hash}:
        errors.append("master_sha256 is missing or does not match exact membership and assignments")
    proposal_ids = {row.get("proposal_id", "") for row in master}
    if proposal_ids != {f"pfp-{expected_hash[:16]}"}:
        errors.append("proposal_id is missing or does not match master_sha256")
    expected_counts = {str(view["id"]): int(view["quota"]) for view in config["views"]}
    actual_counts = Counter(str(row.get("primary_view", "")) for row in master)
    quota_errors = {
        view_id: {"expected": quota, "actual": actual_counts.get(view_id, 0)}
        for view_id, quota in expected_counts.items()
        if actual_counts.get(view_id, 0) != quota
    }
    if quota_errors:
        errors.append(f"master does not meet exact view quotas: {json.dumps(quota_errors, sort_keys=True)}")
    known_rejects = set()
    for row in feedback or []:
        if str(row.get("judgment", "")).strip().lower() == "reject":
            known_rejects.add((canonical_id(row["uuid"]), str(row.get("view_id") or row.get("primary_view") or "")))
    selected_edges = {(canonical_id(row["uuid"]), str(row.get("primary_view", ""))) for row in master}
    reject_overlap = known_rejects & selected_edges
    if reject_overlap:
        errors.append(f"master contains {len(reject_overlap)} known rejected image-view edges")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "view_counts": dict(sorted(actual_counts.items())),
        "quota_errors": quota_errors,
        "known_reject_overlap": len(reject_overlap),
        "master_sha256": expected_hash,
        "proposal_id": f"pfp-{expected_hash[:16]}",
    }
    return errors, metrics


def content_sha256(value: dict, digest_field: str = "plan_sha256") -> str:
    payload = dict(value)
    payload.pop(digest_field, None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    plan = {
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
        "adapter": {"name": "adapter-neutral", "contract_version": 1},
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
    plan["plan_sha256"] = content_sha256(plan)
    return plan
