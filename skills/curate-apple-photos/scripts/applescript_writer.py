#!/usr/bin/env python3
"""Render or explicitly run a fail-closed Photos AppleScript plan adapter.

The adapter accepts the same frozen membership plan as the PhotoKit helper. It
creates folders and albums and adds existing memberships only. It never removes
members, edits assets, or treats its own receipt as independent verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def quote(value: str) -> str:
    if "\n" in value or "\t" in value:
        raise ValueError("Photos titles and paths may not contain tabs or newlines")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def variable(prefix: str, value: str) -> str:
    return prefix + re.sub(r"[^A-Za-z0-9]", "", value.title())


def validate(plan: dict) -> None:
    if plan.get("operation") != "snapshot-membership":
        raise ValueError("AppleScript adapter accepts snapshot-membership plans only")
    if plan.get("schema_version") != 1:
        raise ValueError("unsupported plan schema_version")
    if plan.get("execution_kind") not in {"write-test", "production"}:
        raise ValueError("invalid execution_kind")
    if plan.get("safety_mode") != "create-folders-albums-and-add-membership-only":
        raise ValueError("unsafe or unrecognized plan safety_mode")
    if not re.fullmatch(r"[0-9a-f]{64}", str(plan.get("catalog_plan_sha256", ""))):
        raise ValueError("invalid catalog_plan_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", str(plan.get("source_membership_sha256", ""))):
        raise ValueError("invalid source_membership_sha256")
    if not 1 <= int(plan.get("batch_size", 0)) <= 500:
        raise ValueError("AppleScript batch_size must be within 1...500")
    folder_keys = [folder["key"] for folder in plan.get("folders", [])]
    if len(folder_keys) != len(set(folder_keys)):
        raise ValueError("duplicate folder keys")
    for folder in plan.get("folders", []):
        parent = folder.get("parent_key")
        if parent and parent not in folder_keys:
            raise ValueError(f"unknown parent folder key: {parent}")
    titles = [album["title"] for album in plan.get("albums", [])]
    if len(titles) != len(set(titles)):
        raise ValueError("duplicate target album titles")
    for album in plan.get("albums", []):
        if album["parent_folder_key"] not in folder_keys:
            raise ValueError(f"unknown album parent: {album['parent_folder_key']}")
        ids = album.get("asset_identifiers", [])
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate asset identifier in {album['title']}")
        if any(not value.endswith("/L0/001") for value in ids):
            raise ValueError(f"non-asset identifier in {album['title']}")


def render(plan: dict, id_directory: Path, *, inline_identifiers: bool = False) -> str:
    validate(plan)
    id_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    id_directory.chmod(0o700)
    lines = [
        "with timeout of 7200 seconds",
        '    tell application "Photos"',
        '        set outputText to ""',
    ]
    folder_vars: dict[str, str] = {}
    for folder in plan["folders"]:
        key = folder["key"]
        title = folder["title"]
        folder_var = variable("folder", key)
        matches_var = variable("matching", key)
        folder_vars[key] = folder_var
        parent_key = folder.get("parent_key")
        if parent_key:
            query = f"every folder of {folder_vars[parent_key]} whose name is {quote(title)}"
            create = f"make new folder named {quote(title)} at {folder_vars[parent_key]}"
        else:
            query = f"every folder whose name is {quote(title)}"
            create = f"make new folder named {quote(title)}"
        lines.append(f"        set {matches_var} to {query}")
        if folder.get("existing_identifier"):
            lines.append(
                f'        if (count of {matches_var}) is not 1 then error "Expected exactly one protected folder: " & {quote(title)}'
            )
            lines.append(f"        set {folder_var} to item 1 of {matches_var}")
        else:
            lines.append(
                f'        if (count of {matches_var}) > 1 then error "Duplicate target folder: " & {quote(title)}'
            )
            lines.append(f"        if (count of {matches_var}) = 0 then")
            lines.append(f"            set {folder_var} to {create}")
            lines.append("        else")
            lines.append(f"            set {folder_var} to item 1 of {matches_var}")
            lines.append("        end if")
        lines.append(
            f'        set outputText to outputText & "FOLDER" & tab & {quote(key)} & tab & {quote(title)} & tab & (id of {folder_var} as text) & linefeed'
        )

    batch_size = int(plan["batch_size"])
    for index, album in enumerate(plan["albums"]):
        title = album["title"]
        parent = folder_vars[album["parent_folder_key"]]
        ids = album["asset_identifiers"]
        id_path = id_directory / f"album-{index:03d}.txt"
        id_path.write_text("\n".join(ids), encoding="utf-8")
        id_path.chmod(0o600)
        lines.extend(
            [
                f"        set albumTitle to {quote(title)}",
                f"        set matchingAlbums to every album of {parent} whose name is albumTitle",
                '        if (count of matchingAlbums) > 1 then error "Duplicate protected album: " & albumTitle',
                "        if (count of matchingAlbums) = 0 then",
                f"            set targetAlbum to make new album named albumTitle at {parent}",
                "        else",
                "            set targetAlbum to item 1 of matchingAlbums",
                "        end if",
            ]
        )
        if inline_identifiers:
            lines.append("        set targetIDs to {}")
            for start in range(0, len(ids), 100):
                values = ", ".join(quote(value) for value in ids[start : start + 100])
                lines.append(f"        set targetIDs to targetIDs & {{{values}}}")
        else:
            lines.append(
                f"        set targetIDs to read POSIX file {quote(str(id_path.resolve()))} using delimiter linefeed"
            )
        lines.extend(
            [
                "        set existingIDs to id of media items of targetAlbum",
                "        repeat with existingID in existingIDs",
                "            if targetIDs does not contain (existingID as text) then",
                '                error "Protected album contains an unexpected member: " & albumTitle',
                "            end if",
                "        end repeat",
                "        set batchItems to {}",
                "        repeat with targetID in targetIDs",
                "            set targetIDText to targetID as text",
                "            if targetIDText is not \"\" and existingIDs does not contain targetIDText then",
                "                set targetItem to media item id targetIDText",
                "                copy targetItem to end of batchItems",
                f"                if (count of batchItems) is {batch_size} then",
                "                    add batchItems to targetAlbum",
                "                    set batchItems to {}",
                "                end if",
                "            end if",
                "        end repeat",
                "        if batchItems is not {} then add batchItems to targetAlbum",
                "        set finalIDs to id of media items of targetAlbum",
                f'        if (count of finalIDs) is not {len(ids)} then error "Final count mismatch: " & albumTitle',
                "        repeat with targetID in targetIDs",
                "            if targetID as text is not \"\" and finalIDs does not contain (targetID as text) then",
                '                error "Protected album is missing an expected UUID: " & albumTitle',
                "            end if",
                "        end repeat",
                '        set outputText to outputText & "ALBUM" & tab & albumTitle & tab & (id of targetAlbum as text) & tab & ((count of finalIDs) as text) & linefeed',
            ]
        )
    lines.extend(["        return outputText", "    end tell", "end timeout", ""])
    return "\n".join(lines)


def parse_output(output: str) -> tuple[list[dict], list[dict]]:
    folders = []
    albums = []
    for line in output.splitlines():
        parts = line.split("\t")
        if parts[0] == "FOLDER" and len(parts) == 4:
            folders.append({"key": parts[1], "title": parts[2], "identifier": parts[3]})
        elif parts[0] == "ALBUM" and len(parts) == 4:
            albums.append({"title": parts[1], "identifier": parts[2], "count": int(parts[3])})
    return folders, albums


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--id-directory", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="explicitly run the rendered script")
    args = parser.parse_args()
    plan_bytes = args.plan.read_bytes()
    runtime_plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    if args.execute:
        if not re.fullmatch(r"[0-9a-f]{64}", str(args.plan_sha256 or "")):
            raise ValueError("execution requires --plan-sha256")
        if args.plan_sha256 != runtime_plan_sha256:
            raise ValueError("runtime plan bytes do not match --plan-sha256")
    plan = json.loads(plan_bytes)
    script = render(plan, args.id_directory, inline_identifiers=args.execute)
    args.script.parent.mkdir(parents=True, exist_ok=True)
    args.script.write_text(script, encoding="utf-8")
    args.script.chmod(0o700)
    script_hash = hashlib.sha256(script.encode()).hexdigest()
    print(f"rendered_script={args.script}")
    print(f"script_sha256={script_hash}")
    if not args.execute:
        print("execution_requested=false")
        return 0

    if not re.fullmatch(r"[0-9a-f]{32}", str(plan.get("execution_nonce", ""))):
        raise ValueError("execution requires a valid execution_nonce")
    if not re.fullmatch(r"[0-9a-f]{64}", str(plan.get("adapter_plan_sha256", ""))):
        raise ValueError("execution requires a valid adapter_plan_sha256")

    completed = subprocess.run(
        ["/usr/bin/osascript", "-"],
        check=False,
        capture_output=True,
        text=True,
        input=script,
    )
    if completed.returncode:
        raise SystemExit(completed.stderr.strip() or f"osascript exited {completed.returncode}")
    folders, albums = parse_output(completed.stdout)
    if len(folders) != len(plan["folders"]) or len(albums) != len(plan["albums"]):
        raise SystemExit("AppleScript output did not contain every planned folder and album")
    receipt = {
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "plan_id": plan["plan_id"],
        "execution_kind": plan["execution_kind"],
        "execution_nonce": plan["execution_nonce"],
        "plan_sha256": plan["catalog_plan_sha256"],
        "adapter_plan_sha256": plan["adapter_plan_sha256"],
        "runtime_plan_sha256": runtime_plan_sha256,
        "source_album_identifier": plan["source_album_identifier"],
        "source_count": plan["expected_source_count"],
        "source_membership_sha256": plan["source_membership_sha256"],
        "source_verified_by_writer": False,
        "safety_mode": plan["safety_mode"],
        "writer": "Photos AppleScript membership adapter",
        "writer_script_sha256": script_hash,
        "folders": folders,
        "albums": albums,
        "independent_verification_required": True,
    }
    receipt_path = Path(plan["receipt_path"])
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, receipt_path)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
