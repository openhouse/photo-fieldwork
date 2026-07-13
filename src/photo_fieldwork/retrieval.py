from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def allocate_candidates(
    view_scores: dict[str, dict[str, float]],
    views: list[dict[str, Any]],
    candidate_target: int,
    *,
    multiplier: float,
    attention_scores: dict[str, float] | None = None,
    prior_ids: set[str] | None = None,
    minimum_outside_prior_fraction: float = 0.0,
) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """Reserve view capacity before forming and truncating the global union.

    Input order never controls allocation. View IDs and UUIDs provide stable
    tie-breaks when candidates collide across views.
    """

    if candidate_target < 1:
        raise ValueError("candidate_target must be positive")
    attention_scores = attention_scores or {}
    prior_ids = prior_ids or set()
    ordered_views = sorted(views, key=lambda view: str(view["id"]))
    ranked: dict[str, list[str]] = {}
    requested: dict[str, int] = {}
    for view in ordered_views:
        view_id = str(view["id"])
        requested[view_id] = min(
            candidate_target,
            max(0, math.ceil(int(view.get("quota", 0)) * multiplier)),
        )
        ranked[view_id] = sorted(
            view_scores.get(view_id, {}),
            key=lambda uuid: (
                view_scores[view_id][uuid] + attention_scores.get(uuid, 0.0),
                uuid,
            ),
            reverse=True,
        )

    selected: list[str] = []
    selected_set: set[str] = set()
    reserved_view: dict[str, str] = {}
    pointers: defaultdict[str, int] = defaultdict(int)
    filled: defaultdict[str, int] = defaultdict(int)

    progress = True
    while progress and len(selected) < candidate_target:
        progress = False
        for view in ordered_views:
            view_id = str(view["id"])
            if filled[view_id] >= requested[view_id]:
                continue
            choices = ranked[view_id]
            while pointers[view_id] < len(choices):
                uuid = choices[pointers[view_id]]
                pointers[view_id] += 1
                if uuid in selected_set:
                    continue
                selected.append(uuid)
                selected_set.add(uuid)
                reserved_view[uuid] = view_id
                filled[view_id] += 1
                progress = True
                break
            if len(selected) == candidate_target:
                break

    all_ids = {uuid for scores in view_scores.values() for uuid in scores}

    def aggregate_score(uuid: str) -> float:
        return max((scores.get(uuid, 0.0) for scores in view_scores.values()), default=0.0) + attention_scores.get(uuid, 0.0)

    remainder = sorted(
        (uuid for uuid in all_ids if uuid not in selected_set),
        key=lambda uuid: (aggregate_score(uuid), uuid),
        reverse=True,
    )
    for uuid in remainder:
        if len(selected) == candidate_target:
            break
        selected.append(uuid)
        selected_set.add(uuid)

    required_outside = math.ceil(candidate_target * minimum_outside_prior_fraction)
    current_outside = sum(uuid not in prior_ids for uuid in selected)
    if current_outside < required_outside:
        outside_pool = [
            uuid
            for uuid in remainder
            if uuid not in prior_ids and uuid not in selected_set
        ]
        donors = sorted(
            (uuid for uuid in selected if uuid in prior_ids),
            key=lambda uuid: (uuid in reserved_view, aggregate_score(uuid), uuid),
        )
        while current_outside < required_outside and outside_pool and donors:
            incoming = outside_pool.pop(0)
            outgoing = donors.pop(0)
            index = selected.index(outgoing)
            selected[index] = incoming
            selected_set.remove(outgoing)
            selected_set.add(incoming)
            if outgoing in reserved_view:
                reserved_view[incoming] = reserved_view.pop(outgoing)
            current_outside += 1

    if len(selected) != candidate_target:
        raise ValueError(f"candidate field has {len(selected)} rows; expected {candidate_target}")
    if current_outside < required_outside:
        raise ValueError(
            f"outside-prior floor unavailable: {current_outside} < {required_outside}"
        )

    report = {
        "candidate_target": candidate_target,
        "matched_assets": len(all_ids),
        "requested_by_view": dict(sorted(requested.items())),
        "reserved_by_view": dict(sorted(filled.items())),
        "collisions_skipped_by_view": {
            view_id: pointers[view_id] - filled[view_id]
            for view_id in sorted(requested)
        },
        "outside_prior_required": required_outside,
        "outside_prior_selected": current_outside,
    }
    return selected, reserved_view, report
