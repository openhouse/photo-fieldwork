from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Callable


@dataclass
class Edge:
    to: int
    reverse: int
    capacity: int


class Dinic:
    """Small deterministic max-flow implementation for view assignment."""

    def __init__(self, node_count: int) -> None:
        self.graph: list[list[Edge]] = [[] for _ in range(node_count)]

    def add_edge(self, source: int, target: int, capacity: int) -> int:
        index = len(self.graph[source])
        self.graph[source].append(Edge(target, len(self.graph[target]), capacity))
        self.graph[target].append(Edge(source, index, 0))
        return index

    def max_flow(self, source: int, sink: int) -> int:
        total = 0
        while True:
            level = [-1] * len(self.graph)
            level[source] = 0
            queue = deque([source])
            while queue:
                node = queue.popleft()
                for edge in self.graph[node]:
                    if edge.capacity and level[edge.to] < 0:
                        level[edge.to] = level[node] + 1
                        queue.append(edge.to)
            if level[sink] < 0:
                return total

            cursor = [0] * len(self.graph)

            def send(node: int, available: int) -> int:
                if node == sink:
                    return available
                while cursor[node] < len(self.graph[node]):
                    edge = self.graph[node][cursor[node]]
                    if edge.capacity and level[edge.to] == level[node] + 1:
                        pushed = send(edge.to, min(available, edge.capacity))
                        if pushed:
                            edge.capacity -= pushed
                            self.graph[edge.to][edge.reverse].capacity += pushed
                            return pushed
                    cursor[node] += 1
                return 0

            while pushed := send(source, 10**9):
                total += pushed


def _candidate_views(row: dict[str, str], configured: set[str], unclassified: str) -> list[str]:
    excluded = {value.strip() for value in row.get("excluded_views", "").split(";") if value.strip()}
    candidates = [
        value.strip()
        for value in row.get("candidate_views", "").split(";")
        if value.strip() in configured and value.strip() not in excluded
    ]
    candidates = list(dict.fromkeys(candidates))
    if candidates:
        return candidates
    return [] if unclassified in excluded else [unclassified]


def _attempt(
    rows: list[dict[str, str]],
    quotas: dict[str, int],
    unclassified: str,
    order_key: Callable[[dict[str, str]], tuple],
    has_named_people: Callable[[dict[str, str]], bool],
    named_required: int,
    free_required: int,
) -> tuple[dict[str, str], int]:
    views = [view for view, quota in quotas.items() if quota > 0]
    configured = set(quotas)
    ordered = sorted(rows, key=order_key, reverse=True)

    source = 0
    named_node = 1
    free_node = 2
    candidate_start = 3
    view_start = candidate_start + len(ordered)
    view_nodes = {view: view_start + index for index, view in enumerate(views)}
    sink = view_start + len(views)
    flow = Dinic(sink + 1)

    # A full target flow plus these category ceilings enforces both lower
    # bounds: named >= named_required and person-free >= free_required.
    target = sum(quotas.values())
    flow.add_edge(source, named_node, target - free_required)
    flow.add_edge(source, free_node, target - named_required)

    assignment_edges: list[tuple[str, str, int, int]] = []
    for index, row in enumerate(ordered):
        candidate_node = candidate_start + index
        category_node = named_node if has_named_people(row) else free_node
        flow.add_edge(category_node, candidate_node, 1)
        preferences = _candidate_views(row, configured, unclassified)
        for view in preferences:
            if view not in view_nodes:
                continue
            edge_index = flow.add_edge(candidate_node, view_nodes[view], 1)
            assignment_edges.append((row["uuid"], view, candidate_node, edge_index))

    for view in views:
        flow.add_edge(view_nodes[view], sink, quotas[view])

    achieved = flow.max_flow(source, sink)
    assigned: dict[str, str] = {}
    for uuid, view, node, edge_index in assignment_edges:
        if flow.graph[node][edge_index].capacity == 0:
            assigned[uuid] = view
    return assigned, achieved


def assign_views(
    rows: list[dict[str, str]],
    config: dict,
    rank: Callable[[dict[str, str]], float],
    has_named_people: Callable[[dict[str, str]], bool],
) -> tuple[dict[str, str], dict]:
    """Assign unique candidates to exact view quotas.

    Exact view quotas and global named/person-free floors are represented in a
    single flow network. Candidate order changes only which feasible solution
    wins when several assignments satisfy the same constraints.
    """

    quotas = {str(view["id"]): int(view["quota"]) for view in config["views"]}
    target = int(config["target_count"])
    unclassified = str(config["unclassified_view"])
    configured = set(quotas)
    candidate_counts = Counter()
    for row in rows:
        candidate_counts.update(_candidate_views(row, configured, unclassified))

    named_required = int(config.get("minimum_named_people_count", 0))
    free_required = int(config.get("minimum_person_free_count", 0))

    attempts = [("quota-and-diversity-max-flow", lambda row: (rank(row), row["uuid"]))]

    diagnostics = []
    for method, order_key in attempts:
        assigned, achieved = _attempt(
            rows,
            quotas,
            unclassified,
            order_key,
            has_named_people,
            named_required,
            free_required,
        )
        selected = [row for row in rows if row["uuid"] in assigned]
        named_count = sum(has_named_people(row) for row in selected)
        free_count = len(selected) - named_count
        diagnostics.append(
            {
                "method": method,
                "flow": achieved,
                "named_people_count": named_count,
                "person_free_count": free_count,
            }
        )
        if achieved == target and named_count >= named_required and free_count >= free_required:
            assigned_counts = Counter(assigned.values())
            return assigned, {
                "method": method,
                "target": target,
                "achieved_flow": achieved,
                "quotas": quotas,
                "assigned_counts": dict(sorted(assigned_counts.items())),
                "candidate_counts": dict(sorted(candidate_counts.items())),
                "named_people_count": named_count,
                "minimum_named_people_count": named_required,
                "person_free_count": free_count,
                "minimum_person_free_count": free_required,
                "attempts": diagnostics,
            }

    scarcity = {
        view: {"quota": quota, "candidate_count": candidate_counts.get(view, 0)}
        for view, quota in quotas.items()
        if candidate_counts.get(view, 0) < quota
    }
    raise ValueError(
        "unable to satisfy exact view quotas and diversity floors; "
        f"scarcity={scarcity}; attempts={diagnostics}"
    )
