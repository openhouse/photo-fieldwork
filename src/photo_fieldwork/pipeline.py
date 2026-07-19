from __future__ import annotations

import csv
import hashlib
import json
import random
import math
import re
from datetime import datetime, timezone
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Iterable

from .artifacts import object_digest


BLOCKING_SAFETY_STATES = {
    "hold",
    "auto-hold",
    "needs-human-review",
    "human-added-hold",
    "confirmed-sensitive",
    "unavailable",
    "corrupt",
}


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
    if int(config["target_count"]) < 1:
        raise ValueError("target_count must be positive")
    for name in (
        "minimum_eval_precision",
        "minimum_eval_coverage",
        "minimum_view_precision",
        "maximum_uncertain_fraction",
        "minimum_named_people_fraction",
        "minimum_person_free_fraction",
    ):
        if name in config and not 0 <= float(config[name]) <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if int(config.get("minimum_decisive_samples_per_view", 0)) < 0:
        raise ValueError("minimum_decisive_samples_per_view cannot be negative")
    if int(config.get("event_cluster_limit", 0)) < 0:
        raise ValueError("event_cluster_limit cannot be negative")
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
        str(row.get("safety_status", "clear")).strip().lower() in BLOCKING_SAFETY_STATES
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
            row.get("duplicate_group", "").strip()
            or row.get("duplicate_group_id", "").strip()
            or row.get("perceptual_cluster_id", "").strip()
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
    return candidate_view_ids(row, config)[0]


def candidate_view_ids(row: dict[str, str], config: dict) -> list[str]:
    configured = {view["id"] for view in config["views"]}
    candidates = [view for view in split_values(row.get("candidate_views")) if view in configured]
    return list(dict.fromkeys(candidates)) or [config["unclassified_view"]]


def rank_row(row: dict[str, str], config: dict) -> float:
    return attention_score(row) + evidence_score(row) + stable_noise(int(config["seed"]), row["uuid"])


def event_cluster_key(row: dict[str, str]) -> str:
    return str(row.get("event_cluster_id") or row.get("event_cluster") or "").strip()


