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

from .integrity import assignment_sha256, attach_plan_digest, base_identifier, membership_sha256


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if int(config["target_count"]) < 1:
        raise ValueError("target_count must be positive")
    view_ids = [view["id"] for view in config["views"]]
    if len(view_ids) != len(set(view_ids)):
        raise ValueError("view IDs must be unique")
    if config["unclassified_view"] not in view_ids:
        raise ValueError("unclassified_view must name a configured view")
    if sum(int(view["quota"]) for view in config["views"]) != int(config["target_count"]):
        raise ValueError("view quotas must sum to target_count")
    if any(int(view["quota"]) < 0 for view in config["views"]):
        raise ValueError("view quotas cannot be negative")
    fraction_keys = (
        "exploratory_fraction",
        "minimum_eval_precision",
        "minimum_eval_coverage",
        "minimum_view_precision",
        "minimum_named_people_fraction",
        "minimum_person_free_fraction",
        "minimum_novel_fraction",
        "minimum_fresh_inspection_fraction",
    )
    for key in fraction_keys:
        if key in config and not 0 <= float(config[key]) <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
    if int(config.get("minimum_decisive_per_view", 1)) < 1:
        raise ValueError("minimum_decisive_per_view must be positive")
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
    digest = hashlib.sha256(f"{seed}:{base_identifier(uuid)}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def is_hold(row: dict[str, str], config: dict | None = None) -> bool:
    hold_states = {"hold", "machine-suspected", "human-confirmed-hold"}
    safety_status = str(row.get("safety_status", "")).strip().lower()
    if config and config.get("require_explicit_safety_status") and safety_status != "clear":
        return True
    return (
        safety_status in hold_states
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


def supported_views(row: dict[str, str], config: dict) -> list[str]:
    configured = {view["id"] for view in config["views"]}
    candidates = [view for view in split_values(row.get("candidate_views")) if view in configured]
    unclassified = config["unclassified_view"]
    if not candidates:
        return [unclassified]
    if config.get("allow_unclassified_fallback", True) and unclassified not in candidates:
        candidates.append(unclassified)
    return candidates


def rank_row(row: dict[str, str], config: dict) -> float:
    return attention_score(row) + evidence_score(row) + stable_noise(int(config["seed"]), row["uuid"])


class FlowEdge:
    def __init__(self, destination: int, reverse: int, capacity: int) -> None:
        self.destination = destination
        self.reverse = reverse
        self.capacity = capacity


class CapacityFlow:
    def __init__(self, size: int) -> None:
        self.graph: list[list[FlowEdge]] = [[] for _ in range(size)]

    def add_edge(self, source: int, destination: int, capacity: int) -> FlowEdge:
        forward = FlowEdge(destination, len(self.graph[destination]), capacity)
        reverse = FlowEdge(source, len(self.graph[source]), 0)
        self.graph[source].append(forward)
        self.graph[destination].append(reverse)
        return forward

    def solve(self, source: int, sink: int) -> int:
        total = 0
        while True:
            levels = [-1] * len(self.graph)
            levels[source] = 0
            queue = [source]
            for node in queue:
                for edge in self.graph[node]:
                    if edge.capacity and levels[edge.destination] < 0:
                        levels[edge.destination] = levels[node] + 1
                        queue.append(edge.destination)
            if levels[sink] < 0:
                return total
            offsets = [0] * len(self.graph)

            def send(node: int, amount: int) -> int:
                if node == sink:
                    return amount
                while offsets[node] < len(self.graph[node]):
                    edge = self.graph[node][offsets[node]]
                    if edge.capacity and levels[node] + 1 == levels[edge.destination]:
                        pushed = send(edge.destination, min(amount, edge.capacity))
                        if pushed:
                            edge.capacity -= pushed
                            self.graph[edge.destination][edge.reverse].capacity += pushed
                            return pushed
                    offsets[node] += 1
                return 0

            while pushed := send(source, 1 << 30):
                total += pushed


def assign_views(rows: list[dict[str, str]], config: dict) -> tuple[list[dict], dict]:
    quotas = {view["id"]: int(view["quota"]) for view in config["views"]}
    target = int(config["target_count"])
    ordered = sorted(
        rows,
        key=lambda row: (
            len(supported_views(row, config)),
            -float(row["score_total"]),
            base_identifier(row["uuid"]),
        ),
    )
    source = 0
    first_candidate = 1
    first_view = first_candidate + len(ordered)
    view_ids = list(quotas)
    view_nodes = {view_id: first_view + index for index, view_id in enumerate(view_ids)}
    sink = first_view + len(view_ids)
    flow = CapacityFlow(sink + 1)
    assignment_edges: dict[tuple[int, str], FlowEdge] = {}
    for index, row in enumerate(ordered):
        candidate_node = first_candidate + index
        flow.add_edge(source, candidate_node, 1)
        for view_id in supported_views(row, config):
            assignment_edges[(index, view_id)] = flow.add_edge(candidate_node, view_nodes[view_id], 1)
    quota_edges = {
        view_id: flow.add_edge(view_nodes[view_id], sink, quota)
        for view_id, quota in quotas.items()
    }
    achieved = flow.solve(source, sink)
    if achieved != target:
        deficits = {view_id: edge.capacity for view_id, edge in quota_edges.items() if edge.capacity}
        reach = Counter(view for row in ordered for view in supported_views(row, config))
        detail = {
            "matched": achieved,
            "target": target,
            "deficits": deficits,
            "candidate_reach": dict(sorted(reach.items())),
        }
        raise ValueError(f"quota graph infeasible: {json.dumps(detail, sort_keys=True)}")

    selected = []
    for index, row in enumerate(ordered):
        assigned = next(
            (
                view_id for view_id in view_ids
                if (edge := assignment_edges.get((index, view_id))) is not None and edge.capacity == 0
            ),
            None,
        )
        if assigned is not None:
            item = dict(row)
            item["primary_view"] = assigned
            selected.append(item)
    diagnostics = {
        "allocation": "deterministic capacity flow",
        "target": target,
        "candidate_count": len(rows),
        "candidate_reach": dict(sorted(Counter(view for row in rows for view in supported_views(row, config)).items())),
    }
    return selected, diagnostics


def select(inventory: list[dict[str, str]], config: dict) -> tuple[list[dict], list[dict], dict]:
    holds = [dict(row) for row in inventory if is_hold(row, config)]
    evaluation_exclusions = [dict(row) for row in inventory if truthy(row.get("evaluation_exclusion"))]
    eligible = cluster_representatives(
        [dict(row) for row in inventory if not is_hold(row, config) and not truthy(row.get("evaluation_exclusion"))],
        config,
    )
    for row in eligible:
        row["score_total"] = f"{rank_row(row, config):.6f}"
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_tier"] = "evidence" if confidence in {"high", "medium"} else "exploratory"

    selected, assignment = assign_views(eligible, config)
    for row in selected:
        confidence = str(row.get("evidence_confidence", "unknown")).lower()
        row["selection_reason"] = "; ".join(
            reason
            for reason in [
                f"capacity-flow retrieval hypothesis {row['primary_view']}",
                f"human-visible context: {row.get('human_visible_context')}" if row.get("human_visible_context") else "",
                f"machine observation: {row.get('visible_context')}" if row.get("visible_context") else "",
                f"evidence confidence: {confidence}",
                "pre-existing named people" if split_values(row.get("persons")) else "",
                "prior favorite/edit attention" if attention_score(row) else "",
            ]
            if reason
        )
        row.setdefault("publication_status", "not-approved")

    target = int(config["target_count"])
    selected_ids = {row["uuid"] for row in selected}

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
            supported = supported_views(incoming, config)
            donors = sorted(
                (row for row in selected if not predicate(row) and row["primary_view"] in supported),
                key=lambda row: float(row["score_total"]),
            )
            if not donors:
                break
            outgoing = donors[0]
            selected.remove(outgoing)
            selected_ids.remove(outgoing["uuid"])
            incoming = dict(incoming)
            incoming["primary_view"] = outgoing["primary_view"]
            incoming["selection_reason"] = (
                f"capacity-flow retrieval hypothesis {incoming['primary_view']}; diversity floor: {reason}"
            )
            incoming.setdefault("publication_status", "not-approved")
            selected.append(incoming)
            selected_ids.add(incoming["uuid"])
            current += 1

    named_floor = math.ceil(target * float(config.get("minimum_named_people_fraction", 0)))
    person_free_floor = math.ceil(target * float(config.get("minimum_person_free_fraction", 0)))
    novelty_floor = math.ceil(target * float(config.get("minimum_novel_fraction", 0)))
    fresh_floor = math.ceil(target * float(config.get("minimum_fresh_inspection_fraction", 0)))
    enforce_floor(lambda row: bool(split_values(row.get("persons"))), named_floor, "named relationships")
    enforce_floor(lambda row: not bool(split_values(row.get("persons"))), person_free_floor, "person-free material context")
    enforce_floor(lambda row: not truthy(row.get("previously_selected")), novelty_floor, "novelty")
    enforce_floor(lambda row: truthy(row.get("freshly_inspected")), fresh_floor, "fresh inspection")
    if sum(bool(split_values(row.get("persons"))) for row in selected) < named_floor:
        raise ValueError("candidate field cannot satisfy minimum_named_people_fraction")
    if sum(not bool(split_values(row.get("persons"))) for row in selected) < person_free_floor:
        raise ValueError("candidate field cannot satisfy minimum_person_free_fraction")
    if sum(not truthy(row.get("previously_selected")) for row in selected) < novelty_floor:
        raise ValueError("candidate field cannot satisfy minimum_novel_fraction")
    if sum(truthy(row.get("freshly_inspected")) for row in selected) < fresh_floor:
        raise ValueError("candidate field cannot satisfy minimum_fresh_inspection_fraction")
    selected.sort(
        key=lambda row: (
            row["primary_view"],
            -float(row["score_total"]),
            base_identifier(row["uuid"]),
        )
    )
    summary = {
        **assignment,
        "inventory_count": len(inventory),
        "eligible_after_cluster_reduction": len(eligible),
        "hold_count": len(holds),
        "evaluation_exclusion_count": len(evaluation_exclusions),
        "selected_count": len(selected),
        "view_counts": dict(sorted(Counter(row["primary_view"] for row in selected).items())),
        "named_people_count": sum(bool(split_values(row.get("persons"))) for row in selected),
        "novel_count": sum(not truthy(row.get("previously_selected")) for row in selected),
        "freshly_inspected_count": sum(truthy(row.get("freshly_inspected")) for row in selected),
        "uncertain_count": sum(row.get("evidence_confidence", "unknown") in {"low", "unknown", ""} for row in selected),
        "master_membership_sha256": membership_sha256(row["uuid"] for row in selected),
        "publication_approval_default": "not-approved",
    }
    return selected, holds, summary


def make_sample(master: list[dict[str, str]], per_view: int, seed: int) -> list[dict]:
    if per_view < 1:
        raise ValueError("per_view must be positive")
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
            item["visible_reason"] = ""
            item["safety_status"] = item.get("safety_status", "clear")
            item["public_suitability"] = "unreviewed"
            item["provenance_status"] = "unreviewed"
            item["error_category"] = ""
            item["round_id"] = ""
            item["reviewer_lens"] = ""
            sample.append(item)
    sample_digest = evaluation_sample_sha256(sample)
    for item in sample:
        item["evaluation_sample_sha256"] = sample_digest
        item["evaluation_sample_count"] = str(len(sample))
    return sample


def evaluation_sample_sha256(rows: Iterable[dict[str, str]]) -> str:
    """Bind evaluation membership to the view in which each asset is judged."""
    identities = sorted({
        (base_identifier(row.get("uuid", "")), str(row.get("primary_view", "")).strip())
        for row in rows
    })
    digest = hashlib.sha256()
    for identifier, view in identities:
        digest.update(json.dumps([identifier, view], separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    if total == 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def evaluation_identity_errors(feedback: list[dict[str, str]], config: dict | None = None) -> tuple[list[str], int]:
    config = config or {}
    errors: list[str] = []
    identifiers = [base_identifier(row.get("uuid", "")) for row in feedback]
    if any(not identifier for identifier in identifiers):
        errors.append("evaluation feedback contains a blank UUID")
    if len(identifiers) != len(set(identifiers)):
        errors.append("evaluation feedback contains duplicate canonical UUIDs")

    declared_digests = {
        str(row.get("evaluation_sample_sha256") or "").strip()
        for row in feedback
        if str(row.get("evaluation_sample_sha256") or "").strip()
    }
    declared_counts = {
        str(row.get("evaluation_sample_count") or "").strip()
        for row in feedback
        if str(row.get("evaluation_sample_count") or "").strip()
    }
    binding_present = bool(declared_digests or declared_counts)
    binding_required = bool(config.get("require_evaluation_binding"))
    if binding_required and not binding_present:
        errors.append("evaluation feedback is missing frozen sample identity")
    if binding_present:
        if any(not row.get("evaluation_sample_sha256") or not row.get("evaluation_sample_count") for row in feedback):
            errors.append("evaluation feedback has incomplete sample identity fields")
        if len(declared_digests) != 1:
            errors.append("evaluation feedback contains inconsistent sample digests")
        if len(declared_counts) != 1:
            errors.append("evaluation feedback contains inconsistent sample counts")

    expected_count = len(feedback)
    if len(declared_counts) == 1:
        try:
            expected_count = int(next(iter(declared_counts)))
        except ValueError:
            errors.append("evaluation sample count is not an integer")
        else:
            if expected_count != len(feedback):
                errors.append(
                    f"evaluation feedback row count {len(feedback)} does not match frozen sample count {expected_count}"
                )
    if len(declared_digests) == 1:
        actual_digest = evaluation_sample_sha256(feedback)
        declared_digest = next(iter(declared_digests))
        if actual_digest != declared_digest:
            errors.append("evaluation feedback membership does not match frozen sample digest")
    return errors, expected_count


def evaluate(feedback: list[dict[str, str]], config: dict) -> tuple[dict, bool]:
    integrity_errors, expected_sample_count = evaluation_identity_errors(feedback, config)
    allowed = {"fit", "reject", "uncertain"}
    judged = [row for row in feedback if row.get("judgment", "").strip().lower() in allowed]
    fit = sum(row["judgment"].strip().lower() == "fit" for row in judged)
    reject = sum(row["judgment"].strip().lower() == "reject" for row in judged)
    uncertain = sum(row["judgment"].strip().lower() == "uncertain" for row in judged)
    coverage = len(judged) / expected_sample_count if expected_sample_count else 0.0
    precision = fit / (fit + reject) if fit + reject else 0.0
    decisive_count = fit + reject
    interval = wilson_interval(fit, decisive_count)
    minimum_decisive = int(config.get("minimum_decisive_per_view", 3))
    minimum_view_precision = float(config.get("minimum_view_precision", 0.65))
    configured_views = {
        str(view["id"])
        for view in config.get("views", [])
        if int(view.get("quota", 0)) > 0
    }
    observed_views = {row.get("primary_view", "unknown") for row in feedback}
    by_view = {}
    for view in sorted(configured_views | observed_views):
        rows = [row for row in judged if row.get("primary_view", "unknown") == view]
        decisive = [row for row in rows if row["judgment"].strip().lower() in {"fit", "reject"}]
        view_fit = sum(row["judgment"].strip().lower() == "fit" for row in decisive)
        view_interval = wilson_interval(view_fit, len(decisive))
        view_precision = view_fit / len(decisive) if decisive else None
        by_view[view] = {
            "judged": len(rows),
            "decisive": len(decisive),
            "fit": view_fit,
            "reject": len(decisive) - view_fit,
            "uncertain": sum(row["judgment"].strip().lower() == "uncertain" for row in rows),
            "precision": round(view_precision, 4) if view_precision is not None else None,
            "precision_wilson_95": [round(value, 4) for value in view_interval] if view_interval else None,
            "small_sample_warning": len(decisive) < minimum_decisive,
        }
    material_view_failures = [
        view for view, item in by_view.items()
        if item["decisive"] >= minimum_decisive
        and item["precision"] is not None
        and item["precision"] < minimum_view_precision
    ]
    insufficient_views = [
        view for view in sorted(configured_views)
        if by_view[view]["decisive"] < minimum_decisive
    ]
    missing_views = [view for view in sorted(configured_views) if not any(
        row.get("primary_view", "unknown") == view for row in feedback
    )]
    passed = (
        not integrity_errors
        and coverage >= float(config.get("minimum_eval_coverage", 0.8))
        and precision >= float(config.get("minimum_eval_precision", 0.75))
        and not material_view_failures
        and not missing_views
        and (
            not config.get("require_per_view_sufficiency")
            or not insufficient_views
        )
    )
    report = {
        "sample_count": expected_sample_count,
        "submitted_count": len(feedback),
        "judged_count": len(judged),
        "fit": fit,
        "reject": reject,
        "uncertain": uncertain,
        "coverage": round(coverage, 4),
        "precision": round(precision, 4),
        "decisive_count": decisive_count,
        "precision_wilson_95": [round(value, 4) for value in interval] if interval else None,
        "minimum_coverage": config.get("minimum_eval_coverage", 0.8),
        "minimum_precision": config.get("minimum_eval_precision", 0.75),
        "minimum_view_precision": minimum_view_precision,
        "minimum_decisive_per_view": minimum_decisive,
        "material_view_failures": material_view_failures,
        "insufficient_views": insufficient_views,
        "missing_views": missing_views,
        "integrity_errors": integrity_errors,
        "error_categories": dict(sorted(Counter(row.get("error_category", "unlabeled") or "unlabeled" for row in judged).items())),
        "safety_review_counts": dict(sorted(Counter(row.get("safety_status", "unreviewed") or "unreviewed" for row in judged).items())),
        "public_suitability_counts": dict(sorted(Counter(row.get("public_suitability", "unreviewed") or "unreviewed" for row in judged).items())),
        "passed": passed,
        "by_view": by_view,
    }
    return report, passed


def validate(master: list[dict[str, str]], holds: list[dict[str, str]], config: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    ids = [row["uuid"] for row in master]
    canonical_ids = [base_identifier(value) for value in ids]
    hold_ids = {base_identifier(row["uuid"]) for row in holds}
    if len(master) != int(config["target_count"]):
        errors.append(f"expected {config['target_count']} selected rows, found {len(master)}")
    if len(canonical_ids) != len(set(canonical_ids)):
        errors.append("master contains duplicate canonical UUIDs")
    overlap = set(canonical_ids) & hold_ids
    if overlap:
        errors.append(f"master overlaps safety holds by {len(overlap)} rows")
    if any(not row.get("selection_reason") for row in master):
        errors.append("one or more selected rows lack a selection reason")
    configured = {view["id"] for view in config["views"] if int(view["quota"]) > 0}
    represented = {row.get("primary_view") for row in master}
    missing_views = configured - represented
    if missing_views:
        errors.append(f"configured views absent from master: {', '.join(sorted(missing_views))}")
    expected_counts = {view["id"]: int(view["quota"]) for view in config["views"]}
    actual_counts = Counter(row.get("primary_view") for row in master)
    quota_mismatches = {
        view_id: {"expected": quota, "actual": actual_counts.get(view_id, 0)}
        for view_id, quota in expected_counts.items()
        if actual_counts.get(view_id, 0) != quota
    }
    if quota_mismatches:
        errors.append(f"view quota mismatch: {json.dumps(quota_mismatches, sort_keys=True)}")
    if any(row.get("publication_status", "not-approved") not in {"not-approved", "unreviewed"} for row in master):
        errors.append("proposed master contains a publication-approved state")
    if config.get("require_explicit_safety_status") and any(
        str(row.get("safety_status", "")).strip().lower() != "clear" for row in master
    ):
        errors.append("proposed master contains an uncleared safety state")
    metrics = {
        "status": "PASS" if not errors else "FAIL",
        "master_count": len(master),
        "unique_count": len(set(canonical_ids)),
        "hold_count": len(holds),
        "hold_overlap": len(overlap),
        "represented_views": sorted(represented),
        "view_counts": dict(sorted(actual_counts.items())),
        "master_membership_sha256": membership_sha256(ids),
        "publication_approval_default": "not-approved",
    }
    return errors, metrics


def build_catalog_plan(
    master: list[dict[str, str]],
    config: dict,
    plan_id: str,
    source_title: str,
    source_identifier: str,
    source_members: Iterable[str],
) -> dict:
    """Build an adapter-neutral, membership-only catalog plan."""
    view_labels = {view["id"]: view["label"] for view in config["views"]}
    albums = [
        {
            "key": "master",
            "title": f"00 MASTER - {len(master):,}",
            "asset_ids": [row["uuid"] for row in master],
            "membership_sha256": membership_sha256(row["uuid"] for row in master),
        }
    ]
    for view_id in sorted({row["primary_view"] for row in master}):
        asset_ids = [row["uuid"] for row in master if row["primary_view"] == view_id]
        albums.append(
            {
                "key": f"view-{view_id}",
                "title": f"{view_id} {view_labels.get(view_id, 'Unlabeled View')} - {len(asset_ids):,}",
                "asset_ids": asset_ids,
                "membership_sha256": membership_sha256(asset_ids),
            }
        )
    source_ids = list(source_members)
    if not source_ids:
        raise ValueError("catalog plan requires a non-empty frozen source membership")
    source_set = {base_identifier(value) for value in source_ids}
    master_set = {base_identifier(row["uuid"]) for row in master}
    outside_source = master_set - source_set
    if outside_source:
        raise ValueError(f"proposed master contains {len(outside_source)} IDs outside frozen source")
    plan = {
        "schema_version": 2,
        "plan_id": plan_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safety_mode": "create-folders-albums-and-add-membership-only",
        "source": {
            "title": source_title,
            "identifier": source_identifier,
            "count": len(source_set),
            "membership_sha256": membership_sha256(source_ids),
        },
        "expected_master_count": len(master),
        "master_membership_sha256": membership_sha256(row["uuid"] for row in master),
        "master_assignment_sha256": assignment_sha256(master),
        "write_test_count": min(10, len(master)),
        "publication_approval_default": "not-approved",
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
    return attach_plan_digest(plan)
