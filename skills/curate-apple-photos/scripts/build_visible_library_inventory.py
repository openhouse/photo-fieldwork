#!/usr/bin/env python3
"""Build a compact, read-only snapshot of every visible still in Apple Photos.

The live Photos database is opened mode=ro in a query-only transaction so
committed WAL rows are visible. The output is a separate SQLite database used
for retrieval; this script never writes to or checkpoints Photos.sqlite.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


DEFAULT_PHOTOS_DB = Path(
    "/Volumes/apple-photos-8tb-external-ssd/Photos Library.photoslibrary/database/Photos.sqlite"
)
SOURCE_IDENTIFIER = "visible-library-stills://v1"
APPLE_EPOCH_OFFSET = 978307200


SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE asset (
  uuid TEXT PRIMARY KEY, asset_pk INTEGER NOT NULL, filename TEXT,
  original_filename TEXT, date_created TEXT, year INTEGER, month INTEGER,
  date_added TEXT, date_modified TEXT, width INTEGER, height INTEGER,
  original_width INTEGER, original_height INTEGER, is_photo INTEGER NOT NULL,
  is_movie INTEGER NOT NULL, favorite INTEGER NOT NULL, edited INTEGER NOT NULL,
  external_edit INTEGER NOT NULL, hidden INTEGER NOT NULL, trashed INTEGER NOT NULL,
  missing INTEGER, cloud_asset INTEGER NOT NULL, local_availability INTEGER,
  remote_availability INTEGER, title TEXT, description TEXT,
  screenshot INTEGER NOT NULL, selfie INTEGER NOT NULL, portrait INTEGER NOT NULL,
  panorama INTEGER NOT NULL, burst INTEGER NOT NULL, burst_key TEXT,
  burst_pick_type INTEGER, overall_aesthetic_score REAL, curation_score REAL,
  promotion_score REAL, highlight_visibility_score REAL, failure_score REAL,
  pleasant_composition_score REAL, sharply_focused_subject_score REAL,
  well_chosen_subject_score REAL, well_framed_subject_score REAL,
  well_timed_shot_score REAL, duplicate_group_id TEXT, camera_make TEXT,
  camera_model TEXT, original_file_size INTEGER, latitude REAL, longitude REAL,
  has_location INTEGER NOT NULL, face_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE asset_person (
  uuid TEXT NOT NULL, person TEXT NOT NULL, PRIMARY KEY (uuid, person)
);
CREATE TABLE asset_album (
  uuid TEXT NOT NULL, album_uuid TEXT NOT NULL, album_title TEXT,
  PRIMARY KEY (uuid, album_uuid)
);
CREATE TABLE asset_keyword (
  uuid TEXT NOT NULL, keyword TEXT NOT NULL, PRIMARY KEY (uuid, keyword)
);
CREATE TABLE asset_search (
  uuid TEXT NOT NULL, category INTEGER NOT NULL, category_name TEXT NOT NULL,
  content_string TEXT, normalized_string TEXT, lookup_identifier TEXT,
  PRIMARY KEY (uuid, category, normalized_string, lookup_identifier)
);
CREATE TABLE asset_label (
  uuid TEXT NOT NULL, label TEXT NOT NULL, label_normalized TEXT NOT NULL,
  PRIMARY KEY (uuid, label_normalized)
);
CREATE TABLE asset_place (
  uuid TEXT NOT NULL, place_type TEXT NOT NULL, place TEXT NOT NULL,
  PRIMARY KEY (uuid, place_type, place)
);
"""


VISIBLE_PREDICATE = """
a.ZKIND = 0 AND a.ZTRASHEDSTATE = 0 AND a.ZHIDDEN = 0
AND a.ZVISIBILITYSTATE = 0 AND a.ZBUNDLESCOPE = 0
"""


def readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=120)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    return conn


