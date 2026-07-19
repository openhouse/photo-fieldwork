#!/usr/bin/env python3
"""Build a brief-specific candidate CSV from the shared read-only Photos inventory."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path


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


def signal_coverage(conn: sqlite3.Connection, views: list[dict]) -> dict[str, dict[str, int | bool]]:
    requested = {
        "people": any(view.get("people") for view in views),
        "albums": any(view.get("albums") or view.get("terms") for view in views),
        "keywords": any(view.get("terms") for view in views),
        "labels": any(view.get("terms") for view in views),
        "places": any(view.get("places") or view.get("terms") for view in views),
        "search": any(view.get("search_terms") for view in views),
    }
    tables = {
        "people": "asset_person",
        "albums": "asset_album",
        "keywords": "asset_keyword",
        "labels": "asset_label",
        "places": "asset_place",
        "search": "asset_search",
    }
    return {
        signal: {
            "requested": requested[signal],
            "rows": int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]),
        }
        for signal, table in tables.items()
    }


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
    args = parser.parse_args()

    spec = json.loads(args.retrieval.read_text(encoding="utf-8"))
    views = spec.get("views") or []
    if not views:
        raise SystemExit("retrieval.json requires at least one view")
    candidate_target = max(args.target, math.ceil(args.target * float(spec.get("candidate_multiplier", 1.75))))
    excluded_album_terms = [
        str(value).casefold() for value in spec.get("excluded_album_terms", []) if str(value).strip()
    ]
    conn = connect(args.db)
    asset_count = conn.execute("SELECT count(*) FROM asset WHERE is_photo = 1 AND hidden = 0 AND trashed = 0").fetchone()[0]
    coverage = signal_coverage(conn, views)
    unavailable = [name for name, item in coverage.items() if item["requested"] and not item["rows"]]
    if unavailable and spec.get("strict_signal_coverage", False):
        raise SystemExit(f"requested retrieval signals have no inventory rows: {', '.join(unavailable)}")
    if unavailable:
        print(f"warning_unavailable_signals={','.join(unavailable)}")

    view_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
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
            low = int(year_start or 0)
            high = int(year_end or 9999)
            for uuid in list(view_scores[view_id]):
                year = conn.execute("SELECT year FROM asset WHERE uuid = ?", (uuid,)).fetchone()
                if year and year[0] is not None and low <= int(year[0]) <= high:
                    view_scores[view_id][uuid] += 2.0

    matched_ids = {uuid for scores in view_scores.values() for uuid in scores}
    base_rows = asset_rows(conn, list(matched_ids)) if matched_ids else {}

    def prior_attention(uuid: str) -> float:
        row = base_rows.get(uuid, {})
        favorite = bool(row.get("favorite"))
        edited = bool(row.get("edited"))
        return 12.0 if favorite and edited else 7.0 if favorite else 5.0 if edited else 0.0

    selected: list[str] = []
    selected_set: set[str] = set()
    multiplier = float(spec.get("candidate_multiplier", 1.75))
    for view in views:
        view_id = str(view["id"])
        limit = max(1, math.ceil(int(view.get("quota", 0)) * multiplier))
        ranked = sorted(view_scores[view_id], key=lambda uuid: (view_scores[view_id][uuid] + prior_attention(uuid), uuid), reverse=True)
        for uuid in ranked[:limit]:
            if uuid not in selected_set:
                selected.append(uuid)
                selected_set.add(uuid)

    if len(selected) < candidate_target:
        needed = candidate_target - len(selected)
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
        for (uuid,) in fallback:
            if uuid not in selected_set:
                selected.append(uuid)
                selected_set.add(uuid)
                if len(selected) == candidate_target:
                    break
    selected = selected[:candidate_target]
    if len(selected) != candidate_target:
        raise SystemExit(f"could only retrieve {len(selected)} of {candidate_target} required candidates")
    selected_set = set(selected)

    prior_title = str(spec.get("prior_corpus_album_title") or "").strip()
    outside_fraction = float(spec.get("minimum_outside_prior_fraction", 0.0))
    if prior_title and outside_fraction > 0:
        prior_ids = {
            row[0]
            for row in conn.execute("SELECT uuid FROM asset_album WHERE album_title = ?", (prior_title,))
        }
        required_outside = math.ceil(candidate_target * outside_fraction)

        def aggregate_score(uuid: str) -> float:
            return max((scores.get(uuid, 0.0) for scores in view_scores.values()), default=0.0) + prior_attention(uuid)

        current_outside = sum(uuid not in prior_ids for uuid in selected)
        if current_outside < required_outside:
            outside_pool = sorted(
                (uuid for uuid in matched_ids if uuid not in prior_ids and uuid not in selected_set),
                key=lambda uuid: (aggregate_score(uuid), uuid),
                reverse=True,
            )
            removable = sorted(
                (uuid for uuid in selected if uuid in prior_ids),
                key=lambda uuid: (aggregate_score(uuid), uuid),
            )
            replacements = min(required_outside - current_outside, len(outside_pool), len(removable))
            remove = set(removable[:replacements])
            selected = [uuid for uuid in selected if uuid not in remove] + outside_pool[:replacements]
            current_outside = sum(uuid not in prior_ids for uuid in selected)
        if current_outside < required_outside:
            raise SystemExit(
                f"outside-prior floor unmet: {current_outside} of {required_outside} required"
            )
        print(f"outside_prior_candidates={current_outside}")
        print(f"required_outside_prior_candidates={required_outside}")

    base_rows = asset_rows(conn, selected)
    people = relation_values(conn, "asset_person", "person", selected)
    albums = relation_values(conn, "asset_album", "album_title", selected)
    if excluded_album_terms:
        albums = {
            uuid: [
                title for title in titles
                if not any(term in title.casefold() for term in excluded_album_terms)
            ]
            for uuid, titles in albums.items()
        }
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
        output_rows.append(
            {
                "uuid": uuid,
                "filename": row.get("original_filename") or row.get("filename") or "",
                "candidate_views": ";".join(view for view, _ in scores),
                "evidence_confidence": confidence,
                "metadata_score": f"{metadata_score:.2f}",
                "visible_context": "",
                "persons": ";".join(sorted(people.get(uuid, []))),
                "albums": ";".join(sorted(albums.get(uuid, []))),
                "labels": ";".join(sorted(labels.get(uuid, []))),
                "place": ";".join(sorted(set(places.get(uuid, []))))[:500],
                "favorite": str(bool(row.get("favorite"))).lower(),
                "edited": str(bool(row.get("edited"))).lower(),
                "safety_status": "clear",
                "safety_state": "clear_for_editor_field",
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
    print(f"signal_coverage={json.dumps(coverage, sort_keys=True)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
