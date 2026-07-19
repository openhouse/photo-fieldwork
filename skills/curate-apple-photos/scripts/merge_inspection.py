#!/usr/bin/env python3
"""Merge permissioned-app inspection JSONL into a candidate inventory CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def base(value: str) -> str:
    return value.split("/", 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    inspected = {}
    for line in args.inspection.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        identifier = row.get("asset_identifier") or row.get("uuid")
        if identifier:
            inspected[base(identifier)] = row

    with args.candidates.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    additions = ["visible_context", "visible_observation", "vision_labels_all", "detected_face_count", "automated_safety_state", "safety_status", "safety_reason", "pixel_available", "preview_exported"]
    for field in additions:
        if field not in fields:
            fields.append(field)

    missing = 0
    holds = 0
    for row in rows:
        result = inspected.get(base(row["uuid"]))
        if not result:
            missing += 1
            row.update({"visible_context": "", "visible_observation": "", "vision_labels_all": "", "detected_face_count": "0", "automated_safety_state": "unavailable", "safety_status": "hold", "safety_reason": "local inspection result unavailable", "pixel_available": "false", "preview_exported": "false"})
            holds += 1
            continue
        labels = result.get("vision_labels") or result.get("visible_labels") or []
        faces = int(result.get("detected_face_count") or 0)
        context = "; ".join(labels[:6])
        if faces:
            context = f"{faces} visible face(s)" + (f"; {context}" if context else "")
        state = result.get("safety_state", "unavailable")
        flags = result.get("safety_flags") or []
        held = state in {"hold", "unavailable"} or not result.get("pixel_available", False)
        if held:
            holds += 1
        row.update(
            {
                "visible_context": context,
                "visible_observation": context,
                "vision_labels_all": ";".join(labels),
                "detected_face_count": str(faces),
                "automated_safety_state": state,
                "safety_status": "hold" if held else "clear",
                "safety_reason": "; ".join(flags) if flags else ("local pixels unavailable" if held else ""),
                "pixel_available": str(bool(result.get("pixel_available"))).lower(),
                "preview_exported": str(bool(result.get("preview_exported"))).lower(),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"candidates={len(rows)}")
    print(f"inspection_missing={missing}")
    print(f"holds={holds}")


if __name__ == "__main__":
    main()