def copy_query(
    source: sqlite3.Connection,
    output: sqlite3.Connection,
    select_sql: str,
    insert_sql: str,
    batch_size: int = 5000,
) -> int:
    cursor = source.execute(select_sql)
    count = 0
    while rows := cursor.fetchmany(batch_size):
        output.executemany(insert_sql, rows)
        count += len(rows)
        if count % 100000 < batch_size:
            print(f"rows_copied={count}")
    output.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_PHOTOS_DB)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--quality-report", type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing inventory: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_name(f".{args.output.name}.partial")
    if partial.exists():
        raise SystemExit(f"remove or inspect incomplete inventory first: {partial}")

    photos = readonly(args.photos_db)
    output = sqlite3.connect(partial)
    output.executescript(SCHEMA)
    output.execute("PRAGMA journal_mode=WAL")
    output.execute("PRAGMA synchronous=NORMAL")

    asset_select = f"""
    WITH face_counts AS (
      SELECT ZASSETFORFACE asset_pk, COUNT(*) face_count
      FROM ZDETECTEDFACE
      WHERE coalesce(ZHIDDEN, 0) = 0 AND coalesce(ZISINTRASH, 0) = 0
      GROUP BY ZASSETFORFACE
    )
    SELECT
      a.ZUUID, a.Z_PK, a.ZFILENAME, aa.ZORIGINALFILENAME,
      datetime(a.ZDATECREATED + {APPLE_EPOCH_OFFSET}, 'unixepoch'),
      CAST(strftime('%Y', a.ZDATECREATED + {APPLE_EPOCH_OFFSET}, 'unixepoch') AS INTEGER),
      CAST(strftime('%m', a.ZDATECREATED + {APPLE_EPOCH_OFFSET}, 'unixepoch') AS INTEGER),
      datetime(a.ZADDEDDATE + {APPLE_EPOCH_OFFSET}, 'unixepoch'),
      datetime(a.ZMODIFICATIONDATE + {APPLE_EPOCH_OFFSET}, 'unixepoch'),
      a.ZWIDTH, a.ZHEIGHT, aa.ZORIGINALWIDTH, aa.ZORIGINALHEIGHT,
      1, 0, coalesce(a.ZFAVORITE, 0),
      CASE WHEN coalesce(a.ZADJUSTMENTSSTATE, 0) <> 0 OR aa.ZUNMANAGEDADJUSTMENT IS NOT NULL THEN 1 ELSE 0 END,
      CASE WHEN coalesce(aa.ZEDITORBUNDLEID, '') <> '' THEN 1 ELSE 0 END,
      0, 0, 0,
      CASE WHEN coalesce(a.ZCLOUDASSETGUID, '') <> '' THEN 1 ELSE 0 END,
      NULL, NULL, aa.ZTITLE, ad.ZLONGDESCRIPTION,
      coalesce(a.ZISDETECTEDSCREENSHOT, 0),
      CASE WHEN (coalesce(a.ZKINDSUBTYPE, 0) & 32) <> 0 THEN 1 ELSE 0 END,
      CASE WHEN (coalesce(a.ZKINDSUBTYPE, 0) & 64) <> 0 THEN 1 ELSE 0 END,
      CASE WHEN (coalesce(a.ZKINDSUBTYPE, 0) & 1) <> 0 THEN 1 ELSE 0 END,
      CASE WHEN coalesce(a.ZAVALANCHEKIND, 0) <> 0 THEN 1 ELSE 0 END,
      a.ZAVALANCHEUUID, a.ZAVALANCHEPICKTYPE,
      a.ZOVERALLAESTHETICSCORE, a.ZCURATIONSCORE, a.ZPROMOTIONSCORE,
      a.ZHIGHLIGHTVISIBILITYSCORE, ca.ZFAILURESCORE,
      ca.ZPLEASANTCOMPOSITIONSCORE, ca.ZSHARPLYFOCUSEDSUBJECTSCORE,
      ca.ZWELLCHOSENSUBJECTSCORE, ca.ZWELLFRAMEDSUBJECTSCORE,
      ca.ZWELLTIMEDSHOTSCORE, a.ZMEDIAGROUPUUID,
      ea.ZCAMERAMAKE, ea.ZCAMERAMODEL, aa.ZORIGINALFILESIZE,
      a.ZLATITUDE, a.ZLONGITUDE,
      CASE WHEN a.ZLATITUDE BETWEEN -90 AND 90
             AND a.ZLONGITUDE BETWEEN -180 AND 180
             AND NOT (a.ZLATITUDE = 0 AND a.ZLONGITUDE = 0)
           THEN 1 ELSE 0 END,
      coalesce(fc.face_count, 0)
    FROM ZASSET a
    LEFT JOIN ZADDITIONALASSETATTRIBUTES aa ON aa.ZASSET = a.Z_PK
    LEFT JOIN ZASSETDESCRIPTION ad ON ad.Z_PK = aa.ZASSETDESCRIPTION
    LEFT JOIN ZCOMPUTEDASSETATTRIBUTES ca ON ca.ZASSET = a.Z_PK
    LEFT JOIN ZEXTENDEDATTRIBUTES ea ON ea.ZASSET = a.Z_PK
    LEFT JOIN face_counts fc ON fc.asset_pk = a.Z_PK
    WHERE {VISIBLE_PREDICATE}
    """
    asset_insert = f"INSERT INTO asset VALUES ({','.join('?' for _ in range(51))})"
    asset_count = copy_query(photos, output, asset_select, asset_insert)

    people_select = f"""
    SELECT DISTINCT a.ZUUID,
      coalesce(nullif(trim(p.ZFULLNAME), ''), nullif(trim(p.ZDISPLAYNAME), ''))
    FROM ZASSET a
    JOIN ZDETECTEDFACE f ON f.ZASSETFORFACE = a.Z_PK
    JOIN ZPERSON p ON p.Z_PK = f.ZPERSONFORFACE
    WHERE {VISIBLE_PREDICATE}
      AND coalesce(f.ZHIDDEN, 0) = 0 AND coalesce(f.ZISINTRASH, 0) = 0
      AND coalesce(trim(p.ZDISPLAYNAME), '') <> ''
    """
    people_count = copy_query(
        photos, output, people_select,
        "INSERT OR IGNORE INTO asset_person(uuid, person) VALUES (?, ?)",
    )

    album_select = f"""
    SELECT DISTINCT a.ZUUID, album.ZUUID, album.ZTITLE
    FROM ZASSET a
    JOIN Z_30ASSETS membership ON membership.Z_3ASSETS = a.Z_PK
    JOIN ZGENERICALBUM album ON album.Z_PK = membership.Z_30ALBUMS
    WHERE {VISIBLE_PREDICATE}
      AND album.ZKIND = 2 AND coalesce(album.ZTRASHEDSTATE, 0) = 0
      AND coalesce(trim(album.ZTITLE), '') <> ''
    """
    album_count = copy_query(
        photos, output, album_select,
        "INSERT OR IGNORE INTO asset_album(uuid, album_uuid, album_title) VALUES (?, ?, ?)",
    )

    keyword_select = f"""
    SELECT DISTINCT a.ZUUID, keyword.ZTITLE
    FROM ZASSET a
    JOIN ZADDITIONALASSETATTRIBUTES aa ON aa.ZASSET = a.Z_PK
    JOIN Z_1KEYWORDS relation ON relation.Z_1ASSETATTRIBUTES = aa.Z_PK
    JOIN ZKEYWORD keyword ON keyword.Z_PK = relation.Z_47KEYWORDS
    WHERE {VISIBLE_PREDICATE} AND coalesce(trim(keyword.ZTITLE), '') <> ''
    """
    keyword_count = copy_query(
        photos, output, keyword_select,
        "INSERT OR IGNORE INTO asset_keyword(uuid, keyword) VALUES (?, ?)",
    )

    search_select = f"""
    SELECT a.ZUUID, 1300, 'photos_description', v.ZSTRINGVALUE,
           lower(v.ZSTRINGVALUE), coalesce(n.ZUUID, '')
    FROM ZASSET a
    JOIN ZGRAPHEDGE e ON e.ZSOURCEASSET = a.Z_PK
    JOIN ZGRAPHNODE n ON n.Z_PK = e.ZTARGETNODE
    JOIN ZGRAPHNODEVALUE v ON v.ZNODE = n.Z_PK
    WHERE {VISIBLE_PREDICATE}
      AND v.ZVALUENAME = 'descriptionText'
      AND coalesce(trim(v.ZSTRINGVALUE), '') <> ''
    """
    search_count = copy_query(
        photos, output, search_select,
        "INSERT OR IGNORE INTO asset_search(uuid, category, category_name, content_string, normalized_string, lookup_identifier) VALUES (?, ?, ?, ?, ?, ?)",
    )

    meta = {
        "source_identifier": SOURCE_IDENTIFIER,
        "source_count": str(asset_count),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "photos_database": str(args.photos_db),
        "source_scope": "visible, non-hidden, non-trashed, primary-scope still photographs",
        "direct_photos_writes": "false",
        "external_uploads": "false",
        "people_links": str(people_count),
        "album_links": str(album_count),
        "keyword_links": str(keyword_count),
        "search_description_links": str(search_count),
        "label_links": "0",
        "place_links": "0",
        "photos_schema_user_version": str(photos.execute("PRAGMA user_version").fetchone()[0]),
    }
    output.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", meta.items())
    output.executescript(
        """
        CREATE INDEX idx_asset_year ON asset(year);
        CREATE INDEX idx_asset_favorite ON asset(favorite);
        CREATE INDEX idx_asset_edited ON asset(edited);
        CREATE INDEX idx_asset_burst ON asset(burst_key);
        CREATE INDEX idx_asset_duplicate ON asset(duplicate_group_id);
        CREATE INDEX idx_person_name ON asset_person(person);
        CREATE INDEX idx_album_title ON asset_album(album_title);
        CREATE INDEX idx_keyword_name ON asset_keyword(keyword);
        CREATE INDEX idx_search_name ON asset_search(category_name, normalized_string);
        CREATE INDEX idx_label_name ON asset_label(label_normalized);
        CREATE INDEX idx_place_name ON asset_place(place_type, place);
        ANALYZE;
        """
    )
    output.commit()

    final_count = output.execute("SELECT count(*) FROM asset").fetchone()[0]
    unique_count = output.execute("SELECT count(DISTINCT uuid) FROM asset").fetchone()[0]
    if unique_count != final_count:
        raise SystemExit(f"stable ID uniqueness failed: {unique_count} unique of {final_count}")
    if args.expected_count is not None and final_count != args.expected_count:
        raise SystemExit(f"visible still count changed: {final_count} != {args.expected_count}")
    quality = {
        "source_identifier": SOURCE_IDENTIFIER,
        "generated_at": meta["generated_at"],
        "asset_count": final_count,
        "unique_asset_count": unique_count,
        "signals": {
            "people": {"rows": people_count, "available": people_count > 0},
            "albums": {"rows": album_count, "available": album_count > 0},
            "keywords": {"rows": keyword_count, "available": keyword_count > 0},
            "search": {"rows": search_count, "available": search_count > 0},
            "labels": {"rows": 0, "available": False},
            "places": {"rows": 0, "available": False},
        },
        "expected_count": args.expected_count,
        "direct_photos_writes": False,
        "external_uploads": False,
    }
    print(f"source_identifier={SOURCE_IDENTIFIER}")
    print(f"visible_stills={final_count}")
    print(f"people_links={people_count}")
    print(f"album_links={album_count}")
    print(f"keyword_links={keyword_count}")
    print(f"search_description_links={search_count}")
    photos.rollback()
    photos.close()
    output.close()
    partial.replace(args.output)
    quality_path = args.quality_report or args.output.with_suffix(".quality.json")
    quality_path.write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")
    print(f"quality_report={quality_path}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
