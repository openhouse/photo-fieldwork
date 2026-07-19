from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


FIELDS = [
    "uuid", "filename", "candidate_views", "retrieval_basis", "evidence_confidence",
    "visible_observation", "observation_source", "machine_visible_signals",
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
            "retrieval_basis": f"{view}:synthetic-fixture" if view else "00:synthetic-fixture",
            "evidence_confidence": confidence,
            "visible_observation": context,
            "observation_source": "reviewer",
            "machine_visible_signals": "",
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
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def practice_feedback(sample_path: Path) -> None:
    with sample_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    for index, row in enumerate(rows):
        row["judgment"] = "reject" if index == 3 else "fit"
        row["evaluation_note"] = "Synthetic practice judgment; inspect real pixels in production."
        row["visible_reason"] = "Synthetic visible reason for workflow validation only."
        row["reviewer_lens"] = "synthetic-practice"
        row["error_category"] = "retrieval-mismatch" if index == 3 else "visible-fit"
        inspection_path = sample_path.parent.parent / "previews" / "evaluation" / f"{row['uuid']}.txt"
        inspection_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        inspection_path.write_text(
            f"Synthetic inspection artifact for {row['uuid']} in {row['round_id']}.\n",
            encoding="utf-8",
        )
        inspection_path.chmod(0o600)
        row["inspection_path"] = str(inspection_path.resolve())
        row["inspection_sha256"] = hashlib.sha256(inspection_path.read_bytes()).hexdigest()
        row["inspection_round_id"] = row["round_id"]
        row["inspection_sample_sha256"] = row["sample_sha256"]
    with sample_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    sample_path.chmod(0o600)


def write_demo_readme(path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(
        "# Practice run\n\n"
        "This workspace contains only synthetic records. It demonstrates the complete "
        "selection, safety-hold, sampling, evaluation, and validation loop without reading "
        "a photo library. Replace the synthetic inventory only after reading the project "
        "safety and Apple Photos documentation.\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
