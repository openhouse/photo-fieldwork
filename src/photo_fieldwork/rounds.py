from __future__ import annotations

from collections import Counter

from .pipeline import is_hold, split_values, truthy


def _review_ready(row: dict[str, str], allow_uninspected: bool) -> bool:
    if allow_uninspected:
        return True
    if "pixel_available" not in row:
        return False
    if not truthy(row.get("pixel_available")):
        return False
    if "preview_exported" in row and not truthy(row.get("preview_exported")):
        return False
    return True


def apply_feedback(
    master: list[dict[str, str]],
    inventory: list[dict[str, str]],
    feedback: list[dict[str, str]],
    *,
    round_id: str,
    allow_uninspected: bool = False,
) -> tuple[list[dict[str, str]], list[dict]]:
    decisions = {row["uuid"]: row for row in feedback if row.get("uuid")}
    removed: list[dict[str, str]] = []
    retained: list[dict[str, str]] = []
    events: list[dict] = []
    for row in master:
        decision = decisions.get(row["uuid"], {})
        judgment = decision.get("judgment", "").strip().lower()
        safety = decision.get("safety_status", "clear").strip().lower()
        if judgment == "reject" or safety in {"hold", "needs-review"}:
            removed.append(row)
            events.append(
                {
                    "asset_uuid": row["uuid"],
                    "event_type": "placed-on-hold" if safety != "clear" else "reviewed-reject",
                    "previous_state": "selected",
                    "new_state": safety if safety != "clear" else "rejected",
                    "reason": decision.get("visible_reason") or decision.get("evaluation_note") or "round feedback",
                    "payload": {"round_id": round_id, "primary_view": row.get("primary_view", "")},
                }
            )
        else:
            retained.append(dict(row))

    selected_ids = {row["uuid"] for row in retained}
    removed_ids = {row["uuid"] for row in removed}
    pool = [
        dict(row)
        for row in inventory
        if row["uuid"] not in selected_ids
        and row["uuid"] not in removed_ids
        and not is_hold(row)
        and _review_ready(row, allow_uninspected)
    ]
    pool.sort(key=lambda row: (float(row.get("score_total") or 0), row["uuid"]), reverse=True)

    replacements = []
    for outgoing in removed:
        same_view = next(
            (row for row in pool if row.get("primary_view") == outgoing.get("primary_view")),
            None,
        )
        incoming = same_view or (pool[0] if pool else None)
        if incoming is None:
            raise ValueError(f"no inspected clear replacement available for {outgoing['uuid']}")
        pool.remove(incoming)
        incoming["selection_reason"] = "; ".join(
            part for part in (
                incoming.get("selection_reason", ""),
                f"replacement in {round_id} for {outgoing['uuid']}",
            ) if part
        )
        replacements.append(incoming)
        events.append(
            {
                "asset_uuid": incoming["uuid"],
                "event_type": "replaced",
                "previous_state": "eligible",
                "new_state": "selected",
                "reason": f"replacement for {outgoing['uuid']}",
                "payload": {
                    "round_id": round_id,
                    "outgoing_uuid": outgoing["uuid"],
                    "primary_view": incoming.get("primary_view", ""),
                },
            }
        )

    result = retained + replacements
    result.sort(key=lambda row: (row.get("primary_view", ""), -float(row.get("score_total") or 0), row["uuid"]))
    if len(result) != len(master) or len({row["uuid"] for row in result}) != len(result):
        raise ValueError("replacement round did not preserve an exact unique master")
    return result, events


def convergence(reports: list[dict]) -> dict:
    rounds = []
    errors = Counter()
    for index, report in enumerate(reports, start=1):
        rounds.append(
            {
                "round": index,
                "precision": report.get("precision"),
                "coverage": report.get("coverage"),
                "passed": bool(report.get("passed")),
                "fit": report.get("fit", 0),
                "reject": report.get("reject", 0),
                "uncertain": report.get("uncertain", 0),
            }
        )
        errors.update(report.get("error_categories", {}))
    return {
        "round_count": len(rounds),
        "rounds": rounds,
        "precision_trajectory": [item["precision"] for item in rounds],
        "coverage_trajectory": [item["coverage"] for item in rounds],
        "final_passed": bool(rounds and rounds[-1]["passed"]),
        "error_categories": dict(sorted(errors.items())),
    }
