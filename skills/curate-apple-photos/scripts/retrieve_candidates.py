#!/usr/bin/env python3
"""Build candidates through explicit, auditable retrieval channels."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
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
        matched.update(row[0] for row in conn.execute(query, (f"%{value.casefold()}%",)))
    return matched


def album_matches(
    conn: sqlite3.Connection,
    values: list[str],
    excluded_identifiers: set[str],
    excluded_terms: list[str],
) -> set[str]:
    matched: set[str] = set()
    clauses = ["lower(coalesce(album_title,'')) LIKE ?"]
    if excluded_identifiers:
        clauses.append(
            f"album_uuid NOT IN ({','.join('?' for _ in excluded_identifiers)})"
        )
    clauses.extend("lower(coalesce(album_title,'')) NOT LIKE ?" for _ in excluded_terms)
    query = "SELECT uuid FROM asset_album WHERE " + " AND ".join(clauses)
    for value in values:
        params = [f"%{value.casefold()}%", *sorted(excluded_identifiers)]
        params.extend(f"%{term.casefold()}%" for term in excluded_terms)
        matched.update(row[0] for row in conn.execute(query, params))
    return matched


def exact_album_members(
    conn: sqlite3.Connection,
    identifiers: list[str],
    titles: list[str],
) -> set[str]:
    matched: set[str] = set()
    if identifiers:
        placeholders = ",".join("?" for _ in identifiers)
        matched.update(
            row[0]
            for row in conn.execute(
                f"SELECT uuid FROM asset_album WHERE album_uuid IN ({placeholders})",
                identifiers,
            )
        )
    if titles:
        placeholders = ",".join("?" for _ in titles)
        matched.update(
            row[0]
            for row in conn.execute(
                f"SELECT uuid FROM asset_album WHERE album_title IN ({placeholders})",
                titles,
            )
        )
    return matched


def relation_values(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    ids: list[str],
) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    for start in range(0, len(ids), 700):
        batch = ids[start : start + 700]
        placeholders = ",".join("?" for _ in batch)
        for uuid, value in conn.execute(
            f"SELECT uuid, {column} FROM {table} WHERE uuid IN ({placeholders})",
            batch,
        ):
            if value and value not in values[uuid]:
                values[uuid].append(str(value))
    return values


def album_values(
    conn: sqlite3.Connection,
    ids: list[str],
    excluded_identifiers: set[str],
    excluded_terms: list[str],
) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    for start in range(0, len(ids), 700):
        batch = ids[start : start + 700]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"SELECT uuid, album_uuid, album_title FROM asset_album WHERE uuid IN ({placeholders})",
            batch,
        )
        for uuid, album_uuid, title in rows:
            if not title or album_uuid in excluded_identifiers:
                continue
            if any(term in title.casefold() for term in excluded_terms):
                continue
            if title not in values[uuid]:
                values[uuid].append(title)
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


def normalized(values: list[object]) -> list[str]:
    return [str(value).casefold() for value in values if str(value).strip()]


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
    multiplier = float(spec.get("candidate_multiplier", 1.75))
    candidate_target = max(args.target, math.ceil(args.target * multiplier))
    discovery_fraction = float(spec.get("outside_prior_discovery_fraction", 0.0))
    if not 0 <= discovery_fraction <= 0.5:
        raise SystemExit("outside_prior_discovery_fraction must be between 0 and 0.5")
    excluded_album_identifiers = {
        str(value).split("/", 1)[0]
        for value in spec.get("excluded_album_identifiers", [])
        if str(value).strip()
    }
    excluded_album_terms = normalized(spec.get("excluded_album_terms", []))

    conn = connect(args.db)
    asset_count = conn.execute(
        "SELECT count(*) FROM asset WHERE is_photo = 1 AND hidden = 0 AND trashed = 0"
    ).fetchone()[0]
    prior_ids = exact_album_members(
        conn,
        [str(value).split("/", 1)[0] for value in spec.get("prior_corpus_album_identifiers", [])],
        [str(value) for value in spec.get("prior_corpus_album_titles", [])],
    )

    view_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    channels: dict[str, set[str]] = defaultdict(set)

    def contribute(view_id: str, ids: set[str], weight: float, channel: str) -> None:
        for uuid in ids:
            view_scores[view_id][uuid] += weight
            channels[uuid].add(channel)

    for view in views:
        view_id = str(view["id"])
        terms = normalized(view.get("terms", []))
        people = normalized(view.get("people", []))
        albums = normalized(view.get("albums", []))
        places = normalized(view.get("places", []))
        search_terms = normalized(view.get("search_terms", []))
        base_query = """
            SELECT uuid FROM asset
            WHERE is_photo = 1 AND hidden = 0 AND trashed = 0 AND lower(
                coalesce(filename,'') || ' ' || coalesce(original_filename,'') || ' ' ||
                coalesce(title,'') || ' ' || coalesce(description,'')
            ) LIKE ?
        """
        for term in terms:
            contribute(view_id, like_matches(conn, base_query, [term]), 7.0, f"metadata:{view_id}")
            contribute(
                view_id,
                album_matches(conn, [term], excluded_album_identifiers, excluded_album_terms),
                7.0,
                f"album-term:{view_id}",
            )
            for query, weight, channel in [
                ("SELECT uuid FROM asset_keyword WHERE lower(keyword) LIKE ?", 6.0, "keyword"),
                ("SELECT uuid FROM asset_label WHERE lower(label_normalized) LIKE ?", 4.0, "label"),
                ("SELECT uuid FROM asset_place WHERE lower(place) LIKE ?", 4.0, "place"),
            ]:
                contribute(view_id, like_matches(conn, query, [term]), weight, f"{channel}:{view_id}")
        contribute(
            view_id,
            like_matches(conn, "SELECT uuid FROM asset_person WHERE lower(person) LIKE ?", people),
            8.0,
            f"person:{view_id}",
        )
        contribute(
            view_id,
            album_matches(conn, albums, excluded_album_identifiers, excluded_album_terms),
            10.0,
            f"album:{view_id}",
        )
        contribute(
            view_id,
            like_matches(conn, "SELECT uuid FROM asset_place WHERE lower(place) LIKE ?", places),
            5.0,
            f"place:{view_id}",
        )
        contribute(
            view_id,
            like_matches(
                conn,
                "SELECT uuid FROM asset_search WHERE lower(coalesce(normalized_string,'')) LIKE ?",
                search_terms,
            ),
            4.0,
            f"search:{view_id}",
        )
        provenance = exact_album_members(
            conn,
            [str(value).split("/", 1)[0] for value in view.get("provenance_album_identifiers", [])],
            [str(value) for value in view.get("provenance_album_titles", [])],
        )
        contribute(view_id, provenance, 12.0, f"provenance:{view_id}")

        low = int(view.get("year_start", 0))
        high = int(view.get("year_end", 9999))
        if "year_start" in view or "year_end" in view:
            for uuid in list(view_scores[view_id]):
                year = conn.execute("SELECT year FROM asset WHERE uuid = ?", (uuid,)).fetchone()
                if year and year[0] is not None and low <= int(year[0]) <= high:
                    view_scores[view_id][uuid] += 2.0
                    channels[uuid].add(f"date-support:{view_id}")

    matched_ids = {uuid for scores in view_scores.values() for uuid in scores}
    base_rows = asset_rows(conn, list(matched_ids)) if matched_ids else {}

    def prior_attention(uuid: str) -> float:
        row = base_rows.get(uuid, {})
        favorite = bool(row.get("favorite"))
        edited = bool(row.get("edited"))
        return 12.0 if favorite and edited else 7.0 if favorite else 5.0 if edited else 0.0

    def aggregate_score(uuid: str) -> float:
        return max((scores.get(uuid, 0.0) for scores in view_scores.values()), default=0.0) + prior_attention(uuid)

    discovery_target = math.ceil(candidate_target * discovery_fraction)
    contextual_target = candidate_target - discovery_target
    selected: list[str] = []
    selected_set: set[str] = set()
    context_scale = 1.0 - discovery_fraction
    ranked_by_view: list[tuple[str, list[str]]] = []
    for view in views:
        view_id = str(view["id"])
        limit = max(1, math.ceil(int(view.get("quota", 0)) * multiplier * context_scale))
        ranked = sorted(
            view_scores[view_id],
            key=lambda uuid: (view_scores[view_id][uuid] + prior_attention(uuid), uuid),
            reverse=True,
        )
        ranked_by_view.append((view_id, ranked[:limit]))
    positions = {view_id: 0 for view_id, _ in ranked_by_view}
    while len(selected) < contextual_target:
        progressed = False
        for view_id, ranked in ranked_by_view:
            while positions[view_id] < len(ranked):
                uuid = ranked[positions[view_id]]
                positions[view_id] += 1
                if uuid in selected_set:
                    continue
                selected.append(uuid)
                selected_set.add(uuid)
                channels[uuid].add("contextual-allocation")
                progressed = True
                break
            if len(selected) >= contextual_target:
                break
        if not progressed:
            break

    discovery_pool = sorted(
        (
            uuid
            for uuid in matched_ids
            if uuid not in selected_set and uuid not in prior_ids
        ),
        key=lambda uuid: (aggregate_score(uuid), uuid),
        reverse=True,
    )
    for uuid in discovery_pool[:discovery_target]:
        selected.append(uuid)
        selected_set.add(uuid)
        channels[uuid].add("outside-prior-discovery")

    if len(selected) < candidate_target:
        fallback = conn.execute(
            """
            SELECT uuid FROM asset
            WHERE is_photo = 1 AND hidden = 0 AND trashed = 0
              AND (favorite = 1 OR edited = 1 OR face_count > 0)
            ORDER BY (favorite + edited) DESC, face_count DESC, uuid
            LIMIT ?
            """,
            ((candidate_target - len(selected)) * 8,),
        )
        for (uuid,) in fallback:
            if uuid not in selected_set:
                selected.append(uuid)
                selected_set.add(uuid)
                channels[uuid].add("fallback-attention")
                if len(selected) == candidate_target:
                    break
    selected = selected[:candidate_target]

    base_rows = asset_rows(conn, selected)
    people_values = relation_values(conn, "asset_person", "person", selected)
    albums_values = album_values(
        conn,
        selected,
        excluded_album_identifiers,
        excluded_album_terms,
    )
    labels_values = relation_values(conn, "asset_label", "label", selected)
    places_values = relation_values(conn, "asset_place", "place", selected)
    conn.close()

    output_rows = []
    for uuid in selected:
        row = base_rows[uuid]
        scores = sorted(
            (
                (view_id, score_map.get(uuid, 0.0))
                for view_id, score_map in view_scores.items()
                if score_map.get(uuid, 0.0) > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )
        metadata_score = scores[0][1] if scores else 0.0
        confidence = "high" if metadata_score >= 12 else "medium" if metadata_score >= 6 else "low" if metadata_score > 0 else "unknown"
        output_rows.append(
            {
                "uuid": uuid,
                "filename": row.get("original_filename") or row.get("filename") or "",
                "candidate_views": ";".join(view for view, _ in scores),
                "assigned_view": "",
                "assignment_status": "",
                "assignment_reason": "",
                "evidence_confidence": confidence,
                "metadata_score": f"{metadata_score:.2f}",
                "retrieval_channels": ";".join(sorted(channels.get(uuid, []))),
                "prior_corpus_member": str(uuid in prior_ids).lower(),
                "visible_context": "",
                "persons": ";".join(sorted(people_values.get(uuid, []))),
                "albums": ";".join(sorted(albums_values.get(uuid, []))),
                "labels": ";".join(sorted(labels_values.get(uuid, []))),
                "place": ";".join(sorted(set(places_values.get(uuid, []))))[:500],
                "favorite": str(bool(row.get("favorite"))).lower(),
                "edited": str(bool(row.get("edited"))).lower(),
                "safety_status": "clear-automated",
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
    if not output_rows:
        raise SystemExit("retrieval produced no candidates; revise retrieval channels")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    channel_counts = Counter(
        channel
        for uuid in selected
        for channel in channels.get(uuid, set())
    )
    report = {
        "schema_version": 2,
        "artifact_sensitivity": "private-operational",
        "source_photos": asset_count,
        "matched_assets": len(matched_ids),
        "candidate_target": candidate_target,
        "candidate_rows": len(output_rows),
        "prior_corpus_assets": len(prior_ids),
        "selected_prior_corpus_members": sum(uuid in prior_ids for uuid in selected),
        "selected_outside_prior": sum(uuid not in prior_ids for uuid in selected),
        "outside_prior_discovery_target": discovery_target,
        "channel_counts": dict(sorted(channel_counts.items())),
    }
    report_path = args.report or args.output.with_suffix(".retrieval-report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"output={args.output}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