def assign_exact_quotas(rows: list[dict[str, str]], config: dict) -> tuple[dict[str, str], dict]:
    """Assign overlapping view hypotheses once under exact quotas and event caps."""
    positive_views = [view for view in config["views"] if int(view["quota"]) > 0]
    quotas = {view["id"]: int(view["quota"]) for view in positive_views}
    target = int(config["target_count"])
    row_map = {row["uuid"]: row for row in rows}
    if len(row_map) != len(rows):
        raise ValueError("eligible candidate rows require unique UUIDs")
    candidates = {
        uuid: [view for view in candidate_view_ids(row, config) if view in quotas]
        for uuid, row in row_map.items()
    }
    candidates = {uuid: views for uuid, views in candidates.items() if views}
    eligible_by_view = {
        view_id: sum(view_id in views for views in candidates.values())
        for view_id in quotas
    }
    overlaps = Counter(";".join(sorted(views)) for views in candidates.values())

    source = 0
    view_nodes = {view_id: index + 1 for index, view_id in enumerate(quotas)}
    asset_start = 1 + len(view_nodes)
    asset_nodes = {uuid: asset_start + index for index, uuid in enumerate(sorted(candidates))}
    cluster_keys = {
        uuid: event_cluster_key(row_map[uuid]) or f"asset:{uuid}"
        for uuid in candidates
    }
    cluster_start = asset_start + len(asset_nodes)
    cluster_nodes = {
        key: cluster_start + index
        for index, key in enumerate(sorted(set(cluster_keys.values())))
    }
    sink = cluster_start + len(cluster_nodes)
    graph: list[list[dict[str, int]]] = [[] for _ in range(sink + 1)]

    def add_edge(start: int, stop: int, capacity: int) -> dict[str, int]:
        forward = {"to": stop, "rev": len(graph[stop]), "cap": capacity}
        backward = {"to": start, "rev": len(graph[start]), "cap": 0}
        graph[start].append(forward)
        graph[stop].append(backward)
        return forward

    source_edges = {
        view_id: add_edge(source, view_nodes[view_id], quota)
        for view_id, quota in quotas.items()
    }
    benefits = {}
    for uuid, views in candidates.items():
        for preference, view_id in enumerate(views):
            benefits[(uuid, view_id)] = (
                int(rank_row(row_map[uuid], config) * 1_000_000)
                + (len(views) - preference) * 1_000
                + int(stable_noise(int(config["seed"]), f"{uuid}:{view_id}") * 999)
            )
    assignment_edges: list[tuple[str, str, dict[str, int]]] = []
    for (uuid, view_id), _ in sorted(
        benefits.items(),
        key=lambda item: (item[0][1], -item[1], item[0][0]),
    ):
        assignment_edges.append((uuid, view_id, add_edge(view_nodes[view_id], asset_nodes[uuid], 1)))
    for uuid, asset_node in asset_nodes.items():
        add_edge(asset_node, cluster_nodes[cluster_keys[uuid]], 1)
    event_limit = int(config.get("event_cluster_limit", 0))
    cluster_counts = Counter(cluster_keys.values())
    for key, cluster_node in cluster_nodes.items():
        is_event = not key.startswith("asset:")
        capacity = min(cluster_counts[key], event_limit) if is_event and event_limit else cluster_counts[key]
        add_edge(cluster_node, sink, capacity)

    flow = 0

    def levels() -> list[int]:
        level = [-1] * len(graph)
        level[source] = 0
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for edge in graph[node]:
                if edge["cap"] > 0 and level[edge["to"]] < 0:
                    level[edge["to"]] = level[node] + 1
                    queue.append(edge["to"])
        return level

    while flow < target:
        level = levels()
        if level[sink] < 0:
            break
        cursors = [0] * len(graph)

        def send(node: int, amount: int) -> int:
            if node == sink:
                return amount
            while cursors[node] < len(graph[node]):
                edge = graph[node][cursors[node]]
                if edge["cap"] > 0 and level[edge["to"]] == level[node] + 1:
                    pushed = send(edge["to"], min(amount, edge["cap"]))
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

    assigned_by_view = {
        view_id: quotas[view_id] - source_edges[view_id]["cap"]
        for view_id in quotas
    }
    deficits = {
        view_id: quotas[view_id] - assigned_by_view[view_id]
        for view_id in quotas
        if assigned_by_view[view_id] != quotas[view_id]
    }
    report = {
        "status": "PASS" if flow == target and not deficits else "INFEASIBLE",
        "target_count": target,
        "eligible_asset_count": len(candidates),
        "eligible_by_view": eligible_by_view,
        "assigned_by_view": assigned_by_view,
        "deficits": deficits,
        "overlap_groups": dict(sorted(overlaps.items())),
        "event_cluster_limit": event_limit,
        "quotas_changed": False,
    }
    if report["status"] != "PASS":
        raise ValueError(f"exact view quota deficit: {json.dumps(report, sort_keys=True)}")
    assignments = {
        uuid: view_id
        for uuid, view_id, edge in assignment_edges
        if edge["cap"] == 0
    }
    return assignments, report


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

    assignments, capacity = assign_exact_quotas(eligible, config)
    selected: list[dict] = []
    selected_ids: set[str] = set()
    event_counts: Counter = Counter()
    event_limit = int(config.get("event_cluster_limit", 0))

    def add(row: dict) -> None:
        selected.append(row)
        selected_ids.add(row["uuid"])
        cluster = event_cluster_key(row)
        if cluster:
            event_counts[cluster] += 1

    def remove(row: dict) -> None:
        selected.remove(row)
        selected_ids.remove(row["uuid"])
        cluster = event_cluster_key(row)
        if cluster:
            event_counts[cluster] -= 1

    def can_add(row: dict, removing: dict | None = None) -> bool:
        cluster = event_cluster_key(row)
        if not cluster or not event_limit:
            return True
        count = event_counts[cluster]
        if removing and event_cluster_key(removing) == cluster:
            count -= 1
        return count < event_limit

    for row in eligible:
        assigned_view = assignments.get(row["uuid"])
        if assigned_view:
            row["primary_view"] = assigned_view
            row["selection_reason"] = row["selection_reason"].replace(
                row["selection_reason"].split(";", 1)[0],
                f"retrieval hypothesis {assigned_view}",
                1,
            )
            selected.append(row)
            selected_ids.add(row["uuid"])
            cluster = event_cluster_key(row)
            if cluster:
                event_counts[cluster] += 1

    target = int(config["target_count"])
    floor_specs: list[tuple] = []

    def enforce_floor(predicate, required: int, reason: str) -> None:
        current = sum(predicate(row) for row in selected)
        if current >= required:
            floor_specs.append((predicate, required, reason))
            return
        candidates = sorted(
            (row for row in eligible if row["uuid"] not in selected_ids and predicate(row)),
            key=lambda row: float(row["score_total"]),
            reverse=True,
        )
        while current < required and candidates:
            incoming = candidates.pop(0)
            supported_views = set(candidate_view_ids(incoming, config))
            donors = sorted(
                (
                    row
                    for row in selected
                    if row["primary_view"] in supported_views
                    and not predicate(row)
                    and can_add(incoming, removing=row)
                    and all(
                        sum(prior(item) for item in selected)
                        - int(prior(row))
                        + int(prior(incoming))
                        >= minimum
                        for prior, minimum, _ in floor_specs
                    )
                ),
                key=lambda row: float(row["score_total"]),
            )
            if not donors:
                continue
            outgoing = donors[0]
            remove(outgoing)
            incoming["primary_view"] = outgoing["primary_view"]
            incoming["selection_reason"] += f"; diversity floor: {reason}"
            add(incoming)
            current += 1
        floor_specs.append((predicate, required, reason))
        if current < required:
            raise ValueError(f"candidate field cannot satisfy {reason} floor of {required}")

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
        "assignment_capacity": capacity,
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


