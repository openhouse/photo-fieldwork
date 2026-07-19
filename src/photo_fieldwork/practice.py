from __future__ import annotations

import csv
import json
from pathlib import Path


FIELDS = [
    "uuid", "filename", "candidate_views", "evidence_confidence", "visible_context",
    "persons", "favorite", "edited", "safety_status", "safety_reason", "hidden",
    "missing", "duplicate_group", "burst_group", "aesthetic_score", "event_cluster",
    "date", "place", "local_path",
]


def create_demo_inventory(path: Path) -> None:
    rows = []
    contexts = [
        ("01", "high", "people", "Alex Example;Jamie Example"),
        ("02", "high", "apparatus", "Jamie Example"),
        ("03", "high", "document", ""),
        ("04", "medium", "place", ""),
        ("", "unknown", "", ""),
    ]
    for index in range(1, 31):
        view, confidence, context, people = contexts[(index - 1) % len(contexts)]
        row = {
            "uuid": f"DEMO-{index:03d}",
            "filename": f"practice-{index:03d}.jpg",
            "candidate_views": view,
            "evidence_confidence": confidence,
            "visible_context": context,
            "persons": people,
            "favorite": "true" if index % 7 == 0 else "false",
            "edited": "true" if index % 6 == 0 else "false",
            "safety_status": "hold" if index in {9, 24} else "clear",
            "safety_reason": "possible private document" if index == 9 else "possible private contact information" if index == 24 else "",
            "hidden": "false",
            "missing": "false",
            "duplicate_group": "duplicate-a" if index in {11, 12} else "",
            "burst_group": "burst-a" if index in {16, 17, 18} else "",
            "aesthetic_score": str((index % 5) / 5),
            "event_cluster": f"event-{(index - 1) // 5 + 1}",
            "date": f"2026-01-{index:02d}",
            "place": "Example City",
            "local_path": "",
        }
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def practice_feedback(sample_path: Path) -> None:
    with sample_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    for index, row in enumerate(rows):
        row["judgment"] = "reject" if index == 3 else "fit"
        row["visible_reason"] = "Synthetic practice judgment; inspect real pixels in production."
        row["safety_status"] = "clear_automated"
        row["error_category"] = "retrieval-mismatch" if index == 3 else "visible-fit"
        row["round_id"] = "practice-round-01"
        row["reviewer_lens"] = "synthetic-practice"
    with sample_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_demo_readme(path: Path) -> None:
    path.write_text(
        "# Practice run\n\n"
        "This workspace contains only synthetic records. It demonstrates the complete "
        "selection, safety-hold, sampling, evaluation, and validation loop without reading "
        "a photo library. Replace the synthetic inventory only after reading the project "
        "safety and Apple Photos documentation.\n",
        encoding="utf-8",
    )
