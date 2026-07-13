from __future__ import annotations


SAFETY_STATES = {
    "clear_automated",
    "hold_automated",
    "review_sensitive",
    "cleared_editor_private",
    "cleared_public_candidate",
    "restricted_private",
}

LEGACY_SAFETY_STATES = {
    "": "clear_automated",
    "clear": "clear_automated",
    "hold": "hold_automated",
    "needs-review": "review_sensitive",
}

GENERAL_MASTER_STATES = {
    "clear_automated",
    "cleared_editor_private",
    "cleared_public_candidate",
}

ALLOWED_TRANSITIONS = {
    "clear_automated": {"hold_automated", "review_sensitive"},
    "hold_automated": {"review_sensitive", "restricted_private"},
    "review_sensitive": {
        "cleared_editor_private",
        "cleared_public_candidate",
        "restricted_private",
    },
    "cleared_editor_private": {
        "review_sensitive",
        "cleared_public_candidate",
        "restricted_private",
    },
    "cleared_public_candidate": {"review_sensitive", "restricted_private"},
    "restricted_private": {"review_sensitive"},
}


def normalize_safety_state(value: object) -> str:
    state = str(value or "").strip().lower()
    state = LEGACY_SAFETY_STATES.get(state, state)
    if state not in SAFETY_STATES:
        raise ValueError(f"unknown safety state: {value!r}")
    return state


def may_enter_general_master(value: object) -> bool:
    return normalize_safety_state(value) in GENERAL_MASTER_STATES


def validate_safety_transition(previous: object, current: object, actor: str) -> tuple[str, str]:
    old = normalize_safety_state(previous)
    new = normalize_safety_state(current)
    if old == new:
        return old, new
    if new not in ALLOWED_TRANSITIONS[old]:
        raise ValueError(f"safety transition is not allowed: {old} -> {new}")
    if new in {"cleared_editor_private", "cleared_public_candidate"} and actor != "human-editor":
        raise ValueError(f"{new} requires actor=human-editor")
    return old, new
