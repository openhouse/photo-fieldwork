#!/usr/bin/env python3
"""Build a brief-specific candidate CSV from the shared read-only Photos inventory."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from photo_fieldwork.contracts import write_json  # noqa: E402
from photo_fieldwork.retrieval import allocate_candidates  # noqa: E402


BASE_COLUMNS = [
    "uuid", "filename", "original_filename", "date_created", "year", "width", "height",
    "is_photo", "is_movie", "favorite", "edited", "hidden", "trashed", "missing",
    "screenshot", "selfie", "portrait", "burst", "burst_key", "burst_pick_type",
    "overall_aesthetic_score", "duplicate_group_id", "camera_make", "camera_model",
    "face_count", "title", "description",
]


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def like_matches(conn: sqlite3.Connection, query: str, values: list[str]) -> set[str]:
    matched: set[str] = set()
    for value in values:
        pattern = f"%{value.casefold()}%"
        matched.update(row[0] for row in conn.execute(query, (pattern,)))
    return matched


def album_matches(conn: sqlite3.Connection, values: list[str], excluded_terms: list[str]) -> set[str]:
    matched: set[str] = set()
    exclusions = "".join(" AND lower(coalesce(album_title,'')) NOT LIKE ?" for _ in excluded_terms)
    query = "SELECT uuid FROM asset_album WHERE lower(coalesce(album_title,'')) LIKE ?" + exclusions
    for value in values:
        params = [f"%{value.casefold()}%", *[f"%{term.casefold()}%" for term in excluded_terms]]
        matched.update(row[0] for row in conn.execute(query, params))
    return matched


def relation_values(conn: sqlite3.Connection, table: str, column: str, ids: list[str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    for start in range(0, len(ids), 700):
        batch = ids[start : start + 700]
        placeholders = ",".join("?" for _ in batch)
        for uuid, value in conn.execute(f"SELECT uuid, {column} FROM {table} WHERE uuid IN ({placeholders})", batch):
            if value and value not in values[uuid]:
                values[uuid].append(str(value))
    return values


def asset_rows(conn: sqlite3.Connection, ids: list[str]) -> dict[str, dict]:
    values = {}
    for start in range(0, len(ids), 700):
        batch = ids[start : start + 700]
        placeholders = ",".join("?" for _ in batch)
        for row in conn.execute(
            f"SELECT {','.join(BASE_COLUMNS)} FROM asset WHERE uuid IN ({placeholders})",
            batch,
        ):
            values[row["uuid"]] = dict(row)
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    spec = json.loads(args.retrieval.read_text(encoding="utf-8"))
    views = spec.get("views") or []
    if not views:
        raise SystemExit("retrieval.json requires at least one view")
    candidate_target = max(args.target, math.ceil(args.target * float(spec.get("candidate_multiplier", 1.75))))
    excluded_album_terms = [
        str(value).casefold()
        for value in spec.get("excluded_album_terms", [])
        if str(value).strip()
    ]
    conn = connect(args.db)
    asset_count = conn.execute("SELECT count(*) FROM asset WHERE is_photo = 1 AND hidden = 0 AND trashed = 0").fetchone()[0]

    view_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    year_ranges: dict[str, tuple[int, int]] = {}
    for view in views:
        view_id = str(view["id"])
        terms = [str(value).casefold() for value in view.get("terms", []) if str(value).strip()]
        people = [str(value).casefold() for value in view.get("people", []) if str(value).strip()]
        albums = [str(value).casefold() for value in view.get("albums", []) if str(value).strip()]
        places = [str(value).casefold() for value in view.get("places", []) if str(value).strip()]
        search_terms = [str(value).casefold() for value in view.get("search_terms", []) if str(value).strip()]

        base_query = """
            SELECT uuid FROM asset
            WHERE is_photo = 1 AND hidden = 0 AND trashed = 0 AND lower(
                coalesce(filename,'') || ' ' || coalesce(original_filename,'') || ' ' ||
                coalesce(title,'') || ' ' || coalesce(description,'')
            ) LIKE ?
        """
        relation_queries = [
            ("SELECT uuid FROM asset_keyword WHERE lower(keyword) LIKE ?", 6.0),
            ("SELECT uuid FROM asset_label WHERE lower(label_normalized) LIKE ?", 4.0),
            ("SELECT uuid FROM asset_place WHERE lower(place) LIKE ?", 4.0),
        ]
        for term in terms:
            for uuid in like_matches(conn, base_query, [term]):
                view_scores[view_id][uuid] += 7.0
            for uuid in album_matches(conn, [term], excluded_album_terms):
                view_scores[view_id][uuid] += 7.0
            for query, weight in relation_queries:
                for uuid in like_matches(conn, query, [term]):
                    view_scores[view_id][uuid] += weight
        for uuid in like_matches(conn, "SELECT uuid FROM asset_person WHERE lower(person) LIKE ?", people):
            view_scores[view_id][uuid] += 8.0
        for uuid in album_matches(conn, albums, excluded_album_terms):
            view_scores[view_id][uuid] += 10.0
        for uuid in like_matches(conn, "SELECT uuid FROM asset_place WHERE lower(place) LIKE ?", places):
            view_scores[view_id][uuid] += 5.0
        for uuid in like_matches(conn, "SELECT uuid FROM asset_search WHERE lower(coalesce(normalized_string,'')) LIKE ?", search_terms):
            view_scores[view_id][uuid] += 4.0

        year_start = view.get("year_start")
        year_end = view.get("year_end")
        if year_start is not None or year_end is not None:
            year_ranges[view_id] = (int(year_start or 0), int(year_end or 9999))

    matched_ids = {uuid for scores in view_scores.values() for uuid in scores}
    base_rows = asset_rows(conn, list(matched_ids)) if matched_ids else {}
    for view_id, (low, high) in year_ranges.items():
        for uuid in list(view_scores[view_id]):
            year = base_rows.get(uuid, {}).get("year")
            if year is not None and low <= int(year) <= high:
                view_scores[view_id][uuid] += 2.0

    def prior_attention(uuid: str) -> float:
        row = base_rows.get(uuid, {})
        favorite = bool(row.get("favorite"))
        edited = bool(row.get("edited"))
        return 12.0 if favorite and edited else 7.0 if favorite else 5.0 if edited else 0.0

    multiplier = float(spec.get("candidate_multiplier", 1.75))
    if len(matched_ids) < candidate_target:
        needed = candidate_target - len(matched_ids)
        fallback = conn.execute(
            """
            SELECT uuid FROM asset
            WHERE is_photo = 1 AND hidden = 0 AND trashed = 0
              AND (favorite = 1 OR edited = 1 OR face_count > 0)
            ORDER BY (favorite + edited) DESC, face_count DESC, uuid
            LIMIT ?
            """,
            (needed * 4,),
        )
        fallback_view = str(spec.get("fallback_view") or views[0]["id"])
        for (uuid,) in fallback:
            if uuid not in matched_ids:
                view_scores[fallback_view][uuid] += 0.01
                matched_ids.add(uuid)
                if len(matched_ids) == candidate_target:
                    break
        base_rows.update(asset_rows(conn, list(matched_ids - base_rows.keys())))

    attention_scores = {uuid: prior_attention(uuid) for uuid in matched_ids}
    prior_album_title = str(spec.get("prior_corpus_album_title") or "").strip()
    prior_ids = {
        row[0]
        for row in conn.execute("SELECT uuid FROM asset_album WHERE album_title = ?", (prior_album_title,))
    } if prior_album_title else set()
    selected, reserved_views, allocation_report = allocate_candidates(
        view_scores,
        views,
        candidate_target,
        multiplier=multiplier,
        attention_scores=attention_scores,
        prior_ids=prior_ids,
        minimum_outside_prior_fraction=float(spec.get("minimum_outside_prior_fraction", 0.0)),
    )

    base_rows = asset_rows(conn, selected)
    people = relation_values(conn, "asset_person", "person", selected)
    albums = relation_values(conn, "asset_album", "album_title", selected)
    labels = relation_values(conn, "asset_label", "label", selected)
    places = relation_values(conn, "asset_place", "place", selected)
    conn.close()

    output_rows = []
    for uuid in selected:
        row = base_rows[uuid]
        scores = sorted(
            ((view_id, score_map.get(uuid, 0.0)) for view_id, score_map in view_scores.items() if score_map.get(uuid, 0.0) > 0),
            key=lambda item: (-item[1], item[0]),
        )
        metadata_score = scores[0][1] if scores else 0.0
        confidence = "high" if metadata_score >= 12 else "medium" if metadata_score >= 6 else "low" if metadata_score > 0 else "unknown"
        retrieval_type = "fallback_attention" if metadata_score <= 0.01 else "retrieval_index"
        output_rows.append(
            {
                "uuid": uuid,
                "filename": row.get("original_filename") or row.get("filename") or "",
                "candidate_views": ";".join(view for view, _ in scores),
                "reserved_view": reserved_views.get(uuid, ""),
                "evidence_confidence": confidence,
                "metadata_score": f"{metadata_score:.2f}",
                "visible_context": "",
                "visible_evidence": "",
                "source_provenance": "",
                "editor_hypothesis": ";".join(view for view, _ in scores),
                "retrieval_evidence_types": retrieval_type,
                "persons": ";".join(sorted(people.get(uuid, []))),
                "albums": ";".join(sorted(albums.get(uuid, []))),
                "labels": ";".join(sorted(labels.get(uuid, []))),
                "place": ";".join(sorted(set(places.get(uuid, []))))[:500],
                "favorite": str(bool(row.get("favorite"))).lower(),
                "edited": str(bool(row.get("edited"))).lower(),
                "safety_status": "clear",
                "safety_reason": "",
                "hidden": str(bool(row.get("hidden") or row.get("trashed"))).lower(),
                "missing": str(bool(row.get("missing"))).lower(),
                "duplicate_group": row.get("duplicate_group_id") or "",
                "burst_group": row.get("burst_key") or "",
                "aesthetic_score": row.get("overall_aesthetic_score") if row.get("overall_aesthetic_score") is not None else "",
                "event_cluster": "",
                "date": row.get("date_created") or "",
                "year": row.get("year") or "",
                "width": row.get("width") or "",
                "height": row.get("height") or "",
                "face_count": row.get("face_count") or 0,
                "source_face_count": row.get("face_count") or 0,
                "inspected_face_count": 0,
                "camera_make": row.get("camera_make") or "",
                "camera_model": row.get("camera_model") or "",
                "local_path": "",
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output_rows[0])
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"source_photos={asset_count}")
    print(f"matched_assets={len(matched_ids)}")
    print(f"candidate_target={candidate_target}")
    print(f"candidate_rows={len(output_rows)}")
    print(f"output={args.output}")
    allocation_report.update({"source_photos": asset_count, "output": str(args.output)})
    if args.report:
        write_json(args.report, allocation_report)
    print(json.dumps(allocation_report, sort_keys=True))


if __name__ == "__main__":
    main()
