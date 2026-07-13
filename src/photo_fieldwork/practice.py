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

STARTER_CONFIG = {
    "schema_version": 1,
    "seed": 20260710,
    "target_count": 12,
    "unclassified_view": "00",
    "burst_limit": 2,
    "exploratory_fraction": 0.1,
    "minimum_eval_precision": 0.75,
    "minimum_eval_coverage": 0.8,
    "minimum_view_precision": 0.65,
    "minimum_view_decisions": 1,
    "require_final_field_audit": True,
    "minimum_named_people_fraction": 0.35,
    "minimum_person_free_fraction": 0.2,
    "event_cluster_limit": 4,
    "views": [
        {"id": "00", "label": "Unclassified / Editor Field", "quota": 2},
        {"id": "01", "label": "People / Presence", "quota": 3},
        {"id": "02", "label": "Work / Apparatus", "quota": 3},
        {"id": "03", "label": "Project Evidence - Editor Hypothesis", "quota": 2},
        {"id": "04", "label": "Places / Thresholds / Traces", "quota": 2},
    ],
}


def create_demo_inventory(path: Path) -> None:
    rows = []
    contexts = [
        ("01", "high", "people", "Alex Example;Archive Owner"),
        ("02", "high", "apparatus", "Archive Owner"),
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


def write_starter_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(STARTER_CONFIG, indent=2) + "\n", encoding="utf-8")


def practice_feedback(sample_path: Path) -> None:
    with sample_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    for index, row in enumerate(rows):
        row["judgment"] = "reject" if index == 3 else "fit"
        row["evaluation_note"] = "Synthetic practice judgment; inspect real pixels in production."
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
