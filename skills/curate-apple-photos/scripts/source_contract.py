#!/usr/bin/env python3
"""Shared source-profile contract for Photo Fieldwork Apple Photos adapters."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


VISIBLE_LIBRARY_STILLS = "visible-library-stills://v1"
VISIBLE_STILLS_PREDICATE_VERSION = "apple-photos-visible-stills-v1"
SUPPORTED_SOURCE_KINDS = {"album", "visible-library-stills", "synthetic"}


@dataclass(frozen=True)
class SourceSpec:
    schema_version: int
    kind: str
    identifier: str
    title: str
    snapshot_count: int
    predicate_version: str
    source_fingerprint: str | None = None
    inventory_profile: str | None = None
    artifact_sensitivity: str | None = None
    generated_at: str | None = None
    inventory_path: str | None = None

    def validate(self) -> "SourceSpec":
        if self.schema_version != 1:
            raise ValueError(f"unsupported source schema_version: {self.schema_version}")
        if self.kind not in SUPPORTED_SOURCE_KINDS:
            raise ValueError(f"unsupported source kind: {self.kind}")
        if not self.identifier.strip():
            raise ValueError("source identifier is required")
        if self.snapshot_count < 1:
            raise ValueError("source snapshot_count must be positive")
        if self.kind == "visible-library-stills" and self.identifier != VISIBLE_LIBRARY_STILLS:
            raise ValueError("visible-library-stills requires the canonical identifier")
        return self

    def to_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}


def load_source(path: Path) -> SourceSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    return SourceSpec(
        schema_version=int(data.get("schema_version", 0)),
        kind=str(data.get("kind", "")),
        identifier=str(data.get("identifier", "")),
        title=str(data.get("title", "")),
        snapshot_count=int(data.get("snapshot_count", 0)),
        predicate_version=str(data.get("predicate_version", "")),
        source_fingerprint=data.get("source_fingerprint"),
        inventory_profile=data.get("inventory_profile"),
        artifact_sensitivity=data.get("artifact_sensitivity"),
        generated_at=data.get("generated_at"),
        inventory_path=data.get("inventory_path"),
    ).validate()


def write_source(path: Path, source: SourceSpec) -> None:
    source.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(source.to_dict(), indent=2) + "\n", encoding="utf-8")


def fallback_source(identifier: str, count: int, title: str = "Apple Photos source") -> SourceSpec:
    kind = "visible-library-stills" if identifier == VISIBLE_LIBRARY_STILLS else "album"
    predicate = VISIBLE_STILLS_PREDICATE_VERSION if kind == "visible-library-stills" else "album-membership-v1"
    return SourceSpec(1, kind, identifier, title, count, predicate).validate()


def visible_stills_predicate(alias: str = "a") -> str:
    return (
        f"{alias}.ZKIND = 0 AND {alias}.ZTRASHEDSTATE = 0 "
        f"AND {alias}.ZHIDDEN = 0 AND {alias}.ZVISIBILITYSTATE = 0 "
        f"AND {alias}.ZBUNDLESCOPE = 0"
    )
