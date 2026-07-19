#!/usr/bin/env python3
"""Add local perceptual duplicate clusters to a candidate manifest."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


def preview_path(directories: list[Path], identifier: str) -> Path | None:
    names = [
        f"{identifier}.jpg",
        f"{identifier.replace('/', '_')}.jpg",
        f"{identifier.split('/', 1)[0]}.jpg",
    ]
    for directory in directories:
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def difference_hash(path: Path) -> int:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("L").resize((9, 8))
        pixels = list(image.get_flattened_data()) if hasattr(image, "get_flattened_data") else list(image.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            value = (value << 1) | int(left > right)
    return value


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


class UnionFind:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--previews", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=int, default=8)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 16:
        raise SystemExit("threshold must be between 0 and 16")

    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not rows or "uuid" not in fields:
        raise SystemExit("input requires uuid rows")

    hashes: dict[str, int] = {}
    unavailable: dict[str, str] = {}
    for row in rows:
        identifier = row["uuid"]
        path = preview_path(args.previews, identifier)
        if path is None:
            unavailable[identifier] = "preview unavailable"
            continue
        try:
            hashes[identifier] = difference_hash(path)
        except (UnidentifiedImageError, OSError):
            unavailable[identifier] = "preview decode failure"

    union = UnionFind(list(hashes))
    buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
    for identifier in sorted(hashes):
        value = hashes[identifier]
        candidates: set[str] = set()
        for band in range(4):
            candidates.update(buckets[(band, (value >> (band * 16)) & 0xFFFF)])
        for candidate in candidates:
            if hamming(value, hashes[candidate]) <= args.threshold:
                union.union(identifier, candidate)
        for band in range(4):
            buckets[(band, (value >> (band * 16)) & 0xFFFF)].append(identifier)

    groups: dict[str, list[str]] = defaultdict(list)
    for identifier in hashes:
        groups[union.find(identifier)].append(identifier)
    cluster_by_id = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        representative = min(members)
        cluster_id = f"phash-{hashes[representative]:016x}"
        for identifier in members:
            cluster_by_id[identifier] = cluster_id

    for field in ("perceptual_cluster_id", "perceptual_hash", "perceptual_status"):
        if field not in fields:
            fields.append(field)
    for row in rows:
        identifier = row["uuid"]
        row["perceptual_cluster_id"] = cluster_by_id.get(identifier, "")
        row["perceptual_hash"] = f"{hashes[identifier]:016x}" if identifier in hashes else ""
        row["perceptual_status"] = unavailable.get(identifier, "inspected")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"hashed_previews={len(hashes)}")
    print(f"unavailable_previews={len(unavailable)}")
    print(f"duplicate_clusters={sum(len(members) > 1 for members in groups.values())}")
    print(f"clustered_assets={len(cluster_by_id)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
