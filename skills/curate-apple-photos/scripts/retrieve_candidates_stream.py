#!/usr/bin/env python3
"""Retrieve a fresh whole-library candidate field with bounded one-pass scans.

This performance adapter reads only the compact, read-only inventory. Prior
curated albums may be declared as low-weight seeds, but never as evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path


BASE_COLUMNS = [
    "uuid", "filename", "original_filename", "date_created", "year", "width", "height",
    "favorite", "edited", "hidden", "trashed", "missing", "screenshot", "selfie",
    "portrait", "burst", "burst_key", "burst_pick_type", "overall_aesthetic_score",
    "duplicate_group_id", "camera_make", "camera_model", "face_count", "title", "description",
]


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def noise(seed: int, uuid: str) -> float:
    digest = hashlib.sha256(f"{seed}:{uuid}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def add(scores: dict[str, dict[str, float]], view_id: str, uuid: str, weight: float) -> None:
    scores[view_id][uuid] = scores[view_id].get(uuid, 0.0) + weight


def prune(scores: dict[str, dict[str, float]], view_limits: dict[str, int], seed: int) -> None:
    for view_id, values in scores.items():
        limit = view_limits[view_id]
        if len(values) <= limit * 2:
            continue
        keep = sorted(values, key=lambda uuid: (values[uuid], noise(seed, uuid)), reverse=True)[:limit]
        scores[view_id] = {uuid: values[uuid] for uuid in keep}


def relation_values(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    ids: list[str],
) -> dict[str, list[str]]:
    output: dict[str, list[str]] = defaultdict(list)
    for start in range(0, len(ids), 700):
        batch = ids[start : start + 700]
        marks = ",".join("?" for _ in batch)
        for uuid, value in conn.execute(
            f"SELECT uuid, {column} FROM {table} WHERE uuid IN ({marks})", batch
        ):
            if value and value not in output[uuid]:
                output[uuid].append(str(value))
    return output


def safe_album_values(
    conn: sqlite3.Connection,
    ids: list[str],
    excluded_terms: list[str],
    excluded_lineages: set[str],
    has_lineage: bool,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    titles: dict[str, list[str]] = defaultdict(list)
    lineages: dict[str, list[str]] = defaultdict(list)
    for start in range(0, len(ids), 700):
        batch = ids[start : start + 700]
        marks = ",".join("?" for _ in batch)
        columns = "uuid, album_title, lineage" if has_lineage else "uuid, album_title, 'unknown'"
        for uuid, title, lineage in conn.execute(
            f"SELECT {columns} FROM asset_album WHERE uuid IN ({marks})", batch
        ):
            normalized = str(title or "").casefold()
            if any(term in normalized for term in excluded_terms) or lineage in excluded_lineages:
                continue
            if title and title not in titles[uuid]:
                titles[uuid].append(str(title))
            if lineage and lineage not in lineages[uuid]:
                lineages[uuid].append(str(lineage))
    return titles, lineages


def asset_rows(conn: sqlite3.Connection, ids: list[str]) -> dict[str, dict]:
    output: dict[str, dict] = {}
    for start in range(0, len(ids), 700):
        batch = ids[start : start + 700]
        marks = ",".join("?" for _ in batch)
        query = f"SELECT {','.join(BASE_COLUMNS)} FROM asset WHERE uuid IN ({marks})"
        for row in conn.execute(query, batch):
            output[row["uuid"]] = dict(row)
    return output


def text_matches(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def event_cluster(row: dict) -> str:
    burst = str(row.get("burst_key") or "").strip()
    if burst:
        return f"burst:{burst}"
    captured = str(row.get("date_created") or "")
    camera = str(row.get("camera_model") or "unknown").strip().casefold()
    return f"capture-hour:{captured[:13]}:{camera}" if len(captured) >= 13 else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    spec = json.loads(args.retrieval.read_text(encoding="utf-8"))
    views = spec["views"]
    seed = int(spec["seed"])
    multiplier = float(spec.get("candidate_multiplier", 1.75))
    candidate_target = max(args.target, math.ceil(args.target * multiplier))
    view_limits = {
        str(view["id"]): max(12000, math.ceil(int(view["quota"]) * multiplier * 18))
        for view in views
    }
    terms = {
        str(view["id"]): tuple(
            sorted({str(value).casefold() for value in view.get("terms", []) if str(value).strip()}, key=len, reverse=True)
        )
        for view in views
    }
    scores: dict[str, dict[str, float]] = {str(view["id"]): {} for view in views}
    conn = connect(args.db)
    source_count = conn.execute("SELECT count(*) FROM asset").fetchone()[0]
    has_album_lineage = table_has_column(conn, "asset_album", "lineage")
    excluded_lineages = set(spec.get(
        "excluded_album_lineages",
        ["fieldwork_generated", "private_review", "write_audit"],
    ))

    def source_album_members(title: str) -> list[str]:
        if has_album_lineage and excluded_lineages:
            marks = ",".join("?" for _ in excluded_lineages)
            query = (
                f"SELECT uuid FROM asset_album WHERE album_title = ? "
                f"AND lineage NOT IN ({marks})"
            )
            return [row[0] for row in conn.execute(query, (title, *sorted(excluded_lineages)))]
        return [row[0] for row in conn.execute(
            "SELECT uuid FROM asset_album WHERE album_title = ?", (title,)
        )]

    # Indexed exact relations provide project and relationship anchors.
    for view in views:
        view_id = str(view["id"])
        for person in view.get("people", []):
            for (uuid,) in conn.execute("SELECT uuid FROM asset_person WHERE person = ?", (person,)):
                add(scores, view_id, uuid, 8.0)
        for album in view.get("albums", []):
            for uuid in source_album_members(album):
                add(scores, view_id, uuid, 10.0)
        for album in view.get("seed_albums", []):
            for (uuid,) in conn.execute("SELECT uuid FROM asset_album WHERE album_title = ?", (album,)):
                add(scores, view_id, uuid, 3.0)
        prune(scores, view_limits, seed)

    # Scan the visual-search descriptions once. These remain retrieval
    # hypotheses until the PhotoKit preview is actually inspected.
    scan_views = [view_id for view_id in scores if terms[view_id]]
    scanned = 0
    for uuid, normalized in conn.execute(
        "SELECT uuid, lower(coalesce(normalized_string,'')) FROM asset_search "
        "WHERE category_name = 'photos_description'"
    ):
        if normalized:
            for view_id in scan_views:
                if text_matches(normalized, terms[view_id]):
                    add(scores, view_id, uuid, 4.0)
        scanned += 1
        if scanned % 100000 == 0:
            prune(scores, view_limits, seed)
            print(f"search_descriptions_scanned={scanned}", flush=True)
    prune(scores, view_limits, seed)

    # Human-entered titles, descriptions, filenames, and keywords are stronger
    # than generated visual search text, but are scanned only once.
    scanned = 0
    for row in conn.execute(
        "SELECT uuid, lower(coalesce(filename,'') || ' ' || coalesce(original_filename,'') || ' ' || "
        "coalesce(title,'') || ' ' || coalesce(description,'')) AS text FROM asset"
    ):
        text = row["text"]
        if text:
            for view_id in scan_views:
                if text_matches(text, terms[view_id]):
                    add(scores, view_id, row["uuid"], 7.0)
        scanned += 1
        if scanned % 100000 == 0:
            prune(scores, view_limits, seed)
            print(f"assets_scanned={scanned}", flush=True)
    for uuid, keyword in conn.execute("SELECT uuid, lower(keyword) FROM asset_keyword"):
        for view_id in scan_views:
            if text_matches(keyword or "", terms[view_id]):
                add(scores, view_id, uuid, 6.0)
    prune(scores, view_limits, seed)

    matched_ids = {uuid for values in scores.values() for uuid in values}
    base = asset_rows(conn, list(matched_ids))

    def attention(uuid: str) -> float:
        row = base.get(uuid, {})
        favorite = bool(row.get("favorite"))
        edited = bool(row.get("edited"))
        return 12.0 if favorite and edited else 7.0 if favorite else 5.0 if edited else 0.0

    # Dates only support retrieval and never establish narrative provenance.
    for view in views:
        view_id = str(view["id"])
        low = view.get("year_start")
        high = view.get("year_end")
        if low is None and high is None:
            continue
        for uuid in list(scores[view_id]):
            year = base.get(uuid, {}).get("year")
            if year is not None and int(low or 0) <= int(year) <= int(high or 9999):
                scores[view_id][uuid] += 2.0

    prior_title = spec.get("prior_corpus_album_title")
    outside_fraction = float(spec.get("minimum_outside_prior_fraction", 0.0))
    prior_ids = set()
    if prior_title:
        prior_ids = {
            row[0]
            for row in conn.execute("SELECT uuid FROM asset_album WHERE album_title = ?", (prior_title,))
        }
    person_ids = {row[0] for row in conn.execute("SELECT DISTINCT uuid FROM asset_person")}

    selected: list[str] = []
    selected_set: set[str] = set()
    assigned: dict[str, str] = {}
    for view in views:
        view_id = str(view["id"])
        limit = max(1, math.ceil(int(view["quota"]) * multiplier))
        ranked = sorted(
            scores[view_id],
            key=lambda uuid: (scores[view_id][uuid] + attention(uuid), noise(seed, uuid)),
            reverse=True,
        )
        available = [uuid for uuid in ranked if uuid not in selected_set]
        outside_required = math.ceil(limit * outside_fraction)
        picks = [uuid for uuid in available if uuid not in prior_ids][:outside_required]
        picked = set(picks)
        picks.extend(uuid for uuid in available if uuid not in picked)
        for uuid in picks[:limit]:
            if uuid not in selected_set:
                selected.append(uuid)
                selected_set.add(uuid)
                assigned[uuid] = view_id

    aggregate = {
        uuid: max((values.get(uuid, 0.0) for values in scores.values()), default=0.0) + attention(uuid)
        for uuid in matched_ids
    }
    if len(selected) < candidate_target:
        remainder = sorted(
            (uuid for uuid in matched_ids if uuid not in selected_set),
            key=lambda uuid: (aggregate[uuid], noise(seed, uuid)),
            reverse=True,
        )
        for uuid in remainder[: candidate_target - len(selected)]:
            selected.append(uuid)
            assigned[uuid] = max(scores, key=lambda view_id: scores[view_id].get(uuid, 0.0))
        selected_set = set(selected)
    selected = selected[:candidate_target]
    selected_set = set(selected)
    assigned = {uuid: assigned[uuid] for uuid in selected}

    # Force substantial fresh coverage outside the prior 124,484-item source
    # while preserving the view that contributed each candidate.
    required_outside = math.ceil(candidate_target * outside_fraction)
    current_outside = sum(uuid not in prior_ids for uuid in selected)
    if current_outside < required_outside:
        for view in views:
            view_id = str(view["id"])
            donors = sorted(
                (uuid for uuid in selected if assigned[uuid] == view_id and uuid in prior_ids),
                key=lambda uuid: (scores[view_id].get(uuid, 0.0) + attention(uuid), noise(seed, uuid)),
            )
            pool = sorted(
                (
                    uuid for uuid in scores[view_id]
                    if uuid not in prior_ids and uuid not in selected_set
                ),
                key=lambda uuid: (scores[view_id].get(uuid, 0.0) + attention(uuid), noise(seed, uuid)),
                reverse=True,
            )
            while current_outside < required_outside and donors and pool:
                outgoing = donors.pop(0)
                incoming = pool.pop(0)
                index = selected.index(outgoing)
                selected[index] = incoming
                selected_set.remove(outgoing)
                selected_set.add(incoming)
                assigned.pop(outgoing)
                assigned[incoming] = view_id
                current_outside += 1
            if current_outside >= required_outside:
                break
    if current_outside < required_outside:
        raise SystemExit(f"freshness floor failed: {current_outside} < {required_outside}")

    # Preserve material and spatial context that is not merely a portrait or
    # named social scene. The replacement stays inside the same view and never
    # reduces the outside-prior count.
    person_free_fraction = float(spec.get("person_free_floor", 0.25))
    for view in views:
        view_id = str(view["id"])
        members = [uuid for uuid in selected if assigned[uuid] == view_id]
        required_person_free = math.ceil(len(members) * person_free_fraction)
        current_person_free = sum(uuid not in person_ids for uuid in members)
        if current_person_free >= required_person_free:
            continue
        donors = sorted(
            (uuid for uuid in members if uuid in person_ids),
            key=lambda uuid: (scores[view_id].get(uuid, 0.0) + attention(uuid), noise(seed, uuid)),
        )
        pool = sorted(
            (
                uuid for uuid in scores[view_id]
                if uuid not in person_ids and uuid not in selected_set
            ),
            key=lambda uuid: (
                uuid not in prior_ids,
                scores[view_id].get(uuid, 0.0) + attention(uuid),
                noise(seed, uuid),
            ),
            reverse=True,
        )
        for outgoing in donors:
            if current_person_free >= required_person_free:
                break
            incoming_index = next(
                (
                    index for index, candidate in enumerate(pool)
                    if outgoing in prior_ids or candidate not in prior_ids
                ),
                None,
            )
            if incoming_index is None:
                continue
            incoming = pool.pop(incoming_index)
            index = selected.index(outgoing)
            selected[index] = incoming
            selected_set.remove(outgoing)
            selected_set.add(incoming)
            assigned.pop(outgoing)
            assigned[incoming] = view_id
            current_person_free += 1

    final_person_free = sum(uuid not in person_ids for uuid in selected)
    required_person_free = math.ceil(candidate_target * person_free_fraction)
    if final_person_free < required_person_free:
        raise SystemExit(f"person-free floor failed: {final_person_free} < {required_person_free}")

    base = asset_rows(conn, selected)
    persons = relation_values(conn, "asset_person", "person", selected)
    excluded_terms = [
        str(value).casefold()
        for value in [
            *spec.get("excluded_album_terms", []),
            *spec.get("derived_album_terms", []),
        ]
    ]
    albums, album_lineages = safe_album_values(
        conn, selected, excluded_terms, excluded_lineages, has_album_lineage
    )
    conn.close()

    rows = []
    for uuid in selected:
        row = base[uuid]
        view_scores = sorted(
            ((view_id, values.get(uuid, 0.0)) for view_id, values in scores.items() if values.get(uuid, 0.0) > 0),
            key=lambda item: (-item[1], item[0]),
        )
        primary_view = assigned[uuid]
        ordered_views = [primary_view] + [view_id for view_id, _ in view_scores if view_id != primary_view]
        metadata_score = view_scores[0][1] if view_scores else 0.0
        confidence = "high" if metadata_score >= 12 else "medium" if metadata_score >= 6 else "low" if metadata_score > 0 else "unknown"
        rows.append({
            "uuid": uuid,
            "filename": row.get("original_filename") or row.get("filename") or "",
            "candidate_views": ";".join(ordered_views),
            "evidence_confidence": confidence,
            "source_eligibility": "eligible",
            "retrieval_relevance": confidence,
            "visible_evidence": "unreviewed",
            "metadata_score": f"{metadata_score:.2f}",
            "visible_context": "",
            "persons": ";".join(sorted(persons.get(uuid, []))),
            "albums": ";".join(sorted(albums.get(uuid, [])))[:2000],
            "album_lineages": ";".join(sorted(set(album_lineages.get(uuid, [])))),
            "labels": "",
            "place": "",
            "favorite": str(bool(row.get("favorite"))).lower(),
            "edited": str(bool(row.get("edited"))).lower(),
            "safety_status": "clear",
            "safety_reason": "",
            "hidden": str(bool(row.get("hidden") or row.get("trashed"))).lower(),
            "missing": str(bool(row.get("missing"))).lower(),
            "duplicate_group": row.get("duplicate_group_id") or "",
            "burst_group": row.get("burst_key") or "",
            "aesthetic_score": row.get("overall_aesthetic_score") if row.get("overall_aesthetic_score") is not None else "",
            "event_cluster": event_cluster(row),
            "outside_prior": str(bool(prior_title and uuid not in prior_ids)).lower(),
            "date": row.get("date_created") or "",
            "year": row.get("year") or "",
            "width": row.get("width") or "",
            "height": row.get("height") or "",
            "face_count": row.get("face_count") or 0,
            "camera_make": row.get("camera_make") or "",
            "camera_model": row.get("camera_model") or "",
            "local_path": "",
            "rights_status": "unknown",
            "consent_status": "unknown",
            "claim_status": "caption-review",
            "publication_status": "not-reviewed",
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"source_photos={source_count}")
    print(f"matched_assets={len(matched_ids)}")
    print(f"candidate_rows={len(rows)}")
    print(f"outside_prior_candidates={current_outside}")
    print(f"required_outside_prior_candidates={required_outside}")
    print(f"person_free_candidates={final_person_free}")
    print(f"required_person_free_candidates={required_person_free}")
    assigned_counts = {view_id: sum(value == view_id for value in assigned.values()) for view_id in scores}
    print(f"assigned_view_counts={json.dumps(assigned_counts, sort_keys=True)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