def evaluate(feedback: list[dict[str, str]], config: dict) -> tuple[dict, bool]:
    allowed = {"fit", "reject", "uncertain"}
    identifiers = [row.get("uuid", "").strip() for row in feedback]
    if any(not identifier for identifier in identifiers):
        raise ValueError("evaluation rows require non-empty UUIDs")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("evaluation contains duplicate UUIDs")
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in allowed]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / len(feedback) if feedback else 0.0
    precision = fit / (fit + reject) if fit + reject else 0.0
    uncertainty_rate = uncertain / len(judged) if judged else 0.0
    minimum_view_precision = float(config.get("minimum_view_precision", 0.0))
    minimum_decisive_samples = int(config.get("minimum_decisive_samples_per_view", 0))
    maximum_uncertain_fraction = float(config.get("maximum_uncertain_fraction", 1.0))
    by_view = {}
    view_failures = []
    observed_views = {row.get("primary_view", "unknown") for row in feedback}
    configured_views = {
        view["id"]
        for view in config.get("views", [])
        if int(view.get("quota", 0)) > 0
    }
    for view in sorted(observed_views | configured_views):
        sampled_rows = [row for row in feedback if row.get("primary_view", "unknown") == view]
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_precision = sum(row["judgment"].strip().lower() == "fit" for row in decisive) / len(decisive) if decisive else None
        view_uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in rows)
        reasons = []
        if not sampled_rows:
            reasons.append("no sampled rows")
        if len(decisive) < minimum_decisive_samples:
            reasons.append(f"decisive sample {len(decisive)} below {minimum_decisive_samples}")
        if view_precision is None or view_precision < minimum_view_precision:
            reasons.append(f"precision {view_precision} below {minimum_view_precision}")
        if reasons:
            view_failures.append({"view": view, "reasons": reasons})
        by_view[view] = {
            "sampled": len(sampled_rows),
            "judged": len(rows),
            "decisive": len(decisive),
            "fit": sum(row["judgment"].strip().lower() == "fit" for row in decisive),
            "reject": sum(row["judgment"].strip().lower() == "reject" for row in decisive),
            "uncertain": view_uncertain,
            "uncertainty_rate": round(view_uncertain / len(rows), 4) if rows else None,
            "precision": view_precision,
        }
    passed = (
        coverage >= float(config.get("minimum_eval_coverage", 0.8))
        and precision >= float(config.get("minimum_eval_precision", 0.75))
        and uncertainty_rate <= maximum_uncertain_fraction
        and not view_failures
    )
    report = {
        "sample_count": len(feedback),
        "judged_count": len(judged),
        "fit": fit,
        "reject": reject,
        "uncertain": uncertain,
        "coverage": round(coverage, 4),
        "precision": round(precision, 4),
        "uncertainty_rate": round(uncertainty_rate, 4),
        "minimum_coverage": config.get("minimum_eval_coverage", 0.8),
        "minimum_precision": config.get("minimum_eval_precision", 0.75),
        "minimum_view_precision": minimum_view_precision,
        "minimum_decisive_samples_per_view": minimum_decisive_samples,
        "maximum_uncertain_fraction": maximum_uncertain_fraction,
        "view_failures": view_failures,
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
    blocking_master = [row["uuid"] for row in master if is_hold(row)]
    if blocking_master:
        errors.append(f"master contains {len(blocking_master)} blocking safety states")
    if any(not row.get("selection_reason") for row in master):
        errors.append("one or more selected rows lack a selection reason")
    configured = {view["id"] for view in config["views"] if int(view["quota"]) > 0}
    represented = {row.get("primary_view") for row in master}
    view_counts = Counter(row.get("primary_view") for row in master)
    missing_views = configured - represented
    if missing_views:
        errors.append(f"configured views absent from master: {', '.join(sorted(missing_views))}")
    for view in config["views"]:
        expected = int(view["quota"])
        actual = view_counts[view["id"]]
        if actual != expected:
            errors.append(
                f"view quota mismatch for {view['id']}: expected {expected}, found {actual}"
            )
    event_counts = Counter(event_cluster_key(row) for row in master if event_cluster_key(row))
    event_limit = int(config.get("event_cluster_limit", 0))
    event_overages = {
        cluster: count
        for cluster, count in event_counts.items()
        if event_limit and count > event_limit
    }
    if event_overages:
        errors.append(
            "event cluster limit exceeded: "
            + ", ".join(f"{cluster}={count}" for cluster, count in sorted(event_overages.items()))
        )
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "represented_views": sorted(represented),
        "view_counts": dict(sorted(view_counts.items())),
        "event_cluster_limit": event_limit,
        "event_cluster_overages": event_overages,
    }
    return errors, metrics


def build_catalog_plan(
    master: list[dict[str, str]],
    config: dict,
    plan_id: str,
    source_title: str,
    source_identifier: str,
    source_snapshot: dict | None = None,
    release_seal_fingerprint: str | None = None,
) -> dict:
    """Build an adapter-neutral, membership-only catalog plan."""
    if not release_seal_fingerprint or not re.fullmatch(r"sha256:[a-f0-9]{64}", release_seal_fingerprint):
        raise ValueError("catalog plan requires a verified release seal fingerprint")
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
    source = {"title": source_title, "identifier": source_identifier}
    if source_snapshot:
        source.update(
            {
                "observed_count": int(source_snapshot["observed_count"]),
                "membership_sha256": source_snapshot["membership_sha256"],
                "query_definition_version": int(source_snapshot["query_definition_version"]),
            }
        )
    plan = {
        "schema_version": 1,
        "plan_id": plan_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source": source,
        "expected_master_count": len(master),
        "release_seal_fingerprint": release_seal_fingerprint,
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
    plan["plan_sha256"] = object_digest(plan)
    return plan
