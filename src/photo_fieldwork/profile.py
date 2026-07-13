from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


DEFAULT_PROFILE = Path(
    os.environ.get(
        "PHOTO_FIELDWORK_PROFILE",
        "~/.config/photo-fieldwork/profile.json",
    )
).expanduser()


def _path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"profile field {field} must be a non-empty path")
    return Path(value).expanduser()


def load_profile(path: Path | None = None) -> dict:
    profile_path = (path or DEFAULT_PROFILE).expanduser()
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(
            f"machine profile not found: {profile_path}; copy config/machine-profile.example.json"
        ) from error
    if profile.get("schema_version") != 1:
        raise ValueError("machine profile requires schema_version 1")
    if not str(profile.get("name", "")).strip():
        raise ValueError("machine profile requires a name")
    _path(profile.get("workspace_root"), "workspace_root")
    _path(profile.get("photos_database"), "photos_database")
    helper = profile.get("helper")
    if not isinstance(helper, dict):
        raise ValueError("machine profile requires helper settings")
    _path(helper.get("app_path"), "helper.app_path")
    if not str(helper.get("bundle_id", "")).strip():
        raise ValueError("machine profile requires helper.bundle_id")
    adapter = str(profile.get("default_writer_adapter", "photokit"))
    if adapter not in {"photokit", "applescript"}:
        raise ValueError("default_writer_adapter must be photokit or applescript")
    if adapter == "applescript":
        _path(profile.get("applescript_writer"), "applescript_writer")
    sources = profile.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("machine profile requires at least one source")
    default_source = str(profile.get("default_source", ""))
    if default_source not in sources:
        raise ValueError("machine profile default_source must name a configured source")
    for key, source in sources.items():
        if not isinstance(source, dict) or not str(source.get("identifier", "")).strip():
            raise ValueError(f"profile source {key} requires an identifier")
        count = source.get("expected_count")
        if count is not None and (not isinstance(count, int) or count < 1):
            raise ValueError(f"profile source {key} expected_count must be null or a positive integer")
    folders = profile.get("protected_folders")
    if not isinstance(folders, dict):
        raise ValueError("machine profile requires protected_folders")
    for key in ("root", "private", "audit"):
        item = folders.get(key)
        if not isinstance(item, dict):
            raise ValueError(f"machine profile requires protected_folders.{key}")
        if not str(item.get("title", "")).strip() or not str(item.get("identifier", "")).strip():
            raise ValueError(f"protected_folders.{key} requires title and identifier")
    profile["_profile_path"] = str(profile_path.resolve())
    return profile


def source_settings(profile: dict, key: str | None = None) -> dict:
    source_key = key or str(profile["default_source"])
    try:
        source = dict(profile["sources"][source_key])
    except KeyError as error:
        raise ValueError(f"unknown profile source: {source_key}") from error
    source["key"] = source_key
    return source


def path_is_file_provider(path: Path) -> bool:
    value = str(path.expanduser().resolve(strict=False))
    markers = ("/Mobile Documents/", "/CloudStorage/", "/Library/Mobile Documents/")
    return any(marker in value for marker in markers)


def check_profile(profile: dict, minimum_free_gb: float = 10.0) -> dict:
    workspace = _path(profile["workspace_root"], "workspace_root")
    photos_db = _path(profile["photos_database"], "photos_database")
    app = _path(profile["helper"]["app_path"], "helper.app_path")
    checks = {
        "workspace_exists": workspace.is_dir(),
        "workspace_is_local": not path_is_file_provider(workspace),
        "photos_database_exists": photos_db.is_file(),
        "helper_app_exists": app.is_dir(),
    }
    free_gb = None
    if workspace.exists():
        free_gb = shutil.disk_usage(workspace).free / (1024**3)
        checks["minimum_free_space"] = free_gb >= minimum_free_gb
    else:
        checks["minimum_free_space"] = False
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "profile": profile["name"],
        "profile_path": profile.get("_profile_path"),
        "checks": checks,
        "free_space_gb": round(free_gb, 2) if free_gb is not None else None,
        "default_source": profile["default_source"],
    }
