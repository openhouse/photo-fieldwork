from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


TRUE_VALUES = {"1", "true", "yes", "y"}
FALSE_VALUES = {"", "0", "false", "no", "n"}
BOOLEAN_FIELDS = {
    "edited",
    "favorite",
    "hidden",
    "is_movie",
    "is_photo",
    "missing",
    "pixel_available",
    "preview_exported",
    "trashed",
}


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def canonical_asset_id(value: object) -> str:
    identifier = str(value or "").strip()
    if not identifier:
        raise ValueError("empty asset identifier")
    return identifier.split("/", 1)[0]


def photokit_asset_id(value: object) -> str:
    return f"{canonical_asset_id(value)}/L0/001"


def split_values(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def normalize_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = {str(key): "" if value is None else str(value).strip() for key, value in row.items()}
    if "uuid" in normalized:
        normalized["uuid"] = canonical_asset_id(normalized["uuid"])
    for field in BOOLEAN_FIELDS & normalized.keys():
        value = normalized[field].lower()
        if value not in TRUE_VALUES | FALSE_VALUES:
            raise ValueError(f"invalid boolean value for {field}: {normalized[field]}")
        normalized[field] = "true" if value in TRUE_VALUES else "false"
    return normalized


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stable_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seal_plan(plan: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(plan)
    sealed.pop("plan_digest", None)
    sealed["plan_digest"] = stable_digest(sealed)
    return sealed


def verify_plan_digest(plan: dict[str, Any]) -> bool:
    expected = str(plan.get("plan_digest") or "")
    if not expected:
        return False
    unsigned = dict(plan)
    unsigned.pop("plan_digest", None)
    return expected == stable_digest(unsigned)


def load_source_profile(path: Path) -> dict[str, Any]:
    profile = read_json(path)
    required = {"schema_version", "id", "title", "kind", "expected_count"}
    missing = required - profile.keys()
    if missing:
        raise ValueError(f"source profile missing: {', '.join(sorted(missing))}")
    if int(profile["schema_version"]) != 1:
        raise ValueError("unsupported source profile schema_version")
    if profile["kind"] not in {"album", "visible-library-query", "filesystem", "dam"}:
        raise ValueError(f"unsupported source kind: {profile['kind']}")
    if int(profile["expected_count"]) < 1:
        raise ValueError("source expected_count must be positive")
    profile["fingerprint"] = stable_digest(
        {
            "id": profile["id"],
            "kind": profile["kind"],
            "expected_count": int(profile["expected_count"]),
            "snapshot_at": profile.get("snapshot_at"),
            "predicate": profile.get("predicate"),
        }
    )
    return profile
