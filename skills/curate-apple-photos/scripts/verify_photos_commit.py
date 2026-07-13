#!/usr/bin/env python3
"""Independently verify a permissioned-app plan and receipt through read-only Photos SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from photo_fieldwork.source import fingerprint_identifiers  # noqa: E402


DEFAULT_DB = Path(
    "/Volumes/apple-photos-8tb-external-ssd/Photos Library.photoslibrary/database/Photos.sqlite"
)


def base(value: str) -> str:
    return value.split("/", 1)[0]


def album_record(conn: sqlite3.Connection, identifier: str) -> tuple[int, str]:
    rows = conn.execute("SELECT Z_PK, ZTITLE FROM ZGENERICALBUM WHERE ZUUID = ?", (base(identifier),)).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"expected one album for {identifier}; found {len(rows)}")
    return int(rows[0][0]), rows[0][1] or ""


def members(conn: sqlite3.Connection, album_pk: int) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            """
            SELECT a.ZUUID
            FROM Z_30ASSETS membership
            JOIN ZASSET a ON a.Z_PK = membership.Z_3ASSETS
            WHERE membership.Z_30ALBUMS = ?
            """,
            (album_pk,),
        )
    }


def report_markdown(report: dict) -> str:
    lines = [
        "# Apple Photos commit verification",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"- Plan: `{report['plan_id']}`",
        f"- Status: **{'PASS' if report['passed'] else 'FAIL'}**",
        f"- Source: `{report['source']['title']}`",
        f"- Source membership: {report['source']['actual_count']:,}",
        f"- Source fingerprint: `{report['source']['actual_fingerprint']}`",
        f"- Albums exactly verified: {report['summary']['exact_albums']}",
        f"- Unexpected memberships: {report['summary']['unexpected_memberships']}",
        f"- Missing memberships: {report['summary']['missing_memberships']}",
        f"- Members outside source corpus: {report['summary']['outside_source_memberships']}",
        f"- Master / safety HOLD overlap: {report['summary']['master_hold_overlap']}",
        "",
        "## Albums",
        "",
    ]
    for album in report["albums"]:
        lines.append(
            f"- `{album['title']}` ({album['role']}): {album['actual_count']:,}; "
            f"missing {album['missing_count']}, unexpected {album['unexpected_count']}, "
            f"outside source {album['outside_source_count']}"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", "", *[f"- {error}" for error in report["errors"]]])
    lines.extend(["", "Verification used a read-only, immutable, query-only SQLite connection.", ""])
    return "\n".join(lines)


def output_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.report_json or args.report_md:
        if not args.report_json or not args.report_md:
            raise ValueError("--report-json and --report-md must be provided together")
        return args.report_json, args.report_md
    if not args.report:
        raise ValueError("provide --report or both --report-json and --report-md")
    if args.report.suffix.lower() == ".json":
        return args.report, args.report.with_suffix(".md")
    if args.report.suffix.lower() in {".md", ".markdown"}:
        return args.report.with_suffix(".json"), args.report
    raise ValueError("--report must end in .json, .md, or .markdown")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-md", type=Path)
    parser.add_argument("--photos-db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    json_path, markdown_path = output_paths(args)

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    expected_albums = plan["albums"]
    titles = [item["title"] for item in expected_albums]
    if len(titles) != len(set(titles)):
        raise RuntimeError("plan contains duplicate album titles; independent verification is ambiguous")
    receipt_by_title = {item["title"]: item for item in receipt["albums"]}
    if len(receipt_by_title) != len(receipt["albums"]):
        raise RuntimeError("receipt contains duplicate album titles")

    source_profile = plan.get("source") or {}
    source_identifier = source_profile.get("catalog_identifier") or source_profile.get("id")
    if not source_identifier or str(source_identifier).startswith(("visible-library-", "filesystem:")):
        source_identifier = plan.get("source_album_identifier")
    if not source_identifier:
        raise RuntimeError("plan does not identify a verifiable Photos source album")

    uri = f"file:{args.photos_db}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    source_pk, source_title = album_record(conn, source_identifier)
    source = members(conn, source_pk)
    source_fingerprint = fingerprint_identifiers(source)
    expected_source_count = source_profile.get("actual_count", plan.get("expected_source_count"))
    expected_source_fingerprint = source_profile.get("fingerprint")

    errors = []
    if expected_source_count is not None and len(source) != int(expected_source_count):
        errors.append(f"source count changed: {len(source)} != {expected_source_count}")
    if expected_source_fingerprint and source_fingerprint != expected_source_fingerprint:
        errors.append(f"source fingerprint changed: {source_fingerprint} != {expected_source_fingerprint}")
    if set(titles) != set(receipt_by_title):
        missing_titles = sorted(set(titles) - set(receipt_by_title))
        unexpected_titles = sorted(set(receipt_by_title) - set(titles))
        errors.append(f"plan/receipt album titles differ; missing={missing_titles}, unexpected={unexpected_titles}")

    album_reports = []
    actual_by_role: dict[str, set[str]] = {}
    actual_by_key: dict[str, set[str]] = {}
    singleton_roles = {"editor-master", "safety-hold", "write-test", "people-context", "uncertainty"}
    for planned in expected_albums:
        title = planned["title"]
        expected = {base(identifier) for identifier in planned.get("asset_identifiers", planned.get("asset_ids", []))}
        received = receipt_by_title.get(title)
        if not received:
            actual = set()
            identifier = ""
            actual_title = ""
        else:
            identifier = received["identifier"]
            album_pk, actual_title = album_record(conn, identifier)
            actual = members(conn, album_pk)
        role = planned.get("role", "unspecified")
        if role in singleton_roles and role in actual_by_role:
            errors.append(f"plan contains duplicate semantic role: {role}")
        else:
            actual_by_role.setdefault(role, set()).update(actual)
        key = planned.get("key", title)
        if key in actual_by_key:
            errors.append(f"plan contains duplicate album key: {key}")
        actual_by_key[key] = actual
        missing = expected - actual
        unexpected = actual - expected
        outside = actual - source
        if actual_title and actual_title != title:
            errors.append(f"title mismatch for {title}: catalog has {actual_title}")
        if missing or unexpected or outside:
            errors.append(
                f"membership mismatch for {title}: missing={len(missing)}, "
                f"unexpected={len(unexpected)}, outside_source={len(outside)}"
            )
        album_reports.append(
            {
                "key": key,
                "role": role,
                "title": title,
                "identifier": identifier,
                "expected_count": len(expected),
                "actual_count": len(actual),
                "missing_count": len(missing),
                "unexpected_count": len(unexpected),
                "outside_source_count": len(outside),
                "missing_identifiers": sorted(missing),
                "unexpected_identifiers": sorted(unexpected),
                "outside_source_identifiers": sorted(outside),
            }
        )

    master = actual_by_role.get("editor-master", set())
    holds = actual_by_role.get("safety-hold", set())
    master_hold_overlap = master & holds
    if master_hold_overlap:
        errors.append(f"editor master overlaps safety hold by {len(master_hold_overlap)} assets")
    for album in expected_albums:
        if album.get("role") == "editor-view":
            actual_ids = actual_by_key[album.get("key", album["title"])]
            if not actual_ids <= master:
                errors.append(f"editor view {album['key']} is not a subset of editor master")
    conn.close()

    summary = {
        "album_count": len(album_reports),
        "exact_albums": sum(
            item["missing_count"] == item["unexpected_count"] == item["outside_source_count"] == 0
            for item in album_reports
        ),
        "missing_memberships": sum(item["missing_count"] for item in album_reports),
        "unexpected_memberships": sum(item["unexpected_count"] for item in album_reports),
        "outside_source_memberships": sum(item["outside_source_count"] for item in album_reports),
        "master_hold_overlap": len(master_hold_overlap),
    }
    report = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "plan_id": plan["plan_id"],
        "passed": not errors,
        "source": {
            "title": source_title,
            "identifier": source_identifier,
            "actual_count": len(source),
            "expected_count": expected_source_count,
            "actual_fingerprint": source_fingerprint,
            "expected_fingerprint": expected_source_fingerprint,
        },
        "summary": summary,
        "albums": album_reports,
        "errors": errors,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(report_markdown(report), encoding="utf-8")
    print(f"verification_status={'PASS' if report['passed'] else 'FAIL'}")
    print(f"verified_albums={summary['exact_albums']}")
    print(f"source_count={len(source)}")
    print(f"report_json={json_path}")
    print(f"report_md={markdown_path}")
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
