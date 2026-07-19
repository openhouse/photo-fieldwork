from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


FORBIDDEN_KEYS = {
    "asset_identifier",
    "asset_identifiers",
    "archive_uuid",
    "detected_faces",
    "exact_location",
    "execution_nonce",
    "hold_membership",
    "latitude",
    "local_path",
    "longitude",
    "ocr_text",
    "people",
    "persons",
    "preview_path",
    "raw_ocr",
    "receipt_path",
    "safety_reason",
    "source_path",
    "uuid",
}
TEXT_PATTERNS = {
    "home_path": re.compile(r"/Users/[^/\s]+/"),
    "volume_path": re.compile(r"/Volumes/[^\s]+"),
    "photos_library_path": re.compile(r"Photos Library\.photoslibrary", re.IGNORECASE),
    "photos_local_identifier": re.compile(r"[A-F0-9-]{20,}/L\d+/\d+", re.IGNORECASE),
    "credential": re.compile(r"(?:api[_-]?key|password|access[_-]?token)\s*[:=]", re.IGNORECASE),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
}


def _walk(value: Any, path: str = "$") -> list[dict[str, str]]:
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_KEYS:
                findings.append({"code": "FORBIDDEN_PRIVATE_FIELD", "location": f"{path}.{key}", "detail": normalized})
            findings.extend(_walk(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_walk(child, f"{path}[{index}]"))
    return findings


def _structured_value(path: Path, text: str) -> Any | None:
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(text.splitlines()))
    return None


def audit_public_artifact(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    findings = []
    try:
        structured = _structured_value(path, text)
    except (csv.Error, json.JSONDecodeError) as exc:
        findings.append({"code": "PUBLIC_ARTIFACT_PARSE_FAILED", "location": "$", "detail": str(exc)})
        structured = None
    if structured is not None:
        findings.extend(_walk(structured))
    for name, pattern in TEXT_PATTERNS.items():
        if pattern.search(text):
            findings.append({"code": "PRIVATE_TEXT_PATTERN", "location": "$text", "detail": name})
    return {
        "schema_version": 1,
        "status": "PASS" if not findings else "FAIL",
        "artifact": path.name,
        "findings": findings,
        "finding_count": len(findings),
        "source_mutated": False,
    }
