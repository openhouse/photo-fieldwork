from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Iterable


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version", 1) != 1:
        raise ValueError("configuration requires schema_version 1")
    if not isinstance(config.get("views"), list) or not config["views"]:
        raise ValueError("configuration requires at least one view")
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
    for key in (
        "exploratory_fraction",
        "minimum_eval_precision",
        "minimum_eval_coverage",
        "minimum_view_precision",
        "minimum_named_people_fraction",
        "minimum_person_free_fraction",
    ):
        value = float(config.get(key, 0))
        if not 0 <= value <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
    if float(config.get("minimum_named_people_fraction", 0)) + float(
        config.get("minimum_person_free_fraction", 0)
    ) > 1:
        raise ValueError("named-people and person-free minimum fractions cannot sum above 1")
    if int(config.get("event_cluster_limit", 0)) < 0:
        raise ValueError("event_cluster_limit cannot be negative")
    if int(config.get("minimum_view_decisions", 1)) < 1:
        raise ValueError("minimum_view_decisions must be positive")
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


def membership_sha256(identifiers: Iterable[str]) -> str:
    """Hash exact source membership independently of catalog ordering."""
    normalized = [str(identifier).strip() for identifier in identifiers]
    if any(not identifier for identifier in normalized):
        raise ValueError("membership identifiers cannot be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError("membership identifiers must be unique")
    payload = "\n".join(sorted(normalized)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def master_sha256(rows: Iterable[dict[str, str]]) -> str:
    """Hash exact master membership and editorial assignment."""
    payload = [
        {
            "uuid": str(row["uuid"]).strip(),
            "primary_view": str(row.get("primary_view", "")).strip(),
        }
        for row in rows
    ]
    if any(not item["uuid"] or not item["primary_view"] for item in payload):
        raise ValueError("master identity requires non-empty UUIDs and primary views")
    if len({item["uuid"] for item in payload}) != len(payload):
        raise ValueError("master identity requires unique UUIDs")
    payload.sort(key=lambda item: (item["primary_view"], item["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def content_sha256(value: dict, digest_field: str = "plan_sha256") -> str:
    payload = dict(value)
    payload.pop(digest_field, None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_hold(row: dict[str, str]) -> bool:
    return (
        str(row.get("safety_status", "clear")).lower() in {"hold", "needs-review"}
        or truthy(row.get("historical_hold"))
        or truthy(row.get("hidden"))
        or truthy(row.get("trashed"))
        or truthy(row.get("missing"))
    )


def is_known_reject(row: dict[str, str]) -> bool:
    return truthy(row.get("known_reject")) or str(row.get("prior_judgment", "")).casefold() == "reject"


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
    """Assign exact view quotas with deterministic capacity max-flow.

    A row may support more than one view, but can be selected only once. Event
    clusters share a bounded sink so assignment cannot evade the diversity cap.
    Evidence-ranked edge order makes the feasible result stable and useful.
    """
    positive_views = [view for view in config["views"] if int(view["quota"]) > 0]
    quotas = {view["id"]: int(view["quota"]) for view in positive_views}
    target = int(config["target_count"])
    row_map = {row["uuid"]: row for row in rows}
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
    asset_nodes = {
        uuid: asset_start + index
        for index, uuid in enumerate(sorted(candidates))
    }
    cluster_keys = {
        uuid: row_map[uuid].get("event_cluster", "").strip() or f"asset:{uuid}"
        for uuid in candidates
    }
    cluster_start = asset_start + len(asset_nodes)
    cluster_nodes = {
        key: cluster_start + index
        for index, key in enumerate(sorted(set(cluster_keys.values())))
    }
    sink = cluster_start + len(cluster_nodes)
    graph: list[list[dict]] = [[] for _ in range(sink + 1)]

    def add_edge(start: int, stop: int, capacity: int) -> dict:
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
    assignment_edges: list[tuple[str, str, dict]] = []
    for (uuid, view_id), _ in sorted(
        benefits.items(),
        key=lambda item: (item[0][1], -item[1], item[0][0]),
    ):
        edge = add_edge(view_nodes[view_id], asset_nodes[uuid], 1)
        assignment_edges.append((uuid, view_id, edge))
    for uuid, asset_node in asset_nodes.items():
        add_edge(asset_node, cluster_nodes[cluster_keys[uuid]], 1)
    event_limit = int(config.get("event_cluster_limit", 0))
    cluster_counts = Counter(cluster_keys.values())
    for key, cluster_node in cluster_nodes.items():
        is_real_cluster = not key.startswith("asset:")
        capacity = min(cluster_counts[key], event_limit) if is_real_cluster and event_limit else cluster_counts[key]
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
    known_rejects = [dict(row) for row in inventory if is_known_reject(row)]
    eligible = cluster_representatives(
        [dict(row) for row in inventory if not is_hold(row) and not is_known_reject(row)],
        config,
    )

    def explain(row: dict) -> str:
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

    for row in eligible:
        row["primary_view"] = choose_primary_view(row, config)
        row["score_total"] = f"{rank_row(row, config):.6f}"
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_tier"] = "evidence" if confidence in {"high", "medium"} else "exploratory"
        row["retrieval_basis"] = row.get("retrieval_basis") or (
            f"candidate views: {row.get('candidate_views') or config['unclassified_view']}"
        )
        row["visible_observation"] = row.get("visible_observation") or row.get("visible_context", "")
        row["provenance_basis"] = row.get("provenance_basis") or "retrieval hypothesis only"
        row["claim_boundary"] = row.get("claim_boundary") or (
            "Visible context and archive metadata do not establish authorship, consent, role, or publication permission."
        )
        row["selection_reason"] = explain(row)

    assignments, capacity = assign_exact_quotas(eligible, config)

    selected: list[dict] = []
    selected_ids: set[str] = set()
    event_counts: Counter = Counter()
    event_limit = int(config.get("event_cluster_limit", 0))

    def can_add(row: dict, removing: dict | None = None) -> bool:
        cluster = row.get("event_cluster", "").strip()
        if not cluster or not event_limit:
            return True
        count = event_counts[cluster]
        if removing and removing.get("event_cluster", "").strip() == cluster:
            count -= 1
        return count < event_limit

    def add(row: dict) -> None:
        selected.append(row)
        selected_ids.add(row["uuid"])
        cluster = row.get("event_cluster", "").strip()
        if cluster:
            event_counts[cluster] += 1

    def remove(row: dict) -> None:
        selected.remove(row)
        selected_ids.remove(row["uuid"])
        cluster = row.get("event_cluster", "").strip()
        if cluster:
            event_counts[cluster] -= 1

    for row in eligible:
        assigned_view = assignments.get(row["uuid"])
        if assigned_view:
            row["primary_view"] = assigned_view
            row["selection_reason"] = explain(row)
            add(row)

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
                    row for row in selected
                    if row["primary_view"] in supported_views
                    and not predicate(row)
                    and can_add(incoming, removing=row)
                    and all(
                        sum(prior(item) for item in selected) - int(prior(row)) + int(prior(incoming)) >= minimum
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
            incoming["selection_reason"] = f"{explain(incoming)}; diversity floor: {reason}"
            add(incoming)
            current += 1
        floor_specs.append((predicate, required, reason))
        if current < required:
            raise ValueError(f"candidate field cannot satisfy {reason} floor of {required}")

    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
    exploratory_floor = math.ceil(target * float(config.get("exploratory_fraction", 0)))
    enforce_floor(lambda row: bool(split_values(row.get("persons"))), named_floor, "named relationships")
    enforce_floor(lambda row: not bool(split_values(row.get("persons"))), person_free_floor, "person-free material context")
    enforce_floor(lambda row: row.get("selection_tier") == "exploratory", exploratory_floor, "exploratory field")
    if sum(bool(split_values(row.get("persons"))) for row in selected) < named_floor:
        raise ValueError("candidate field cannot satisfy minimum_named_people_fraction")
    if sum(not bool(split_values(row.get("persons"))) for row in selected) < person_free_floor:
        raise ValueError("candidate field cannot satisfy minimum_person_free_fraction")
    if sum(row.get("selection_tier") == "exploratory" for row in selected) < exploratory_floor:
        raise ValueError("candidate field cannot satisfy exploratory_fraction")
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
        "known_reject_count": len(known_rejects),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "person_free_count": sum(not bool(split_values(row.get("persons"))) for row in selected),
        "exploratory_count": sum(row.get("selection_tier") == "exploratory" for row in selected),
        "largest_event_cluster": max(event_counts.values(), default=0),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "capacity": capacity,
        "master_sha256": digest,
        "proposal_id": proposal_id,
    }
    return selected, holds, summary


def make_sample(master: list[dict[str, str]], per_view: int, seed: int) -> list[dict]:
    if per_view < 1:
        raise ValueError("per_view must be positive")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in master:
        grouped[row.get("primary_view", "unknown")].append(row)
    sample: list[dict] = []
    for view, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: float(row.get("score_total") or 0))
        if len(ordered) <= per_view:
            picks = ordered
        else:
            if per_view == 1:
                positions = [len(ordered) // 2]
            else:
                positions = [
                    round(index * (len(ordered) - 1) / (per_view - 1))
                    for index in range(per_view)
                ]
            picks = [ordered[index] for index in positions]
        for row in picks:
            item = dict(row)
            item["judgment"] = ""
            item["evaluation_note"] = ""
            sample.append(item)
    return sample


def evaluate(feedback: list[dict[str, str]], config: dict, final_field: bool = False) -> tuple[dict, bool]:
    allowed = {"fit", "reject", "uncertain"}
    identity_present = any(
        row.get("master_sha256", "").strip() or row.get("proposal_id", "").strip()
        for row in feedback
    )
    if identity_present and any(
        not row.get("master_sha256", "").strip() or not row.get("proposal_id", "").strip()
        for row in feedback
    ):
        raise ValueError("evaluation identity must be present on every feedback row")
    master_hashes = {row.get("master_sha256", "").strip() for row in feedback if row.get("master_sha256", "").strip()}
    proposal_ids = {row.get("proposal_id", "").strip() for row in feedback if row.get("proposal_id", "").strip()}
    if len(master_hashes) > 1 or len(proposal_ids) > 1:
        raise ValueError("evaluation feedback mixes more than one proposed master")
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in allowed]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / len(feedback) if feedback else 0.0
    precision = fit / (fit + reject) if fit + reject else 0.0
    by_view = {}
    expected_views = {
        view["id"] for view in config["views"] if int(view.get("quota", 0)) > 0
    }
    minimum_view_precision = float(config.get("minimum_view_precision", 0.65))
    minimum_view_decisions = int(config.get("minimum_view_decisions", 1))
    for view in sorted(expected_views | {row.get("primary_view", "unknown") for row in feedback}):
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_precision = sum(row["judgment"].strip().lower() == "fit" for row in decisive) / len(decisive) if decisive else None
        by_view[view] = {
            "judged": len(rows),
            "decisive": len(decisive),
            "precision": view_precision,
            "passed": (
                len(decisive) >= minimum_view_decisions
                and view_precision is not None
                and view_precision >= minimum_view_precision
            ),
        }
    replacements = [row for row in feedback if truthy(row.get("replacement"))]
    judged_ids = {row.get("uuid") for row in judged}
    replacement_coverage = (
        sum(row.get("uuid") in judged_ids for row in replacements) / len(replacements)
        if replacements else 1.0
    )
    passed = (
        coverage >= float(config.get("minimum_eval_coverage", 0.8))
        and precision >= float(config.get("minimum_eval_precision", 0.75))
        and all(item["passed"] for view, item in by_view.items() if view in expected_views)
        and (not final_field or replacement_coverage == 1.0)
    )
    report = {
        "proposal_id": next(iter(proposal_ids), None),
        "master_sha256": next(iter(master_hashes), None),
        "sample_count": len(feedback),
        "judged_count": len(judged),
        "fit": fit,
        "reject": reject,
        "uncertain": uncertain,
        "coverage": round(coverage, 4),
        "precision": round(precision, 4),
        "minimum_coverage": config.get("minimum_eval_coverage", 0.8),
        "minimum_precision": config.get("minimum_eval_precision", 0.75),
        "minimum_view_precision": minimum_view_precision,
        "minimum_view_decisions": minimum_view_decisions,
        "final_field_audit": final_field,
        "replacement_count": len(replacements),
        "replacement_coverage": round(replacement_coverage, 4),
        "passed": passed,
        "by_view": by_view,
    }
    return report, passed


def validate(
    master: list[dict[str, str]],
    holds: list[dict[str, str]],
    config: dict,
    evaluation_report: dict | None = None,
    final_feedback: list[dict[str, str]] | None = None,
) -> tuple[list[str], dict]:
    errors: list[str] = []
    ids = [row["uuid"] for row in master]
    try:
        digest = master_sha256(master)
    except ValueError as error:
        digest = None
        errors.append(str(error))
    proposal_id = f"pfp-{digest[:16]}" if digest else None
    embedded_hashes = {row.get("master_sha256", "") for row in master}
    embedded_proposals = {row.get("proposal_id", "") for row in master}
    if digest and embedded_hashes != {digest}:
        errors.append("master_sha256 is missing or does not match exact membership and assignments")
    if proposal_id and embedded_proposals != {proposal_id}:
        errors.append("proposal_id is missing or does not match master_sha256")
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
    lineage_fields = ("retrieval_basis", "provenance_basis", "claim_boundary")
    if any(not row.get(field) for row in master for field in lineage_fields):
        errors.append("one or more selected rows lack evidence-lineage fields")
    if any(is_hold(row) for row in master):
        errors.append("master contains hidden, trashed, missing, or historical-HOLD rows")
    if any(is_known_reject(row) for row in master):
        errors.append("master contains a known visual reject")
    if any("is_photo" in row and not truthy(row.get("is_photo")) for row in master):
        errors.append("master contains a non-still asset")
    if any("pixel_available" in row and not truthy(row.get("pixel_available")) for row in master):
        errors.append("master contains an asset without locally available pixels")
    configured = {view["id"] for view in config["views"] if int(view["quota"]) > 0}
    represented = {row.get("primary_view") for row in master}
    missing_views = configured - represented
    if missing_views:
        errors.append(f"configured views absent from master: {', '.join(sorted(missing_views))}")
    actual_counts = Counter(row.get("primary_view") for row in master)
    for view in config["views"]:
        if actual_counts[view["id"]] != int(view["quota"]):
            errors.append(
                f"view {view['id']} expected quota {view['quota']}, found {actual_counts[view['id']]}"
            )
    event_limit = int(config.get("event_cluster_limit", 0))
    event_counts = Counter(row.get("event_cluster") for row in master if row.get("event_cluster"))
    if event_limit and any(count > event_limit for count in event_counts.values()):
        errors.append("master exceeds event_cluster_limit")
    floor_checks = {
        "named_people": (
            sum(bool(split_values(row.get("persons"))) for row in master),
            math.ceil(len(master) * float(config.get("minimum_named_people_fraction", 0))),
        ),
        "person_free": (
            sum(not bool(split_values(row.get("persons"))) for row in master),
            math.ceil(len(master) * float(config.get("minimum_person_free_fraction", 0))),
        ),
        "exploratory": (
            sum(row.get("selection_tier") == "exploratory" for row in master),
            math.ceil(len(master) * float(config.get("exploratory_fraction", 0))),
        ),
    }
    for label, (actual, minimum) in floor_checks.items():
        if actual < minimum:
            errors.append(f"master misses {label} floor: {actual} < {minimum}")
    if config.get("require_final_field_audit"):
        if not evaluation_report:
            errors.append("final-field evaluation report is required")
        elif not evaluation_report.get("passed") or not evaluation_report.get("final_field_audit"):
            errors.append("final-field evaluation did not pass")
        if evaluation_report and digest and evaluation_report.get("master_sha256") != digest:
            errors.append("evaluation master identity does not match the frozen field")
        if evaluation_report and proposal_id and evaluation_report.get("proposal_id") != proposal_id:
            errors.append("evaluation proposal identity does not match the frozen field")
        replacements = {row["uuid"] for row in master if truthy(row.get("replacement"))}
        if replacements:
            judged = {
                row["uuid"] for row in final_feedback or []
                if row.get("judgment", "").casefold() in {"fit", "reject", "uncertain"}
            }
            missing_replacements = replacements - judged
            if missing_replacements:
                errors.append(f"final audit omitted {len(missing_replacements)} replacement rows")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "represented_views": sorted(represented),
        "view_counts": dict(sorted(actual_counts.items())),
        "largest_event_cluster": max(event_counts.values(), default=0),
        "floor_counts": {label: actual for label, (actual, _) in floor_checks.items()},
        "final_field_audit": bool(evaluation_report and evaluation_report.get("final_field_audit")),
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
    evaluation_report: dict,
    validation_report: dict,
    source_count: int,
    source_membership_sha256: str,
) -> dict:
    """Build a release-bound, adapter-neutral membership plan."""
    digest = master_sha256(master)
    proposal_id = f"pfp-{digest[:16]}"
    if not evaluation_report.get("passed") or not evaluation_report.get("final_field_audit"):
        raise ValueError("catalog plan requires a passing final-field evaluation")
    if evaluation_report.get("master_sha256") != digest:
        raise ValueError("evaluated master identity does not match the catalog plan")
    if evaluation_report.get("proposal_id") != proposal_id:
        raise ValueError("evaluated proposal identity does not match the catalog plan")
    if validation_report.get("status") != "PASS":
        raise ValueError("catalog plan requires a passing validation report")
    if validation_report.get("master_sha256") != digest:
        raise ValueError("validated master identity does not match the catalog plan")
    if validation_report.get("proposal_id") != proposal_id:
        raise ValueError("validated proposal identity does not match the catalog plan")
    if source_count < len(master):
        raise ValueError("source count cannot be smaller than the proposed master")
    if len(source_membership_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in source_membership_sha256.casefold()
    ):
        raise ValueError("source membership SHA-256 must be a 64-character hexadecimal digest")
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source": {
            "title": source_title,
            "identifier": source_identifier,
            "count": source_count,
            "membership_sha256": source_membership_sha256.casefold(),
        },
        "evaluation": {
            "passed": True,
            "final_field_audit": True,
            "proposal_id": proposal_id,
            "master_sha256": digest,
            "report_sha256": content_sha256(evaluation_report, digest_field="report_sha256"),
        },
        "validation": {
            "status": "PASS",
            "proposal_id": proposal_id,
            "master_sha256": digest,
            "report_sha256": content_sha256(validation_report, digest_field="report_sha256"),
        },
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
